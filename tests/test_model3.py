"""
test_model3.py - Komplexní jednotkové testy pro Model 3 (Hybridní dvoustupňové přizpůsobení).
Ověřuje:
  1. Analytické VF výpočty (100 Ohm vedení, čtvrtvlnný transformátor w_T=0.42mm).
  2. Geometrii v OpenCASCADE (geometry_v3.py).
  3. Směrování routeru (geometry.py).
  4. Generování Palace konfigurace (palace_builder.py).
  5. Klasifikaci fyzikálních skupin a generování 3D sítě (mesh.py).
  6. Sestavení kroků parametrického sweepu (sweep_model3.py).
  7. Kompletní běh main(skip_simulation=True).
"""

import os
import sys
import tempfile
import json
from unittest.mock import patch
# import pytest (optional)
try:
    import pytest
except ImportError:
    pytest = None
import gmsh
import numpy as np

# Cesty k modulům projektu
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(TESTS_DIR, ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
for p in (PROJECT_ROOT, SRC_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from rf_calc import (
    synth_microstrip_w,
    calc_microstrip_eps_eff,
    calc_microstrip_z0,
    calc_quarter_wave_length,
    DESIGN_FREQ_GHZ,
)
from geometry_v3 import build_model_v3
from geometry import build_model
from palace_builder import build_palace_config
from mesh import assign_physical_groups_and_mesh
from postpro_utils import _resolve_env_dir
import sweep_model3
from sweep_model3 import build_sweep_steps_m3, run_sweep_model3
from main import main


def test_rf_calculations_model3():
    """Ověření analytických VF výpočtů pro Model 3 (Cesta B)."""
    h = 1.52
    eps_r = 4.3

    # 1. Vnější 100 Ohm vedení
    w_100 = synth_microstrip_w(100.0, h, eps_r)
    assert 0.65 <= w_100 <= 0.75, f"Šířka w pro 100 Ohm by měla být cca 0.69 mm, ale je {w_100:.4f}"

    eps_eff_100 = calc_microstrip_eps_eff(w_100, h, eps_r)
    assert 2.85 <= eps_eff_100 <= 3.10, f"eps_eff pro 100 Ohm by měla být cca 2.97, ale je {eps_eff_100:.4f}"

    delta_l_expected = calc_quarter_wave_length(DESIGN_FREQ_GHZ, eps_eff_100)
    assert 18.0 <= delta_l_expected <= 19.5, f"Delta L by měla být cca 18.66 mm, ale je {delta_l_expected:.4f}"

    # 2. Vnitřní čtvrtvlnný transformátor
    w_T = 0.42
    z_T = calc_microstrip_z0(w_T, h, eps_r)
    assert 115.0 <= z_T <= 122.0, f"Impedance Z_T pro w=0.42 mm by měla být cca 118.7 Ohm, ale je {z_T:.2f}"

    eps_eff_T = calc_microstrip_eps_eff(w_T, h, eps_r)
    l_T_expected = calc_quarter_wave_length(DESIGN_FREQ_GHZ, eps_eff_T)
    assert 18.2 <= l_T_expected <= 19.5, f"Délka l_T by měla být cca 18.88 mm, ale je {l_T_expected:.4f}"

    # 3. Transformační poměr: R_patch = Z_T^2 / 100
    r_patch_matched = (z_T ** 2) / 100.0
    assert 135.0 <= r_patch_matched <= 145.0, f"Impedance flíčku pro transformátor by měla být ~140 Ohm, ale je {r_patch_matched:.2f}"


def test_geometry_model3_properties():
    """Ověření generování geometrie Modelu 3 a návaznosti dvoustupňového vedení."""
    params = {
        'antenna_model': 3,
        'patch_L': 28.8,
        'patch_W': 28.8,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'air_margin': 30.0,
        'trans_w': 0.42,
        'feed_inset_b': 2.5,
        'feed_inset_l': 2.5,
        'inset_gap_b': 0.5,
        'inset_gap_l': 0.5,
        'sub_W': 80.0,
    }

    try:
        sub_tag, air_tag = build_model_v3(params)
        assert sub_tag is not None
        assert air_tag is not None

        # Ověření entit portů a PEC
        assert len(params['port1_tags']) > 0, "Port 1 fragmenty musí existovat"
        assert len(params['port2_tags']) > 0, "Port 2 fragmenty musí existovat"
        assert len(params['pec_tags']) > 0, "PEC fragmenty musí existovat"

        # Ověření parametrů transformátoru
        assert np.isclose(params['trans_w'], 0.42, atol=1e-3)
        assert 18.5 <= params['trans_l'] <= 19.2

        # Ověření fázovací podmínky v 100 Ohm vedení: feed_len_b == feed_len_l + feed_delta_l
        assert np.isclose(params['feed_len_b'], params['feed_len_l'] + params['feed_delta_l'], atol=1e-3), \
            f"feed_len_b ({params['feed_len_b']}) musí být přesně feed_len_l ({params['feed_len_l']}) + delta_l ({params['feed_delta_l']})"

        # Ověření, že porty leží přesně na hranách substrátu
        assert np.isclose(params['x_port'], -params['sub_W'] / 2.0, atol=1e-2)
        assert np.isclose(params['y_port'], -params['sub_L'] / 2.0, atol=1e-2)

        # Ověření disjunktnosti ploch portů
        p1_set = set(params['port1_tags'])
        p2_set = set(params['port2_tags'])
        assert p1_set.isdisjoint(p2_set), "Plochy Portu 1 a Portu 2 se nesmí překrývat"
    finally:
        if gmsh.isInitialized():
            gmsh.finalize()


def test_geometry_router_model3():
    """Ověření, že router geometry.py správně deleguje na build_model_v3."""
    params = {
        'antenna_model': 3,
        'patch_L': 28.8,
        'patch_W': 28.8,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'air_margin': 30.0,
    }

    try:
        sub_tag, air_tag = build_model(params)
        assert sub_tag is not None
        assert air_tag is not None
        assert params['antenna_model'] == 3
        assert 'trans_w' in params
        assert 'trans_l' in params
        assert 'w_feed' in params
        assert len(params['port1_tags']) > 0
        assert len(params['port2_tags']) > 0
    finally:
        if gmsh.isInitialized():
            gmsh.finalize()


def test_palace_builder_model3():
    """Ověření, že palace_builder.py vygeneruje správnou konfiguraci se dvěma 100 Ohm porty pro Model 3."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        orig_cwd = os.getcwd()
        try:
            os.chdir(tmp_dir)
            os.makedirs("data", exist_ok=True)

            params = {
                'antenna_model': 3,
                'patch_L': 28.8,
                'patch_W': 28.8,
                'sub_h': 1.52,
                'eps_r': 4.3,
                'tan_delta': 0.02,
                'air_margin': 30.0,
                'freq_min': 2.320,
                'freq_max': 2.345,
                'freq_step': 0.005,
                'port_impedance': 100.0,
                'driven_port': 'all',
            }

            build_palace_config(params)

            cfg_file = "data/config.json"
            assert os.path.exists(cfg_file), "data/config.json musí být vytvořen"

            with open(cfg_file, 'r', encoding='utf-8') as f:
                cfg = json.load(f)

            # Ověření sekce LumpedPort
            ports = cfg['Boundaries']['LumpedPort']
            assert len(ports) == 2, f"Model 3 musí mít 2 lumped porty, nalezeno: {len(ports)}"
            assert ports[0]['Index'] == 1 and ports[0]['Attributes'] == [4] and ports[0]['R'] == 100.0
            assert ports[1]['Index'] == 2 and ports[1]['Attributes'] == [6] and ports[1]['R'] == 100.0
            assert cfg['Boundaries']['PEC']['Attributes'] == [3]
            assert cfg['Domains']['Materials'][0]['Attributes'] == [1]  # Substrát

        finally:
            os.chdir(orig_cwd)


def test_mesh_generation_model3():
    """Ověření, že mesh.py vytvoří konformní síť a správné fyzikální skupiny pro Model 3."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        orig_cwd = os.getcwd()
        try:
            os.chdir(tmp_dir)
            os.makedirs("data", exist_ok=True)

            params = {
                'antenna_model': 3,
                'patch_L': 28.8,
                'patch_W': 28.8,
                'sub_h': 1.52,
                'eps_r': 4.3,
                'air_margin': 30.0,
                'trans_w': 0.42,
                'feed_inset_b': 2.5,
                'feed_inset_l': 2.5,
                'mesh_size_max': 12.0,  # Hrubší síť pro rychlý test
                'mesh_size_min': 2.0,
                'mesh_dist_min': 1.0,
                'mesh_dist_max': 8.0,
            }

            build_model_v3(params)
            assign_physical_groups_and_mesh(params)

            mesh_file = "data/mesh.msh"
            assert os.path.exists(mesh_file), "data/mesh.msh musí být vytvořen"
            assert os.path.getsize(mesh_file) > 1000, "Soubor sítě nesmí být prázdný"

        finally:
            if gmsh.isInitialized():
                gmsh.finalize()
            os.chdir(orig_cwd)


def test_sweep_steps_builder_model3():
    """Ověření generátoru kroků sweepu pro Model 3 (sweep_model3.py)."""
    # 1. Sweep zanoření mělkého zářezu (symmetric)
    steps_inset, desc = build_sweep_steps_m3(sweep_target='inset', mode='symmetric', insets=[2.0, 2.5, 3.0])
    assert len(steps_inset) == 3
    assert steps_inset[0]['inset_b'] == 2.0 and steps_inset[0]['inset_l'] == 2.0

    # 2. Sweep šířky transformátoru (trans_w)
    steps_tw, desc_tw = build_sweep_steps_m3(sweep_target='trans_w', trans_w_list=[0.38, 0.42, 0.46])
    assert len(steps_tw) == 3
    assert np.isclose(steps_tw[1]['trans_w'], 0.42)
    assert "m3_tw0.42mm" in steps_tw[1]['run_name']

    # 3. Sweep délky transformátoru (trans_l)
    steps_tl, desc_tl = build_sweep_steps_m3(sweep_target='trans_l', trans_l_list=[18.0, 18.88, 19.5])
    assert len(steps_tl) == 3
    assert np.isclose(steps_tl[1]['trans_l'], 18.88)

    # 4. Sweep fázovacího úseku delta_l
    steps_dl, desc_dl = build_sweep_steps_m3(sweep_target='delta_l', delta_l=[17.5, 18.66, 19.5])
    assert len(steps_dl) == 3
    assert np.isclose(steps_dl[1]['feed_delta_l'], 18.66)

    # 5. Sweep délky flíčku patch_l
    steps_pl, desc_pl = build_sweep_steps_m3(sweep_target='patch_l', patch_lengths=[28.6, 28.8, 29.0])
    assert len(steps_pl) == 3
    assert np.isclose(steps_pl[1]['patch_L'], 28.8)


def test_main_skip_simulation_model3():
    """Ověření, že main(skip_simulation=True) kompletně a bez chyb vytvoří CAD STEP, náhled a síť pro Model 3."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        orig_cwd = os.getcwd()
        tmp_data_dir = os.path.join(tmp_dir, "data")
        tmp_export_dir = os.path.join(tmp_dir, "export")
        fake_env = (tmp_dir, tmp_data_dir)
        try:
            os.chdir(tmp_dir)
            os.makedirs(tmp_data_dir, exist_ok=True)

            custom_params = {
                'antenna_model': 3,
                'patch_L': 28.8,
                'patch_W': 28.8,
                'feed_inset_b': 2.5,
                'feed_inset_l': 2.5,
                'trans_w': 0.42,
                'mesh_size_max': 12.0,
                'mesh_size_min': 2.0,
            }

            with patch.dict(os.environ, {"DATA_DIR": tmp_data_dir, "EXPORT_DIR": tmp_export_dir}), \
                 patch("main.load_env", return_value=fake_env), \
                 patch("postpro_utils.load_env", return_value=fake_env), \
                 patch("geometry.load_env", return_value=fake_env):
                main(custom_params=custom_params, skip_simulation=True, clean=False)

            assert os.path.exists("data/antenna_model.step"), "STEP CAD model musí být vyexportován"
            assert os.path.exists("data/mesh.msh"), "Mesh soubor musí být vygenerován"
            assert os.path.exists("data/config.json"), "Konfigurace Palace musí být vytvořena"
            assert os.path.exists("data/geometry_iso.png"), "Obrázek geometrie musí být vygenerován"
            assert os.path.exists("data/params.json"), "Parametry modelu musí být uloženy v dočasné složce"

        finally:
            if gmsh.isInitialized():
                gmsh.finalize()
            os.chdir(orig_cwd)


def test_resolve_env_dir_relative_nonexistent():
    """Ověření, že _resolve_env_dir přeloží neexistující relativní cestu vůči root_dir."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        expected = os.path.abspath(os.path.join(tmp_dir, "custom_export"))
        assert _resolve_env_dir("./custom_export", tmp_dir, "export") == expected

        os.makedirs(os.path.join(tmp_dir, "export"), exist_ok=True)
        assert _resolve_env_dir("./custom_export", tmp_dir, "export") == expected


def test_geometry_model3_explicit_trans_l():
    """Ověření zachování explicitní délky transformátoru trans_l=17.5 ve všech aliasech params."""
    params = {
        'antenna_model': 3,
        'patch_L': 28.8,
        'patch_W': 28.8,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'air_margin': 30.0,
        'trans_w': 0.42,
        'trans_l': 17.5,
    }
    try:
        sub_tag, air_tag = build_model_v3(params)
        assert sub_tag is not None
        assert air_tag is not None
        for key in ('trans_l', 'l_T', 'l_trans', 'trans_l_b', 'trans_l_l'):
            assert np.isclose(params[key], 17.5, atol=1e-4), f"{key} musí být 17.5, je {params[key]}"
    finally:
        if gmsh.isInitialized():
            gmsh.finalize()


def test_sweep_model3_patch_dims_and_run():
    """Ověření respektování SWEEP_PATCH_L, SWEEP_PATCH_W a explicitního patch_w v build_sweep_steps_m3 i run_sweep_model3."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_data_dir = os.path.join(tmp_dir, "data")
        tmp_export_dir = os.path.join(tmp_dir, "export")
        env_overrides = {
            "SWEEP_PATCH_L": "29.1",
            "SWEEP_PATCH_W": "29.6",
            "SWEEP_PROFILE": "fast",
            "SWEEP_EXPORT_EACH": "false",
        }
        clear_keys = ("SWEEP_TARGET", "PATCH_L", "PATCH_W", "TRANS_L", "FEED_DELTA_L")

        with patch.dict(os.environ, env_overrides):
            for k in clear_keys:
                os.environ.pop(k, None)

            # 1. SWEEP_PATCH_L a SWEEP_PATCH_W v build_sweep_steps_m3
            steps_env, _ = build_sweep_steps_m3(sweep_target="inset", mode="symmetric", insets=[2.5])
            assert len(steps_env) == 1
            assert np.isclose(steps_env[0]['patch_L'], 29.1)
            assert np.isclose(steps_env[0]['patch_W'], 29.6)

            # 2. Explicitní patch_w přepíše SWEEP_PATCH_W
            steps_override, _ = build_sweep_steps_m3(
                sweep_target="inset", mode="symmetric", insets=[2.5], patch_w=30.1
            )
            assert np.isclose(steps_override[0]['patch_L'], 29.1)
            assert np.isclose(steps_override[0]['patch_W'], 30.1)

            # 3. Explicitní patch_w v sweepu patch_l
            steps_pl, _ = build_sweep_steps_m3(
                sweep_target="patch_l", patch_lengths=[28.5, 29.0], patch_w=29.4
            )
            assert len(steps_pl) == 2
            assert np.isclose(steps_pl[0]['patch_L'], 28.5)
            assert np.isclose(steps_pl[0]['patch_W'], 29.4)
            assert np.isclose(steps_pl[1]['patch_L'], 29.0)
            assert np.isclose(steps_pl[1]['patch_W'], 29.4)

            # 4. run_sweep_model3 s mockovaným main()
            with patch.object(sweep_model3, "load_env", return_value=(tmp_dir, tmp_data_dir)), \
                 patch.object(sweep_model3, "get_export_dir", return_value=tmp_export_dir), \
                 patch.object(sweep_model3, "print_summary_table_model3"), \
                 patch.object(sweep_model3, "export_paraview_package"), \
                 patch.object(sweep_model3, "main") as mock_main:
                run_sweep_model3(sweep_target="inset", mode="symmetric", insets=[2.5], skip_simulation=True)
                assert mock_main.call_count == 1
                cfg_env = mock_main.call_args.kwargs['custom_params']
                assert np.isclose(cfg_env['patch_L'], 29.1)
                assert np.isclose(cfg_env['patch_W'], 29.6)

                mock_main.reset_mock()
                run_sweep_model3(
                    sweep_target="patch_l", patch_lengths=[28.6, 29.0], patch_w=29.9, skip_simulation=True
                )
                assert mock_main.call_count == 2
                cfg0 = mock_main.call_args_list[0].kwargs['custom_params']
                cfg1 = mock_main.call_args_list[1].kwargs['custom_params']
                assert np.isclose(cfg0['patch_L'], 28.6) and np.isclose(cfg0['patch_W'], 29.9)
                assert np.isclose(cfg1['patch_L'], 29.0) and np.isclose(cfg1['patch_W'], 29.9)


def test_main_custom_data_dir_model3():
    """Ověření, že main(skip_simulation=True) s DATA_DIR=tmp/custom_data nepoužije neexistující tmp/data."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        orig_cwd = os.getcwd()
        custom_data_dir = os.path.join(tmp_dir, "custom_data")
        custom_export_dir = os.path.join(tmp_dir, "custom_export")
        default_data_dir = os.path.join(tmp_dir, "data")
        assert not os.path.exists(default_data_dir)

        custom_params = {
            'antenna_model': 3,
            'patch_L': 28.8,
            'patch_W': 28.8,
            'feed_inset_b': 2.5,
            'feed_inset_l': 2.5,
            'trans_w': 0.42,
            'mesh_size_max': 12.0,
            'mesh_size_min': 2.0,
        }

        try:
            os.chdir(tmp_dir)
            with patch.dict(os.environ, {"DATA_DIR": custom_data_dir, "EXPORT_DIR": custom_export_dir}), \
                 patch("postpro_utils.get_project_root", return_value=tmp_dir):
                os.environ.pop("ANTENNA_MODEL", None)
                os.environ.pop("PORT_IMPEDANCE", None)
                main(custom_params=custom_params, skip_simulation=True, clean=False)

            assert not os.path.exists(default_data_dir), "Výchozí složka data/ nesmí být vytvořena"
            for fname in ("antenna_model.step", "mesh.msh", "config.json", "geometry_iso.png", "params.json"):
                fpath = os.path.join(custom_data_dir, fname)
                assert os.path.exists(fpath), f"Soubor {fname} musí existovat v {custom_data_dir}"
                assert os.path.getsize(fpath) > 0, f"Soubor {fname} nesmí být prázdný"

            with open(os.path.join(custom_data_dir, "config.json"), "r", encoding="utf-8") as f:
                cfg = json.load(f)
            assert cfg["Model"]["Mesh"] == "data/mesh.msh"
            assert cfg["Problem"]["Output"] == "data/postpro"
        finally:
            if gmsh.isInitialized():
                gmsh.finalize()
            os.chdir(orig_cwd)


if __name__ == "__main__":
    if pytest is not None:
        pytest.main(["-v", __file__])
    else:
        test_funcs = [
            test_rf_calculations_model3,
            test_geometry_model3_properties,
            test_geometry_router_model3,
            test_palace_builder_model3,
            test_mesh_generation_model3,
            test_sweep_steps_builder_model3,
            test_main_skip_simulation_model3,
            test_resolve_env_dir_relative_nonexistent,
            test_geometry_model3_explicit_trans_l,
            test_sweep_model3_patch_dims_and_run,
            test_main_custom_data_dir_model3,
        ]
        passed = 0
        failed = 0
        print("=== SPOUŠTÍM TESTY PRO MODEL 3 ===")
        for fn in test_funcs:
            print(f"Běží: {fn.__name__} ...", end=" ")
            try:
                fn()
                print("PASSED [OK]")
                passed += 1
            except Exception as e:
                print(f"FAILED [CHYBA: {e}]")
                import traceback
                traceback.print_exc()
                failed += 1
        print(f"\nVýsledek: {passed} prošlo, {failed} selhalo.")
        if failed > 0:
            sys.exit(1)
