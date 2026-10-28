"""
test_model2.py - Komplexní jednotkové testy pro Model 2 a zpětnou kompatibilitu Modelu 1.
"""

import os
import sys
import shutil
import tempfile
import json
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
    calc_quarter_wave_length,
    DESIGN_FREQ_GHZ,
)
from geometry_v1 import build_model_v1
from geometry_v2 import build_model_v2
from geometry import build_model
from palace_builder import build_palace_config
from tracker import (
    extract_s_parameters_model2,
    extract_farfield_metrics,
    record_run,
    record_run_model2,
    update_markdown_summary,
    print_summary_table_model2,
    TRACKED_METRICS_MODEL2,
    FIELDNAMES_V2,
)
from sweep_model2 import build_sweep_pairs


def test_rf_calculations():
    """Test analytických VF výpočtů pro 100 Ohm vedení."""
    h = 1.52
    eps_r = 4.3
    w = synth_microstrip_w(100.0, h, eps_r)
    assert 0.65 <= w <= 0.75, f"Šířka w pro 100 Ohm by měla být cca 0.69 mm, ale je {w:.4f}"

    eps_eff = calc_microstrip_eps_eff(w, h, eps_r)
    assert 2.8 <= eps_eff <= 3.2, f"eps_eff by měla být cca 2.97, ale je {eps_eff:.4f}"

    lambda_g_4 = calc_quarter_wave_length(DESIGN_FREQ_GHZ, eps_eff)
    assert 18.0 <= lambda_g_4 <= 19.5, f"lambda_g/4 by měla být cca 18.66 mm, ale je {lambda_g_4:.4f}"


def test_geometry_model2_properties():
    """Test geometrie Modelu 2 a ověření fázovací podmínky prodloužení o lambda_g/4."""
    params = {
        'patch_L': 30.3,
        'patch_W': 30.3,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'air_margin': 30.0,
        'feed_inset_b': 3.0,
        'feed_inset_l': 2.5,
        'sub_W': 80.0,
    }

    sub_tag, air_tag = build_model_v2(params)
    assert sub_tag is not None
    assert air_tag is not None

    # Ověření portů
    assert len(params['port1_tags']) > 0, "Port 1 fragmenty musí existovat"
    assert len(params['port2_tags']) > 0, "Port 2 fragmenty musí existovat"
    assert len(params['pec_tags']) > 0, "PEC fragmenty musí existovat"

    # Ověření fázovací podmínky: L_feed_bottom = L_ref + lambda_g_4
    assert np.isclose(params['L_feed_bottom'], params['L_ref'] + params['lambda_g_4'], atol=1e-3), \
        f"L_feed_bottom ({params['L_feed_bottom']}) musí být přesně L_ref + lambda_g/4 ({params['L_ref'] + params['lambda_g_4']})"

    # Ověření polohy spodního portu: y_port = -L/2 + inset_b - L_feed_bottom
    expected_y_port = -params['patch_L'] / 2.0 + params['feed_inset_b'] - params['L_feed_bottom']
    assert np.isclose(params['y_port'], expected_y_port, atol=1e-3), \
        f"y_port ({params['y_port']}) musí odpovídat hraně substrátu ({expected_y_port})"

    # Ověření, že port 1 a port 2 mají disjunktní plochy
    p1_set = set(params['port1_tags'])
    p2_set = set(params['port2_tags'])
    assert p1_set.isdisjoint(p2_set), "Plochy Portu 1 a Portu 2 se nesmí překrývat"

    import gmsh
    gmsh.clear()


def test_geometry_router():
    """Test routeru geometry.py pro obě verze modelu."""
    # Model 2
    params_v2 = {
        'antenna_model': 2,
        'patch_L': 30.3,
        'patch_W': 30.3,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'air_margin': 30.0,
        'feed_inset_b': 0.0,
        'feed_inset_l': 0.0,
    }
    s2, a2 = build_model(params_v2)
    assert params_v2.get('antenna_model') == 2
    assert 'port1_tags' in params_v2
    assert 'port2_tags' in params_v2

    import gmsh
    gmsh.clear()


def test_palace_builder_configs():
    """Test generování Palace konfigurace pro Model 1 (1 port) i Model 2 (2 porty)."""
    os.makedirs("data", exist_ok=True)

    # 1. Test Model 1
    params_v1 = {
        'antenna_model': 1,
        'eps_r': 4.3,
        'tan_delta': 0.02,
        'freq_min': 2.32,
        'freq_max': 2.345,
        'freq_step': 0.005,
    }
    build_palace_config(params_v1)
    with open("data/config.json", "r") as f:
        cfg1 = json.load(f)

    ports1 = cfg1["Boundaries"]["LumpedPort"]
    assert len(ports1) == 1, "Model 1 musí mít přesně 1 LumpedPort"
    assert ports1[0]["Index"] == 1
    assert ports1[0]["Attributes"] == [4]
    assert ports1[0]["R"] == 50.0

    # 2. Test Model 2
    params_v2 = {
        'antenna_model': 2,
        'eps_r': 4.3,
        'tan_delta': 0.02,
        'freq_min': 2.32,
        'freq_max': 2.345,
        'freq_step': 0.005,
    }
    build_palace_config(params_v2)
    with open("data/config.json", "r") as f:
        cfg2 = json.load(f)

    ports2 = cfg2["Boundaries"]["LumpedPort"]
    assert len(ports2) == 2, "Model 2 musí mít přesně 2 LumpedPorty"
    assert ports2[0]["Index"] == 1
    assert ports2[0]["Attributes"] == [4]
    assert ports2[0]["R"] == 100.0
    assert ports2[0]["Excitation"] is True

    assert ports2[1]["Index"] == 2
    assert ports2[1]["Attributes"] == [6]
    assert ports2[1]["R"] == 100.0
    assert ports2[1]["Excitation"] is True


def test_tracker_model2_extraction():
    """Test extrakce S11 a S22 ze syntetických dat napětí a proudu pro Model 2."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        freqs = np.array([2.30, 2.32, 2.33, 2.34, 2.36])
        # Port 1 (spodní): rezonance na 2.33 GHz -> Z1 = 100 Ohm (přesné přizpůsobení)
        # Port 2 (levý): rezonance na 2.34 GHz -> Z2 = 100 Ohm
        # V = 10 V. Na 2.33 GHz pro Port 1: I1 = 0.1 A -> Z1 = 100 Ohm -> Gamma = 0 -> S11 = -inf
        v_data = np.zeros((len(freqs), 7))
        v_data[:, 0] = freqs
        v_data[:, 1] = 10.0  # V_inc1
        v_data[:, 2] = 10.0  # Re{V1}
        v_data[:, 3] = 0.0   # Im{V1}
        v_data[:, 4] = 10.0  # V_inc2
        v_data[:, 5] = 10.0  # Re{V2}
        v_data[:, 6] = 0.0   # Im{V2}

        i_data = np.zeros((len(freqs), 7))
        i_data[:, 0] = freqs
        i_data[:, 1] = 0.1
        # I1: maximum (0.1 A) na 2.33 GHz
        i_data[:, 2] = np.array([0.05, 0.08, 0.10, 0.08, 0.05])
        i_data[:, 3] = 0.0
        # I2: maximum (0.1 A) na 2.34 GHz
        i_data[:, 4] = 0.1
        i_data[:, 5] = np.array([0.05, 0.07, 0.08, 0.10, 0.06])
        i_data[:, 6] = 0.0

        v_file = os.path.join(tmp_dir, "port-V.csv")
        i_file = os.path.join(tmp_dir, "port-I.csv")

        np.savetxt(v_file, v_data, delimiter=',', header="f (GHz), V_inc[1], Re{V[1]}, Im{V[1]}, V_inc[2], Re{V[2]}, Im{V[2]}")
        np.savetxt(i_file, i_data, delimiter=',', header="f (GHz), I_inc[1], Re{I[1]}, Im{I[1]}, I_inc[2], Re{I[2]}, Im{I[2]}")

        metrics = extract_s_parameters_model2(tmp_dir, z0=100.0)
        assert metrics['f0_b_GHz'] == 2.33, f"Port 1 rezonance by měla být 2.33 GHz, je {metrics['f0_b_GHz']}"
        assert metrics['f0_l_GHz'] == 2.34, f"Port 2 rezonance by měla být 2.34 GHz, je {metrics['f0_l_GHz']}"
        assert metrics['s11_min_dB'] < -40.0, f"S11 min by mělo být velmi nízké (přesné přizpůsobení), je {metrics['s11_min_dB']}"
        assert metrics['s22_min_dB'] < -40.0, f"S22 min by mělo být velmi nízké (přesné přizpůsobení), je {metrics['s22_min_dB']}"
        assert np.isclose(metrics['zin1_re_ohm'], 100.0, atol=0.1)
        assert np.isclose(metrics['zin2_re_ohm'], 100.0, atol=0.1)


def test_tracker_model2_record():
    """Test zápisu běhu Modelu 2 do samostatné CSV a Markdown tabulky."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        res_dir = os.path.join(tmp_dir, "export")
        postpro_dir = os.path.join(tmp_dir, "postpro")
        os.makedirs(postpro_dir, exist_ok=True)

        # Syntetická farfield data pro LHCP
        ff_file = os.path.join(postpro_dir, "farfield-rE.csv")
        ff_data = np.array([[2.33, 1, 0.0, 0.0, 1.0, 0.0, 0.0, -1.0, 0.0, 0.0]])
        header_ff = "f (GHz), exc, theta (deg.), phi (deg.), r*Re{E_x}, r*Im{E_x}, r*Re{E_y}, r*Im{E_y}, r*Re{E_z}, r*Im{E_z}"
        np.savetxt(ff_file, ff_data, delimiter=',', header=header_ff)

        # Syntetická port-V a port-I data
        v_file = os.path.join(postpro_dir, "port-V.csv")
        i_file = os.path.join(postpro_dir, "port-I.csv")
        np.savetxt(v_file, np.array([[2.33, 10.0, 10.0, 0.0, 10.0, 10.0, 0.0]]), delimiter=',', header="f,v1,v1r,v1i,v2,v2r,v2i")
        np.savetxt(i_file, np.array([[2.33, 0.1, 0.1, 0.0, 0.1, 0.1, 0.0]]), delimiter=',', header="f,i1,i1r,i1i,i2,i2r,i2i")

        params = {
            'antenna_model': 2,
            'feed_inset_b': 3.0,
            'feed_inset_l': 2.5,
            'patch_L': 30.3,
            'port_impedance': 100.0,
        }

        row = record_run(params, output_dir=postpro_dir, run_name="test_m2", results_dir=res_dir)

        csv_path = os.path.join(res_dir, "sweep_results_model2.csv")
        md_path = os.path.join(res_dir, "sweep_results_model2.md")
        assert os.path.exists(csv_path), "CSV soubor pro Model 2 musí existovat"
        assert os.path.exists(md_path), "Markdown soubor pro Model 2 musí existovat"

        with open(csv_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        assert len(lines) == 2, "V CSV musí být záhlaví a 1 řádek dat"
        assert "run_name,inset_b_mm,inset_l_mm,patch_L_mm" in lines[0]
        assert "test_m2,3.00,2.50,30.30" in lines[1]
        assert row['Polarizace'] == "LHCP"


def test_tracker_model2_multiexc_superposition():
    """Test superpozice dálkového pole z více excitací (Port 1 + Port 2)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        from tracker import extract_farfield_metrics
        ff_file = os.path.join(tmp_dir, "farfield-rE.csv")
        # Excitation 1 (spodní port Ey): Ey = -1j, Ex = 0
        # Excitation 2 (levý port Ex): Ex = 1.0, Ey = 0
        ff_data = np.array([
            [2.33, 1, 0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0],
            [2.33, 2, 0.0, 0.0, 1.0, 0.0, 0.0,  0.0, 0.0, 0.0],
        ])
        header_ff = "f (GHz), exc, theta (deg.), phi (deg.), r*Re{E_x}, r*Im{E_x}, r*Re{E_y}, r*Im{E_y}, r*Re{E_z}, r*Im{E_z}"
        np.savetxt(ff_file, ff_data, delimiter=',', header=header_ff)

        metrics = extract_farfield_metrics(ff_file, target_freq=2.33)
        assert metrics['polarization'] == "LHCP", f"Polarizace musí být LHCP, je {metrics['polarization']}"
        assert metrics['axial_ratio_db'] < 0.1, f"AR pro čistou LHCP musí být < 0.1 dB, je {metrics['axial_ratio_db']}"
        assert metrics['e_lhcp'] > metrics['e_rhcp'] * 10, "LHCP složka musí výrazně dominovat"


def test_sweep_modes_pairs():
    """Test generování dvojic zanoření v režimech symmetric, single_fixed a grid."""
    # 1. Symmetric
    p_sym, _ = build_sweep_pairs("symmetric", insets=[1.0, 2.0, 3.0])
    assert p_sym == [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0)]

    # 2. Single Fixed (fixní levý)
    p_fixed_l, _ = build_sweep_pairs("single_fixed", insets=[1.0, 2.0], fixed_name="inset_l", fixed_val=2.5)
    assert p_fixed_l == [(1.0, 2.5), (2.0, 2.5)]

    # 3. Single Fixed (fixní spodní)
    p_fixed_b, _ = build_sweep_pairs("single_fixed", insets=[1.0, 2.0], fixed_name="inset_b", fixed_val=3.0)
    assert p_fixed_b == [(3.0, 1.0), (3.0, 2.0)]

    # 4. Grid (kartézský součin)
    p_grid, _ = build_sweep_pairs("grid", insets_b=[2.0, 3.0], insets_l=[1.0, 4.0])
    assert p_grid == [(2.0, 1.0), (2.0, 4.0), (3.0, 1.0), (3.0, 4.0)]


def test_tracker_model2_port_s_priority():
    """
    Test, že Model 2 prioritně čte data z port-S.csv a nevrací falešných -200 dB
    i když jsou přítomny soubory port-V.csv a port-I.csv.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        freqs = np.array([2.30, 2.32, 2.335, 2.340, 2.36])
        # Port 1 má rezonanci na 2.335 GHz s minimem -18.5 dB
        s11_db = np.array([-5.2, -10.1, -18.5, -12.3, -4.1])
        s11_deg = np.array([30.0, 15.0, 0.0, -15.0, -30.0])
        # Port 2 má rezonanci na 2.340 GHz s minimem -16.2 dB
        s22_db = np.array([-4.8, -9.5, -12.0, -16.2, -5.0])
        s22_deg = np.array([25.0, 12.0, -5.0, 0.0, -25.0])
        s21_db = np.array([-20.0, -22.0, -25.0, -24.0, -21.0])
        s21_deg = np.zeros_like(s21_db)
        s12_db = s21_db
        s12_deg = s21_deg

        s_mat = np.column_stack([freqs, s11_db, s11_deg, s21_db, s21_deg, s12_db, s12_deg, s22_db, s22_deg])
        s_file = os.path.join(tmp_dir, "port-S.csv")
        s_header = "f (GHz), |S[1][1]| (dB), arg(S[1][1]) (deg.), |S[2][1]| (dB), arg(S[2][1]) (deg.), |S[1][2]| (dB), arg(S[1][2]) (deg.), |S[2][2]| (dB), arg(S[2][2]) (deg.)"
        np.savetxt(s_file, s_mat, delimiter=',', header=s_header)

        # Přítomnost zavádějících port-V a port-I (kde poměr V_inc/I_inc = 100 Ohm dříve způsobil -200 dB)
        v_file = os.path.join(tmp_dir, "port-V.csv")
        i_file = os.path.join(tmp_dir, "port-I.csv")
        v_dummy = np.ones((len(freqs), 7)) * 10.0
        v_dummy[:, 0] = freqs
        i_dummy = np.ones((len(freqs), 7)) * 0.1
        i_dummy[:, 0] = freqs
        np.savetxt(v_file, v_dummy, delimiter=',', header="f, V_inc[1], Re{V[1]}, Im{V[1]}, V_inc[2], Re{V[2]}, Im{V[2]}")
        np.savetxt(i_file, i_dummy, delimiter=',', header="f, I_inc[1], Re{I[1]}, Im{I[1]}, I_inc[2], Re{I[2]}, Im{I[2]}")

        metrics = extract_s_parameters_model2(tmp_dir, z0=100.0)

        assert metrics['f0_b_GHz'] == 2.335, f"f0_b by měla být 2.335 GHz, je {metrics['f0_b_GHz']}"
        assert metrics['f0_l_GHz'] == 2.340, f"f0_l by měla být 2.340 GHz, je {metrics['f0_l_GHz']}"
        assert np.isclose(metrics['s11_min_dB'], -18.5, atol=0.1), f"S11 min nesmí být -200 dB! Je {metrics['s11_min_dB']}"
        assert np.isclose(metrics['s22_min_dB'], -16.2, atol=0.1), f"S22 min nesmí být -200 dB! Je {metrics['s22_min_dB']}"
        assert metrics['s11_min_dB'] > -50.0, "S11 min nesmí být -200 dB"
        assert metrics['s22_min_dB'] > -50.0, "S22 min nesmí být -200 dB"
        assert 's21_db' in metrics, "S21 by mělo být nalezeno v Palace matici"


def test_farfield_metrics_fgainmax_and_gain_max():
    """
    Test nalezení maximálního zisku LHCP a jeho frekvence (fGainMaxLhcp, Gain_max_LHCP)
    přes frekvenční sweep ve farfield-rE.csv.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        ff_file = os.path.join(tmp_dir, "farfield-rE.csv")

        # 4 frekvence: 2.30, 2.33 (rezonance), 2.35 (posunuté maximum záření zanořením), 2.38
        # Na 2.35 GHz je záření nejvyšší: Ex = 2.0, Ey = -2.0j
        # Na 2.33 GHz je záření střední: Ex = 1.0, Ey = -1.0j
        # Na 2.30 GHz je záření nízké: Ex = 0.5, Ey = -0.5j
        ff_rows = [
            # f, exc, theta, phi, rRe{Ex}, rIm{Ex}, rRe{Ey}, rIm{Ey}, rRe{Ez}, rIm{Ez}
            [2.30, 1, 0.0, 0.0, 0.5, 0.0, 0.0, -0.5, 0.0, 0.0],
            [2.33, 1, 0.0, 0.0, 1.0, 0.0, 0.0, -1.0, 0.0, 0.0],
            [2.35, 1, 0.0, 0.0, 2.0, 0.0, 0.0, -2.0, 0.0, 0.0],
            [2.38, 1, 0.0, 0.0, 0.8, 0.0, 0.0, -0.8, 0.0, 0.0],
        ]
        header_ff = "f (GHz), exc, theta (deg.), phi (deg.), r*Re{E_x}, r*Im{E_x}, r*Re{E_y}, r*Im{E_y}, r*Re{E_z}, r*Im{E_z}"
        np.savetxt(ff_file, np.array(ff_rows), delimiter=',', header=header_ff)

        # Vyhodnotíme s target_freq=2.33 (rezonance)
        metrics = extract_farfield_metrics(ff_file, target_freq=2.33)

        assert 'f_gain_max_lhcp_ghz' in metrics, "Klíč f_gain_max_lhcp_ghz musí být přítomen"
        assert 'gain_max_lhcp_dbi' in metrics, "Klíč gain_max_lhcp_dbi musí být přítomen"
        assert 'ar_at_max_gain_db' in metrics, "Klíč ar_at_max_gain_db musí být přítomen"

        assert metrics['f_gain_max_lhcp_ghz'] == 2.35, f"Frekvence maxima zisku musí být 2.35 GHz, je {metrics['f_gain_max_lhcp_ghz']}"
        assert metrics['gain_max_lhcp_dbi'] > metrics['gain_lhcp_dbi'], "Maximální zisk na 2.35 GHz musí být vyšší než zisk na 2.33 GHz"
        diff_gain = metrics['gain_max_lhcp_dbi'] - metrics['gain_lhcp_dbi']
        assert np.isclose(diff_gain, 20.0 * np.log10(2.0), atol=0.2), f"Rozdíl zisku při zdvojnásobení pole by měl být cca 6 dB, je {diff_gain:.2f} dB"
        assert metrics['ar_at_max_gain_db'] < 0.1, "Osový poměr na maximu zisku musí být < 0.1 dB pro ideální LHCP"
        assert metrics['polarization'] == "LHCP"


def test_tracker_model2_record_with_gain_max():
    """
    Test zápisu běhu Modelu 2 do tabulky včetně nových metrik fGainMaxLhcp a Gain_max_LHCP.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        res_dir = os.path.join(tmp_dir, "export")
        postpro_dir = os.path.join(tmp_dir, "postpro")
        os.makedirs(postpro_dir, exist_ok=True)

        # Port-S soubor s reálnými daty
        s_file = os.path.join(postpro_dir, "port-S.csv")
        s_data = np.array([
            [2.30, -5.0, 0.0, -20.0, 0.0, -20.0, 0.0, -5.0, 0.0],
            [2.33, -19.5, 0.0, -25.0, 0.0, -25.0, 0.0, -18.0, 0.0],
            [2.36, -6.0, 0.0, -20.0, 0.0, -20.0, 0.0, -6.0, 0.0],
        ])
        s_header = "f (GHz), |S[1][1]| (dB), arg(S[1][1]) (deg.), |S[2][1]| (dB), arg(S[2][1]) (deg.), |S[1][2]| (dB), arg(S[1][2]) (deg.), |S[2][2]| (dB), arg(S[2][2]) (deg.)"
        np.savetxt(s_file, s_data, delimiter=',', header=s_header)

        # Farfield s maximem zisku na 2.36 GHz
        ff_file = os.path.join(postpro_dir, "farfield-rE.csv")
        ff_data = np.array([
            [2.30, 1, 0.0, 0.0, 1.0, 0.0, 0.0, -1.0, 0.0, 0.0],
            [2.33, 1, 0.0, 0.0, 1.2, 0.0, 0.0, -1.2, 0.0, 0.0],
            [2.36, 1, 0.0, 0.0, 2.5, 0.0, 0.0, -2.5, 0.0, 0.0],
        ])
        header_ff = "f (GHz), exc, theta (deg.), phi (deg.), r*Re{E_x}, r*Im{E_x}, r*Re{E_y}, r*Im{E_y}, r*Re{E_z}, r*Im{E_z}"
        np.savetxt(ff_file, ff_data, delimiter=',', header=header_ff)

        params = {
            'antenna_model': 2,
            'feed_inset_b': 3.5,
            'feed_inset_l': 2.8,
            'patch_L': 30.3,
            'port_impedance': 100.0,
        }

        row = record_run(params, output_dir=postpro_dir, run_name="test_m2_gainmax", results_dir=res_dir)

        csv_path = os.path.join(res_dir, "sweep_results_model2.csv")
        md_path = os.path.join(res_dir, "sweep_results_model2.md")
        assert os.path.exists(csv_path)
        assert os.path.exists(md_path)

        with open(csv_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        header = lines[0].strip().split(',')
        data = lines[1].strip().split(',')

        assert 'fGainMaxLhcp [GHz]' in header, "Sloupec fGainMaxLhcp [GHz] musí být v hlavičce CSV"
        assert 'Gain_max_LHCP [dBi]' in header, "Sloupec Gain_max_LHCP [dBi] musí být v hlavičce CSV"

        f_gmax_idx = header.index('fGainMaxLhcp [GHz]')
        assert data[f_gmax_idx] == "2.360", f"fGainMaxLhcp musí být 2.360 GHz, je {data[f_gmax_idx]}"

        s11_idx = header.index('S11_min [dB]')
        assert float(data[s11_idx]) > -50.0, f"S11 min nesmí být -200 dB, je {data[s11_idx]}"
        assert data[s11_idx] == "-19.50"

        # Ověření výpisu tabulky
        print_summary_table_model2(csv_file=csv_path)


if __name__ == "__main__":
    tests = [
        test_rf_calculations,
        test_geometry_model2_properties,
        test_geometry_router,
        test_palace_builder_configs,
        test_tracker_model2_extraction,
        test_tracker_model2_record,
        test_tracker_model2_multiexc_superposition,
        test_sweep_modes_pairs,
        test_tracker_model2_port_s_priority,
        test_farfield_metrics_fgainmax_and_gain_max,
        test_tracker_model2_record_with_gain_max,
    ]
    passed = 0
    failed = 0
    print(f"Spouštím {len(tests)} jednotkových testů pro Model 2...")
    for t in tests:
        try:
            t()
            print(f"  [PASS] {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\nVýsledek: {passed} prošlo, {failed} selhalo.")
    if failed > 0:
        sys.exit(1)
