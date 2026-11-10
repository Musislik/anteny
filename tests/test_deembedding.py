"""
test_deembedding.py - Jednotkové testy pro analytický de-embedding impedančních skoků (Model 1, 2 i 3).
Ověřuje:
  1. Vlnové parametry mikropáskového vedení (calc_microstrip_propagation).
  2. Invertibilitu a přesnost de-embeddingu úseku přenosového vedení (deembed_transmission_line).
  3. Dvoustupňový kaskádní de-embedding Modelu 3 (calculate_deembedding_model3).
  4. Fallback chování pro Model 2 a Model 1.
  5. Vykreslení 2x2 diagnostického grafu (plot_impedance_deembedding).
"""

import os
import sys
import json
import shutil
import zipfile
from unittest.mock import patch, MagicMock
import pytest
import numpy as np
import pandas as pd

# Cesty k modulům projektu
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(TESTS_DIR, ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")

for p in (PROJECT_ROOT, SRC_DIR, SCRIPTS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from rf_calc import (
    calc_microstrip_propagation,
    deembed_transmission_line,
    calculate_deembedding_model3,
    synth_microstrip_w,
    calc_quarter_wave_length,
    DESIGN_FREQ_GHZ,
)
from postpro_utils import load_port_v_voltages
from plot_deembedding import plot_impedance_deembedding
from plot_s_parameters import plot_s_parameters
from plot_radiation_pattern import (
    compute_farfield_metrics,
    plot_radiation_pattern_2d,
    plot_radiation_pattern_3d,
)
import export_package


def test_microstrip_propagation_parameters():
    """Test vlnových parametrů pro 100 Ohm vedení a transformátor."""
    h = 1.52
    eps_r = 4.3
    tan_delta = 0.02

    # 1. Vnější 100 Ohm vedení (w ≈ 0.694 mm)
    w_100 = synth_microstrip_w(100.0, h, eps_r)
    z0, eps_eff, beta, alpha, gamma = calc_microstrip_propagation(w_100, h, eps_r, tan_delta, DESIGN_FREQ_GHZ)

    assert 98.0 <= z0 <= 102.0, f"Z0 by mělo být ~100 Ohm, je {z0:.2f}"
    assert 2.90 <= eps_eff <= 3.05, f"eps_eff by mělo být ~2.97, je {eps_eff:.3f}"
    assert beta > 0.08, f"beta by mělo být > 0.08 rad/mm, je {beta:.4f}"
    assert alpha > 0.0, f"alpha by mělo být kladné, je {alpha:.6f}"
    assert np.isclose(gamma.real, alpha)
    assert np.isclose(gamma.imag, beta)

    # 2. Vnitřní transformátor w_T = 0.42 mm
    w_T = 0.42
    z0_T, eps_eff_T, beta_T, alpha_T, gamma_T = calc_microstrip_propagation(w_T, h, eps_r, tan_delta, DESIGN_FREQ_GHZ)
    assert 115.0 <= z0_T <= 122.0, f"Z0_T by mělo být ~118.7 Ohm, je {z0_T:.2f}"
    assert 2.80 <= eps_eff_T <= 2.95, f"eps_eff_T by mělo být ~2.89, je {eps_eff_T:.3f}"

    # 3. Vektorový vstup frekvencí
    freqs = np.linspace(2.32, 2.345, 11)
    z0_arr, eps_eff_arr, beta_arr, alpha_arr, gamma_arr = calc_microstrip_propagation(w_100, h, eps_r, tan_delta, freqs)
    assert len(beta_arr) == 11
    assert len(gamma_arr) == 11
    assert np.all(np.diff(beta_arr) > 0), "Fázová konstanta beta musí monotónně růst s frekvencí"


def test_transmission_line_deembedding_invertibility():
    """Test dokonalé invertibility de-embeddingu napříč úsekem vedení."""
    h = 1.52
    eps_r = 4.3
    tan_delta = 0.02
    w_100 = 0.694
    length = 18.66

    z0, _, _, _, gamma = calc_microstrip_propagation(w_100, h, eps_r, tan_delta, DESIGN_FREQ_GHZ)

    # Komplexní zátěž flíčku
    z_load = 140.0 + 25.0j

    # Dopředná transformace k portu
    tanh_gl = np.tanh(gamma * length)
    z_in = z0 * (z_load + z0 * tanh_gl) / (z0 + z_load * tanh_gl)

    # Zpětný de-embedding (odečtení délky vedení)
    z_load_recovered = deembed_transmission_line(z_in, z0, gamma, length)

    diff = abs(z_load_recovered - z_load)
    assert diff < 1e-10, f"De-embedding musí zrekonstruovat zátěž s vysokou přesností (chyba = {diff:.2e})"

    # Test nulové délky (musí vrátit identickou hodnotu)
    z_same = deembed_transmission_line(z_in, z0, gamma, 0.0)
    assert np.isclose(z_same, z_in)

    # Test přizpůsobené zátěže (Z_L = Z0 -> Z_in = Z0 pro libovolnou délku)
    z_matched = deembed_transmission_line(z0, z0, gamma, 50.0)
    assert np.isclose(z_matched, z0)


def test_quarter_wave_transformer_cascade_model3():
    """Test kompletní kaskády dvoustupňového přizpůsobení Modelu 3 (RP1 -> RP2 -> RP3)."""
    h = 1.52
    eps_r = 4.3
    tan_delta = 0.00  # Pro ideální test bezztrátového čtvrtvlnného přenosu
    f_c = DESIGN_FREQ_GHZ

    # Cílová impedance na vstupu flíčku v zářezu
    r_patch = 140.0

    # Čtvrtvlnný transformátor
    z_T = np.sqrt(100.0 * r_patch)  # ~118.32 Ohm
    w_T = synth_microstrip_w(z_T, h, eps_r)
    z0_T, eps_eff_T, beta_T, _, gamma_T = calc_microstrip_propagation(w_T, h, eps_r, tan_delta, f_c)
    l_T = calc_quarter_wave_length(f_c, eps_eff_T)

    # Vnější 100 Ohm mikropásek
    w_100 = synth_microstrip_w(100.0, h, eps_r)
    z0_feed, eps_eff_feed, beta_feed, _, gamma_feed = calc_microstrip_propagation(w_100, h, eps_r, tan_delta, f_c)
    l_100 = 20.0

    # Na RP3 (flíček): Z = 140 Ohm
    # Na RP2 (svorka transformátoru): Z = Z_T^2 / 140 ≈ 100 Ohm (s přesností reálného mikropásku)
    t_T = np.tanh(gamma_T * l_T)
    z_rp2 = z0_T * (r_patch + z0_T * t_T) / (z0_T + r_patch * t_T)
    assert abs(z_rp2.real - 100.0) < 0.5, f"Z_RP2 by mělo být ~100 Ohm, je {z_rp2.real:.3f}"

    # Na RP1 (port): po 100 Ohm vedení je Z stále ~100 Ohm
    t_100 = np.tanh(gamma_feed * l_100)
    z_rp1 = z0_feed * (z_rp2 + z0_feed * t_100) / (z0_feed + z_rp2 * t_100)
    assert abs(z_rp1.real - 100.0) < 0.5, f"Z_RP1 by mělo být ~100 Ohm, je {z_rp1.real:.3f}"

    # De-embedding RP1 -> RP2
    z_deembed_rp2 = deembed_transmission_line(z_rp1, z0_feed, gamma_feed, l_100)
    assert abs(z_deembed_rp2.real - 100.0) < 0.5

    # De-embedding RP2 -> RP3
    z_deembed_rp3 = deembed_transmission_line(z_deembed_rp2, z0_T, gamma_T, l_T)
    assert abs(z_deembed_rp3.real - 140.0) < 1e-6, f"Z_RP3 po de-embeddingu by mělo být 140 Ohm, je {z_deembed_rp3.real:.3f}"


def test_calculate_deembedding_model3_interface():
    """Test funkce calculate_deembedding_model3 pro Model 3, Model 2 i Model 1."""
    freqs = np.linspace(2.32, 2.345, 6)
    # Syntetické S11 a S22 s rezonancí kolem 2.333 GHz
    s11 = 0.05 * np.ones_like(freqs, dtype=complex)
    s22 = 0.04 * np.ones_like(freqs, dtype=complex)

    params_m3 = {
        'antenna_model': 3,
        'patch_L': 28.8,
        'patch_W': 28.8,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'trans_w': 0.42,
        'trans_l': 18.9,
        'feed_len_b': 37.5,
        'feed_len_l': 18.8,
        'port_impedance': 100.0,
    }

    res_m3 = calculate_deembedding_model3(freqs, s11, s22, params=params_m3)
    assert res_m3['model'] == 3
    assert 'rp1' in res_m3 and 'rp2' in res_m3 and 'rp3' in res_m3
    assert len(res_m3['rp1']['z1']) == 6
    assert len(res_m3['rp3']['z1']) == 6
    assert res_m3['rp1']['z2'] is not None
    assert res_m3['rp3']['z0_ref'] > 130.0  # Cíl kolem 140 Ohm

    # Test pro Model 2 (kde l_T = 0 a RP2 == RP3)
    params_m2 = {
        'antenna_model': 2,
        'patch_L': 28.8,
        'patch_W': 28.8,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'feed_len_b': 30.0,
        'feed_len_l': 15.0,
        'port_impedance': 100.0,
    }
    res_m2 = calculate_deembedding_model3(freqs, s11, s22, params=params_m2)
    assert res_m2['model'] == 2
    assert np.allclose(res_m2['rp2']['z1'], res_m2['rp3']['z1']), "U Modelu 2 musí RP2 splývat s RP3"
    assert res_m2['rp3']['z0_ref'] == 100.0

    # Test pro Model 1 (bezpečný průchod)
    params_m1 = {
        'antenna_model': 1,
        'port_impedance': 50.0,
    }
    res_m1 = calculate_deembedding_model3(freqs, s11, None, params=params_m1)
    assert res_m1['model'] == 1
    assert res_m1['rp1']['z0_ref'] == 50.0


def test_plot_impedance_deembedding_synthetic(tmp_path):
    """Test generování 2x2 grafu de-embeddingu na syntetických datech."""
    test_dir = str(tmp_path / "test_sim")
    os.makedirs(test_dir, exist_ok=True)

    # Vytvoření syntetického port-S.csv
    freqs = np.linspace(2.320, 2.345, 11)
    s_csv_path = os.path.join(test_dir, "port-S.csv")
    with open(s_csv_path, "w", encoding="utf-8") as f:
        f.write("f (GHz),|S[1][1]| (dB),argbit(S[1][1]) (deg.),|S[2][2]| (dB),arg(S[2][2]) (deg.)\n")
        for fq in freqs:
            # Simulace rezonance
            s11_val = -25.0 + 10.0 * (fq - 2.3325)**2 * 1000
            s22_val = -24.0 + 10.0 * (fq - 2.3325)**2 * 1000
            f.write(f"{fq:.6e},{s11_val:.4e},-145.0,{s22_val:.4e},-140.0\n")

    # Vytvoření params.json
    params = {
        'antenna_model': 3,
        'patch_L': 28.8,
        'patch_W': 28.8,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'trans_w': 0.42,
        'feed_len_b': 37.5,
        'feed_len_l': 18.8,
        'port_impedance': 100.0,
    }
    with open(os.path.join(test_dir, "params.json"), "w", encoding="utf-8") as f:
        json.dump(params, f)

    out_png = os.path.join(test_dir, "graf_impedance_skoky.png")
    result_path = plot_impedance_deembedding(test_dir, params=params, output_png=out_png)

    assert result_path is not None
    assert os.path.exists(out_png)
    assert os.path.getsize(out_png) > 10000, "Vygenerovaný graf musí mít validní velikost"


def test_plot_impedance_deembedding_two_port_split_layout(tmp_path):
    """Test generování 2-portového de-embedding grafu v rozložení split a dílčích RP grafů."""
    test_dir = str(tmp_path / "sim_2port")
    os.makedirs(test_dir, exist_ok=True)

    # Syntetický 2-portový port-S.csv (S11, S21, S12, S22 včetně fází)
    freqs = np.linspace(2.320, 2.345, 11)
    s_csv_path = os.path.join(test_dir, "port-S.csv")
    with open(s_csv_path, "w", encoding="utf-8") as f:
        f.write(
            "f (GHz),|S[1][1]| (dB),arg(S[1][1]) (deg.),"
            "|S[2][1]| (dB),arg(S[2][1]) (deg.),"
            "|S[1][2]| (dB),arg(S[1][2]) (deg.),"
            "|S[2][2]| (dB),arg(S[2][2]) (deg.)\n"
        )
        for fq in freqs:
            delta = (fq - 2.3325) / 0.0125
            s11_db = -24.0 + 18.0 * (delta ** 2)
            s11_deg = -45.0 * delta
            s22_db = -22.0 + 16.0 * (delta ** 2)
            s22_deg = -40.0 * delta
            s21_db = -18.5 - 1.5 * (delta ** 2)
            s21_deg = -120.0 + 25.0 * delta
            s12_db = s21_db
            s12_deg = s21_deg
            f.write(
                f"{fq:.6e},{s11_db:.4e},{s11_deg:.4e},"
                f"{s21_db:.4e},{s21_deg:.4e},"
                f"{s12_db:.4e},{s12_deg:.4e},"
                f"{s22_db:.4e},{s22_deg:.4e}\n"
            )

    params = {
        'antenna_model': 3,
        'driven_port': 'all',
        'patch_L': 28.8,
        'patch_W': 28.8,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'tan_delta': 0.02,
        'trans_w': 0.42,
        'feed_inset_b': 2.5,
        'feed_inset_l': 2.5,
        'inset_gap_b': 0.5,
        'inset_gap_l': 0.5,
        'feed_len_b': 37.5,
        'feed_len_l': 18.8,
        'port_impedance': 100.0,
    }
    with open(os.path.join(test_dir, "params.json"), "w", encoding="utf-8") as f:
        json.dump(params, f)

    result_path = plot_impedance_deembedding(test_dir, params=params, layout="split")

    out_png = os.path.join(test_dir, "graf_impedance_skoky.png")
    assert result_path is not None
    assert os.path.abspath(result_path) == os.path.abspath(out_png)
    assert os.path.exists(out_png)
    assert os.path.getsize(out_png) > 10000

    for rp_name in ("graf_impedance_RP1.png", "graf_impedance_RP2.png", "graf_impedance_RP3.png"):
        rp_png = os.path.join(test_dir, "grafy", rp_name)
        assert os.path.exists(rp_png), f"Dílčí graf {rp_name} musí existovat"
        assert os.path.getsize(rp_png) > 10000, f"Dílčí graf {rp_name} musí mít nenulovou velikost"


def test_plot_impedance_deembedding_single_port_rules(tmp_path):
    """Test pravidel 1 a 2 pro buzení pouze jednoho portu (Port 1 a Port 2)."""
    test_dir_p1 = str(tmp_path / "sim_p1")
    os.makedirs(test_dir_p1, exist_ok=True)

    freqs = np.linspace(2.320, 2.345, 11)
    s_csv_p1 = os.path.join(test_dir_p1, "port-S.csv")
    with open(s_csv_p1, "w", encoding="utf-8") as f:
        f.write("f (GHz),|S[1][1]| (dB),arg(S[1][1]) (deg.),|S[2][1]| (dB),arg(S[2][1]) (deg.)\n")
        for fq in freqs:
            f.write(f"{fq:.6e},-22.5,-140.0,-15.5,-120.0\n")

    p1_params = {'antenna_model': 3, 'driven_port': '1', 'patch_L': 28.8, 'patch_W': 28.8, 'port_impedance': 100.0}
    with open(os.path.join(test_dir_p1, "params.json"), "w", encoding="utf-8") as f:
        json.dump(p1_params, f)

    out_p1 = os.path.join(test_dir_p1, "graf_impedance_skoky.png")
    res_p1 = plot_impedance_deembedding(test_dir_p1, params=p1_params, output_png=out_p1)
    assert res_p1 is not None
    assert os.path.exists(out_p1)
    assert os.path.getsize(out_p1) > 10000

    # Port 2 buzení
    test_dir_p2 = str(tmp_path / "sim_p2")
    os.makedirs(test_dir_p2, exist_ok=True)
    s_csv_p2 = os.path.join(test_dir_p2, "port-S.csv")
    with open(s_csv_p2, "w", encoding="utf-8") as f:
        f.write("f (GHz),|S[1][2]| (dB),arg(S[1][2]) (deg.),|S[2][2]| (dB),arg(S[2][2]) (deg.)\n")
        for fq in freqs:
            f.write(f"{fq:.6e},-16.0,-125.0,-24.0,-142.0\n")

    p2_params = {'antenna_model': 3, 'driven_port': '2', 'patch_L': 29.2, 'patch_W': 29.2, 'port_impedance': 100.0}
    with open(os.path.join(test_dir_p2, "params.json"), "w", encoding="utf-8") as f:
        json.dump(p2_params, f)

    out_p2 = os.path.join(test_dir_p2, "graf_impedance_skoky.png")
    res_p2 = plot_impedance_deembedding(test_dir_p2, params=p2_params, output_png=out_p2)
    assert res_p2 is not None
    assert os.path.exists(out_p2)
    assert os.path.getsize(out_p2) > 10000


def test_plot_s_parameters_rules(tmp_path):
    """Test generování graf_S_parametry.png pro buzení 1 portem i oběma porty."""
    test_dir = str(tmp_path / "sim_sparams")
    os.makedirs(test_dir, exist_ok=True)

    freqs = np.linspace(2.320, 2.345, 11)
    s_csv = os.path.join(test_dir, "port-S.csv")
    with open(s_csv, "w", encoding="utf-8") as f:
        f.write("f (GHz),|S[1][1]| (dB),arg(S[1][1]) (deg.),|S[2][2]| (dB),arg(S[2][2]) (deg.),|S[2][1]| (dB)\n")
        for fq in freqs:
            f.write(f"{fq:.6e},-20.0,-140.0,-18.0,-135.0,-16.5\n")

    out_png = os.path.join(test_dir, "graf_S_parametry.png")
    res = plot_s_parameters(test_dir, output_png=out_png)
    assert res is not None
    assert os.path.exists(out_png)
    assert os.path.getsize(out_png) > 10000


def test_port_v_header_order_and_plots(tmp_path):
    """Test načtení port-V.csv v pořadí [f, V_inc[1], Re{V[1]}, Im{V[1]}, V_inc[2], Re{V[2]}, Im{V[2]}] a vykreslení grafů."""
    sim_2p = tmp_path / "portv_2p"
    sim_2p.mkdir()
    freqs = np.linspace(2.320, 2.345, 7)

    # 1. Obouportové buzení (V_inc[1]=10, V_inc[2]=10)
    v_2p_path = sim_2p / "port-V.csv"
    expected_s11 = 0.10 - 0.05j
    expected_s22 = -0.08 + 0.04j
    with open(v_2p_path, "w", encoding="utf-8") as f:
        f.write("f (GHz), V_inc[1], Re{V[1]}, Im{V[1]}, V_inc[2], Re{V[2]}, Im{V[2]}\n")
        for fq in freqs:
            v1 = 10.0 * (1.0 + expected_s11)
            v2 = 10.0 * (1.0 + expected_s22)
            f.write(f"{fq:.6e}, 10.0, {v1.real:.6f}, {v1.imag:.6f}, 10.0, {v2.real:.6f}, {v2.imag:.6f}\n")

    f_loaded, s11_c, s22_c, s21_c, s12_c = load_port_v_voltages(str(v_2p_path))
    assert f_loaded is not None and len(f_loaded) == len(freqs)
    assert s11_c is not None and np.allclose(s11_c, expected_s11, atol=1e-6)
    assert s22_c is not None and np.allclose(s22_c, expected_s22, atol=1e-6)
    assert s21_c is None and s12_c is None

    # Vykreslení grafů čistě z port-V.csv (bez port-S.csv)
    params_m3 = {
        'antenna_model': 3,
        'patch_L': 28.8,
        'patch_W': 28.8,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'trans_w': 0.42,
        'feed_len_b': 37.5,
        'feed_len_l': 18.8,
        'port_impedance': 100.0,
    }
    with open(sim_2p / "params.json", "w", encoding="utf-8") as f:
        json.dump(params_m3, f)

    out_s = sim_2p / "graf_S_parametry.png"
    res_s = plot_s_parameters(str(sim_2p), output_png=str(out_s), params=params_m3)
    assert res_s is not None and out_s.exists() and out_s.stat().st_size > 10000

    out_deemb = sim_2p / "graf_impedance_skoky.png"
    res_d = plot_impedance_deembedding(str(sim_2p), params=params_m3, output_png=str(out_deemb))
    assert res_d is not None and out_deemb.exists() and out_deemb.stat().st_size > 10000

    # 2. Jednoportové buzení Port 1 (V_inc[2] == 0) ve stejném 7-sloupcovém rozložení
    sim_1p = tmp_path / "portv_1p"
    sim_1p.mkdir()
    v_1p_path = sim_1p / "port-V.csv"
    expected_s21 = -0.12 + 0.06j
    with open(v_1p_path, "w", encoding="utf-8") as f:
        f.write("f (GHz), V_inc[1], Re{V[1]}, Im{V[1]}, V_inc[2], Re{V[2]}, Im{V[2]}\n")
        for fq in freqs:
            v1 = 10.0 * (1.0 + expected_s11)
            v2 = 10.0 * expected_s21
            f.write(f"{fq:.6e}, 10.0, {v1.real:.6f}, {v1.imag:.6f}, 0.0, {v2.real:.6f}, {v2.imag:.6f}\n")

    _, s11_1p, s22_1p, s21_1p, s12_1p = load_port_v_voltages(str(v_1p_path))
    assert s11_1p is not None and np.allclose(s11_1p, expected_s11, atol=1e-6)
    assert s21_1p is not None and np.allclose(s21_1p, expected_s21, atol=1e-6)
    assert s22_1p is None and s12_1p is None


def test_plot_impedance_deembedding_model1_50ohm(tmp_path):
    """Test de-embedding grafu pro Model 1 (1 port, 50 Ohm)."""
    sim_m1 = tmp_path / "sim_model1"
    sim_m1.mkdir()

    freqs = np.linspace(2.320, 2.345, 9)
    with open(sim_m1 / "port-S.csv", "w", encoding="utf-8") as f:
        f.write("f (GHz),|S[1][1]| (dB),arg(S[1][1]) (deg.)\n")
        for fq in freqs:
            s11_db = -18.0 + 10.0 * ((fq - 2.3325) / 0.0125) ** 2
            f.write(f"{fq:.6e},{s11_db:.4e},-135.0\n")

    params_m1 = {
        'antenna_model': 1,
        'patch_L': 30.3,
        'patch_W': 30.3,
        'port_impedance': 50.0,
    }
    with open(sim_m1 / "params.json", "w", encoding="utf-8") as f:
        json.dump(params_m1, f)

    out_png = sim_m1 / "graf_impedance_skoky.png"
    res = plot_impedance_deembedding(str(sim_m1), output_png=str(out_png))
    assert res is not None and out_png.exists() and out_png.stat().st_size > 10000
    for rp_name in ("graf_impedance_RP1.png", "graf_impedance_RP2.png", "graf_impedance_RP3.png"):
        rp_png = sim_m1 / "grafy" / rp_name
        assert rp_png.exists() and rp_png.stat().st_size > 10000


def test_plot_radiation_pattern_multi_exc(tmp_path):
    """Test 2D a 3D vyzařovacího diagramu na syntetickém multi-excitačním farfield-rE.csv (exc=1 a exc=2)."""
    ff_dir = tmp_path / "sim_farfield"
    ff_dir.mkdir()
    ff_csv = ff_dir / "farfield-rE.csv"

    thetas = np.arange(0.0, 181.0, 30.0)
    phis = np.arange(0.0, 360.0, 45.0)
    f_val = 2.3325

    rows = []
    for exc in (1, 2):
        for th in thetas:
            amp = 0.35 + 0.65 * np.cos(np.deg2rad(th) / 2.0)
            for ph in phis:
                if exc == 1:
                    # Port 1: Ey = -j * amp
                    ex_re, ex_im, ey_re, ey_im = 0.0, 0.0, 0.0, -amp
                else:
                    # Port 2: Ex = +amp
                    ex_re, ex_im, ey_re, ey_im = amp, 0.0, 0.0, 0.0
                rows.append([f_val, exc, th, ph, ex_re, ex_im, ey_re, ey_im, 0.0, 0.0])

    header_ff = (
        "f (GHz), exc, theta (deg.), phi (deg.), "
        "r*Re{E_x}, r*Im{E_x}, r*Re{E_y}, r*Im{E_y}, r*Re{E_z}, r*Im{E_z}"
    )
    np.savetxt(ff_csv, np.array(rows), delimiter=",", header=header_ff, comments="")

    df = pd.read_csv(ff_csv)
    metrics = compute_farfield_metrics(df)
    assert len(metrics['th_deg']) == len(thetas) * len(phis)
    zenith_mask = np.isclose(metrics['th_deg'], 0.0)
    assert np.all(metrics['ar_db'][zenith_mask] < 0.1)

    out_2d = ff_dir / "vyzarovaci_diagram_2d.png"
    out_3d = ff_dir / "vyzarovaci_diagram_3d.png"
    plot_radiation_pattern_2d(str(ff_dir), freq_target=f_val, output_png=str(out_2d))
    plot_radiation_pattern_3d(str(ff_dir), freq_target=f_val, output_png=str(out_3d))

    assert out_2d.exists() and out_2d.stat().st_size > 10000
    assert out_3d.exists() and out_3d.stat().st_size > 10000
    for sub_png in ("vyzarovaci_diagram_rez_XZ.png", "vyzarovaci_diagram_rez_YZ.png", "graf_osovy_pomer_AR.png"):
        p = ff_dir / "grafy" / sub_png
        assert p.exists() and p.stat().st_size > 10000


def test_export_paraview_package_cwd_and_rf_calc(tmp_path):
    """Test export_paraview_package: obnovení CWD při prázdném i platném běhu a přítomnost rf_calc.py v ZIPu."""
    fake_root = tmp_path / "proj"
    fake_src = fake_root / "src"
    fake_data = tmp_path / "data"
    fake_export = tmp_path / "export"
    caller_cwd = tmp_path / "caller"

    fake_src.mkdir(parents=True)
    fake_data.mkdir()
    fake_export.mkdir()
    caller_cwd.mkdir()

    for mod_name in ("rf_calc.py", "postpro_utils.py"):
        shutil.copy2(os.path.join(SRC_DIR, mod_name), fake_src / mod_name)

    orig_cwd = os.getcwd()
    try:
        os.chdir(str(caller_cwd))
        with patch.object(export_package, "load_env", return_value=(str(fake_root), str(fake_data))), \
             patch.object(export_package, "get_export_dir", return_value=str(fake_export)), \
             patch.object(export_package, "ensure_paraview_linked", return_value=None):
            # 1. Prázdná data -> vrací False a obnoví CWD
            res_empty = export_package.export_paraview_package(output_name="empty_pkg")
            assert res_empty is False
            assert os.path.realpath(os.getcwd()) == os.path.realpath(str(caller_cwd))

            # 2. Platný běh -> vrací True, obnoví CWD a ZIP obsahuje rf_calc.py
            postpro_dir = fake_data / "postpro"
            postpro_dir.mkdir()
            with open(postpro_dir / "port-S.csv", "w", encoding="utf-8") as f:
                f.write("f (GHz),|S[1][1]| (dB),arg(S[1][1]) (deg.)\n")
                f.write("2.330000e+00,-20.0,-140.0\n")
                f.write("2.335000e+00,-22.0,-145.0\n")
            with open(fake_data / "params.json", "w", encoding="utf-8") as f:
                json.dump({'antenna_model': 1, 'port_impedance': 50.0}, f)

            res_valid = export_package.export_paraview_package(output_name="valid_pkg")
            assert res_valid is True
            assert os.path.realpath(os.getcwd()) == os.path.realpath(str(caller_cwd))

            zip_path = fake_export / "valid_pkg.zip"
            assert zip_path.exists()
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
            assert "rf_calc.py" in names
            assert "postpro_utils.py" in names
    finally:
        os.chdir(orig_cwd)


def test_plot_efield_mocked_pyvista(tmp_path):
    """Test plot_efield.plot_e_field s mockovaným pyvista: prostřední Cycle*/data.pvtu, rodičovský adresář a close()."""
    data_dir = tmp_path / "data"
    driven_dir = data_dir / "postpro" / "paraview" / "driven_boundary"
    for cname in ("Cycle000001", "Cycle000002", "Cycle000003"):
        cdir = driven_dir / cname
        cdir.mkdir(parents=True)
        (cdir / "data.pvtu").write_text("<VTKFile/>", encoding="utf-8")

    expected_pvtu = str(driven_dir / "Cycle000002" / "data.pvtu")
    output_img = tmp_path / "nested_out" / "sub" / "efield.png"
    assert not output_img.parent.exists()

    fake_pv = MagicMock()
    fake_mesh = MagicMock()
    fake_mesh.point_data = {"E_real": np.zeros((4, 3))}
    fake_pv.read.return_value = fake_mesh
    fake_plotter = MagicMock()
    fake_pv.Plotter.return_value = fake_plotter

    with patch.dict(sys.modules, {"pyvista": fake_pv}):
        sys.modules.pop("plot_efield", None)
        import plot_efield
        try:
            with patch.object(plot_efield, "load_env", return_value=(str(tmp_path), str(data_dir))), \
                 patch.object(plot_efield, "ensure_paraview_linked", return_value=None):
                plot_efield.plot_e_field(vtu_file=None, output_image=str(output_img))

                fake_pv.read.assert_called_once_with(expected_pvtu)
                fake_pv.Plotter.assert_called_once_with(off_screen=True)
                assert output_img.parent.is_dir()
                fake_plotter.screenshot.assert_called_once_with(str(output_img))
                fake_plotter.close.assert_called_once()

                # Ověření close() i při chybě screenshot()
                fake_plotter.reset_mock()
                fake_plotter.screenshot.side_effect = RuntimeError("render error")
                try:
                    plot_efield.plot_e_field(vtu_file=None, output_image=str(output_img))
                    assert False, "Měla být vyvolána výjimka RuntimeError"
                except RuntimeError:
                    pass
                fake_plotter.close.assert_called_once()
        finally:
            sys.modules.pop("plot_efield", None)


if __name__ == "__main__":
    pytest.main(["-v", __file__])
