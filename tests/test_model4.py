"""
test_model4.py - Komplexní jednotkové testy pro finální Model 4 (50 Ohm T-článek s oblouky).
Ověřuje:
  1. Analytiku drah s oblouky a přesný fázový rozdíl L_100_b - L_100_l == feed_delta_l.
  2. Geometrii OpenCASCADE (oblouky bez 90° ohybů, T-článek, přebrání výchozích parametrů z Modelu 3).
  3. Router geometry.py, konfiguraci Palace (1× 50 Ohm port) a 3D konformní síťování (mesh.py).
  4. Parametrické sweepy (sweep_model4.py), tracking (sweep_results_model4.csv/.md), vizualizaci a de-embedding.
  5. Kompletní end-to-end běh main(skip_simulation=True) včetně parametrizace z prostředí (.env).
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
    build_model_v4,
    calc_curved_path_length,
    compute_curved_ribbon_outline,
    compute_model4_routing,
)
from main import main
from mesh import assign_physical_groups_and_mesh
from palace_builder import build_palace_config
from plot_deembedding import plot_impedance_deembedding
from plot_s_parameters import plot_s_parameters
from rf_calc import DESIGN_FREQ_GHZ, calculate_deembedding_model3, synth_microstrip_w
import sweep_model4
from sweep_model4 import build_sweep_steps_m4, run_sweep_model4
from tracker import print_summary_table_model4, record_run
from visualization import plot_geometry


def test_curved_path_length_and_phase_balance_model4():
    """Ověření výpočtu délky obloukové trasy a přesné shody fázování Delta L."""
    # Jednoduchý 90° roh se čtvrtkruhým obloukem: délka = (10 - R) + (10 - R) + pi*R/2
    pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
    expected = (10.0 - 3.0) + (10.0 - 3.0) + 0.5 * np.pi * 3.0
    assert np.isclose(calc_curved_path_length(pts, 3.0), expected, atol=1e-9)

    base = {
        'patch_L': 29.81,
        'patch_W': 29.81,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'port_impedance': 50.0,
    }

    # Výchozí nastavení (otočený levý T-článek bez meandru), různý R/fillet i explicitní offset/y_T
    variants = [
        {},
        {'feed_bend_radius': 3.5, 'feed_end_straight': 4.6},
        {'feed_bend_radius': 2.5, 'feed_t_fillet_r': 0.0},
        {'feed_arm_offset': 9.0, 'feed_delta_l': 19.2},
        {'feed_y_T': -30.5},
    ]
    for extra in variants:
        cfg = dict(base, **extra)
        info = compute_model4_routing(cfg)
        diff = info['L_100_b'] - info['L_100_l']
        assert np.isclose(diff, info['feed_delta_l'], atol=1e-6), (
            f"Rozdíl drah L_100_b - L_100_l ({diff:.6f}) musí odpovídat delta_l ({info['feed_delta_l']:.6f})"
        )
        assert np.isclose(info['x_port'], -info['W_sub'] / 2.0, atol=1e-6)
        assert np.isclose(info['y_port'], info['y_T'], atol=1e-6)
        assert info['s_end_l'] >= 0.5 - 1e-6
        assert info['s_end_b'] >= info['end_straight'] - 1e-6
        assert info['s_T_up'] >= 0.5 - 1e-6
        assert info['s_T_down'] >= 0.5 - 1e-6
        assert info['s_horiz_b'] >= -1e-6

        # Ověření generování 2D obrysu pro obě zakřivené větve
        poly_l = compute_curved_ribbon_outline(info['arm_l_build_waypoints'], info['w_feed'], info['bend_radius'])
        poly_b = compute_curved_ribbon_outline(info['arm_b_build_waypoints'], info['w_feed'], info['bend_radius'])
        assert len(poly_l) > 10 and len(poly_b) > 10


def test_geometry_model4_defaults_and_validation():
    """Ověření převzetí výchozích hodnot Modelu 3, tvorby OCC entit a kontroly neplatných vstupů."""
    params = {
        'antenna_model': 4,
        'patch_L': 28.8,
        'patch_W': 28.8,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'air_margin': 30.0,
    }
    try:
        sub_tag, air_tag = build_model_v4(params)
        assert sub_tag is not None and air_tag is not None
        assert params['antenna_model'] == 4

        # Převzaté výchozí hodnoty Modelu 3
        assert np.isclose(params['trans_w'], 0.42, atol=1e-4)
        assert 18.5 <= params['trans_l'] <= 19.2
        assert np.isclose(params['feed_inset_b'], 2.5, atol=1e-4)
        assert np.isclose(params['feed_inset_l'], 2.5, atol=1e-4)
        assert np.isclose(params['inset_gap_b'], 0.5, atol=1e-4)
        assert np.isclose(params['inset_gap_l'], 0.5, atol=1e-4)

        # Šířky 50 Ohm a 100 Ohm vedení
        expected_w50 = synth_microstrip_w(50.0, 1.52, 4.3)
        expected_w100 = synth_microstrip_w(100.0, 1.52, 4.3)
        assert np.isclose(params['w_50'], expected_w50, atol=1e-3)
        assert np.isclose(params['w_feed'], expected_w100, atol=1e-3)

        # Jediný 50 Ohm port na levém okraji substrátu disjunktní s PEC
        assert len(params['port_tags']) > 0
        assert len(params['pec_tags']) > 0
        assert set(params['port_tags']).isdisjoint(set(params['pec_tags']))
        assert np.isclose(params['x_port'], -params['sub_W'] / 2.0, atol=1e-3)
        assert np.isclose(params['y_port'], params['feed_y_T'], atol=1e-3)
    finally:
        if gmsh.isInitialized():
            gmsh.finalize()

    # Kontrola neplatných geometrických vstupů
    for bad_override in (
        {'feed_bend_radius': 0.2},
        {'feed_inset_b': -1.0},
        {'feed_arm_offset': 2.5, 'feed_bend_radius': 3.0},
        {'feed_end_straight': 0.1},
        {'feed_x_T': -4.0, 'feed_bend_radius': 3.0},
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
            compute_model4_routing(bad_params)


def test_geometry_router_palace_and_mesh_model4(tmp_path):
    """Ověření routeru, konfigurace Palace (1× 50 Ohm port) a 3D sítě Gmsh s oblouky."""
    orig_cwd = os.getcwd()
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)
    params = {
        'antenna_model': 4,
        'patch_L': 29.81,
        'patch_W': 29.81,
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
        'feed_t_fillet_r': 0.0,    # Ostrý T-uzel fallback
    }
    try:
        os.chdir(str(tmp_path))
        sub_tag, air_tag = build_model(params)
        assert sub_tag is not None and air_tag is not None
        assert params['antenna_model'] == 4

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


def test_sweep_model4_steps_and_run(tmp_path):
    """Ověření generátoru kroků sweepu a běhu run_sweep_model4 s mockovaným main()."""
    clear_keys = (
        "SWEEP_TARGET", "PATCH_L", "PATCH_W", "SWEEP_PATCH_L", "SWEEP_PATCH_W",
        "TRANS_W", "TRANS_L", "FEED_DELTA_L", "FEED_BEND_RADIUS", "FEED_T_FILLET_R",
        "FEED_50_LEN", "FEED_ARM_OFFSET", "FEED_END_STRAIGHT",
    )
    with patch.dict(os.environ, {"SWEEP_PROFILE": "fast", "SWEEP_EXPORT_EACH": "false"}):
        for k in clear_keys:
            os.environ.pop(k, None)

        steps_pl, _ = build_sweep_steps_m4(sweep_target="patch_l", patch_lengths=[29.6, 29.81])
        assert len(steps_pl) == 2
        assert steps_pl[0]['run_name'] == "m4_patchL_29.60mm"
        assert np.isclose(steps_pl[1]['patch_L'], 29.81)

        steps_dl, _ = build_sweep_steps_m4(sweep_target="delta_l", delta_l=[18.0, 18.66, 19.2])
        assert len(steps_dl) == 3
        assert steps_dl[1]['run_name'] == "m4_dl18.66mm"

        steps_br, _ = build_sweep_steps_m4(sweep_target="bend_radius", bend_radii=[2.5, 3.0, 4.0])
        assert len(steps_br) == 3
        assert steps_br[2]['run_name'] == "m4_rbend4.00mm"
        assert np.isclose(steps_br[2]['feed_bend_radius'], 4.0)
        assert np.isclose(steps_br[2]['feed_50_len'], 9.0)

        steps_l50, _ = build_sweep_steps_m4(sweep_target="feed_50_len", feed_50_lens=[12.0, 18.0])
        assert len(steps_l50) == 2
        assert steps_l50[0]['run_name'] == "m4_l50_12.00mm"

        steps_in, _ = build_sweep_steps_m4(sweep_target="inset", mode="symmetric", insets=[2.0, 2.5])
        assert len(steps_in) == 2
        assert steps_in[0]['run_name'] == "m4_ib2.00_il2.00mm"

        with patch.object(sweep_model4, "load_env", return_value=(str(tmp_path), str(tmp_path / "data"))), \
             patch.object(sweep_model4, "get_export_dir", return_value=str(tmp_path / "export")), \
             patch.object(sweep_model4, "print_summary_table_model4") as mock_summary, \
             patch.object(sweep_model4, "main") as mock_main:
            run_sweep_model4(sweep_target="bend_radius", bend_radii=[2.5, 3.5], skip_simulation=True)
            assert mock_main.call_count == 2
            assert mock_main.call_args_list[0].kwargs['custom_params']['antenna_model'] == 4
            assert np.isclose(mock_main.call_args_list[1].kwargs['custom_params']['feed_bend_radius'], 3.5)
            mock_summary.assert_called_once()


def test_tracker_deembedding_and_plots_model4(tmp_path):
    """Ověření záznamu do sweep_results_model4.csv/.md, de-embeddingu a grafů pro Model 4."""
    res_dir = str(tmp_path / "export")
    postpro_dir = str(tmp_path / "postpro")
    os.makedirs(postpro_dir, exist_ok=True)

    freqs = np.linspace(2.320, 2.345, 11)
    s_path = os.path.join(postpro_dir, "port-S.csv")
    with open(s_path, "w", encoding="utf-8") as f:
        f.write("f (GHz),|S[1][1]| (dB),arg(S[1][1]) (deg.)\n")
        for fq in freqs:
            delta = (fq - 2.3325) / 0.0125
            s11_db = -22.0 + 14.0 * (delta ** 2)
            f.write(f"{fq:.6e},{s11_db:.4e},{-40.0 * delta:.4e}\n")

    ff_path = os.path.join(postpro_dir, "farfield-rE.csv")
    ff_rows = [[fq, 1, 0.0, 0.0, 1.0, 0.0, 0.0, -1.0, 0.0, 0.0] for fq in freqs]
    np.savetxt(
        ff_path,
        np.array(ff_rows),
        delimiter=",",
        header="f (GHz), exc, theta (deg.), phi (deg.), r*Re{E_x}, r*Im{E_x}, r*Re{E_y}, r*Im{E_y}, r*Re{E_z}, r*Im{E_z}",
        comments="",
    )

    params = {
        'antenna_model': 4,
        'patch_L': 29.81,
        'patch_W': 29.81,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'tan_delta': 0.02,
        'trans_w': 0.42,
        'trans_l': 18.88,
        'feed_inset_b': 2.5,
        'feed_inset_l': 2.5,
        'feed_delta_l': 18.66,
        'feed_bend_radius': 3.0,
        'feed_50_len': 9.0,
        'feed_end_straight': 4.6,
        'feed_arm_offset': 7.6,
        'L_100_b': 53.88,
        'L_100_l': 35.22,
        'port_impedance': 50.0,
    }
    with open(os.path.join(postpro_dir, "params.json"), "w", encoding="utf-8") as f:
        json.dump(params, f)

    row = record_run(params, output_dir=postpro_dir, run_name="m4_test", results_dir=res_dir)
    csv_path = os.path.join(res_dir, "sweep_results_model4.csv")
    md_path = os.path.join(res_dir, "sweep_results_model4.md")
    assert os.path.exists(csv_path) and os.path.exists(md_path)
    assert row['Polarizace'] == "LHCP"
    assert float(row['S11_min [dB]']) < -20.0
    print_summary_table_model4(csv_file=csv_path)

    # Analytický de-embedding 50 Ohm přívodu -> T-článek
    s11_c = 0.08 * np.ones_like(freqs, dtype=complex)
    deemb = calculate_deembedding_model3(freqs, s11_c, None, params=params)
    assert deemb['model'] == 4
    assert np.isclose(deemb['rp1']['z0_ref'], 50.0)
    assert 48.0 <= deemb['rp2']['z0_ref'] <= 52.0
    assert np.isclose(deemb['rp3']['z0_ref'], 100.0)

    # Graf S-parametrů, de-embeddingu i geometrie
    s_png = os.path.join(postpro_dir, "graf_S_parametry.png")
    d_png = os.path.join(postpro_dir, "graf_impedance_skoky.png")
    g_png = os.path.join(postpro_dir, "geometry_iso.png")
    assert plot_s_parameters(postpro_dir, output_png=s_png, params=params) is not None
    assert plot_impedance_deembedding(postpro_dir, params=params, output_png=d_png) is not None
    plot_geometry(params, filename=g_png)

    for p_check in (
        s_png,
        d_png,
        g_png,
        os.path.join(postpro_dir, "obrazky", "geometrie_shora.png"),
        os.path.join(postpro_dir, "obrazky", "geometrie_detail_transformatoru.png"),
    ):
        assert os.path.exists(p_check) and os.path.getsize(p_check) > 10000


def test_main_skip_simulation_model4_and_env_defaults():
    """Ověření kompletního dry-run běhu main() pro Model 4 včetně parametrů z prostředí (.env)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        orig_cwd = os.getcwd()
        data_dir = os.path.join(tmp_dir, "data")
        export_dir = os.path.join(tmp_dir, "export")
        env_patch = {
            "DATA_DIR": data_dir,
            "EXPORT_DIR": export_dir,
            "ANTENNA_MODEL": "4",
            "FEED_BEND_RADIUS": "3.2",
            "FEED_T_FILLET_R": "0.6",
            "FEED_50_LEN": "9.5",
            "FEED_END_STRAIGHT": "4.8",
            "FEED_ARM_OFFSET": "8.0",
            "SUB_MARGIN": "8.0",
            "DESIGN_FREQ_GHZ": str(DESIGN_FREQ_GHZ),
        }
        clear_keys = (
            "PORT_IMPEDANCE", "PATCH_L", "PATCH_W", "TRANS_W",
            "FEED_INSET_B", "FEED_INSET_L", "FEED_T_X", "FEED_T_Y", "SUB_W", "SUB_L",
        )

        try:
            os.chdir(tmp_dir)
            with patch.dict(os.environ, env_patch), \
                 patch("postpro_utils.get_project_root", return_value=tmp_dir):
                for k in clear_keys:
                    os.environ.pop(k, None)

                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    main(
                        custom_params={'mesh_size_max': 12.0, 'mesh_size_min': 1.2},
                        skip_simulation=True,
                        clean=False,
                    )

                legend_warns = [
                    w for w in caught
                    if issubclass(w.category, UserWarning)
                    and ("legend" in str(w.message).lower() or "artists with labels" in str(w.message).lower())
                ]
                assert not legend_warns

            for fname in ("antenna_model.step", "mesh.msh", "config.json", "geometry_iso.png", "params.json"):
                fpath = os.path.join(data_dir, fname)
                assert os.path.exists(fpath) and os.path.getsize(fpath) > 0

            with open(os.path.join(data_dir, "config.json"), "r", encoding="utf-8") as f:
                cfg = json.load(f)
            assert len(cfg["Boundaries"]["LumpedPort"]) == 1
            assert cfg["Boundaries"]["LumpedPort"][0]["R"] == 50.0

            with open(os.path.join(data_dir, "params.json"), "r", encoding="utf-8") as f:
                saved = json.load(f)
            assert saved["antenna_model"] == 4
            assert np.isclose(saved["patch_L"], 28.8)
            assert np.isclose(saved["port_impedance"], 50.0)
            assert np.isclose(saved["feed_bend_radius"], 3.2)
            assert np.isclose(saved["feed_t_fillet_r"], 0.6)
            assert np.isclose(saved["feed_50_len"], 9.5)
            assert np.isclose(saved["feed_end_straight"], 4.8)
            assert np.isclose(saved["feed_arm_offset"], 8.0)
            assert np.isclose(saved["x_port"], -saved["sub_W"] / 2.0, atol=1e-3)
            assert np.isclose(saved["y_port"], saved["feed_y_T"], atol=1e-3)
        finally:
            if gmsh.isInitialized():
                gmsh.finalize()
            os.chdir(orig_cwd)


if __name__ == "__main__":
    pytest.main(["-v", __file__])
