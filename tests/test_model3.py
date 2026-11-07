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
import shutil
import tempfile
import json
# import pytest (optional)
try:
    import pytest
except ImportError:
    pytest = None
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
from sweep_model3 import build_sweep_steps_m3
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

    import gmsh
    gmsh.clear()


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

    sub_tag, air_tag = build_model(params)
    assert params['antenna_model'] == 3
    assert 'trans_w' in params
    assert 'trans_l' in params
    assert 'w_feed' in params
    assert len(params['port1_tags']) > 0
    assert len(params['port2_tags']) > 0

    import gmsh
    gmsh.clear()


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
        try:
            os.chdir(tmp_dir)
            os.makedirs("data", exist_ok=True)

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

            main(custom_params=custom_params, skip_simulation=True, clean=False)

            assert os.path.exists("data/antenna_model.step"), "STEP CAD model musí být vyexportován"
            assert os.path.exists("data/mesh.msh"), "Mesh soubor musí být vygenerován"
            assert os.path.exists("data/config.json"), "Konfigurace Palace musí být vytvořena"
            assert os.path.exists("data/geometry_iso.png"), "Obrázek geometrie musí být vygenerován"

        finally:
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
