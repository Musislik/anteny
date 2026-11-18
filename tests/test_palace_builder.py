import os
import sys
import json
import tempfile
import unittest
from unittest import mock

# Mock external packages so tests run on standard python without numpy/gmsh
for mod in ["numpy", "matplotlib", "matplotlib.pyplot", "gmsh"]:
    if mod not in sys.modules:
        sys.modules[mod] = mock.MagicMock()

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from palace_builder import build_palace_config
from main import _resolve_param


class TestPalaceBuilderLinearSolver(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_params = {
            'antenna_model': 4,
            'eps_r': 4.1,
            'tan_delta': 0.013,
            'freq_min': 2.32,
            'freq_max': 2.345,
            'freq_step': 0.001,
            'linear_tol': 1e-5,
            'linear_max_its': 200,
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def _read_config(self):
        config_path = os.path.join(self.temp_dir.name, "config.json")
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_default_without_max_size(self):
        """Když není linear_max_size zadán, config nesmí obsahovat MaxSize (plný GMRES bez restartu)."""
        params = dict(self.base_params)
        build_palace_config(params, data_dir=self.temp_dir.name)
        cfg = self._read_config()
        
        linear_cfg = cfg["Solver"]["Linear"]
        self.assertEqual(linear_cfg["Type"], "SuperLU")
        self.assertEqual(linear_cfg["KSPType"], "FGMRES")
        self.assertEqual(linear_cfg["Tol"], 1e-5)
        self.assertEqual(linear_cfg["MaxIts"], 200)
        self.assertNotIn("MaxSize", linear_cfg)

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_explicit_none_max_size(self):
        """Explicitní linear_max_size=None v params nesmí vložit MaxSize."""
        params = dict(self.base_params)
        params['linear_max_size'] = None
        build_palace_config(params, data_dir=self.temp_dir.name)
        cfg = self._read_config()
        
        self.assertNotIn("MaxSize", cfg["Solver"]["Linear"])

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_explicit_integer_max_size(self):
        """Explicitní hodnota linear_max_size vloží odpovídající MaxSize."""
        params = dict(self.base_params)
        params['linear_max_size'] = 50
        build_palace_config(params, data_dir=self.temp_dir.name)
        cfg = self._read_config()
        
        self.assertEqual(cfg["Solver"]["Linear"]["MaxSize"], 50)

    @mock.patch.dict(os.environ, {"LINEAR_MAX_SIZE": "80"}, clear=True)
    def test_env_linear_max_size(self):
        """LINEAR_MAX_SIZE v prostředí se uplatní, pokud není v params."""
        params = dict(self.base_params)
        build_palace_config(params, data_dir=self.temp_dir.name)
        cfg = self._read_config()
        
        self.assertEqual(cfg["Solver"]["Linear"]["MaxSize"], 80)

    @mock.patch.dict(os.environ, {"LINEAR_MAX_SIZE": ""}, clear=True)
    def test_env_empty_linear_max_size(self):
        """Prázdná hodnota LINEAR_MAX_SIZE v prostředí nevloží MaxSize."""
        params = dict(self.base_params)
        build_palace_config(params, data_dir=self.temp_dir.name)
        cfg = self._read_config()
        
        self.assertNotIn("MaxSize", cfg["Solver"]["Linear"])


class TestResolveParamLinearMaxSize(unittest.TestCase):
    @mock.patch.dict(os.environ, {}, clear=True)
    def test_resolve_default_none(self):
        """Bez env a bez custom_params vrací None."""
        val = _resolve_param('linear_max_size', 'LINEAR_MAX_SIZE', None, {}, int)
        self.assertIsNone(val)

    @mock.patch.dict(os.environ, {"LINEAR_MAX_SIZE": ""}, clear=True)
    def test_resolve_empty_env(self):
        """S prázdným env vrací None."""
        val = _resolve_param('linear_max_size', 'LINEAR_MAX_SIZE', None, {}, int)
        self.assertIsNone(val)

    @mock.patch.dict(os.environ, {"LINEAR_MAX_SIZE": "60"}, clear=True)
    def test_resolve_from_env(self):
        """S platným číslem v env vrací int."""
        val = _resolve_param('linear_max_size', 'LINEAR_MAX_SIZE', None, {}, int)
        self.assertEqual(val, 60)

    @mock.patch.dict(os.environ, {"LINEAR_MAX_SIZE": "60"}, clear=True)
    def test_resolve_custom_params_override(self):
        """custom_params má přednost před env."""
        val = _resolve_param('linear_max_size', 'LINEAR_MAX_SIZE', None, {'linear_max_size': 75}, int)
        self.assertEqual(val, 75)


if __name__ == "__main__":
    unittest.main()
