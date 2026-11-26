"""
test_gain_plot.py - Tests for gain, directivity, axial ratio (AR),
cross-polarization discrimination (XPD) calculation, and generation of the 2-panel plot plot_gain_frequency.png.
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
    """Verify locating farfield-rE.csv at different levels of the directory tree."""
    # 1. Direct path
    p1 = find_farfield_csv(os.path.join(PROJECT_ROOT, "data", "postpro"))
    assert p1 is not None and os.path.exists(p1)
    assert p1.endswith("farfield-rE.csv")

    # 2. Path from parent data directory
    p2 = find_farfield_csv(os.path.join(PROJECT_ROOT, "data"))
    assert p2 is not None and os.path.exists(p2)

    # 3. Non-existent directory
    assert find_farfield_csv("non_existent_directory_xyz") is None


def test_calculate_gain_frequency_real_data():
    """Verify gain and radiation parameter calculation on real data from an AMR=1 simulation."""
    csv_path = os.path.join(PROJECT_ROOT, "data", "postpro", "farfield-rE.csv")
    if not os.path.exists(csv_path):
        pytest.skip("File data/postpro/farfield-rE.csv is not present.")

    res = calculate_gain_frequency(csv_path, num_ports=2, design_freq=2.3325)

    freqs = res['freqs']
    assert len(freqs) >= 20
    assert np.isclose(freqs.min(), 2.320, atol=1e-3)
    assert np.isclose(freqs.max(), 2.345, atol=1e-3)

    # Physical relationship checks:
    # 1. Co-polarization (LHCP) must dominate over RHCP
    assert np.all(res['g_lhcp'] > res['g_rhcp'])
    assert np.all(res['xpd_db'] > 20.0)  # XPD > 20 dB across the entire band

    # 2. Total gain G_tot must be equal to or slightly higher than G_LHCP
    assert np.all(res['g_tot'] >= res['g_lhcp'])
    assert np.all(res['g_tot'] <= res['g_lhcp'] + 0.1)  # negligible RHCP component

    # 3. Directivity must exceed gain (due to dielectric and copper losses, eta_rad < 100%)
    assert np.all(res['d_lhcp'] > res['g_lhcp'])
    assert np.all(res['d_tot'] > res['g_tot'])

    # 4. Values at design frequency 2.3325 GHz
    dm = res['design_metrics']
    assert 2.0 <= dm['g_lhcp_dbi'] <= 2.6
    assert 2.0 <= dm['g_tot_dbi'] <= 2.6
    assert dm['g_rhcp_dbi'] < -15.0
    assert 7.0 <= dm['d_lhcp_dbi'] <= 8.5
    assert 25.0 <= dm['eta_rad_pct'] <= 35.0  # FR4 losses ~ 29%
    assert 0.5 <= dm['ar_db'] <= 2.0         # Excellent circular polarization AR < 2 dB (limit is 3 dB)
    assert dm['xpd_db'] >= 21.0

    # 5. Peak gain
    assert 2.325 <= res['f_gain_max_lhcp_ghz'] <= 2.335
    assert 2.2 <= res['gain_max_lhcp_dbi'] <= 2.5


def test_calculate_gain_frequency_synthetic_pure_lhcp():
    """Synthetic test: ideal circular LHCP wave on boresight (AR = 0 dB, infinite XPD)."""
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
    assert np.isclose(res['ar_db'][0], 0.0, atol=1e-4)  # Ideal circular polarization
    assert res['xpd_db'][0] > 100.0                     # Negligible RHCP component


def test_calculate_gain_frequency_synthetic_linear():
    """Synthetic test: linearly polarized wave (Ex = 1, Ey = 0) -> E_LHCP = E_RHCP -> XPD = 0 dB, AR -> inf."""
    data = [
        [2.3325, 1, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    ]
    df = pd.DataFrame(data, columns=[
        'f', 'exc', 'theta', 'phi', 'ReEx', 'ImEx', 'ReEy', 'ImEy', 'ReEz', 'ImEz'
    ])

    res = calculate_gain_frequency(df, p_in=1.0, design_freq=2.3325)

    # For linear polarization, power splits equally between LHCP and RHCP:
    # G_LHCP = G_RHCP = G_tot - 3.01 dB
    assert np.isclose(res['g_lhcp'][0], res['g_rhcp'][0], atol=1e-5)
    assert np.isclose(res['g_lhcp'][0], res['g_tot'][0] - 10.0 * np.log10(2.0), atol=1e-5)
    assert np.isclose(res['xpd_db'][0], 0.0, atol=1e-5)
    assert res['ar_db'][0] > 100.0  # Infinite axial ratio for linear polarization


def test_plot_gain_frequency_generation(tmp_path):
    """Verify PNG file generation by plot_gain_frequency."""
    csv_path = os.path.join(PROJECT_ROOT, "data", "postpro", "farfield-rE.csv")
    if not os.path.exists(csv_path):
        pytest.skip("File data/postpro/farfield-rE.csv is not present.")

    out_png = tmp_path / "test_plot_gain.png"
    res = plot_gain_frequency(os.path.dirname(csv_path), output_png=str(out_png))

    assert res is not None
    assert out_png.exists()
    assert out_png.stat().st_size > 15_000  # Plot must have a realistic file size

    # Verify that a copy was also created in the plots/ subdirectory
    plots_copy = tmp_path / "plots" / "plot_gain_frequency.png"
    assert plots_copy.exists()
    assert plots_copy.stat().st_size > 15_000


def test_plot_gain_frequency_missing_source(tmp_path):
    """Verify graceful failure when data is missing without an unhandled exception."""
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()

    res = plot_gain_frequency(str(empty_dir))
    assert res is None


def test_main_advanced_plots_gain_integration(tmp_path, monkeypatch):
    """Verify integration of gain plot generation into _generate_advanced_plots in main.py."""
    from main import _generate_advanced_plots

    # Prepare test environment with a minimal farfield-rE.csv
    test_data_dir = tmp_path / "data"
    test_post_dir = tmp_path / "data" / "postpro"
    test_post_dir.mkdir(parents=True)

    # Create synthetic farfield-rE.csv with boresight points for 2 frequencies
    ff_csv = test_post_dir / "farfield-rE.csv"
    ff_content = (
        "f,exc,theta,phi,ReEx,ImEx,ReEy,ImEy,ReEz,ImEz\n"
        "2.330,1,0.0,0.0,1.0,0.0,0.0,-1.0,0.0,0.0\n"
        "2.335,1,0.0,0.0,1.0,0.0,0.0,-1.0,0.0,0.0\n"
    )
    ff_csv.write_text(ff_content, encoding="utf-8")

    # Run _generate_advanced_plots
    _generate_advanced_plots(str(test_post_dir), str(test_data_dir))

    # Verify that plot_gain_frequency.png was created
    gain_png = test_data_dir / "plot_gain_frequency.png"
    assert gain_png.exists()
    assert gain_png.stat().st_size > 5_000
