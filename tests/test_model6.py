"""
test_model6.py - Komplexní jednotkové testy pro dvouportový Model 6 (interní 100 Ohm porty s oblouky z M4).
Ověřuje:
  1. Analytiku drah a přesnou shodu fázování (L_100_b - d_t) - (L_100_l - d_t) == feed_delta_l.
  2. Shodu rozměrů substrátu a trasování s Modelem 4.
  3. Geometrii OpenCASCADE (dva interní lumped porty v rovině XZ na y_T ± d_t, Tag 4 a Tag 6).
  4. Router geometry.py, konfiguraci Palace (2× 100 Ohm porty) a 3D konformní síťování (mesh.py).
  5. Parametrické sweepy (sweep_model6.py), tracking (sweep_results_model6.csv/.md) a vizualizaci.
  6. Kompletní end-to-end běh main(skip_simulation=True) pro Model 6.
"""

import os
import sys
import json
from unittest.mock import patch
import gmsh
import numpy as np
import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(TESTS_DIR, ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
for p in (PROJECT_ROOT, SRC_DIR, SCRIPTS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from geometry import build_model
from geometry_v6 import (
    build_model_v6,
    calc_curved_path_length,
    compute_model6_routing,
)
from geometry_v4 import compute_model4_routing, compute_curved_ribbon_outline
from main import main
from mesh import assign_physical_groups_and_mesh
from palace_builder import build_palace_config
from rf_calc import DESIGN_FREQ_GHZ, synth_microstrip_w
import sweep_model6
from sweep_model6 import build_sweep_steps_m6
from tracker import print_summary_table_model6, record_run
from visualization import plot_geometry


def test_model6_routing_and_exact_phase_delay():
    """Ověření výpočtu obloukových drah a striktní rovnosti (L_100_b - d_t) - (L_100_l - d_t) == Delta L."""
    base = {
        'patch_L': 28.8,
        'patch_W': 28.8,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'port_impedance': 100.0,
        'trans_w': 0.42,
        'trans_l': 19.00,
        'feed_inset_b': 2.5,
        'feed_inset_l': 2.5,
        'feed_delta_l': 18.66,
        'bend_radius': 3.0,
        'feed_t_fillet_r': 0.8,
    }

    variants = [
        {},
        {'feed_bend_radius': 3.5, 'feed_end_straight': 4.6},
        {'feed_bend_radius': 2.5, 'feed_t_fillet_r': 0.5},
        {'feed_arm_offset': 9.0, 'feed_delta_l': 19.2},
        {'feed_y_T': -30.5},
    ]

    for extra in variants:
        cfg = dict(base, **extra)
        info6 = compute_model6_routing(cfg)
        cfg4 = dict(cfg, port_impedance=50.0)
        info4 = compute_model4_routing(cfg4)

        # 1. Shoda rozměrů substrátu a polohy T-uzlu s Modelem 4
        assert np.isclose(info6['W_sub'], info4['W_sub'], atol=1e-6)
        assert np.isclose(info6['L_sub'], info4['L_sub'], atol=1e-6)
        assert np.isclose(info6['x_T'], info4['x_T'], atol=1e-6)
        assert np.isclose(info6['y_T'], info4['y_T'], atol=1e-6)
        assert np.isclose(info6['d_t'], info4['d_t'], atol=1e-6)

        # 2. Striktní splnění rozdílu délek větví (L_100_b - d_t) - (L_100_l - d_t) == feed_delta_l
        diff_analytical = (info6['L_100_b'] - info6['d_t']) - (info6['L_100_l'] - info6['d_t'])
        assert np.isclose(diff_analytical, info6['feed_delta_l'], atol=1e-6)

        # 3. Přesná shoda přímo ze stavebních waypoints
        len_b_built = calc_curved_path_length(info6['arm_b_build_waypoints'], info6['bend_radius'])
        len_l_built = calc_curved_path_length(info6['arm_l_build_waypoints'], info6['bend_radius'])
        diff_built = len_b_built - len_l_built
        assert np.isclose(diff_built, info6['feed_delta_l'], atol=1e-6)
        assert np.isclose(len_b_built, info6['L_100_b_eff'], atol=1e-6)
        assert np.isclose(len_l_built, info6['L_100_l_eff'], atol=1e-6)

        # 4. Polohy interních portů
        assert np.isclose(info6['port1_x'], info6['x_T'], atol=1e-6)
        assert np.isclose(info6['port2_x'], info6['x_T'], atol=1e-6)
        assert np.isclose(info6['port1_y'], info6['y_T'] - info6['d_t'], atol=1e-6)
        assert np.isclose(info6['port2_y'], info6['y_T'] + info6['d_t'], atol=1e-6)

        # 5. Kontrola délek rovných úseků
        assert info6['s_end_l'] >= 0.5 - 1e-6
        assert info6['s_end_b'] >= info6['end_straight'] - 1e-6
        assert info6['s_T_up'] >= 0.5 - 1e-6
        assert info6['s_T_down'] >= 0.5 - 1e-6
        assert info6['s_horiz_b'] >= -1e-6

        # 6. Ověření generování 2D obrysů pro vizualizaci
        poly_l = compute_curved_ribbon_outline(info6['arm_l_build_waypoints'], info6['w_feed'], info6['bend_radius'])
        poly_b = compute_curved_ribbon_outline(info6['arm_b_build_waypoints'], info6['w_feed'], info6['bend_radius'])
        assert len(poly_l) > 10 and len(poly_b) > 10


def test_model6_geometry_and_defaults():
    """Ověření OpenCASCADE CAD geometrie Modelu 6, interních portů a parametrů."""
    params = {
        'antenna_model': 6,
        'patch_L': 28.8,
        'patch_W': 28.8,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'air_margin': 30.0,
    }
    try:
        sub_tag, air_tag = build_model_v6(params)
        assert sub_tag is not None and air_tag is not None
        assert params['antenna_model'] == 6

        # Výchozí rozměry
        assert np.isclose(params['patch_L'], 28.8, atol=1e-3)
        assert np.isclose(params['patch_W'], 28.8, atol=1e-3)
        assert np.isclose(params['feed_inset_b'], 2.5, atol=1e-3)
        assert np.isclose(params['feed_inset_l'], 2.5, atol=1e-3)

        # 100 Ohm mikropáskové vedení
        expected_w100 = synth_microstrip_w(100.0, 1.52, 4.3)
        assert np.isclose(params['w_feed'], expected_w100, atol=1e-3)

        # Dva portové povrchy (Tag 4 a Tag 6)
        assert len(params['port_tags']) == 2
        assert len(params['port1_tags']) == 1
        assert len(params['port2_tags']) == 1
        assert len(params['pec_tags']) > 0
        assert set(params['port_tags']).isdisjoint(set(params['pec_tags']))
        assert params['port1_surface_tag'] in params['port_tags']
        assert params['port2_surface_tag'] in params['port_tags']

        # Pozice portů (interní XZ plochy)
        assert np.isclose(params['port1_x'], params['feed_x_T'], atol=1e-3)
        assert np.isclose(params['port2_x'], params['feed_x_T'], atol=1e-3)
        assert np.isclose(params['port1_y'], params['feed_y_T'] - params['d_t'], atol=1e-3)
        assert np.isclose(params['port2_y'], params['feed_y_T'] + params['d_t'], atol=1e-3)
        assert params['port2_y'] > params['port1_y']

    finally:
        if gmsh.isInitialized():
            gmsh.finalize()

    # Kontrola neplatných geometrických vstupů
    for bad_override in (
        {'feed_bend_radius': 0.2},
        {'feed_inset_b': -1.0},
        {'feed_t_fillet_r': -0.5},
    ):
        bad_params = {
            'patch_L': 28.8,
            'patch_W': 28.8,
            'sub_h': 1.52,
            'eps_r': 4.3,
            **bad_override,
        }
        with pytest.raises(ValueError):
            compute_model6_routing(bad_params)


def test_model6_router_and_palace_config(tmp_path):
    """Ověření routeru build_model pro model=6 a konfigurace dvou 100 Ohm portů v Palace."""
    orig_cwd = os.getcwd()
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)
    params = {
        'antenna_model': 6,
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
        'feed_bend_radius': 3.0,
        'driven_port': 'simultaneous',
    }
    try:
        os.chdir(str(tmp_path))
        sub_tag, air_tag = build_model(params)
        assert sub_tag is not None and air_tag is not None
        assert params['antenna_model'] == 6

        # 1. Test simultánního buzení obou portů
        build_palace_config(params, data_dir=data_dir)
        with open(os.path.join(data_dir, "config.json"), "r", encoding="utf-8") as f:
            cfg = json.load(f)

        ports = cfg['Boundaries']['LumpedPort']
        assert len(ports) == 2

        # Port 1 (Tag 4, 100 Ohm, Direction +Z)
        p1 = next(p for p in ports if p['Index'] == 1)
        assert p1['Attributes'] == [4]
        assert np.isclose(p1['R'], 100.0)
        assert p1['Direction'] == "+Z"
        assert p1['Excitation'] is True

        # Port 2 (Tag 6, 100 Ohm, Direction +Z)
        p2 = next(p for p in ports if p['Index'] == 2)
        assert p2['Attributes'] == [6]
        assert np.isclose(p2['R'], 100.0)
        assert p2['Direction'] == "+Z"
        assert p2['Excitation'] is True

        # 2. Test sekvenčního režimu (driven_port='all' -> staticky v config.json buzen Port 1)
        params['driven_port'] = 'all'
        build_palace_config(params, data_dir=data_dir)
        with open(os.path.join(data_dir, "config.json"), "r", encoding="utf-8") as f:
            cfg_all = json.load(f)
        p1_all = next(p for p in cfg_all['Boundaries']['LumpedPort'] if p['Index'] == 1)
        p2_all = next(p for p in cfg_all['Boundaries']['LumpedPort'] if p['Index'] == 2)
        assert p1_all['Excitation'] is True
        assert p2_all['Excitation'] is False

        # 3. Test buzení pouze Portu 2
        params['driven_port'] = '2'
        build_palace_config(params, data_dir=data_dir)
        with open(os.path.join(data_dir, "config.json"), "r", encoding="utf-8") as f:
            cfg_p2 = json.load(f)
        p1_p2 = next(p for p in cfg_p2['Boundaries']['LumpedPort'] if p['Index'] == 1)
        p2_p2 = next(p for p in cfg_p2['Boundaries']['LumpedPort'] if p['Index'] == 2)
        assert p1_p2['Excitation'] is False
        assert p2_p2['Excitation'] is True

    finally:
        if gmsh.isInitialized():
            gmsh.finalize()
        os.chdir(orig_cwd)


def test_model6_mesh_and_physical_groups(tmp_path):
    """Ověření generování konformní Gmsh sítě pro Model 6 a správného zařazení Physical Groups."""
    orig_cwd = os.getcwd()
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)
    params = {
        'antenna_model': 6,
        'patch_L': 28.8,
        'patch_W': 28.8,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'tan_delta': 0.02,
        'air_margin': 25.0,
        'freq_min': 2.320,
        'freq_max': 2.345,
        'freq_step': 0.005,
        'port_impedance': 100.0,
        'mesh_size_max': 15.0,
        'mesh_size_min': 1.5,
        'mesh_dist_min': 0.5,
        'mesh_dist_max': 6.0,
        'feed_bend_radius': 3.0,
    }
    try:
        os.chdir(str(tmp_path))
        sub_tag, air_tag = build_model(params)
        assign_physical_groups_and_mesh(params, data_dir=data_dir)
        mesh_path = os.path.join(data_dir, "mesh.msh")
        assert os.path.exists(mesh_path)
        assert os.path.getsize(mesh_path) > 5000

        with open(mesh_path, "r", encoding="utf-8", errors="ignore") as f:
            msh_content = f.read()

        assert '$PhysicalNames' in msh_content
        # Physical Groups: 1="Substrate", 2="Air", 3="PEC", 4="Port1", 5="Absorbing", 6="Port2"
        assert '"Substrate"' in msh_content
        assert '"Air"' in msh_content
        assert '"PEC"' in msh_content
        assert '"Port1"' in msh_content
        assert '"Absorbing"' in msh_content
        assert '"Port2"' in msh_content

    finally:
        if gmsh.isInitialized():
            gmsh.finalize()
        os.chdir(orig_cwd)


def test_model6_visualization_and_tracker(tmp_path):
    """Ověření 2D náhledu geometrie a zapisování výsledků do CSV/Markdown pro Model 6."""
    orig_cwd = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        params = {
            'antenna_model': 6,
            'patch_L': 28.80,
            'patch_W': 28.80,
            'trans_w': 0.42,
            'trans_l': 19.00,
            'feed_inset_b': 2.5,
            'feed_inset_l': 2.5,
            'feed_delta_l': 18.66,
            'feed_bend_radius': 3.0,
            'feed_t_fillet_r': 0.8,
            'd_t': 2.25,
        }

        # 1. Vizualizace
        vis_file = os.path.join(str(tmp_path), "test_vis_m6.png")
        plot_geometry(params, filename=vis_file)
        assert os.path.exists(vis_file) and os.path.getsize(vis_file) > 1000

        # 2. Tracker
        out_dir = str(tmp_path / "postpro")
        res_dir = str(tmp_path / "export")
        os.makedirs(out_dir, exist_ok=True)
        os.makedirs(res_dir, exist_ok=True)

        s_csv_path = os.path.join(out_dir, "port-S.csv")
        with open(s_csv_path, "w", encoding="utf-8") as f:
            f.write("f, |S[1][1]|, arg(S[1][1]), |S[2][1]|, arg(S[2][1]), |S[1][2]|, arg(S[1][2]), |S[2][2]|, arg(S[2][2])\n")
            f.write("2.320, -17.8, 0.0, -21.5, 0.0, -21.5, 0.0, -18.9, 0.0\n")

        row = record_run(params, output_dir=out_dir, run_name="test_m6_run", results_dir=res_dir)
        assert row is not None
        assert row['run_name'] == "test_m6_run"
        assert np.isclose(float(row['patch_L_mm']), 28.80)
        assert np.isclose(float(row['trans_w_mm']), 0.42)
        assert np.isclose(float(row['trans_l_mm']), 19.00)
        assert np.isclose(float(row['S11_min [dB]']), -17.8)
        assert np.isclose(float(row['S22_min [dB]']), -18.9)
        assert np.isclose(float(row['S21_min [dB]']), -21.5)

        csv_summary = os.path.join(res_dir, "sweep_results_model6.csv")
        assert os.path.exists(csv_summary)
        md_summary = os.path.join(res_dir, "sweep_results_model6.md")
        assert os.path.exists(md_summary)

        # 3. Test výpisu souhrnné tabulky
        print_summary_table_model6(csv_file=csv_summary)

    finally:
        os.chdir(orig_cwd)


def test_model6_sweep_builder():
    """Ověření sestavování kroků sweepu pro Model 6."""
    # 1. Sweep patch_l
    steps_pl, desc_pl = build_sweep_steps_m6(sweep_target="patch_l", patch_lengths=[28.6, 28.8, 29.0])
    assert len(steps_pl) == 3
    assert "patch_l" in desc_pl
    for s in steps_pl:
        assert s['antenna_model'] == 6
        assert s['port_impedance'] == 100.0

    # 2. Sweep bend_radius
    steps_br, desc_br = build_sweep_steps_m6(sweep_target="bend_radius", bend_radii=[2.5, 3.0, 3.5])
    assert len(steps_br) == 3
    assert steps_br[0]['bend_radius'] == 2.5

    # 3. Sweep t_fillet_r
    steps_tf, desc_tf = build_sweep_steps_m6(sweep_target="t_fillet_r", t_fillet_list=[0.6, 0.8, 1.0])
    assert len(steps_tf) == 3
    assert steps_tf[1]['t_fillet_r'] == 0.8

    # 4. Sweep driven_port
    steps_dp, desc_dp = build_sweep_steps_m6(sweep_target="driven_port")
    assert len(steps_dp) == 3
    driven_modes = [s['driven_port'] for s in steps_dp]
    assert driven_modes == ['all', '1', '2']


def test_model6_end_to_end_main(tmp_path):
    """Ověření kompletní pipeline Modelu 6 přes main(skip_simulation=True)."""
    orig_cwd = os.getcwd()
    data_dir = str(tmp_path / "data")
    export_dir = str(tmp_path / "export")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(export_dir, exist_ok=True)

    env_patch = {
        "DATA_DIR": data_dir,
        "EXPORT_DIR": export_dir,
        "ANTENNA_MODEL": "6",
    }

    try:
        os.chdir(str(tmp_path))
        with patch.dict(os.environ, env_patch, clear=False):
            custom_params = {
                'run_name': "test_m6_pipeline",
                'antenna_model': 6,
                'patch_L': 28.8,
                'patch_W': 28.8,
                'trans_w': 0.42,
                'trans_l': 19.00,
                'feed_inset_b': 2.5,
                'feed_inset_l': 2.5,
                'feed_delta_l': 18.66,
                'feed_bend_radius': 3.0,
                'feed_t_fillet_r': 0.8,
                'air_margin': 25.0,
                'mesh_size_max': 15.0,
                'mesh_size_min': 1.5,
            }
            main(custom_params=custom_params, skip_simulation=True)

            # Ověření výstupů
            mesh_file = os.path.join(data_dir, "mesh.msh")
            cfg_file = os.path.join(data_dir, "config.json")
            step_file = os.path.join(data_dir, "antenna_model.step")
            vis_file = os.path.join(data_dir, "geometry_iso.png")

            assert os.path.exists(mesh_file)
            assert os.path.exists(cfg_file)
            assert os.path.exists(step_file)
            assert os.path.exists(vis_file)

            # Ověření config.json
            with open(cfg_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            lumped_ports = cfg['Boundaries']['LumpedPort']
            assert len(lumped_ports) == 2
            assert lumped_ports[0]['Attributes'] == [4]
            assert lumped_ports[1]['Attributes'] == [6]
            assert lumped_ports[0]['R'] == 100.0
            assert lumped_ports[1]['R'] == 100.0
            assert lumped_ports[0]['Direction'] == "+Z"
            assert lumped_ports[1]['Direction'] == "+Z"

    finally:
        if gmsh.isInitialized():
            gmsh.finalize()
        os.chdir(orig_cwd)
