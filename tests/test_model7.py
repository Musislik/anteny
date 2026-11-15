"""
test_model7.py - Komplexní jednotkové testy pro Model 7 (zrcadlený Model 4 pro RHCP).
Ověřuje:
  1. Analytiku trasování podél osy Y:
       - Zrcadlení souřadnic x -> -x, y -> y (x_T_m7 == -x_T_m4, x_port_m7 == +W_sub/2).
       - Přesnou rovnost délek drah L_100_r == L_100_l a L_100_b == L_100_b.
       - Splnění fázovací podmínky L_100_b - L_100_r == feed_delta_l.
  2. Geometrii OpenCASCADE:
       - Správné umístění pravého zářezu, pravého transformátoru a pravého 50 Ohm přívodu.
       - Hladké kruhové oblouky a zaoblený T-článek vpravo bez překryvů.
       - 1 výstupní 50 Ohm port na pravé hraně substrátu (x = +W_sub/2).
  3. Integraci routeru geometry.py, konfigurace Palace (1× 50 Ohm port) a 3D sítě (mesh.py).
  4. Generování opačné polarizace RHCP (Right-Hand Circular Polarization) z vyzařovacích dat.
  5. Parametrické sweepy (sweep_model7.py), tracking (sweep_results_model7.csv/.md) a 2D vizualizaci.
  6. Kompletní end-to-end běh main(skip_simulation=True) pro Model 7.
"""

import os
import sys
import json
import tempfile
import warnings
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
from geometry_v4 import (
    calc_curved_path_length,
    compute_curved_ribbon_outline,
    compute_model4_routing,
)
from geometry_v7 import (
    build_model_v7,
    compute_model7_routing,
)
from main import main
from mesh import assign_physical_groups_and_mesh
from palace_builder import build_palace_config
from rf_calc import DESIGN_FREQ_GHZ, synth_microstrip_w
import sweep_model7
from sweep_model7 import build_sweep_steps_m7, run_sweep_model7
from tracker import print_summary_table_model7, record_run
from visualization import plot_geometry


def test_model7_mirroring_and_phase_balance():
    """Ověření, že Model 7 je přesným zrcadlením Modelu 4 podél osy Y se stejným fázováním."""
    base = {
        'patch_L': 29.81,
        'patch_W': 29.81,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'port_impedance': 50.0,
    }

    variants = [
        {},
        {'feed_bend_radius': 3.5, 'feed_end_straight': 4.6},
        {'feed_bend_radius': 2.5, 'feed_t_fillet_r': 0.0},
        {'feed_arm_offset': 9.0, 'feed_delta_l': 19.2},
        {'feed_y_T': -30.5},
    ]

    for extra in variants:
        cfg = dict(base, **extra)
        info4 = compute_model4_routing(cfg)
        info7 = compute_model7_routing(cfg)

        # 1. Zrcadlení souřadnic kolem osy Y: x_7 == -x_4, y_7 == y_4
        assert np.isclose(info7['x_T'], -info4['x_T'], atol=1e-7)
        assert np.isclose(info7['y_T'], info4['y_T'], atol=1e-7)
        assert np.isclose(info7['x_port'], -info4['x_port'], atol=1e-7)
        assert np.isclose(info7['x_port'], info7['W_sub'] / 2.0, atol=1e-7)
        assert np.isclose(info7['y_port'], info4['y_port'], atol=1e-7)
        assert np.isclose(info7['x_junc_r'], -info4['x_junc_l'], atol=1e-7)
        assert np.isclose(info7['y_junc_b'], info4['y_junc_b'], atol=1e-7)
        assert np.isclose(info7['y_bot'], info4['y_bot'], atol=1e-7)

        # 2. Shoda délek drah (izometrie reflexe)
        assert np.isclose(info7['L_100_r'], info4['L_100_l'], atol=1e-7)
        assert np.isclose(info7['L_100_b'], info4['L_100_b'], atol=1e-7)

        # 3. Přesný fázový posuv Delta L
        diff = info7['L_100_b'] - info7['L_100_r']
        assert np.isclose(diff, info7['feed_delta_l'], atol=1e-6)

        # 4. Zrcadlení všech waypoints
        for (x7, y7), (x4, y4) in zip(info7['arm_r_waypoints'], info4['arm_l_waypoints']):
            assert np.isclose(x7, -x4, atol=1e-4)
            assert np.isclose(y7, y4, atol=1e-4)

        for (x7, y7), (x4, y4) in zip(info7['arm_b_waypoints'], info4['arm_b_waypoints']):
            assert np.isclose(x7, -x4, atol=1e-4)
            assert np.isclose(y7, y4, atol=1e-4)

        # 5. Generování 2D polygonů bez chyb
        poly_r = compute_curved_ribbon_outline(info7['arm_r_build_waypoints'], info7['w_feed'], info7['bend_radius'])
        poly_b = compute_curved_ribbon_outline(info7['arm_b_build_waypoints'], info7['w_feed'], info7['bend_radius'])
        assert len(poly_r) > 10 and len(poly_b) > 10


def test_geometry_model7_defaults_and_validation():
    """Ověření OCC geometrie Modelu 7, portu na pravé straně a kontroly mezních hodnot."""
    params = {
        'antenna_model': 7,
        'patch_L': 28.8,
        'patch_W': 28.8,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'air_margin': 30.0,
    }
    try:
        sub_tag, air_tag = build_model_v7(params)
        assert sub_tag is not None and air_tag is not None
        assert params['antenna_model'] == 7
        assert params['polarization_type'] == 'RHCP'

        # Převzaté a zrcadlené parametry
        assert np.isclose(params['trans_w'], 0.42, atol=1e-4)
        assert np.isclose(params['trans_w_r'], 0.42, atol=1e-4)
        assert np.isclose(params['feed_inset_r'], 2.5, atol=1e-4)
        assert np.isclose(params['feed_inset_b'], 2.5, atol=1e-4)

        # Port na pravé hraně substrátu (x = +W_sub / 2)
        assert np.isclose(params['x_port'], params['sub_W'] / 2.0, atol=1e-3)
        assert np.isclose(params['y_port'], params['feed_y_T'], atol=1e-3)

        # Disjunktní port a PEC
        assert len(params['port_tags']) > 0
        assert len(params['pec_tags']) > 0
        assert set(params['port_tags']).isdisjoint(set(params['pec_tags']))
    finally:
        if gmsh.isInitialized():
            gmsh.finalize()

    # Kontrola neplatných vstupů
    for bad_override in (
        {'feed_bend_radius': 0.2},
        {'feed_inset_b': -1.0},
        {'feed_arm_offset': 2.5, 'feed_bend_radius': 3.0},
        {'feed_end_straight': 0.1},
        {'feed_y_T': -1.0},
    ):
        bad_params = {
            'patch_L': 28.8,
            'patch_W': 28.8,
            'sub_h': 1.52,
            'eps_r': 4.3,
            **bad_override,
        }
        with pytest.raises(ValueError):
            compute_model7_routing(bad_params)


def test_geometry_router_palace_and_mesh_model7(tmp_path):
    """Ověření routeru build_model pro antenna_model=7, mesh.py a palace_builder."""
    orig_cwd = os.getcwd()
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)
    params = {
        'antenna_model': 7,
        'patch_L': 28.8,
        'patch_W': 28.8,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'tan_delta': 0.02,
        'air_margin': 30.0,
        'freq_min': 2.320,
        'freq_max': 2.345,
        'freq_step': 0.005,
        'port_impedance': 50.0,
        'mesh_size_max': 12.0,
        'mesh_size_min': 1.0,
        'mesh_dist_min': 0.5,
        'mesh_dist_max': 6.0,
        'feed_bend_radius': 3.0,
        'feed_end_straight': 4.6,
        'feed_t_fillet_r': 0.8,
    }
    try:
        os.chdir(str(tmp_path))
        sub_tag, air_tag = build_model(params)
        assert sub_tag is not None and air_tag is not None
        assert params['antenna_model'] == 7

        assign_physical_groups_and_mesh(params, data_dir=data_dir)
        mesh_path = os.path.join(data_dir, "mesh.msh")
        assert os.path.exists(mesh_path) and os.path.getsize(mesh_path) > 5000

        build_palace_config(params, data_dir=data_dir)
        with open(os.path.join(data_dir, "config.json"), "r", encoding="utf-8") as f:
            cfg = json.load(f)
        ports = cfg['Boundaries']['LumpedPort']
        assert len(ports) == 1
        assert ports[0]['Index'] == 1
        assert ports[0]['Attributes'] == [4]
        assert ports[0]['R'] == 50.0
        assert ports[0]['Excitation'] is True
    finally:
        if gmsh.isInitialized():
            gmsh.finalize()
        os.chdir(orig_cwd)


def test_tracker_and_rhcp_polarization_model7(tmp_path):
    """Ověření vyhodnocení pravotočivé polarizace RHCP pro Model 7."""
    res_dir = str(tmp_path / "export")
    postpro_dir = str(tmp_path / "postpro")
    os.makedirs(postpro_dir, exist_ok=True)

    freqs = np.linspace(2.320, 2.345, 11)
    s_path = os.path.join(postpro_dir, "port-S.csv")
    with open(s_path, "w", encoding="utf-8") as f:
        f.write("f (GHz),|S[1][1]| (dB),arg(S[1][1]) (deg.)\n")
        for fq in freqs:
            delta = (fq - 2.3325) / 0.0125
            s11_db = -23.0 + 15.0 * (delta ** 2)
            f.write(f"{fq:.6e},{s11_db:.4e},{-35.0 * delta:.4e}\n")

    # Syntetická data pro čistou RHCP: Ex = 1.0, Ey = +1.0j
    # E_LHCP = abs(Ex + j*Ey)/sqrt(2) = abs(1.0 + 1j*1j)/sqrt(2) = 0
    # E_RHCP = abs(Ex - j*Ey)/sqrt(2) = abs(1.0 - 1j*1j)/sqrt(2) = 2/sqrt(2) = sqrt(2)
    ff_path = os.path.join(postpro_dir, "farfield-rE.csv")
    ff_rows = [[fq, 1, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0] for fq in freqs]
    np.savetxt(
        ff_path,
        np.array(ff_rows),
        delimiter=",",
        header="f (GHz), exc, theta (deg.), phi (deg.), r*Re{E_x}, r*Im{E_x}, r*Re{E_y}, r*Im{E_y}, r*Re{E_z}, r*Im{E_z}",
        comments="",
    )

    params = {
        'antenna_model': 7,
        'patch_L': 28.8,
        'patch_W': 28.8,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'tan_delta': 0.02,
        'trans_w': 0.42,
        'trans_l': 18.88,
        'feed_inset_b': 2.5,
        'feed_inset_r': 2.5,
        'feed_delta_l': 18.66,
        'feed_bend_radius': 3.0,
        'feed_50_len': 9.0,
        'feed_end_straight': 4.6,
        'feed_arm_offset': 7.6,
        'L_100_b': 53.88,
        'L_100_r': 35.22,
        'port_impedance': 50.0,
    }
    with open(os.path.join(postpro_dir, "params.json"), "w", encoding="utf-8") as f:
        json.dump(params, f)

    row = record_run(params, output_dir=postpro_dir, run_name="m7_rhcp_test", results_dir=res_dir)
    csv_path = os.path.join(res_dir, "sweep_results_model7.csv")
    md_path = os.path.join(res_dir, "sweep_results_model7.md")
    assert os.path.exists(csv_path) and os.path.exists(md_path)
    assert row['Polarizace'] == "RHCP", f"Očekávána polarizace RHCP, získána: {row['Polarizace']}"
    assert float(row['Gain_RHCP [dBi]']) > float(row['Gain_LHCP [dBi]']) + 20.0
    assert float(row['S11_min [dB]']) < -20.0


def test_sweep_model7_steps_and_run(tmp_path):
    """Ověření generátoru kroků sweepu Modelu 7 a mockovaného běhu."""
    with patch.dict(os.environ, {"SWEEP_PROFILE": "fast", "SWEEP_EXPORT_EACH": "false"}):
        steps_pl, _ = build_sweep_steps_m7(sweep_target="patch_l", patch_lengths=[28.6, 28.8])
        assert len(steps_pl) == 2
        assert steps_pl[0]['run_name'] == "m7_patchL_28.60mm"
        assert np.isclose(steps_pl[1]['patch_L'], 28.8)

        steps_br, _ = build_sweep_steps_m7(sweep_target="bend_radius", bend_radii=[2.5, 3.5])
        assert len(steps_br) == 2
        assert steps_br[1]['run_name'] == "m7_rbend3.50mm"
        assert np.isclose(steps_br[1]['feed_bend_radius'], 3.5)

        with patch.object(sweep_model7, "load_env", return_value=(str(tmp_path), str(tmp_path / "data"))), \
             patch.object(sweep_model7, "get_export_dir", return_value=str(tmp_path / "export")), \
             patch.object(sweep_model7, "print_summary_table_model7") as mock_summary, \
             patch.object(sweep_model7, "main") as mock_main:
            run_sweep_model7(sweep_target="bend_radius", bend_radii=[2.5, 3.5], skip_simulation=True)
            assert mock_main.call_count == 2
            assert mock_main.call_args_list[0].kwargs['custom_params']['antenna_model'] == 7
            assert np.isclose(mock_main.call_args_list[1].kwargs['custom_params']['feed_bend_radius'], 3.5)
            mock_summary.assert_called_once()


def test_model7_visualization_generation(tmp_path):
    """Ověření vykreslení 2D náhledu geometrie a detailu T-článku Modelu 7."""
    params = {
        'antenna_model': 7,
        'patch_L': 28.8,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'air_margin': 30.0,
    }
    out_png = str(tmp_path / "geom_m7.png")
    plot_geometry(params, filename=out_png)
    assert os.path.exists(out_png) and os.path.getsize(out_png) > 10000
    det_png = os.path.join(str(tmp_path), "obrazky", "geometrie_detail_transformatoru.png")
    assert os.path.exists(det_png) and os.path.getsize(det_png) > 10000


def test_model7_end_to_end_main(tmp_path):
    """Kompletní end-to-end běh main() se skip_simulation=True pro Model 7."""
    orig_cwd = os.getcwd()
    data_dir = str(tmp_path / "data")
    export_dir = str(tmp_path / "export")
    env_patch = {
        "DATA_DIR": data_dir,
        "EXPORT_DIR": export_dir,
        "ANTENNA_MODEL": "7",
    }
    try:
        os.chdir(str(tmp_path))
        with patch.dict(os.environ, env_patch), \
             patch("postpro_utils.get_project_root", return_value=str(tmp_path)):
            main(
                custom_params={
                    'run_name': 'm7_e2e_test',
                    'antenna_model': 7,
                    'patch_L': 28.8,
                    'patch_W': 28.8,
                    'sub_h': 1.52,
                    'eps_r': 4.3,
                    'mesh_size_max': 12.0,
                    'mesh_size_min': 1.0,
                },
                skip_simulation=True,
                clean=False,
            )
        assert os.path.exists(os.path.join(data_dir, "mesh.msh"))
        assert os.path.exists(os.path.join(data_dir, "antenna_model.step"))
        assert os.path.exists(os.path.join(data_dir, "config.json"))
        assert os.path.exists(os.path.join(data_dir, "geometry_iso.png"))
        assert os.path.exists(os.path.join(data_dir, "params.json"))

        with open(os.path.join(data_dir, "params.json"), "r", encoding="utf-8") as f:
            saved_params = json.load(f)
        assert saved_params['antenna_model'] == 7
        assert saved_params['polarization_type'] == 'RHCP'
        assert np.isclose(saved_params['x_port'], saved_params['sub_W'] / 2.0, atol=1e-3)
    finally:
        if gmsh.isInitialized():
            gmsh.finalize()
        os.chdir(orig_cwd)
