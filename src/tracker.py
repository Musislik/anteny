"""
tracker.py - Jednoduchý, robustní a transparentní systém pro sledování parametrů a výsledků simulací.
Nahrazuje těžkopádný MLflow: ukládá výsledky do přehledné CSV a Markdown tabulky v export/.
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
# 1. KONFIGURACE SLEDOVANÝCH VSTUPNÍCH PARAMETRŮ
# Zde lze jednoduše přidat jakýkoliv další parametr ze slovníku params
# ==============================================================================
TRACKED_PARAMS = [
    ('feed_inset', 'inset_mm', '{:.2f}'),
    ('patch_L', 'patch_L_mm', '{:.2f}'),
    ('patch_W', 'patch_W_mm', '{:.2f}'),
    ('freq_min', 'f_min_GHz', '{:.3f}'),
    ('freq_max', 'f_max_GHz', '{:.3f}'),
    ('amr_max_its', 'amr_its', '{:d}'),
    ('linear_tol', 'lin_tol', '{:.1e}'),
]

# ==============================================================================
# 2. DEFINICE VÝSTUPNÍCH METRIK PRO TABULKU
# ==============================================================================
TRACKED_METRICS = [
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


def extract_s11_metrics(s11_file, z0=50.0):
    """Extrahuje rezonanční frekvenci, minimum S11, šířku pásma a vstupní impedanci."""
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

        # Výpočet impedance z S11 při rezonanci f0 (Z0 typicky 50 Ohm)
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


def extract_farfield_metrics(farfield_file, target_freq=None, s11_min_db=None):
    """
    Vyhodnotí vyzařování z farfield-rE.csv:
    - Amplitudy LHCP a RHCP v ose vyzařování (+Z, theta=0)
    - Osový poměr (Axial Ratio v dB)
    - Dominantní polarizaci (LHCP / RHCP)
    - Odhad zisku v dBi
    """
    if not os.path.exists(farfield_file) or os.path.getsize(farfield_file) == 0:
        return {}

    try:
        data = np.loadtxt(farfield_file, delimiter=',', skiprows=1)
        if data.ndim == 1:
            data = data.reshape(1, -1)

        freqs = np.unique(data[:, 0])
        if len(freqs) == 0:
            return {}

        # Vybereme frekvenci nejblíže target_freq (rezonanci nebo 2.3325 GHz)
        eval_f = target_freq if target_freq is not None else DESIGN_FREQ_GHZ
        f_best = freqs[np.argmin(np.abs(freqs - eval_f))]
        f_data = data[data[:, 0] == f_best]

        # Boresight bod: theta nejblíže 0 (osa +Z)
        theta_col = f_data[:, 2]
        boresight_rows = f_data[np.abs(theta_col) < 1e-2]
        if len(boresight_rows) == 0:
            boresight_rows = f_data[np.argmin(np.abs(theta_col))]

        row = boresight_rows[0] if boresight_rows.ndim > 1 else boresight_rows
        ex = row[4] + 1j * row[5]
        ey = row[6] + 1j * row[7]

        # Rozklad na LHCP a RHCP fázory
        # Pro vlnu šířící se v ose +Z dle IEEE: E_LHCP = (Ex + j*Ey)/sqrt(2), E_RHCP = (Ex - j*Ey)/sqrt(2)
        e_lhcp = float(abs(ex + 1j * ey) / np.sqrt(2.0))
        e_rhcp = float(abs(ex - 1j * ey) / np.sqrt(2.0))

        # Osový poměr (Axial Ratio v dB)
        major = max(e_lhcp, e_rhcp) + min(e_lhcp, e_rhcp)
        minor = max(abs(e_lhcp - e_rhcp), 1e-9)
        ar_db = float(20.0 * np.log10(major / minor))

        polarization = "LHCP" if e_lhcp >= e_rhcp else "RHCP"

        # Odhad zisku v dBi (Poyntingův tok vs. vstupní výkon při 1 W excitaci)
        u_lhcp = (e_lhcp ** 2) / (2.0 * ETA_0)
        u_rhcp = (e_rhcp ** 2) / (2.0 * ETA_0)
        p_in = 1.0 - (10.0 ** (s11_min_db / 10.0)) if s11_min_db is not None else 1.0
        p_in = max(p_in, 0.01)  # zamezení dělení nulou
        gain_lhcp_lin = (4.0 * np.pi * u_lhcp) / p_in
        gain_lhcp_dbi = float(10.0 * np.log10(max(gain_lhcp_lin, 1e-4)))
        gain_rhcp_lin = (4.0 * np.pi * u_rhcp) / p_in
        gain_rhcp_dbi = float(10.0 * np.log10(max(gain_rhcp_lin, 1e-4)))

        return {
            'e_lhcp': e_lhcp,
            'e_rhcp': e_rhcp,
            'axial_ratio_db': ar_db,
            'polarization': polarization,
            'gain_lhcp_dbi': gain_lhcp_dbi,
            'gain_rhcp_dbi': gain_rhcp_dbi,
            'gain_dbi': gain_lhcp_dbi,
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
    Hlavní funkce pro zaznamenání běhu:
    1. Vypočte metriky z výstupních souborů
    2. Zapíše řádek do <export_dir>/sweep_results.csv a <export_dir>/sweep_results.md
    3. Vytiskne přehledný řádek přímo do terminálu
    """
    if results_dir is None:
        try:
            from postpro_utils import get_export_dir
            results_dir = get_export_dir()
        except ImportError:
            results_dir = "export"

    os.makedirs(results_dir, exist_ok=True)
    csv_file = os.path.join(results_dir, "sweep_results.csv")
    md_file = os.path.join(results_dir, "sweep_results.md")

    # 1. Extrakce výsledků z výstupních souborů
    s11_path = os.path.join(output_dir, "port-S.csv")
    farfield_path = os.path.join(output_dir, "farfield-rE.csv")

    port_z0 = float(params.get('port_impedance', 50.0))
    s11_metrics = extract_s11_metrics(s11_path, z0=port_z0)
    f0 = s11_metrics.get('f0_GHz')
    s11_min = s11_metrics.get('s11_min_dB')
    farfield_metrics = extract_farfield_metrics(farfield_path, target_freq=f0, s11_min_db=s11_min)

    # 2. Sestavení řádku dat (Vstupy + Výstupy)
    row = {'run_name': run_name or params.get('run_name', 'run')}

    # Vstupy
    for param_key, col_name, fmt in TRACKED_PARAMS:
        val = params.get(param_key)
        row[col_name] = format_value(val, fmt) if val is not None else ""

    # Výstupy
    for metric_key, col_name, fmt in TRACKED_METRICS:
        if metric_key in s11_metrics:
            val = s11_metrics[metric_key]
            row[col_name] = format_value(val, fmt) if val is not None else ""
        elif metric_key in farfield_metrics:
            val = farfield_metrics[metric_key]
            row[col_name] = format_value(val, fmt) if val is not None else ""
        else:
            row[col_name] = ""

    row['export_zip'] = export_zip or (f"{run_name}.zip" if run_name else "-")

    # 3. Zápis do CSV
    fieldnames = ['run_name'] + [col for _, col, _ in TRACKED_PARAMS] + [col for _, col, _ in TRACKED_METRICS] + ['export_zip']
    file_exists = os.path.exists(csv_file) and os.path.getsize(csv_file) > 0

    if file_exists:
        try:
            with open(csv_file, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                existing_headers = reader.fieldnames or []
                existing_rows = list(reader)

            if existing_headers != fieldnames:
                for r in existing_rows:
                    if 'Gain [dBi]' in r and 'Gain_LHCP [dBi]' not in r:
                        r['Gain_LHCP [dBi]'] = r.pop('Gain [dBi]')
                with open(csv_file, mode='w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                    writer.writeheader()
                    for r in existing_rows:
                        writer.writerow(r)
        except Exception as e:
            print(f"Upozornění při migraci CSV záhlaví: {e}")

    file_exists = os.path.exists(csv_file) and os.path.getsize(csv_file) > 0

    with open(csv_file, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    # 4. Aktualizace Markdown tabulky v export/sweep_results.md
    update_markdown_summary(csv_file, md_file)

    # 5. Výpis do terminálu
    print("\n" + "=" * 95)
    print("VÝSLEDKY SIMULAČNÍHO KROKU (Zaznamenáno do export/sweep_results.csv):")
    print("-" * 95)
    info_parts = [
        f"Krok: {row['run_name']}",
        f"Zanoření: {row['inset_mm']} mm" if row.get('inset_mm') else "",
        f"f0: {row['f0 [GHz]']} GHz" if row.get('f0 [GHz]') else "",
        f"S11: {row['S11_min [dB]']} dB" if row.get('S11_min [dB]') else "",
        f"BW: {row['BW_-10dB [MHz]']} MHz" if row.get('BW_-10dB [MHz]') else "",
    ]
    if row.get('Polarizace'):
        info_parts.append(f"Pol: {row['Polarizace']}")
    if row.get('AR [dB]'):
        info_parts.append(f"AR: {row['AR [dB]']} dB")
    if row.get('Gain_LHCP [dBi]'):
        info_parts.append(f"G_LHCP: {row['Gain_LHCP [dBi]']} dBi")
    elif row.get('Gain [dBi]'):
        info_parts.append(f"Gain: {row['Gain [dBi]']} dBi")
    if row.get('Gain_RHCP [dBi]'):
        info_parts.append(f"G_RHCP: {row['Gain_RHCP [dBi]']} dBi")

    print(" | ".join([p for p in info_parts if p]))
    print("=" * 95)

    return row


def update_markdown_summary(csv_file, md_file):
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
            "# 📊 Souhrnná tabulka výsledků simulací (Sweep Results)\n",
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


def print_summary_table(csv_file=None):
    """Vytiskne celou souhrnnou tabulku přehledně do konzole."""
    if csv_file is None:
        try:
            from postpro_utils import get_export_dir
            csv_file = os.path.join(get_export_dir(), "sweep_results.csv")
        except ImportError:
            csv_file = "export/sweep_results.csv"

    if not os.path.exists(csv_file):
        print(f"Tabulka {csv_file} zatím neexistuje.")
        return

    with open(csv_file, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("Tabulka výsledků je prázdná.")
        return

    print("\n" + "=" * 120)
    print("KOMPLETNÍ SOUHRNNÁ TABULKA VŠECH PROVEDENÝCH SIMULACÍ:")
    print("=" * 120)

    # Zvolíme klíčové sloupce pro konzoli, aby se vešly na šířku terminálu
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

    header_str = " | ".join([f"{title:^{width}}" for _, title, width in disp_cols])
    sep_str = "-+-".join(["-" * width for _, _, width in disp_cols])
    print(header_str)
    print(sep_str)

    for r in rows:
        if 'Gain_LHCP [dBi]' not in r and 'Gain [dBi]' in r:
            r['Gain_LHCP [dBi]'] = r['Gain [dBi]']
        row_str = " | ".join([f"{str(r.get(key) if r.get(key) not in (None, '') else '-'):^{width}}" for key, _, width in disp_cols])
        print(row_str)

    print("=" * 120)
    print(f"Kompletní data uložena v: {csv_file}")
    print(f"Markdown přehled uložen v: {os.path.splitext(csv_file)[0] + '.md'}")
    print("=" * 120)


# Zpětná kompatibilita pro main.py
def analyze_and_log_run(params, csv_filepath, run_name=None):
    """Zpětně kompatibilní volání z main.py."""
    output_dir = os.path.dirname(csv_filepath) or "data/postpro"
    return record_run(params, output_dir=output_dir, run_name=run_name)
