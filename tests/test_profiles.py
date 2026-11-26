"""
test_profiles.py - Unit tests for the board variant manufacturing profile system (results/<variant>/).
Designed to run in pure standard Python without dependencies on numpy/gmsh.
"""

import ast
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(TESTS_DIR, ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")

for _p in (PROJECT_ROOT, SRC_DIR, SCRIPTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import export_kicad
import postpro_utils
from kicad_generator import generate_kicad_footprint, generate_kicad_pcb
from postpro_utils import (
    get_profile_env_path,
    get_profile_kicad_dir,
    load_env,
)


class TestProfileHelpersAndLoadEnv(unittest.TestCase):
    """Tests for profile helper functions and extended load_env(profile=...)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_dir = self.temp_dir.name
        self.root_env = os.path.join(self.root_dir, ".env")

        with open(self.root_env, "w", encoding="utf-8") as f:
            f.write(
                "CONF_DIR=.\n"
                "DATA_DIR=./data\n"
                "EXPORT_DIR=./export\n"
                "PALACE_CORES=5\n"
                "ANTENNA_MODEL=4\n"
                "SUB_H=1.52\n"
                "EPS_R=4.3\n"
                "TAN_DELTA=0.02\n"
                "PATCH_L=29.95\n"
                "PATCH_W=29.95\n"
            )

        self.rogers_dir = os.path.join(self.root_dir, "results", "rogers_08")
        os.makedirs(self.rogers_dir, exist_ok=True)
        self.rogers_env = os.path.join(self.rogers_dir, "rogers_08.env")
        with open(self.rogers_env, "w", encoding="utf-8") as f:
            f.write(
                "ANTENNA_MODEL=7\n"
                "SUB_H=0.813\n"
                "EPS_R=3.55\n"
                "TAN_DELTA=0.0027\n"
                "PATCH_L=31.20\n"
                "PATCH_W=31.20\n"
            )

        self.custom_dir = os.path.join(self.root_dir, "results", "custom_16")
        os.makedirs(self.custom_dir, exist_ok=True)
        self.custom_env = os.path.join(self.custom_dir, "custom_16.env")
        with open(self.custom_env, "w", encoding="utf-8") as f:
            f.write(
                "SUB_H=1.60\n"
                "EPS_R=4.40\n"
                "PROFILE_NAME=CustomBoard_16\n"
                "SILKSCREEN_SUBTITLE=Custom 1.6mm er=4.40\n"
            )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_profile_env_path_and_kicad_dir(self):
        """Verify paths to profile .env file and output kicad/ directory."""
        env_path = get_profile_env_path("rogers_08", root_dir=self.root_dir)
        self.assertEqual(env_path, os.path.abspath(self.rogers_env))

        kicad_dir = get_profile_kicad_dir("rogers_08", root_dir=self.root_dir)
        self.assertEqual(kicad_dir, os.path.abspath(os.path.join(self.rogers_dir, "kicad")))

        # Direct path to an existing .env file
        direct_env = get_profile_env_path(self.rogers_env, root_dir=self.root_dir)
        self.assertEqual(direct_env, os.path.abspath(self.rogers_env))
        direct_kicad = get_profile_kicad_dir(self.rogers_env, root_dir=self.root_dir)
        self.assertEqual(direct_kicad, os.path.abspath(os.path.join(self.rogers_dir, "kicad")))

    def test_missing_profile_raises_file_not_found(self):
        """Nonexistent profile must raise FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            get_profile_env_path("nonexistent_board", root_dir=self.root_dir)

        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(FileNotFoundError):
                load_env(env_path=self.root_env, profile="nonexistent_board")

    def test_path_traversal_and_invalid_names_rejected(self):
        """Protection against path traversal and invalid profile names."""
        invalid_names = [
            "../evil",
            "../../.env",
            "..\\evil",
            "foo/bar",
            "foo\\bar",
            "/etc/passwd",
            ".hidden",
            "foo..bar",
            "",
            "   ",
        ]
        for bad_name in invalid_names:
            with self.subTest(bad_name=bad_name):
                with self.assertRaises(ValueError):
                    get_profile_env_path(bad_name, root_dir=self.root_dir)
                with self.assertRaises(ValueError):
                    get_profile_kicad_dir(bad_name, root_dir=self.root_dir)

    def test_load_env_profile_overrides_root_and_survives_repeated_calls(self):
        """Profile overrides values from root .env even after a prior load_env() call."""
        with mock.patch.dict(os.environ, {}, clear=True):
            # 1. Initial load of root .env (as when importing sweep.py)
            root_dir, data_dir = load_env(env_path=self.root_env)
            self.assertEqual(root_dir, os.path.abspath(self.root_dir))
            self.assertEqual(data_dir, os.path.abspath(os.path.join(self.root_dir, "data")))
            self.assertEqual(os.environ["SUB_H"], "1.52")
            self.assertEqual(os.environ["EPS_R"], "4.3")
            self.assertEqual(os.environ["ANTENNA_MODEL"], "4")
            self.assertEqual(os.environ["PALACE_CORES"], "5")
            self.assertNotIn("ANTENNA_PROFILE", os.environ)

            # 2. Subsequent profile load must override previously loaded root .env values
            load_env(env_path=self.root_env, profile="rogers_08")
            self.assertEqual(os.environ["SUB_H"], "0.813")
            self.assertEqual(os.environ["EPS_R"], "3.55")
            self.assertEqual(os.environ["TAN_DELTA"], "0.0027")
            self.assertEqual(os.environ["PATCH_L"], "31.20")
            self.assertEqual(os.environ["ANTENNA_MODEL"], "7")
            self.assertEqual(os.environ["PALACE_CORES"], "5")  # preserved from root .env
            self.assertEqual(os.environ["ANTENNA_PROFILE"], "rogers_08")
            self.assertEqual(os.environ["PROFILE_NAME"], "rogers_08")

            # 3. Repeated load_env() call without profile (e.g. inside main/sweep_model) preserves profile
            load_env(env_path=self.root_env)
            self.assertEqual(os.environ["SUB_H"], "0.813")
            self.assertEqual(os.environ["EPS_R"], "3.55")
            self.assertEqual(os.environ["ANTENNA_PROFILE"], "rogers_08")

            # 4. Switching to another profile with custom PROFILE_NAME and SILKSCREEN_SUBTITLE
            load_env(env_path=self.root_env, profile="custom_16")
            self.assertEqual(os.environ["SUB_H"], "1.60")
            self.assertEqual(os.environ["EPS_R"], "4.40")
            self.assertEqual(os.environ["ANTENNA_PROFILE"], "custom_16")
            self.assertEqual(os.environ["PROFILE_NAME"], "CustomBoard_16")
            self.assertEqual(os.environ["SILKSCREEN_SUBTITLE"], "Custom 1.6mm er=4.40")

    def test_load_env_uses_antenna_profile_env_var_and_preserves_shell_vars(self):
        """Environment variable ANTENNA_PROFILE activates the profile; external shell variables are preserved."""
        initial_env = {
            "ANTENNA_PROFILE": "rogers_08",
            "SMA_GAP": "0.95",
        }
        with mock.patch.dict(os.environ, initial_env, clear=True):
            load_env(env_path=self.root_env)
            self.assertEqual(os.environ["SUB_H"], "0.813")
            self.assertEqual(os.environ["EPS_R"], "3.55")
            self.assertEqual(os.environ["PROFILE_NAME"], "rogers_08")
            self.assertEqual(os.environ["SMA_GAP"], "0.95")


class TestKiCadGeneratorProfiles(unittest.TestCase):
    """Tests for F.SilkS silkscreen text and footprint naming in kicad_generator.py."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_params = {
            "patch_L": 28.8,
            "patch_W": 28.8,
            "sub_h": 1.52,
            "eps_r": 4.3,
            "design_freq_ghz": 2.3325,
            "port_impedance": 50.0,
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_pcb_without_profile_preserves_existing_silkscreen(self):
        """Without profile_name and silkscreen_subtitle, no extra subtitle is created."""
        pcb_path = os.path.join(self.temp_dir.name, "base.kicad_pcb")
        generate_kicad_pcb(self.base_params, pcb_path)
        with open(pcb_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertEqual(content.count("(gr_text "), 2)
        self.assertIn('(gr_text "Model 4 LHCP SDARS Patch Antenna (2.3325 GHz)"', content)
        self.assertIn('(gr_text "50 Ohm RF IN"', content)

    def test_pcb_with_profile_name_generates_auto_subtitle(self):
        """With profile_name and no silkscreen_subtitle, an automatic label is generated on F.SilkS."""
        params = dict(self.base_params, sub_h=0.813, eps_r=3.55, profile_name="rogers_08")
        pcb_path = os.path.join(self.temp_dir.name, "rogers.kicad_pcb")
        generate_kicad_pcb(params, pcb_path)
        with open(pcb_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertEqual(content.count("(gr_text "), 3)
        self.assertIn("(thickness 0.813)", content)
        self.assertIn('(gr_text "rogers_08 | h=0.81 mm, er=3.55"', content)
        self.assertIn('(layer "F.SilkS")', content)

    def test_pcb_with_explicit_silkscreen_subtitle(self):
        """Explicit silkscreen_subtitle takes precedence over automatic label."""
        params = dict(
            self.base_params,
            profile_name="rogers_08",
            silkscreen_subtitle="RO4003C 0.813mm Rev.A",
        )
        pcb_path = os.path.join(self.temp_dir.name, "custom_sub.kicad_pcb")
        generate_kicad_pcb(params, pcb_path)
        with open(pcb_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('(gr_text "RO4003C 0.813mm Rev.A"', content)
        self.assertNotIn("rogers_08 | h=", content)

    def test_footprint_naming_with_profile_and_explicit_name(self):
        """Footprint uses Antenna_Model4_LHCP_<profile_name>, or explicit footprint_name."""
        fp_default = os.path.join(self.temp_dir.name, "default.kicad_mod")
        generate_kicad_footprint(self.base_params, fp_default)
        with open(fp_default, "r", encoding="utf-8") as f:
            c_def = f.read()
        self.assertIn('(footprint "Antenna_Model4_LHCP"', c_def)
        self.assertIn('(property "Value" "Antenna_Model4_LHCP"', c_def)

        fp_prof = os.path.join(self.temp_dir.name, "prof.kicad_mod")
        generate_kicad_footprint(dict(self.base_params, profile_name="rogers_08"), fp_prof)
        with open(fp_prof, "r", encoding="utf-8") as f:
            c_prof = f.read()
        self.assertIn('(footprint "Antenna_Model4_LHCP_rogers_08"', c_prof)
        self.assertIn('(property "Value" "Antenna_Model4_LHCP_rogers_08"', c_prof)

        fp_explicit = os.path.join(self.temp_dir.name, "explicit.kicad_mod")
        generate_kicad_footprint(
            dict(self.base_params, profile_name="rogers_08", footprint_name="My_Custom_Antenna"),
            fp_explicit,
        )
        with open(fp_explicit, "r", encoding="utf-8") as f:
            c_exp = f.read()
        self.assertIn('(footprint "My_Custom_Antenna"', c_exp)
        self.assertIn('(property "Value" "My_Custom_Antenna"', c_exp)


class TestExportKicadProfileWorkflow(unittest.TestCase):
    """End-to-end tests of scripts/export_kicad.py with profile and backwards compatibility without profile."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.fake_root = self.temp_dir.name

        with open(os.path.join(self.fake_root, ".env"), "w", encoding="utf-8") as f:
            f.write(
                "EXPORT_DIR=./export\n"
                "SUB_H=1.52\n"
                "EPS_R=4.3\n"
                "PATCH_L=29.95\n"
                "PATCH_W=29.95\n"
            )

        self.profile_dir = os.path.join(self.fake_root, "results", "fr4_thin")
        os.makedirs(self.profile_dir, exist_ok=True)
        self.profile_env = os.path.join(self.profile_dir, "fr4_thin.env")
        with open(self.profile_env, "w", encoding="utf-8") as f:
            f.write(
                "SUB_H=0.80\n"
                "EPS_R=4.40\n"
                "PATCH_L=29.10\n"
                "PATCH_W=29.10\n"
                "SILKSCREEN_SUBTITLE=FR4 0.80mm er=4.40\n"
            )

        # Working directory kicad/antena1/ with sentinel file (MUST NOT be overwritten when using a profile)
        self.alt_kicad_dir = os.path.join(self.fake_root, "kicad", "antena1")
        os.makedirs(self.alt_kicad_dir, exist_ok=True)
        self.sentinel_pcb = os.path.join(self.alt_kicad_dir, "antenna_model4.kicad_pcb")
        with open(self.sentinel_pcb, "w", encoding="utf-8") as f:
            f.write("SENTINEL_UNTOUCHED")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_export_kicad_with_profile_writes_to_results_and_skips_antena1_sync(self):
        """export_kicad.py --profile outputs to results/<name>/kicad/ and does not sync to kicad/antena1/."""
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(postpro_utils, "get_project_root", return_value=self.fake_root), \
             mock.patch.object(sys, "argv", ["export_kicad.py", "--profile", "fr4_thin"]), \
             contextlib.redirect_stdout(buf):
            rc = export_kicad.main()

        self.assertEqual(rc, 0)
        stdout = buf.getvalue()
        self.assertRegex(stdout, r"Active profile:\s*fr4_thin")
        self.assertRegex(stdout, r"Active variant profile:\s*fr4_thin")

        expected_kicad_dir = os.path.join(self.fake_root, "results", "fr4_thin", "kicad")
        pcb_file = os.path.join(expected_kicad_dir, "antenna_model4_fr4_thin.kicad_pcb")
        fp_file = os.path.join(expected_kicad_dir, "Antenna_Model4_LHCP_fr4_thin.kicad_mod")
        self.assertTrue(os.path.isfile(pcb_file))
        self.assertTrue(os.path.isfile(fp_file))

        with open(pcb_file, "r", encoding="utf-8") as f:
            pcb_content = f.read()
        self.assertIn("(thickness 0.800)", pcb_content)
        self.assertIn('(gr_text "FR4 0.80mm er=4.40"', pcb_content)
        self.assertIn('(layer "F.SilkS")', pcb_content)

        with open(fp_file, "r", encoding="utf-8") as f:
            fp_content = f.read()
        self.assertIn('(footprint "Antenna_Model4_LHCP_fr4_thin"', fp_content)
        self.assertIn('(property "Value" "Antenna_Model4_LHCP_fr4_thin"', fp_content)

        # Verify kicad/antena1/ was not overwritten
        with open(self.sentinel_pcb, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "SENTINEL_UNTOUCHED")
        self.assertFalse(os.path.exists(os.path.join(self.alt_kicad_dir, "Antenna_Model4_LHCP_fr4_thin.kicad_mod")))

    def test_export_kicad_without_profile_backwards_compatibility(self):
        """Without --profile, default files are generated in export/kicad/ without profile subtitle."""
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(postpro_utils, "get_project_root", return_value=self.fake_root), \
             mock.patch.object(sys, "argv", ["export_kicad.py"]), \
             contextlib.redirect_stdout(buf):
            rc = export_kicad.main()

        self.assertEqual(rc, 0)
        stdout = buf.getvalue()
        self.assertNotIn("Active variant profile:", stdout)

        default_dir = os.path.join(self.fake_root, "export", "kicad")
        pcb_file = os.path.join(default_dir, "antenna_model4.kicad_pcb")
        fp_file = os.path.join(default_dir, "Antenna_Model4_LHCP.kicad_mod")
        self.assertTrue(os.path.isfile(pcb_file))
        self.assertTrue(os.path.isfile(fp_file))

        with open(pcb_file, "r", encoding="utf-8") as f:
            pcb_content = f.read()
        self.assertIn("(thickness 1.520)", pcb_content)
        self.assertEqual(pcb_content.count("(gr_text "), 2)

        with open(fp_file, "r", encoding="utf-8") as f:
            fp_content = f.read()
        self.assertIn('(footprint "Antenna_Model4_LHCP"', fp_content)
        self.assertIn('(property "Value" "Antenna_Model4_LHCP"', fp_content)

    def test_export_kicad_cli_subprocess_direct_profile_env_file(self):
        """Run scripts/export_kicad.py as a subprocess with a direct path to a temporary .env profile."""
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "export_kicad.py"),
            "--profile",
            self.profile_env,
        ]
        env = os.environ.copy()
        env.pop("ANTENNA_PROFILE", None)
        env.pop("PROFILE_NAME", None)
        env.pop("SILKSCREEN_SUBTITLE", None)
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        self.assertEqual(proc.returncode, 0, f"CLI failed:\n{proc.stderr}")

        out_dir = os.path.join(self.profile_dir, "kicad")
        pcb_file = os.path.join(out_dir, "antenna_model4_fr4_thin.kicad_pcb")
        fp_file = os.path.join(out_dir, "Antenna_Model4_LHCP_fr4_thin.kicad_mod")
        self.assertTrue(os.path.isfile(pcb_file))
        self.assertTrue(os.path.isfile(fp_file))
        self.assertRegex(proc.stdout, r"Active variant profile:\s*fr4_thin")

        with open(pcb_file, "r", encoding="utf-8") as f:
            self.assertIn("(thickness 0.800)", f.read())
        with open(fp_file, "r", encoding="utf-8") as f:
            self.assertIn('(footprint "Antenna_Model4_LHCP_fr4_thin"', f.read())


class TestMainAndSweepCliContracts(unittest.TestCase):
    """CLI interface contract checks for src/main.py and src/sweep.py without importing numpy/gmsh."""

    @staticmethod
    def _extract_cli_flags(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=file_path)
        flags = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
            ):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("-"):
                        flags.add(arg.value)
        return tree, flags

    def test_main_py_has_profile_and_no_substrate_cli_flags(self):
        """src/main.py has --profile and parameter profile=None, but does NOT have --sub-h, --eps-r, --tan-delta."""
        main_path = os.path.join(SRC_DIR, "main.py")
        tree, flags = self._extract_cli_flags(main_path)

        self.assertIn("--profile", flags)
        self.assertNotIn("--sub-h", flags)
        self.assertNotIn("--eps-r", flags)
        self.assertNotIn("--tan-delta", flags)

        main_fn = next(
            (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"),
            None,
        )
        self.assertIsNotNone(main_fn)
        arg_names = [a.arg for a in main_fn.args.args]
        self.assertIn("profile", arg_names)

        # Verify that main() passes profile to load_env(profile=profile)
        load_env_calls = [
            n
            for n in ast.walk(main_fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "load_env"
        ]
        self.assertTrue(
            any(any(kw.arg == "profile" for kw in call.keywords) for call in load_env_calls),
            "main() must pass profile to load_env(profile=...)",
        )

    def test_sweep_py_parses_profile_before_antenna_model(self):
        """src/sweep.py registers --profile and calls load_env(profile=...) before evaluating ANTENNA_MODEL."""
        sweep_path = os.path.join(SRC_DIR, "sweep.py")
        with open(sweep_path, "r", encoding="utf-8") as f:
            source = f.read()
        _, flags = self._extract_cli_flags(sweep_path)

        self.assertIn("--profile", flags)

        main_block = source.split('if __name__ == "__main__":', 1)[1]
        pos_profile_arg = main_block.index('add_argument("--profile"')
        pos_parse_known = main_block.index("parse_known_args()")
        pos_load_profile = main_block.index("load_env(profile=known_args.profile)")
        pos_env_model = main_block.index('os.getenv("ANTENNA_MODEL"')

        self.assertLess(pos_profile_arg, pos_parse_known)
        self.assertLess(pos_parse_known, pos_load_profile)
        self.assertLess(pos_load_profile, pos_env_model)


if __name__ == "__main__":
    unittest.main()
