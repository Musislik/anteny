"""
test_gain_plot.py - Testy pro výpočet zisku, směrovosti, osového poměru (AR),
potlačení křížové polarizace (XPD) a generování 2-panelového grafu graf_zisk_frekvence.png.
"""

import os
import sys
import shutil
import tempfile
import numpy as np
import pandas as pd
import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(TESTS_DIR, ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
for p in (PROJECT_ROOT, SRC_DIR, SCRIPTS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from plot_gain_frequency import (
    find_farfield_csv,
    calculate_gain_frequency,
    plot_gain_frequency,
)
from rf_calc import ETA_0, DESIGN_FREQ_GHZ


def test_find_farfield_csv():
    """Ověření vyhledání farfield-rE.csv v různých úrovních adresářové struktury."""
    # 1. Přímá cesta
    p1 = find_farfield_csv(os.path.join(PROJECT_ROOT, "data", "postpro"))
    assert p1 is not None and os.path.exists(p1)
    assert p1.endswith("farfield-rE.csv")

    # 2. Cesta z nadřazené složky data
    p2 = find_farfield_csv(os.path.join(PROJECT_ROOT, "data"))
    assert p2 is not None and os.path.exists(p2)

    # 3. Neexistující složka
    assert find_farfield_csv("non_existent_directory_xyz") is None


def test_calculate_gain_frequency_real_data():
    """Ověření výpočtu zisku a vyzařovacích parametrů na reálných datech z AMR=1 simulace."""
    csv_path = os.path.join(PROJECT_ROOT, "data", "postpro", "farfield-rE.csv")
    if not os.path.exists(csv_path):
        pytest.skip("Soubor data/postpro/farfield-rE.csv není přítomen.")

    res = calculate_gain_frequency(csv_path, num_ports=2, design_freq=2.3325)

    freqs = res['freqs']
    assert len(freqs) >= 20
    assert np.isclose(freqs.min(), 2.320, atol=1e-3)
    assert np.isclose(freqs.max(), 2.345, atol=1e-3)

    # Kontrola fyzikálních vztahů:
    # 1. Hlavní polarizace (LHCP) musí dominovat nad RHCP
    assert np.all(res['g_lhcp'] > res['g_rhcp'])
    assert np.all(res['xpd_db'] > 20.0)  # XPD > 20 dB napříč celým pásmem

    # 2. Celkový zisk G_tot musí být roven nebo mírně vyšší než G_LHCP
    assert np.all(res['g_tot'] >= res['g_lhcp'])
    assert np.all(res['g_tot'] <= res['g_lhcp'] + 0.1)  # zanedbatelná RHCP složka

    # 3. Směrovost musí být vyšší než zisk (kvůli ztrátám v dielektriku a mědi, eta_rad < 100 %)
    assert np.all(res['d_lhcp'] > res['g_lhcp'])
    assert np.all(res['d_tot'] > res['g_tot'])

    # 4. Hodnoty na návrhové frekvenci 2.3325 GHz
    dm = res['design_metrics']
    assert 2.0 <= dm['g_lhcp_dbi'] <= 2.6
    assert 2.0 <= dm['g_tot_dbi'] <= 2.6
    assert dm['g_rhcp_dbi'] < -15.0
    assert 7.0 <= dm['d_lhcp_dbi'] <= 8.5
    assert 25.0 <= dm['eta_rad_pct'] <= 35.0  # FR4 ztráty ~ 29 %
    assert 0.5 <= dm['ar_db'] <= 2.0         # Excelentní kruhová polarizace AR < 2 dB (mez je 3 dB)
    assert dm['xpd_db'] >= 21.0

    # 5. Maximum zisku
    assert 2.325 <= res['f_gain_max_lhcp_ghz'] <= 2.335
    assert 2.2 <= res['gain_max_lhcp_dbi'] <= 2.5


def test_calculate_gain_frequency_synthetic_pure_lhcp():
    """Syntetický test: dokonale kruhová LHCP vlna v ose (AR = 0 dB, nekonečné XPD)."""
    # Ex = 1.0, Ey = -1.0j -> Ex + j*Ey = 2.0 -> E_LHCP = sqrt(2), E_RHCP = 0
    # U_LHCP = 2 / (2 * ETA_0) = 1 / ETA_0
    # P_in = 1.0 W
    # G_LHCP = 10 * log10(4*pi / ETA_0)
    data = [
        # f, exc, theta, phi, Re(Ex), Im(Ex), Re(Ey), Im(Ey), Re(Ez), Im(Ez)
        [2.3325, 1, 0.0, 0.0, 1.0, 0.0, 0.0, -1.0, 0.0, 0.0]
    ]
    df = pd.DataFrame(data, columns=[
        'f', 'exc', 'theta', 'phi', 'ReEx', 'ImEx', 'ReEy', 'ImEy', 'ReEz', 'ImEz'
    ])

    res = calculate_gain_frequency(df, p_in=1.0, design_freq=2.3325)

    expected_g_lin = 4.0 * np.pi * (1.0 / ETA_0) / 1.0
    expected_g_dbi = 10.0 * np.log10(expected_g_lin)

    assert np.isclose(res['g_lhcp'][0], expected_g_dbi, atol=1e-4)
    assert np.isclose(res['g_tot'][0], expected_g_dbi, atol=1e-4)
    assert np.isclose(res['ar_db'][0], 0.0, atol=1e-4)  # Dokonalá kruhová polarizace
    assert res['xpd_db'][0] > 100.0                     # Zanedbatelná RHCP složka


def test_calculate_gain_frequency_synthetic_linear():
    """Syntetický test: lineárně polarizovaná vlna (Ex = 1, Ey = 0) -> E_LHCP = E_RHCP -> XPD = 0 dB, AR -> inf."""
    data = [
        [2.3325, 1, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    ]
    df = pd.DataFrame(data, columns=[
        'f', 'exc', 'theta', 'phi', 'ReEx', 'ImEx', 'ReEy', 'ImEy', 'ReEz', 'ImEz'
    ])

    res = calculate_gain_frequency(df, p_in=1.0, design_freq=2.3325)

    # U lineární polarizace se výkon dělí přesně napůl mezi LHCP a RHCP:
    # G_LHCP = G_RHCP = G_tot - 3.01 dB
    assert np.isclose(res['g_lhcp'][0], res['g_rhcp'][0], atol=1e-5)
    assert np.isclose(res['g_lhcp'][0], res['g_tot'][0] - 10.0 * np.log10(2.0), atol=1e-5)
    assert np.isclose(res['xpd_db'][0], 0.0, atol=1e-5)
    assert res['ar_db'][0] > 100.0  # Nekonečný osový poměr pro lineární polarizaci


def test_plot_gain_frequency_generation(tmp_path):
    """Ověření generování PNG souborů funkcí plot_gain_frequency."""
    csv_path = os.path.join(PROJECT_ROOT, "data", "postpro", "farfield-rE.csv")
    if not os.path.exists(csv_path):
        pytest.skip("Soubor data/postpro/farfield-rE.csv není přítomen.")

    out_png = tmp_path / "test_graf_zisk.png"
    res = plot_gain_frequency(os.path.dirname(csv_path), output_png=str(out_png))

    assert res is not None
    assert out_png.exists()
    assert out_png.stat().st_size > 15_000  # Graf musí mít reálnou velikost

    # Ověření, že byla vytvořena i kopie v podadresáři grafy/
    grafy_copy = tmp_path / "grafy" / "graf_zisk_frekvence.png"
    assert grafy_copy.exists()
    assert grafy_copy.stat().st_size > 15_000


def test_plot_gain_frequency_missing_source(tmp_path):
    """Ověření bezpečného selhání při absenci dat bez neošetřené výjimky."""
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()

    res = plot_gain_frequency(str(empty_dir))
    assert res is None


def test_main_advanced_plots_gain_integration(tmp_path, monkeypatch):
    """Ověření začlenění generování grafu zisku do _generate_advanced_plots v main.py."""
    from main import _generate_advanced_plots

    # Příprava testovacího prostředí s minimálním farfield-rE.csv
    test_data_dir = tmp_path / "data"
    test_post_dir = tmp_path / "data" / "postpro"
    test_post_dir.mkdir(parents=True)

    # Vytvoření syntetického farfield-rE.csv s boresight body pro 2 frekvence
    ff_csv = test_post_dir / "farfield-rE.csv"
    ff_content = (
        "f,exc,theta,phi,ReEx,ImEx,ReEy,ImEy,ReEz,ImEz\n"
        "2.330,1,0.0,0.0,1.0,0.0,0.0,-1.0,0.0,0.0\n"
        "2.335,1,0.0,0.0,1.0,0.0,0.0,-1.0,0.0,0.0\n"
    )
    ff_csv.write_text(ff_content, encoding="utf-8")

    # Spustíme _generate_advanced_plots
    _generate_advanced_plots(str(test_post_dir), str(test_data_dir))

    # Ověříme, že vznikl graf_zisk_frekvence.png
    gain_png = test_data_dir / "graf_zisk_frekvence.png"
    assert gain_png.exists()
    assert gain_png.stat().st_size > 5_000
