"""
tracker.py - Jednoduchý, robustní a transparentní systém pro sledování parametrů a výsledků simulací.
Podporuje:
  - Model 1 (1 port, T-dělič): zapisuje do export/sweep_results.csv a .md
  - Model 2 (2 porty, 100 Ohm LHCP): zapisuje do export/sweep_results_model2.csv a .md
"""

import os
import csv
import numpy as np

# Konstanty pro VF výpočty
S11_BW_THRESHOLD_DB = -10.0
GHZ_TO_MHZ = 1000.0
ETA_0 = 376.7303135  # Vlnová impedance vakua [Ohm]
DESIGN_FREQ_GHZ = 2.3325

# ==============================================================================
# 1. KONFIGURACE PRO MODEL 1 (Původní)
# ==============================================================================
TRACKED_PARAMS_V1 = [
    ('feed_inset', 'inset_mm', '{:.2f}'),
    ('patch_L', 'patch_L_mm', '{:.2f}'),
    ('patch_W', 'patch_W_mm', '{:.2f}'),
    ('freq_min', 'f_min_GHz', '{:.3f}'),
    ('freq_max', 'f_max_GHz', '{:.3f}'),
    ('amr_max_its', 'amr_its', '{:d}'),
    ('linear_tol', 'lin_tol', '{:.1e}'),
]

TRACKED_METRICS_V1 = [
    ('f0_GHz', 'f0 [GHz]', '{:.3f}'),
    ('s11_min_dB', 'S11_min [dB]', '{:.2f}'),
    ('bw_mhz', 'BW_-10dB [MHz]', '{:.1f}'),
    ('zin_re_ohm', 'Zin_Re [Ohm]', '{:.1f}'),
    ('zin_im_ohm', 'Zin_Im [Ohm]', '{:.1f}'),
    ('e_lhcp', 'E_LHCP [V]', '{:.2f}'),
    ('e_rhcp', 'E_RHCP [V]', '{:.2f}'),
    ('axial_ratio_db', 'AR [dB]', '{:.2f}'),
    ('polarization', 'Polarizace', '{}'),
    ('gain_lhcp_dbi', 'Gain_LHCP [dBi]', '{:.2f}'),
    ('gain_rhcp_dbi', 'Gain_RHCP [dBi]', '{:.2f}'),
]

# ==============================================================================
# 2. KONFIGURACE PRO MODEL 2 (Dvouportový model)
# ==============================================================================
TRACKED_PARAMS_V2 = [
    ('feed_inset_b', 'inset_b_mm', '{:.2f}'),
    ('feed_inset_l', 'inset_l_mm', '{:.2f}'),
    ('patch_L', 'patch_L_mm', '{:.2f}'),
]
TRACKED_PARAMS_MODEL2 = TRACKED_PARAMS_V2

TRACKED_METRICS_V2 = [
    ('f0_b_GHz', 'f0_b_GHz', '{:.3f}'),
    ('f0_l_GHz', 'f0_l_GHz', '{:.3f}'),
    ('s11_min_dB', 'S11_min [dB]', '{:.2f}'),
    ('s22_min_dB', 'S22_min [dB]', '{:.2f}'),
    ('f_gain_max_lhcp_ghz', 'fGainMaxLhcp [GHz]', '{:.3f}'),
    ('gain_max_lhcp_dbi', 'Gain_max_LHCP [dBi]', '{:.2f}'),
    ('zin1_re_ohm', 'Zin1_Re [Ohm]', '{:.1f}'),
    ('zin2_re_ohm', 'Zin2_Re [Ohm]', '{:.1f}'),
    ('e_lhcp', 'E_LHCP [V]', '{:.2f}'),
    ('e_rhcp', 'E_RHCP [V]', '{:.2f}'),
    ('axial_ratio_db', 'AR [dB]', '{:.2f}'),
    ('polarization', 'Polarizace', '{}'),
    ('gain_lhcp_dbi', 'Gain_LHCP [dBi]', '{:.2f}'),
    ('gain_rhcp_dbi', 'Gain_RHCP [dBi]', '{:.2f}'),
]
TRACKED_METRICS_MODEL2 = TRACKED_METRICS_V2

FIELDNAMES_V2 = [
    'run_name',
    'inset_b_mm',
    'inset_l_mm',
    'patch_L_mm',
    'f0_b_GHz',
    'f0_l_GHz',
    'S11_min [dB]',
    'S22_min [dB]',
    'fGainMaxLhcp [GHz]',
    'Gain_max_LHCP [dBi]',
    'Zin1_Re [Ohm]',
    'Zin2_Re [Ohm]',
    'E_LHCP [V]',
    'E_RHCP [V]',
    'AR [dB]',
    'Polarizace',
    'Gain_LHCP [dBi]',
    'Gain_RHCP [dBi]',
    'export_zip',
]
FIELDNAMES_MODEL2 = FIELDNAMES_V2


def extract_s11_metrics(s11_file, z0=50.0):
    """Extrahuje rezonanční frekvenci, minimum S11, šířku pásma a vstupní impedanci pro Model 1."""
    if not os.path.exists(s11_file) or os.path.getsize(s11_file) == 0:
        return {}

    try:
        data = np.loadtxt(s11_file, delimiter=',', skiprows=1)
        if data.ndim == 1:
            data = data.reshape(1, -1)
        freqs = data[:, 0]
        s11_db = data[:, 1]
        s11_deg = data[:, 2] if data.shape[1] > 2 else np.zeros_like(s11_db)

        min_idx = int(np.argmin(s11_db))
        f0 = float(freqs[min_idx])
        s11_min = float(s11_db[min_idx])

        # Výpočet impedance z S11 při rezonanci f0
        s11_lin = 10.0 ** (s11_min / 20.0)
        s11_rad = np.deg2rad(s11_deg[min_idx])
        gamma = s11_lin * np.exp(1j * s11_rad)
        zin = z0 * (1.0 + gamma) / (1.0 - gamma + 1e-12)

        # Šířka pásma pod -10 dB s lineární interpolací
        bw_mhz = 0.0
        if s11_min <= S11_BW_THRESHOLD_DB:
            f_low = freqs[0] if s11_db[0] <= S11_BW_THRESHOLD_DB else None
            f_high = freqs[-1] if s11_db[-1] <= S11_BW_THRESHOLD_DB else None

            for i in range(min_idx, 0, -1):
                if s11_db[i] <= S11_BW_THRESHOLD_DB and s11_db[i - 1] > S11_BW_THRESHOLD_DB:
                    denom = s11_db[i] - s11_db[i - 1]
                    frac = (S11_BW_THRESHOLD_DB - s11_db[i - 1]) / (denom if abs(denom) > 1e-12 else 1e-12)
                    f_low = freqs[i - 1] + frac * (freqs[i] - freqs[i - 1])
                    break
            for i in range(min_idx, len(freqs) - 1):
                if s11_db[i] <= S11_BW_THRESHOLD_DB and s11_db[i + 1] > S11_BW_THRESHOLD_DB:
                    denom = s11_db[i + 1] - s11_db[i]
                    frac = (S11_BW_THRESHOLD_DB - s11_db[i]) / (denom if abs(denom) > 1e-12 else 1e-12)
                    f_high = freqs[i] + frac * (freqs[i + 1] - freqs[i])
                    break

            if f_low is not None and f_high is not None:
                bw_mhz = float(np.round((f_high - f_low) * GHZ_TO_MHZ, 1))

        return {
            'f0_GHz': f0,
            's11_min_dB': s11_min,
            'bw_mhz': bw_mhz,
            'zin_re_ohm': float(zin.real),
            'zin_im_ohm': float(zin.imag),
        }
    except Exception as e:
        print(f"Upozornění: Chyba při čtení S-parametrů z {s11_file}: {e}")
        return {}


def extract_s_parameters_model2(output_dir, z0=100.0):
    """
    Vyhodnotí VF parametry pro dvouportový Model 2:
    - Primární a spolehlivý zdroj: port-S.csv (přímo z Palace)
      Obsahuje reálná data rozptylu |S[1][1]|, |S[2][2]|, |S[2][1]| a fáze.
      Určí skutečná minima S11_min a S22_min a rezonanční frekvence f0_b a f0_l.
      Zin1 a Zin2 počítá z komplexního činitele odrazu: Zin = Z0 * (1 + Gamma) / (1 - Gamma).
    - Sekundární / doplňkový fallback: port-V.csv a port-I.csv
      Nikdy nepoužívá incidentní sloupce (V_inc, I_inc), striktně hledá Re{V}, Im{V}, Re{I}, Im{I}.
    """
    v_path = os.path.join(output_dir, "port-V.csv")
    i_path = os.path.join(output_dir, "port-I.csv")
    s_path = os.path.join(output_dir, "port-S.csv")

    metrics = {}

    def find_col_idx(header, patterns, exclude_patterns=None):
        for idx, col in enumerate(header):
            col_low = col.lower()
            if exclude_patterns and any(ep.lower() in col_low for ep in exclude_patterns):
                continue
            for pat in patterns:
                if pat.lower() in col_low:
                    return idx
        return None

    # 1. PRIMÁRNÍ ZDROJ: port-S.csv
    if os.path.exists(s_path) and os.path.getsize(s_path) > 0:
        try:
            with open(s_path, 'r', encoding='utf-8') as f:
                s_header = [h.strip() for h in f.readline().split(',')]

            s_data = np.loadtxt(s_path, delimiter=',', skiprows=1)
            if s_data.ndim == 1:
                s_data = s_data.reshape(1, -1)

            if s_data.shape[0] > 0 and s_data.shape[1] >= 2:
                freqs = s_data[:, 0]

                # Vyhledání sloupců pro S11 (|S[1][1]|) a případnou fázi
                s11_idx = find_col_idx(s_header, ["|s[1][1]|", "s[1][1]", "s[1,1]", "|s11|", "s11"])
                if s11_idx is None:
                    s11_idx = 1
                s11_db = s_data[:, s11_idx]

                s11_deg_idx = find_col_idx(s_header, ["arg(s[1][1])", "arg(s[1,1])", "arg(s11)", "phase(s[1][1])", "phase(s11)"])
                if s11_deg_idx is None and s_data.shape[1] > 2 and ("arg" in s_header[2].lower() or "deg" in s_header[2].lower()):
                    s11_deg_idx = 2

                # Vyhledání sloupců pro S22 (|S[2][2]|) a případnou fázi
                s22_idx = find_col_idx(s_header, ["|s[2][2]|", "s[2][2]", "s[2,2]", "|s22|", "s22"])
                s22_deg_idx = find_col_idx(s_header, ["arg(s[2][2])", "arg(s[2,2])", "arg(s22)", "phase(s[2][2])", "phase(s22)"])

                if s22_idx is None:
                    # Běžná Palace matice 2 portů: [f, S11, arg11, S21, arg21, S12, arg12, S22, arg22]
                    if s_data.shape[1] >= 8:
                        s22_idx = 7
                        if s22_deg_idx is None and s_data.shape[1] >= 9:
                            s22_deg_idx = 8
                    elif s_data.shape[1] == 4:
                        s22_idx = 3
                    elif s_data.shape[1] == 3 and s11_deg_idx is None:
                        s22_idx = 2

                if s22_idx is not None and s22_idx < s_data.shape[1]:
                    s22_db = s_data[:, s22_idx]
                else:
                    # Pokud druhý port chybí, zrcadlíme port 1
                    s22_db = s11_db.copy()

                # Vyhledání S21 (přenos)
                s21_idx = find_col_idx(s_header, ["|s[2][1]|", "s[2][1]", "s[2,1]", "|s21|", "s21"])
                if s21_idx is None and s_data.shape[1] >= 4 and s22_idx != 3:
                    s21_idx = 3
                s21_db = s_data[:, s21_idx] if s21_idx is not None and s21_idx < s_data.shape[1] else None

                min1_idx = int(np.argmin(s11_db))
                f0_b = float(freqs[min1_idx])
                s11_min = float(s11_db[min1_idx])

                min2_idx = int(np.argmin(s22_db))
                f0_l = float(freqs[min2_idx])
                s22_min = float(s22_db[min2_idx])

                # Výpočet impedance Zin ze činitele odrazu
                if s11_deg_idx is not None and s11_deg_idx < s_data.shape[1]:
                    s11_deg = s_data[:, s11_deg_idx]
                    s11_lin = 10.0 ** (s11_min / 20.0)
                    gamma1 = s11_lin * np.exp(1j * np.deg2rad(s11_deg[min1_idx]))
                    zin1 = z0 * (1.0 + gamma1) / (1.0 - gamma1 + 1e-12)
                    zin1_re = float(zin1.real)
                else:
                    gamma1_mag = 10.0 ** (s11_min / 20.0)
                    zin1_re = float(z0 * (1.0 + gamma1_mag) / max(1.0 - gamma1_mag, 1e-4))

                if s22_deg_idx is not None and s22_deg_idx < s_data.shape[1]:
                    s22_deg = s_data[:, s22_deg_idx]
                    s22_lin = 10.0 ** (s22_min / 20.0)
                    gamma2 = s22_lin * np.exp(1j * np.deg2rad(s22_deg[min2_idx]))
                    zin2 = z0 * (1.0 + gamma2) / (1.0 - gamma2 + 1e-12)
                    zin2_re = float(zin2.real)
                else:
                    gamma2_mag = 10.0 ** (s22_min / 20.0)
                    zin2_re = float(z0 * (1.0 + gamma2_mag) / max(1.0 - gamma2_mag, 1e-4))

                metrics.update({
                    'f0_b_GHz': f0_b,
                    'f0_l_GHz': f0_l,
                    's11_min_dB': s11_min,
                    's22_min_dB': s22_min,
                    'zin1_re_ohm': zin1_re,
                    'zin2_re_ohm': zin2_re,
                    'freqs': freqs,
                    's11_db': s11_db,
                    's22_db': s22_db,
                })
                if s21_db is not None:
                    metrics['s21_db'] = s21_db
                    metrics['s21_min_dB'] = float(s21_db[min1_idx])

                return metrics
        except Exception as e:
            print(f"Upozornění: Chyba při čtení primárního souboru port-S.csv: {e}")

    # 2. SEKUNDÁRNÍ / FALLBACK VÝPOČET: port-V.csv a port-I.csv
    # Používá se, pokud port-S.csv chybí (např. syntetické testy)
    if os.path.exists(v_path) and os.path.exists(i_path) and os.path.getsize(v_path) > 0 and os.path.getsize(i_path) > 0:
        try:
            with open(v_path, 'r', encoding='utf-8') as f:
                v_header = [h.strip() for h in f.readline().split(',')]
            with open(i_path, 'r', encoding='utf-8') as f:
                i_header = [h.strip() for h in f.readline().split(',')]

            v_data = np.loadtxt(v_path, delimiter=',', skiprows=1)
            i_data = np.loadtxt(i_path, delimiter=',', skiprows=1)

            if v_data.ndim == 1:
                v_data = v_data.reshape(1, -1)
            if i_data.ndim == 1:
                i_data = i_data.reshape(1, -1)

            freqs = v_data[:, 0]

            # Striktně vyřazujeme incidentní sloupce (obsahující 'inc')!
            v1_re_idx = find_col_idx(v_header, ["re{v[1]}", "re(v[1])", "v[1]_re", "re_v1", "v1r", "rev1", "re{v_1}", "v1_re"], exclude_patterns=["inc"])
            v1_im_idx = find_col_idx(v_header, ["im{v[1]}", "im(v[1])", "v[1]_im", "im_v1", "v1i", "imv1", "im{v_1}", "v1_im"], exclude_patterns=["inc"])
            v2_re_idx = find_col_idx(v_header, ["re{v[2]}", "re(v[2])", "v[2]_re", "re_v2", "v2r", "rev2", "re{v_2}", "v2_re"], exclude_patterns=["inc"])
            v2_im_idx = find_col_idx(v_header, ["im{v[2]}", "im(v[2])", "v[2]_im", "im_v2", "v2i", "imv2", "im{v_2}", "v2_im"], exclude_patterns=["inc"])

            i1_re_idx = find_col_idx(i_header, ["re{i[1]}", "re(i[1])", "i[1]_re", "re_i1", "i1r", "rei1", "re{i_1}", "i1_re"], exclude_patterns=["inc"])
            i1_im_idx = find_col_idx(i_header, ["im{i[1]}", "im(i[1])", "i[1]_im", "im_i1", "i1i", "imi1", "im{i_1}", "i1_im"], exclude_patterns=["inc"])
            i2_re_idx = find_col_idx(i_header, ["re{i[2]}", "re(i[2])", "i[2]_re", "re_i2", "i2r", "rei2", "re{i_2}", "i2_re"], exclude_patterns=["inc"])
            i2_im_idx = find_col_idx(i_header, ["im{i[2]}", "im(i[2])", "i[2]_im", "im_i2", "i2i", "imi2", "im{i_2}", "i2_im"], exclude_patterns=["inc"])

            # Bezpečné fallback indexy pro strukturu: col 0=f, col 1=V_inc1, col 2=Re{V1}, col 3=Im{V1}, col 4=V_inc2, col 5=Re{V2}, col 6=Im{V2}
            if v1_re_idx is None:
                v1_re_idx = 2 if v_data.shape[1] > 2 else 1
            if v1_im_idx is None:
                v1_im_idx = 3 if v_data.shape[1] > 3 else None
            if v2_re_idx is None and v_data.shape[1] > 5:
                v2_re_idx = 5
            if v2_im_idx is None and v_data.shape[1] > 6:
                v2_im_idx = 6

            if i1_re_idx is None:
                i1_re_idx = 2 if i_data.shape[1] > 2 else 1
            if i1_im_idx is None:
                i1_im_idx = 3 if i_data.shape[1] > 3 else None
            if i2_re_idx is None and i_data.shape[1] > 5:
                i2_re_idx = 5
            if i2_im_idx is None and i_data.shape[1] > 6:
                i2_im_idx = 6

            # Port 1 (spodní port)
            v1_re = v_data[:, v1_re_idx]
            v1_im = v_data[:, v1_im_idx] if v1_im_idx is not None else np.zeros_like(v1_re)
            v1 = v1_re + 1j * v1_im

            i1_re = i_data[:, i1_re_idx]
            i1_im = i_data[:, i1_im_idx] if i1_im_idx is not None else np.zeros_like(i1_re)
            i1 = i1_re + 1j * i1_im

            z_in1 = v1 / (i1 + 1e-15)
            gamma1 = (z_in1 - z0) / (z_in1 + z0 + 1e-15)
            s11_db = 20.0 * np.log10(np.clip(np.abs(gamma1), 1e-10, 10.0))

            min1_idx = int(np.argmin(s11_db))
            f0_b = float(freqs[min1_idx])
            s11_min = float(s11_db[min1_idx])
            zin1_re = float(z_in1[min1_idx].real)

            metrics['f0_b_GHz'] = f0_b
            metrics['s11_min_dB'] = s11_min
            metrics['zin1_re_ohm'] = zin1_re
            metrics['freqs'] = freqs
            metrics['s11_db'] = s11_db

            # Port 2 (levý port)
            if v2_re_idx is not None and i2_re_idx is not None:
                v2_re = v_data[:, v2_re_idx]
                v2_im = v_data[:, v2_im_idx] if v2_im_idx is not None else np.zeros_like(v2_re)
                v2 = v2_re + 1j * v2_im

                i2_re = i_data[:, i2_re_idx]
                i2_im = i_data[:, i2_im_idx] if i2_im_idx is not None else np.zeros_like(i2_re)
                i2 = i2_re + 1j * i2_im

                z_in2 = v2 / (i2 + 1e-15)
                gamma2 = (z_in2 - z0) / (z_in2 + z0 + 1e-15)
                s22_db = 20.0 * np.log10(np.clip(np.abs(gamma2), 1e-10, 10.0))

                min2_idx = int(np.argmin(s22_db))
                f0_l = float(freqs[min2_idx])
                s22_min = float(s22_db[min2_idx])
                zin2_re = float(z_in2[min2_idx].real)

                metrics['f0_l_GHz'] = f0_l
                metrics['s22_min_dB'] = s22_min
                metrics['zin2_re_ohm'] = zin2_re
                metrics['s22_db'] = s22_db
            else:
                metrics['f0_l_GHz'] = f0_b
                metrics['s22_min_dB'] = s11_min
                metrics['zin2_re_ohm'] = zin1_re
                metrics['s22_db'] = s11_db

            return metrics
        except Exception as e:
            print(f"Upozornění: Chyba při výpočtu S-parametrů z port-V a port-I: {e}")

    return metrics


def extract_farfield_metrics(farfield_file, target_freq=None, s11_min_db=None):
    """
    Vyhodnotí vyzařování z farfield-rE.csv:
    - Vyhodnocuje všechny frekvence f v souboru pro koherentní superpozici Portu 1 a Portu 2.
    - Hledá maximum zisku LHCP a jeho frekvenci (fGainMaxLhcp, Gain_max_LHCP).
    - Zachovává metriky na zadané rezonanční / cílové frekvenci target_freq.
    """
    if not os.path.exists(farfield_file) or os.path.getsize(farfield_file) == 0:
        return {}

    try:
        data = np.loadtxt(farfield_file, delimiter=',', skiprows=1)
        if data.ndim == 1:
            data = data.reshape(1, -1)

        freqs = np.unique(data[:, 0])
        freqs.sort()
        if len(freqs) == 0:
            return {}

        gain_lhcp_list = []
        gain_rhcp_list = []
        ar_list = []
        e_lhcp_list = []
        e_rhcp_list = []

        p_in_single = 1.0 - (10.0 ** (s11_min_db / 10.0)) if s11_min_db is not None else 1.0
        p_in_single = max(p_in_single, 0.01)

        for f_val in freqs:
            f_data = data[np.isclose(data[:, 0], f_val, atol=1e-7)]

            # Boresight bod: theta nejblíže 0 (osa +Z)
            # Podpora pro více excitačních módů v Palace (Model 2 má 2 nezávislé buzené porty / excitace)
            unique_excs = np.unique(f_data[:, 1]) if f_data.shape[1] > 1 else [1]
            ex_tot = 0.0 + 0.0j
            ey_tot = 0.0 + 0.0j
            num_excs = max(len(unique_excs), 1)

            for e in unique_excs:
                e_data = f_data[np.isclose(f_data[:, 1], e, atol=1e-5)] if f_data.shape[1] > 1 else f_data
                theta_col = e_data[:, 2]
                b_rows = e_data[np.abs(theta_col) < 1e-2]
                if len(b_rows) == 0:
                    b_rows = e_data[np.argmin(np.abs(theta_col))]
                row = b_rows[0] if b_rows.ndim > 1 else b_rows
                ex_tot += row[4] + 1j * row[5]
                ey_tot += row[6] + 1j * row[7]

            # Rozklad na LHCP a RHCP fázory dle standardu IEEE (+Z):
            # E_LHCP = (Ex + j*Ey)/sqrt(2), E_RHCP = (Ex - j*Ey)/sqrt(2)
            e_lhcp_f = float(abs(ex_tot + 1j * ey_tot) / np.sqrt(2.0))
            e_rhcp_f = float(abs(ex_tot - 1j * ey_tot) / np.sqrt(2.0))

            # Osový poměr (Axial Ratio v dB)
            major_f = max(e_lhcp_f, e_rhcp_f) + min(e_lhcp_f, e_rhcp_f)
            minor_f = max(abs(e_lhcp_f - e_rhcp_f), 1e-9)
            ar_db_f = float(20.0 * np.log10(major_f / minor_f))

            # Odhad zisku v dBi
            u_lhcp_f = (e_lhcp_f ** 2) / (2.0 * ETA_0)
            u_rhcp_f = (e_rhcp_f ** 2) / (2.0 * ETA_0)
            p_in = max(num_excs * p_in_single, 0.01)

            gain_lhcp_lin_f = (4.0 * np.pi * u_lhcp_f) / p_in
            gain_lhcp_dbi_f = float(10.0 * np.log10(max(gain_lhcp_lin_f, 1e-4)))

            gain_rhcp_lin_f = (4.0 * np.pi * u_rhcp_f) / p_in
            gain_rhcp_dbi_f = float(10.0 * np.log10(max(gain_rhcp_lin_f, 1e-4)))

            gain_lhcp_list.append(gain_lhcp_dbi_f)
            gain_rhcp_list.append(gain_rhcp_dbi_f)
            ar_list.append(ar_db_f)
            e_lhcp_list.append(e_lhcp_f)
            e_rhcp_list.append(e_rhcp_f)

        gain_lhcp_freqs = np.array(gain_lhcp_list)
        ar_freqs = np.array(ar_list)

        # Nalezení frekvence s maximálním ziskem LHCP (s uvažováním posunu frekvence zanořením)
        max_idx = int(np.argmax(gain_lhcp_freqs))
        f_gain_max = float(freqs[max_idx])
        gain_max_lhcp = float(gain_lhcp_freqs[max_idx])
        ar_at_gain_max = float(ar_freqs[max_idx])

        # Hodnoty na cílové / rezonanční frekvenci target_freq
        eval_f = target_freq if target_freq is not None else DESIGN_FREQ_GHZ
        target_idx = int(np.argmin(np.abs(freqs - eval_f)))

        e_lhcp = float(e_lhcp_list[target_idx])
        e_rhcp = float(e_rhcp_list[target_idx])
        ar_db = float(ar_list[target_idx])
        polarization = "LHCP" if e_lhcp >= e_rhcp else "RHCP"
        gain_lhcp_dbi = float(gain_lhcp_list[target_idx])
        gain_rhcp_dbi = float(gain_rhcp_list[target_idx])

        return {
            'e_lhcp': e_lhcp,
            'e_rhcp': e_rhcp,
            'axial_ratio_db': ar_db,
            'polarization': polarization,
            'gain_lhcp_dbi': gain_lhcp_dbi,
            'gain_rhcp_dbi': gain_rhcp_dbi,
            'gain_dbi': gain_lhcp_dbi,
            'f_gain_max_lhcp_ghz': f_gain_max,
            'gain_max_lhcp_dbi': gain_max_lhcp,
            'ar_at_max_gain_db': ar_at_gain_max,
        }
    except Exception as e:
        print(f"Upozornění: Chyba při analýze vyzařování z {farfield_file}: {e}")
        return {}


def format_value(val, fmt):
    """Pomocné bezpečné formátování hodnoty."""
    if val is None or val == "":
        return "-"
    try:
        return fmt.format(val)
    except Exception:
        return str(val)


def record_run(params, output_dir="data/postpro", run_name=None, export_zip=None, results_dir=None):
    """
    Zaznamená běh do příslušné tabulky podle verze modelu (ANTENNA_MODEL):
      - Model 1 -> export/sweep_results.csv a .md
      - Model 2 -> export/sweep_results_model2.csv a .md
    """
    model_version = int(params.get('antenna_model', os.getenv('ANTENNA_MODEL', '1')))
    
    if results_dir is None:
        try:
            from postpro_utils import get_export_dir
            results_dir = get_export_dir()
        except ImportError:
            results_dir = "export"

    os.makedirs(results_dir, exist_ok=True)

    if model_version == 2:
        return _record_run_model2(params, output_dir, run_name, export_zip, results_dir)
    else:
        return _record_run_model1(params, output_dir, run_name, export_zip, results_dir)


def _record_run_model1(params, output_dir, run_name, export_zip, results_dir):
    csv_file = os.path.join(results_dir, "sweep_results.csv")
    md_file = os.path.join(results_dir, "sweep_results.md")

    s11_path = os.path.join(output_dir, "port-S.csv")
    farfield_path = os.path.join(output_dir, "farfield-rE.csv")

    port_z0 = float(params.get('port_impedance', 50.0))
    s11_metrics = extract_s11_metrics(s11_path, z0=port_z0)
    f0 = s11_metrics.get('f0_GHz')
    s11_min = s11_metrics.get('s11_min_dB')
    farfield_metrics = extract_farfield_metrics(farfield_path, target_freq=f0, s11_min_db=s11_min)

    row = {'run_name': run_name or params.get('run_name', 'run')}

    for param_key, col_name, fmt in TRACKED_PARAMS_V1:
        val = params.get(param_key)
        row[col_name] = format_value(val, fmt) if val is not None else ""

    for metric_key, col_name, fmt in TRACKED_METRICS_V1:
        if metric_key in s11_metrics:
            val = s11_metrics[metric_key]
            row[col_name] = format_value(val, fmt) if val is not None else ""
        elif metric_key in farfield_metrics:
            val = farfield_metrics[metric_key]
            row[col_name] = format_value(val, fmt) if val is not None else ""
        else:
            row[col_name] = ""

    row['export_zip'] = export_zip or (f"{run_name}.zip" if run_name else "-")

    fieldnames = ['run_name'] + [col for _, col, _ in TRACKED_PARAMS_V1] + [col for _, col, _ in TRACKED_METRICS_V1] + ['export_zip']
    file_exists = os.path.exists(csv_file) and os.path.getsize(csv_file) > 0

    with open(csv_file, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    update_markdown_summary(csv_file, md_file, title="Souhrnná tabulka výsledků Modelu 1 (T-dělič)")

    print("\n" + "=" * 95)
    print("VÝSLEDKY SIMULAČNÍHO KROKU MODELU 1 (Zaznamenáno do export/sweep_results.csv):")
    print("-" * 95)
    info_parts = [
        f"Krok: {row['run_name']}",
        f"Zanoření: {row.get('inset_mm', '-') } mm",
        f"f0: {row.get('f0 [GHz]', '-')} GHz",
        f"S11: {row.get('S11_min [dB]', '-')} dB",
        f"BW: {row.get('BW_-10dB [MHz]', '-')} MHz",
        f"Pol: {row.get('Polarizace', '-')}",
        f"AR: {row.get('AR [dB]', '-')} dB",
        f"G_LHCP: {row.get('Gain_LHCP [dBi]', '-')} dBi",
    ]
    print(" | ".join([p for p in info_parts if p]))
    print("=" * 95)

    return row


def _record_run_model2(params, output_dir, run_name, export_zip, results_dir):
    csv_file = os.path.join(results_dir, "sweep_results_model2.csv")
    md_file = os.path.join(results_dir, "sweep_results_model2.md")

    port_z0 = float(params.get('port_impedance', 100.0))
    s_metrics = extract_s_parameters_model2(output_dir, z0=port_z0)
    
    f0_b = s_metrics.get('f0_b_GHz')
    s11_min = s_metrics.get('s11_min_dB')
    
    farfield_path = os.path.join(output_dir, "farfield-rE.csv")
    farfield_metrics = extract_farfield_metrics(farfield_path, target_freq=f0_b, s11_min_db=s11_min)

    row = {
        'run_name': run_name or params.get('run_name', 'run_m2'),
        'inset_b_mm': format_value(params.get('feed_inset_b', params.get('inset_b', 0.0)), '{:.2f}'),
        'inset_l_mm': format_value(params.get('feed_inset_l', params.get('inset_l', 0.0)), '{:.2f}'),
        'patch_L_mm': format_value(params.get('patch_L', 30.3), '{:.2f}'),
        'f0_b_GHz': format_value(s_metrics.get('f0_b_GHz'), '{:.3f}'),
        'f0_l_GHz': format_value(s_metrics.get('f0_l_GHz'), '{:.3f}'),
        'S11_min [dB]': format_value(s_metrics.get('s11_min_dB'), '{:.2f}'),
        'S22_min [dB]': format_value(s_metrics.get('s22_min_dB'), '{:.2f}'),
        'fGainMaxLhcp [GHz]': format_value(farfield_metrics.get('f_gain_max_lhcp_ghz'), '{:.3f}'),
        'Gain_max_LHCP [dBi]': format_value(farfield_metrics.get('gain_max_lhcp_dbi'), '{:.2f}'),
        'Zin1_Re [Ohm]': format_value(s_metrics.get('zin1_re_ohm'), '{:.1f}'),
        'Zin2_Re [Ohm]': format_value(s_metrics.get('zin2_re_ohm'), '{:.1f}'),
        'E_LHCP [V]': format_value(farfield_metrics.get('e_lhcp'), '{:.2f}'),
        'E_RHCP [V]': format_value(farfield_metrics.get('e_rhcp'), '{:.2f}'),
        'AR [dB]': format_value(farfield_metrics.get('axial_ratio_db'), '{:.2f}'),
        'Polarizace': format_value(farfield_metrics.get('polarization'), '{}'),
        'Gain_LHCP [dBi]': format_value(farfield_metrics.get('gain_lhcp_dbi'), '{:.2f}'),
        'Gain_RHCP [dBi]': format_value(farfield_metrics.get('gain_rhcp_dbi'), '{:.2f}'),
        'export_zip': export_zip or (f"{run_name}.zip" if run_name else "-"),
    }

    file_exists = os.path.exists(csv_file) and os.path.getsize(csv_file) > 0

    with open(csv_file, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES_V2, extrasaction='ignore')
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    update_markdown_summary(csv_file, md_file, title="Souhrnná tabulka výsledků Modelu 2 (Dvouportový LHCP)")

    print("\n" + "=" * 105)
    print("VÝSLEDKY SIMULAČNÍHO KROKU MODELU 2 (Zaznamenáno do export/sweep_results_model2.csv):")
    print("-" * 105)
    info_parts = [
        f"Krok: {row['run_name']}",
        f"ib={row['inset_b_mm']} mm",
        f"il={row['inset_l_mm']} mm",
        f"f0_b={row['f0_b_GHz']} GHz",
        f"f0_l={row['f0_l_GHz']} GHz",
        f"S11={row['S11_min [dB]']} dB",
        f"S22={row['S22_min [dB]']} dB",
        f"fGMax={row['fGainMaxLhcp [GHz]']} GHz",
        f"G_max_LHCP={row['Gain_max_LHCP [dBi]']} dBi",
        f"Zin1={row['Zin1_Re [Ohm]']} Ohm",
        f"Zin2={row['Zin2_Re [Ohm]']} Ohm",
        f"Pol={row['Polarizace']}",
        f"AR={row['AR [dB]']} dB",
        f"G_LHCP={row['Gain_LHCP [dBi]']} dBi",
    ]
    print(" | ".join([p for p in info_parts if p]))
    print("=" * 105)

    return row

record_run_model2 = _record_run_model2


def update_markdown_summary(csv_file, md_file, title="Souhrnná tabulka výsledků simulací"):
    """Převede CSV soubor na přehlednou Markdown tabulku."""
    if not os.path.exists(csv_file):
        return

    try:
        with open(csv_file, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if not rows:
            return

        headers = list(rows[0].keys())
        md_lines = [
            f"# 📊 {title}\n",
            f"Poslední aktualizace: automaticky vygenerováno z `{os.path.basename(csv_file)}`.\n",
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
        ]

        for r in rows:
            line = "| " + " | ".join([str(r.get(h) if r.get(h) not in (None, "") else "-") for h in headers]) + " |"
            md_lines.append(line)

        with open(md_file, mode='w', encoding='utf-8') as f:
            f.write("\n".join(md_lines) + "\n")
    except Exception as e:
        print(f"Upozornění: Nepodařilo se aktualizovat Markdown tabulku: {e}")


def print_summary_table_model2(csv_file=None):
    """Vytiskne celou souhrnnou tabulku Modelu 2 (Dvouportový LHCP) do konzole."""
    if csv_file is None:
        try:
            from postpro_utils import get_export_dir
            exp_dir = get_export_dir()
        except ImportError:
            exp_dir = "export"
        csv_file = os.path.join(exp_dir, "sweep_results_model2.csv")

    if not os.path.exists(csv_file):
        print(f"Tabulka {csv_file} zatím neexistuje.")
        return

    with open(csv_file, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("Tabulka výsledků Modelu 2 je prázdná.")
        return

    print("\n" + "=" * 145)
    print("KOMPLETNÍ SOUHRNNÁ TABULKA MODELU 2 (DVOUPOVRTOVÝ LHCP):")
    disp_cols = [
        ('run_name', 'Krok', 20),
        ('inset_b_mm', 'ib [mm]', 8),
        ('inset_l_mm', 'il [mm]', 8),
        ('f0_b_GHz', 'f0_b', 8),
        ('f0_l_GHz', 'f0_l', 8),
        ('S11_min [dB]', 'S11 [dB]', 10),
        ('S22_min [dB]', 'S22 [dB]', 10),
        ('fGainMaxLhcp [GHz]', 'fGMax [GHz]', 12),
        ('Gain_max_LHCP [dBi]', 'G_max [dBi]', 12),
        ('Zin1_Re [Ohm]', 'Zin1 [Ohm]', 10),
        ('Zin2_Re [Ohm]', 'Zin2 [Ohm]', 10),
        ('AR [dB]', 'AR [dB]', 8),
        ('Polarizace', 'Pol', 6),
        ('Gain_LHCP [dBi]', 'G_LHCP', 8),
    ]
    print("=" * 145)
    header_str = " | ".join([f"{title:^{width}}" for _, title, width in disp_cols])
    sep_str = "-+-".join(["-" * width for _, _, width in disp_cols])
    print(header_str)
    print(sep_str)

    for r in rows:
        row_str = " | ".join([f"{str(r.get(key) if r.get(key) not in (None, '') else '-'):^{width}}" for key, _, width in disp_cols])
        print(row_str)

    print("=" * 145)
    print(f"Kompletní data uložena v: {csv_file}")
    print(f"Markdown přehled uložen v: {os.path.splitext(csv_file)[0] + '.md'}")
    print("=" * 145)


def print_summary_table(csv_file=None, model_version=None):
    """Vytiskne celou souhrnnou tabulku přehledně do konzole."""
    if model_version is None:
        model_version = int(os.getenv("ANTENNA_MODEL", "1"))

    if model_version == 2:
        return print_summary_table_model2(csv_file=csv_file)

    if csv_file is None:
        try:
            from postpro_utils import get_export_dir
            exp_dir = get_export_dir()
        except ImportError:
            exp_dir = "export"
        csv_file = os.path.join(exp_dir, "sweep_results.csv")

    if not os.path.exists(csv_file):
        print(f"Tabulka {csv_file} zatím neexistuje.")
        return

    with open(csv_file, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("Tabulka výsledků je prázdná.")
        return

    print("\n" + "=" * 125)
    print("KOMPLETNÍ SOUHRNNÁ TABULKA MODELU 1 (T-DĚLIČ):")
    disp_cols = [
        ('run_name', 'Krok', 18),
        ('inset_mm', 'Zanoření', 10),
        ('f0 [GHz]', 'f0 [GHz]', 10),
        ('S11_min [dB]', 'S11 [dB]', 10),
        ('BW_-10dB [MHz]', 'BW [MHz]', 10),
        ('Zin_Re [Ohm]', 'Zin_Re', 8),
        ('AR [dB]', 'AR [dB]', 8),
        ('Polarizace', 'Pol', 8),
        ('Gain_LHCP [dBi]', 'G_LHCP', 8),
        ('Gain_RHCP [dBi]', 'G_RHCP', 8),
    ]

    print("=" * 125)
    header_str = " | ".join([f"{title:^{width}}" for _, title, width in disp_cols])
    sep_str = "-+-".join(["-" * width for _, _, width in disp_cols])
    print(header_str)
    print(sep_str)

    for r in rows:
        row_str = " | ".join([f"{str(r.get(key) if r.get(key) not in (None, '') else '-'):^{width}}" for key, _, width in disp_cols])
        print(row_str)

    print("=" * 125)
    print(f"Kompletní data uložena v: {csv_file}")
    print(f"Markdown přehled uložen v: {os.path.splitext(csv_file)[0] + '.md'}")
    print("=" * 125)


# Zpětná kompatibilita pro main.py
def analyze_and_log_run(params, csv_filepath, run_name=None):
    """Zpětně kompatibilní volání z main.py."""
    output_dir = os.path.dirname(csv_filepath) or "data/postpro"
    return record_run(params, output_dir=output_dir, run_name=run_name)
