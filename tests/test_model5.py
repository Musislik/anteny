"""
test_model5.py - Comprehensive unit tests for two-port Model 5 (100 Ohm ports with curved bends).
Verifies:
  1. Curved path analytics and exact phase difference L_100_b - L_100_l == feed_delta_l.
  2. OpenCASCADE geometry (circular bends, two separate 100 Ohm ports without T-junction, valid defaults).
  3. geometry.py router, Palace config (2x 100 Ohm ports Tag 4 and Tag 6), and 3D conformal meshing (mesh.py).
  4. Parametric sweeps (sweep_model5.py), tracking (sweep_results_model5.csv/.md), and visualization.
  5. Complete end-to-end run of main(skip_simulation=True) for Model 5.
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
from geometry_v5 import (
    build_model_v5,
    calc_curved_path_length,
    compute_model5_routing,
)
from geometry_v4 import compute_curved_ribbon_outline
from main import main
from mesh import assign_physical_groups_and_mesh
from palace_builder import build_palace_config
from rf_calc import DESIGN_FREQ_GHZ, synth_microstrip_w
import sweep_model5
from sweep_model5 import build_sweep_steps_m5
from tracker import print_summary_table_model5, record_run
from visualization import plot_geometry


def test_model5_routing_and_exact_phase_delay():
    """Verify curved path calculation and strict equality L_100_b - L_100_l == Delta L."""
    base = {
        'patch_L': 29.95,
        'patch_W': 29.95,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'port_impedance': 100.0,
        'trans_w': 0.30,
        'trans_l': 19.00,
        'feed_inset_b': 2.5,
        'feed_inset_l': 2.5,
        'feed_delta_l': 18.66,
        'bend_radius': 3.0,
    }

    variants = [
        {},
        {'feed_bend_radius': 3.5, 'feed_end_straight': 4.6},
        {'feed_bend_radius': 2.5, 'port_offset': 2.0},
        {'feed_arm_offset': 9.0, 'feed_delta_l': 19.2},
        {'port_offset': 3.2},
    ]

    for extra in variants:
        cfg = dict(base, **extra)
        info = compute_model5_routing(cfg)
        diff = info['L_100_b'] - info['L_100_l']
        assert np.isclose(diff, info['feed_delta_l'], atol=1e-6), (
            f"Path difference L_100_b - L_100_l ({diff:.6f}) must exactly match delta_l ({info['feed_delta_l']:.6f})"
        )

        # Both ports lie on the left substrate edge
        assert np.isclose(info['x_port'], -info['W_sub'] / 2.0, atol=1e-6)

        # Port spacing 2 * port_offset
        port_dist = abs(info['y_port_2'] - info['y_port_1'])
        assert np.isclose(port_dist, 2.0 * info['port_offset'], atol=1e-6)
        # Spacing must safely exceed feedline width
        assert port_dist > 4.0 * info['w_feed']

        # Straight segment length checks
        assert info['s_end_l'] >= 0.5 - 1e-6
        assert info['s_end_b'] >= info['end_straight'] - 1e-6
        assert info['s_vert_b'] >= -1e-6
        assert info['s_horiz_b'] >= -1e-6
        assert info['s_lead_l'] >= -1e-6
        assert info['s_lead_b'] >= -1e-6

        # Verify outline generation for both branches
        poly_l = compute_curved_ribbon_outline(info['arm_l_build_waypoints'], info['w_feed'], info['bend_radius'])
        poly_b = compute_curved_ribbon_outline(info['arm_b_build_waypoints'], info['w_feed'], info['bend_radius'])
        assert len(poly_l) > 10 and len(poly_b) > 10


def test_model5_geometry_and_defaults():
    """Verify OpenCASCADE CAD geometry for Model 5, 2 ports, and default parameters."""
    params = {
        'antenna_model': 5,
        'patch_L': 29.95,
        'patch_W': 29.95,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'air_margin': 30.0,
    }
    try:
        sub_tag, air_tag = build_model_v5(params)
        assert sub_tag is not None and air_tag is not None
        assert params['antenna_model'] == 5

        # Default patch and transformer dimensions for Model 5
        assert np.isclose(params['patch_L'], 29.95, atol=1e-3)
        assert np.isclose(params['patch_W'], 29.95, atol=1e-3)
        assert np.isclose(params['trans_w'], 0.30, atol=1e-3)
        assert np.isclose(params['trans_l'], 19.00, atol=1e-3)
        assert np.isclose(params['feed_inset_b'], 2.5, atol=1e-3)
        assert np.isclose(params['feed_inset_l'], 2.5, atol=1e-3)

        # 100 Ohm microstrip line
        expected_w100 = synth_microstrip_w(100.0, 1.52, 4.3)
        assert np.isclose(params['w_feed'], expected_w100, atol=1e-3)

        # Two port surfaces on the left substrate edge
        assert len(params['port_tags']) == 2
        assert len(params['pec_tags']) > 0
        assert set(params['port_tags']).isdisjoint(set(params['pec_tags']))
        assert params['port1_surface_tag'] in params['port_tags']
        assert params['port2_surface_tag'] in params['port_tags']

        # Port positions
        assert np.isclose(params['x_port'], -params['sub_W'] / 2.0, atol=1e-3)
        assert 'y_port_1' in params and 'y_port_2' in params
        assert params['y_port_2'] > params['y_port_1']

    finally:
        if gmsh.isInitialized():
            gmsh.finalize()

    # Invalid geometric input checks
    for bad_override in (
        {'feed_bend_radius': 0.2},
        {'feed_inset_b': -1.0},
        {'port_offset': 15.0},
    ):
        bad_params = {
            'patch_L': 29.95,
            'patch_W': 29.95,
            'sub_h': 1.52,
            'eps_r': 4.3,
            **bad_override,
        }
        with pytest.raises(ValueError):
            compute_model5_routing(bad_params)


def test_model5_router_and_palace_config(tmp_path):
    """Verify build_model router for model=5 and two 100 Ohm ports configuration in Palace."""
    orig_cwd = os.getcwd()
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)
    params = {
        'antenna_model': 5,
        'patch_L': 29.95,
        'patch_W': 29.95,
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
        assert params['antenna_model'] == 5

        # 1. Test simultaneous excitation of both ports
        build_palace_config(params, data_dir=data_dir)
        with open(os.path.join(data_dir, "config.json"), "r", encoding="utf-8") as f:
            cfg = json.load(f)

        ports = cfg['Boundaries']['LumpedPort']
        assert len(ports) == 2

        # Port 1 (Tag 4, 100 Ohm)
        p1 = next(p for p in ports if p['Index'] == 1)
        assert p1['Attributes'] == [4]
        assert np.isclose(p1['R'], 100.0)
        assert p1['Excitation'] is True

        # Port 2 (Tag 6, 100 Ohm)
        p2 = next(p for p in ports if p['Index'] == 2)
        assert p2['Attributes'] == [6]
        assert np.isclose(p2['R'], 100.0)
        assert p2['Excitation'] is True

        # 2. Test sequential mode (driven_port='all' -> static config.json excites Port 1)
        params['driven_port'] = 'all'
        build_palace_config(params, data_dir=data_dir)
        with open(os.path.join(data_dir, "config.json"), "r", encoding="utf-8") as f:
            cfg_all = json.load(f)
        p1_all = next(p for p in cfg_all['Boundaries']['LumpedPort'] if p['Index'] == 1)
        p2_all = next(p for p in cfg_all['Boundaries']['LumpedPort'] if p['Index'] == 2)
        assert p1_all['Excitation'] is True
        assert p2_all['Excitation'] is False

        # 3. Test exciting Port 2 only
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


def test_model5_mesh_and_physical_groups(tmp_path):
    """Verify conformal Gmsh mesh generation for Model 5 and correct Physical Groups assignment."""
    orig_cwd = os.getcwd()
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)
    params = {
        'antenna_model': 5,
        'patch_L': 29.95,
        'patch_W': 29.95,
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

        # Verify presence of Physical Groups in exported MSH file
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


def test_model5_visualization_and_tracker(tmp_path):
    """Verify 2D geometry preview and recording results to CSV/Markdown for Model 5."""
    orig_cwd = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        params = {
            'antenna_model': 5,
            'patch_L': 29.95,
            'patch_W': 29.95,
            'trans_w': 0.30,
            'trans_l': 19.00,
            'feed_inset_b': 2.5,
            'feed_inset_l': 2.5,
            'feed_delta_l': 18.66,
            'feed_bend_radius': 3.0,
            'port_offset': 3.0,
        }

        # 1. Visualization
        vis_file = os.path.join(str(tmp_path), "test_vis_m5.png")
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
            f.write("2.320, -18.5, 0.0, -22.0, 0.0, -22.0, 0.0, -19.2, 0.0\n")

        row = record_run(params, output_dir=out_dir, run_name="test_m5_run", results_dir=res_dir)
        assert row is not None
        assert row['run_name'] == "test_m5_run"
        assert np.isclose(float(row['patch_L_mm']), 29.95)
        assert np.isclose(float(row['trans_w_mm']), 0.30)
        assert np.isclose(float(row['trans_l_mm']), 19.00)
        assert np.isclose(float(row['S11_min [dB]']), -18.5)
        assert np.isclose(float(row['S22_min [dB]']), -19.2)
        assert np.isclose(float(row['S21_min [dB]']), -22.0)

        csv_summary = os.path.join(res_dir, "sweep_results_model5.csv")
        assert os.path.exists(csv_summary)
        md_summary = os.path.join(res_dir, "sweep_results_model5.md")
        assert os.path.exists(md_summary)

        # 3. Test printing summary table
        print_summary_table_model5(csv_file=csv_summary)

    finally:
        os.chdir(orig_cwd)


def test_model5_sweep_builder():
    """Verify sweep step builder for Model 5."""
    # 1. patch_l sweep
    steps_pl, desc_pl = build_sweep_steps_m5(sweep_target="patch_l", patch_lengths=[29.8, 29.95, 30.1])
    assert len(steps_pl) == 3
    assert "patch_l" in desc_pl
    for s in steps_pl:
        assert s['antenna_model'] == 5
        assert s['port_impedance'] == 100.0

    # 2. bend_radius sweep
    steps_br, desc_br = build_sweep_steps_m5(sweep_target="bend_radius", bend_radii=[2.5, 3.0, 3.5])
    assert len(steps_br) == 3
    assert steps_br[0]['bend_radius'] == 2.5

    # 3. port_offset sweep
    steps_po, desc_po = build_sweep_steps_m5(sweep_target="port_offset", port_offsets=[2.0, 3.0])
    assert len(steps_po) == 2
    assert steps_po[1]['port_offset'] == 3.0

    # 4. driven_port sweep
    steps_dp, desc_dp = build_sweep_steps_m5(sweep_target="driven_port")
    assert len(steps_dp) == 3
    driven_modes = [s['driven_port'] for s in steps_dp]
    assert driven_modes == ['all', '1', '2']


def test_model5_end_to_end_main(tmp_path):
    """Verify complete Model 5 pipeline via main(skip_simulation=True)."""
    orig_cwd = os.getcwd()
    data_dir = str(tmp_path / "data")
    export_dir = str(tmp_path / "export")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(export_dir, exist_ok=True)

    env_patch = {
        "DATA_DIR": data_dir,
        "EXPORT_DIR": export_dir,
        "ANTENNA_MODEL": "5",
    }

    try:
        os.chdir(str(tmp_path))
        with patch.dict(os.environ, env_patch, clear=False):
            custom_params = {
                'run_name': "test_m5_pipeline",
                'antenna_model': 5,
                'patch_L': 29.95,
                'patch_W': 29.95,
                'trans_w': 0.30,
                'trans_l': 19.00,
                'feed_inset_b': 2.5,
                'feed_inset_l': 2.5,
                'feed_delta_l': 18.66,
                'feed_bend_radius': 3.0,
                'port_offset': 3.0,
                'air_margin': 25.0,
                'mesh_size_max': 15.0,
                'mesh_size_min': 1.5,
            }
            main(custom_params=custom_params, skip_simulation=True)

            # Verify generated outputs in data_dir
            mesh_file = os.path.join(data_dir, "mesh.msh")
            cfg_file = os.path.join(data_dir, "config.json")
            step_file = os.path.join(data_dir, "antenna_model.step")
            vis_file = os.path.join(data_dir, "geometry_iso.png")

            assert os.path.exists(mesh_file)
            assert os.path.exists(cfg_file)
            assert os.path.exists(step_file)
            assert os.path.exists(vis_file)

            # Verify config.json contents
            with open(cfg_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            lumped_ports = cfg['Boundaries']['LumpedPort']
            assert len(lumped_ports) == 2
            assert lumped_ports[0]['Attributes'] == [4]
            assert lumped_ports[1]['Attributes'] == [6]
            assert lumped_ports[0]['R'] == 100.0
            assert lumped_ports[1]['R'] == 100.0

    finally:
        if gmsh.isInitialized():
            gmsh.finalize()
        os.chdir(orig_cwd)
