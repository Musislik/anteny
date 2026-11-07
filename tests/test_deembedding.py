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
import shutil
import tempfile
import json
import pytest
import numpy as np

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
from plot_deembedding import plot_impedance_deembedding


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


def test_plot_impedance_deembedding_existing_export():
    """Test generování de-embedding grafu na reálném exportu antena3_1_1."""
    export_dir = os.path.join(PROJECT_ROOT, "export", "antena3_1_1")
    if os.path.exists(export_dir) and (os.path.exists(os.path.join(export_dir, "port-S.csv")) or os.path.exists(os.path.join(export_dir, "port-V.csv"))):
        out_png = os.path.join(export_dir, "test_deembedding_check.png")
        try:
            res = plot_impedance_deembedding(export_dir, output_png=out_png)
            assert res is not None
            assert os.path.exists(out_png)
            assert os.path.getsize(out_png) > 10000
        finally:
            if os.path.exists(out_png):
                os.remove(out_png)


if __name__ == "__main__":
    pytest.main(["-v", __file__])
