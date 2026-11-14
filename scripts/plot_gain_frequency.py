"""
plot_gain_frequency.py - Výpočet a vykreslení závislosti zisku v ose vyzařování (+Z, theta=0°)
a polarizační čistoty (AR, XPD) na frekvenci z dat dálkového pole farfield-rE.csv (Palace FEM řešič).
"""

import os
import sys
import json
import argparse
import shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_CURRENT_DIR, ".."))
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
for _p in (_CURRENT_DIR, _SRC_DIR, _ROOT_DIR):
    if os.path.exists(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import _env  # noqa: F401
except ImportError:
    pass

from postpro_utils import load_env
from rf_calc import ETA_0, DESIGN_FREQ_GHZ


def find_farfield_csv(export_dir):
    """Najde soubor farfield-rE.csv v zadaném adresáři nebo v postpro podadresářích."""
    if export_dir is None:
        return None
    if os.path.isfile(export_dir) and export_dir.lower().endswith(".csv") and os.path.exists(export_dir):
        return os.path.abspath(export_dir)
        
    search_dirs = [
        export_dir,
        os.path.join(export_dir, "postpro"),
        os.path.join(export_dir, "..", "postpro"),
        os.path.join(export_dir, "data", "postpro"),
    ]
    for d in search_dirs:
        p = os.path.join(d, "farfield-rE.csv")
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return os.path.abspath(p)
    return None


def calculate_gain_frequency(farfield_source, p_in=None, num_ports=None, design_freq=None, params=None):
    """
    Vypočte frekvenční závislost zisku v ose vyzařování (+Z, theta=0°) a souvisejících metrik:
      - Fázory Ex, Ey, Ez a rozklad na kruhové složky E_LHCP, E_RHCP.
      - Vyzařovací intenzity U_LHCP, U_RHCP a celkovou U_tot = U_LHCP + U_RHCP.
      - Realizovaný zisk v ose: G_LHCP, G_RHCP, G_tot (vztažený k celkovému budicímu výkonu P_in).
      - Směrovost (Directivity): D_tot, D_LHCP, D_RHCP vztažené k integrálnímu vyzařovanému výkonu P_rad = 4*pi*u_avg.
      - Vyzařovací účinnost: eta_rad = P_rad / P_in.
      - Axiální poměr v ose: AR(f) = 20*log10((|E_LHCP| + |E_RHCP|) / ||E_LHCP| - |E_RHCP||).
      - Potlačení křížové polarizace: XPD(f) = G_LHCP - G_RHCP [dB].

    :param farfield_source: Cesta k farfield-rE.csv nebo načtený pd.DataFrame / np.ndarray
    :param p_in: Celkový vstupní výkon ve Wattech (výchozí: odvozen z num_ports * 0.5 W)
    :param num_ports: Počet buzených portů (1 pro model s integrovaným děličem, 2 pro dvouportový model)
    :param design_freq: Návrhová frekvence v GHz (výchozí: DESIGN_FREQ_GHZ = 2.3325 GHz)
    :param params: Slovník parametrů modelu (pro detekci modelu a počtu portů)
    :return: Slovník s vypočtenými poli a metrikami na všech frekvencích a na návrhové frekvenci.
    """
    if design_freq is None:
        design_freq = DESIGN_FREQ_GHZ

    # 1. Načtení dat
    csv_dir = None
    if isinstance(farfield_source, str):
        if not os.path.exists(farfield_source) or os.path.getsize(farfield_source) == 0:
            raise FileNotFoundError(f"Soubor s dálkovým polem nebyl nalezen nebo je prázdný: {farfield_source}")
        csv_dir = os.path.dirname(os.path.abspath(farfield_source))
        df = pd.read_csv(farfield_source)
    elif isinstance(farfield_source, pd.DataFrame):
        df = farfield_source.copy()
    elif isinstance(farfield_source, np.ndarray):
        df = pd.DataFrame(farfield_source)
    else:
        raise ValueError(f"Neplatný formát farfield_source: {type(farfield_source)}")

    if df.shape[1] < 10:
        raise ValueError(f"Tabulka dálkového pole musí mít alespoň 10 sloupců, má: {df.shape[1]}")

    # Detekce počtu buzených portů / P_in
    if p_in is None:
        if num_ports is None:
            # Zkusíme detekovat z params nebo sourozeneckých souborů
            res_params = params or {}
            model_num = int(res_params.get("antenna_model", 0))
            if model_num in (2, 3, 5, 6):
                num_ports = 2
            elif model_num in (1, 4):
                num_ports = 1
            elif csv_dir:
                p1_ff = os.path.join(csv_dir, "farfield_p1-rE.csv")
                p2_ff = os.path.join(csv_dir, "farfield_p2-rE.csv")
                if os.path.isfile(p1_ff) and os.path.isfile(p2_ff):
                    num_ports = 2

            if num_ports is None:
                # Kontrola počtu unikátních exc v datech
                exc_col = df.iloc[:, 1]
                if exc_col.nunique() > 1:
                    num_ports = exc_col.nunique()
                elif model_num in (1, 4):
                    num_ports = 1
                else:
                    num_ports = 2  # Standardní výchozí hodnota pro dvouportové modely
        p_in = float(num_ports) * 0.5

    p_in = max(float(p_in), 1e-4)

    # 2. Sloučení vícenásobných excitačních módů koherentní superpozicí
    cols = list(df.columns)
    f_col = cols[0]
    th_col = cols[2]
    ph_col = cols[3]

    if df.iloc[:, 1].nunique() > 1:
        work = df.copy()
        work["_f_key"] = np.round(work.iloc[:, 0].to_numpy(dtype=float), 8)
        work["_th_key"] = np.round(work.iloc[:, 2].to_numpy(dtype=float), 6)
        work["_ph_key"] = np.round(work.iloc[:, 3].to_numpy(dtype=float), 6)
        agg_spec = {f_col: "first", th_col: "first", ph_col: "first"}
        for col_name in cols[4:10]:
            agg_spec[col_name] = "sum"
        agg_df = work.groupby(["_f_key", "_th_key", "_ph_key"], as_index=False, sort=False).agg(agg_spec)
        f_vals = agg_df[f_col].to_numpy(dtype=float)
        th_deg = agg_df[th_col].to_numpy(dtype=float)
        ph_deg = agg_df[ph_col].to_numpy(dtype=float)
        e_vals = agg_df[cols[4:10]].to_numpy(dtype=float)
    else:
        f_vals = df[f_col].to_numpy(dtype=float)
        th_deg = df[th_col].to_numpy(dtype=float)
        ph_deg = df[ph_col].to_numpy(dtype=float)
        e_vals = df[cols[4:10]].to_numpy(dtype=float)

    th_rad = np.deg2rad(th_deg)
    ph_rad = np.deg2rad(ph_deg)

    ex = e_vals[:, 0] + 1j * e_vals[:, 1]
    ey = e_vals[:, 2] + 1j * e_vals[:, 3]
    ez = e_vals[:, 4] + 1j * e_vals[:, 5]

    # Sférické složky E_theta a E_phi pro celou kouli (pro výpočet P_rad a směrovosti)
    e_th = (ex * np.cos(ph_rad) + ey * np.sin(ph_rad)) * np.cos(th_rad) - ez * np.sin(th_rad)
    e_ph = -ex * np.sin(ph_rad) + ey * np.cos(ph_rad)
    u_sphere = (np.abs(e_th)**2 + np.abs(e_ph)**2) / (2.0 * ETA_0)

    # 3. Výpočet pro jednotlivé frekvence
    freqs = np.unique(f_vals)
    freqs.sort()

    res_freqs = []
    res_g_tot = []
    res_g_lhcp = []
    res_g_rhcp = []
    res_d_tot = []
    res_d_lhcp = []
    res_d_rhcp = []
    res_ar_db = []
    res_xpd_db = []
    res_eta_rad = []
    res_p_rad = []
    res_u_avg = []

    for f in freqs:
        f_mask = np.isclose(f_vals, f, atol=1e-7)
        th_sub = th_deg[f_mask]
        
        # Boresight bod (+Z, theta = 0°)
        b_idx_local = np.where(np.abs(th_sub) < 1e-3)[0]
        if len(b_idx_local) == 0:
            b_idx_local = [int(np.argmin(np.abs(th_sub)))]
            
        f_indices = np.where(f_mask)[0]
        boresight_global_idx = f_indices[b_idx_local[0]]

        ex_0 = ex[boresight_global_idx]
        ey_0 = ey[boresight_global_idx]

        # Rozklad na LHCP a RHCP fázory dle standardu IEEE (+Z směr šíření):
        # E_LHCP = (Ex + j*Ey) / sqrt(2)
        # E_RHCP = (Ex - j*Ey) / sqrt(2)
        e_lhcp = (ex_0 + 1j * ey_0) / np.sqrt(2.0)
        e_rhcp = (ex_0 - 1j * ey_0) / np.sqrt(2.0)

        mag_l = float(np.abs(e_lhcp))
        mag_r = float(np.abs(e_rhcp))

        u_lhcp = (mag_l**2) / (2.0 * ETA_0)
        u_rhcp = (mag_r**2) / (2.0 * ETA_0)
        u_tot = u_lhcp + u_rhcp

        # Průměrná vyzařovací intenzita po kouli
        u_sphere_sub = u_sphere[f_mask]
        is_boresight_only = (len(u_sphere_sub) == 1) or np.all(np.abs(th_sub) < 1e-3)
        if is_boresight_only:
            u_avg_f = u_tot
            p_rad_f = p_in
            eta_rad_f = 1.0
        else:
            u_avg_f = max(float(np.mean(u_sphere_sub)), 1e-30)
            p_rad_f = 4.0 * np.pi * u_avg_f
            eta_rad_f = float(p_rad_f / p_in)

        # Realizovaný zisk v ose vyzařování [dBi]
        g_lhcp = float(10.0 * np.log10(max(4.0 * np.pi * u_lhcp / p_in, 1e-12)))
        g_rhcp = float(10.0 * np.log10(max(4.0 * np.pi * u_rhcp / p_in, 1e-12)))
        g_tot = float(10.0 * np.log10(max(4.0 * np.pi * u_tot / p_in, 1e-12)))

        # Směrovost v ose vyzařování [dBi]
        d_lhcp = float(10.0 * np.log10(max(u_lhcp / u_avg_f, 1e-12)))
        d_rhcp = float(10.0 * np.log10(max(u_rhcp / u_avg_f, 1e-12)))
        d_tot = float(10.0 * np.log10(max(u_tot / u_avg_f, 1e-12)))

        # Osový poměr AR (Axial Ratio v dB)
        major = mag_l + mag_r
        minor = max(abs(mag_l - mag_r), 1e-9)
        ar_db = float(20.0 * np.log10(major / minor))

        # Křížová polarizační diskriminace XPD [dB]
        xpd_db = float(g_lhcp - g_rhcp)

        res_freqs.append(f)
        res_g_tot.append(g_tot)
        res_g_lhcp.append(g_lhcp)
        res_g_rhcp.append(g_rhcp)
        res_d_tot.append(d_tot)
        res_d_lhcp.append(d_lhcp)
        res_d_rhcp.append(d_rhcp)
        res_ar_db.append(ar_db)
        res_xpd_db.append(xpd_db)
        res_eta_rad.append(eta_rad_f)
        res_p_rad.append(p_rad_f)
        res_u_avg.append(u_avg_f)

    res_freqs = np.array(res_freqs)
    res_g_tot = np.array(res_g_tot)
    res_g_lhcp = np.array(res_g_lhcp)
    res_g_rhcp = np.array(res_g_rhcp)
    res_d_tot = np.array(res_d_tot)
    res_d_lhcp = np.array(res_d_lhcp)
    res_d_rhcp = np.array(res_d_rhcp)
    res_ar_db = np.array(res_ar_db)
    res_xpd_db = np.array(res_xpd_db)
    res_eta_rad = np.array(res_eta_rad)

    # Maximum LHCP zisku
    max_idx = int(np.argmax(res_g_lhcp))
    f_max_lhcp = float(res_freqs[max_idx])
    g_max_lhcp = float(res_g_lhcp[max_idx])
    ar_at_max = float(res_ar_db[max_idx])
    xpd_at_max = float(res_xpd_db[max_idx])

    # Hodnoty na návrhové frekvenci (lineární interpolace pro přesné stanovení)
    design_interp = {
        'freq_ghz': design_freq,
        'g_tot_dbi': float(np.interp(design_freq, res_freqs, res_g_tot)),
        'g_lhcp_dbi': float(np.interp(design_freq, res_freqs, res_g_lhcp)),
        'g_rhcp_dbi': float(np.interp(design_freq, res_freqs, res_g_rhcp)),
        'd_tot_dbi': float(np.interp(design_freq, res_freqs, res_d_tot)),
        'd_lhcp_dbi': float(np.interp(design_freq, res_freqs, res_d_lhcp)),
        'd_rhcp_dbi': float(np.interp(design_freq, res_freqs, res_d_rhcp)),
        'ar_db': float(np.interp(design_freq, res_freqs, res_ar_db)),
        'xpd_db': float(np.interp(design_freq, res_freqs, res_xpd_db)),
        'eta_rad_pct': float(np.interp(design_freq, res_freqs, res_eta_rad) * 100.0),
    }

    return {
        'freqs': res_freqs,
        'g_tot': res_g_tot,
        'g_lhcp': res_g_lhcp,
        'g_rhcp': res_g_rhcp,
        'd_tot': res_d_tot,
        'd_lhcp': res_d_lhcp,
        'd_rhcp': res_d_rhcp,
        'ar_db': res_ar_db,
        'xpd_db': res_xpd_db,
        'eta_rad': res_eta_rad,
        'p_in': p_in,
        'f_gain_max_lhcp_ghz': f_max_lhcp,
        'gain_max_lhcp_dbi': g_max_lhcp,
        'ar_at_max_gain_db': ar_at_max,
        'xpd_at_max_gain_db': xpd_at_max,
        'design_freq_ghz': design_freq,
        'design_metrics': design_interp,
    }


def plot_gain_frequency(target_dir, output_png=None, params=None):
    """
    Vygeneruje přehledný 2-panelový graf závislosti zisku v ose a osového poměru na frekvenci:
      - Horní panel: Realizovaný zisk v ose (+Z, theta=0°) G_LHCP, G_tot, G_RHCP [dBi]
                     s vyznačením maxima a návrhové frekvence 2.3325 GHz.
      - Spodní panel: Osový poměr v ose AR(f) [dB] se zeleně vystínovanou oblastí AR <= 3 dB
                      a potlačení křížové polarizace XPD = G_LHCP - G_RHCP [dB] na vedlejší ose.
    Uloží graf do output_png a kopii do podadresáře grafy/graf_zisk_frekvence.png.
    """
    csv_path = find_farfield_csv(target_dir)
    if not csv_path:
        print(f"[CHYBA] Soubor farfield-rE.csv nebyl v {target_dir} nalezen.")
        return None

    # Zjištění parametrů modelu
    res_params = {}
    if params:
        res_params.update(params)
    params_candidates = [
        os.path.join(target_dir, "params.json"),
        os.path.join(target_dir, "..", "params.json"),
        os.path.join(os.path.dirname(csv_path), "params.json"),
        os.path.join(os.path.dirname(csv_path), "..", "params.json"),
    ]
    for pp in params_candidates:
        if os.path.exists(pp) and os.path.getsize(pp) > 0:
            try:
                with open(pp, "r", encoding="utf-8") as pf:
                    loaded = json.load(pf)
                    for k, v in loaded.items():
                        if k not in res_params or res_params[k] is None:
                            res_params[k] = v
                break
            except Exception:
                pass

    design_f = float(res_params.get("design_freq_ghz", DESIGN_FREQ_GHZ))

    # Výpočet metrik
    data = calculate_gain_frequency(csv_path, design_freq=design_f, params=res_params)

    freqs = data['freqs']
    g_lhcp = data['g_lhcp']
    g_tot = data['g_tot']
    g_rhcp = data['g_rhcp']
    ar_db = data['ar_db']
    xpd_db = data['xpd_db']
    dm = data['design_metrics']

    # Příprava cest pro uložení
    if output_png is None:
        try:
            _, data_dir = load_env()
            output_png = os.path.join(data_dir, "graf_zisk_frekvence.png")
        except Exception:
            output_png = os.path.join(target_dir, "graf_zisk_frekvence.png")

    output_png = os.path.abspath(output_png)
    os.makedirs(os.path.dirname(output_png) or ".", exist_ok=True)

    # ------------------ VYKRESLENÍ GRAFU ------------------
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(10, 8), sharex=True,
        gridspec_kw={'height_ratios': [1.25, 1.0]}
    )

    # --- HORNÍ PANEL: Realizovaný zisk v ose vyzařování ---
    ax1.plot(freqs, g_lhcp, color='#0055d4', lw=2.4, label=r'$G_{\mathrm{LHCP}}$ (hlavní polarizace)')
    ax1.plot(freqs, g_tot, color='#111111', ls=':', lw=1.8, label=r'$G_{\mathrm{tot}}$ (celkový zisk)')
    ax1.plot(freqs, g_rhcp, color='#d32f2f', ls='--', lw=1.8, label=r'$G_{\mathrm{RHCP}}$ (křížová polarizace)')

    # Vyznačení návrhové frekvence f0
    if freqs.min() <= design_f <= freqs.max():
        ax1.axvline(design_f, color='gray', linestyle='-.', lw=1.3, alpha=0.85,
                    label=rf'Návrhová frekvence $f_0 = {design_f:.4f}\ \mathrm{{GHz}}$')
        ax1.scatter([design_f], [dm['g_lhcp_dbi']], color='#0055d4', s=45, zorder=5)
        ax1.scatter([design_f], [dm['g_tot_dbi']], color='#111111', s=40, zorder=5)

    # Vyznačení maxima LHCP zisku
    f_max = data['f_gain_max_lhcp_ghz']
    g_max = data['gain_max_lhcp_dbi']
    ax1.scatter([f_max], [g_max], color='#e65100', s=60, zorder=6, marker='o')
    
    # Anotace maxima
    ax1.annotate(
        rf"Max $G_{{\mathrm{{LHCP}}}} = {g_max:.2f}\ \mathrm{{dBi}}$ ({f_max:.3f} GHz)",
        xy=(f_max, g_max),
        xytext=(0.04, 0.93),
        textcoords='axes fraction',
        verticalalignment='top',
        fontsize=9.5,
        fontweight='bold',
        bbox=dict(boxstyle="round,pad=0.4", fc="#fff9c4", ec="#fbc02d", alpha=0.95),
        arrowprops=dict(arrowstyle="->", color="#e65100", lw=1.3, connectionstyle="arc3,rad=-0.15")
    )

    # Textový panel s přesnými hodnotami na návrhové frekvenci
    info_text = (
        rf"$\mathbf{{Při\ f_0 = {design_f:.4f}\ GHz:}}$" + "\n"
        rf"$G_{{\mathrm{{LHCP}}}} = {dm['g_lhcp_dbi']:+.2f}\ \mathrm{{dBi}}$  |  $G_{{\mathrm{{tot}}}} = {dm['g_tot_dbi']:+.2f}\ \mathrm{{dBi}}$" + "\n"
        rf"$D_{{\mathrm{{LHCP}}}} = {dm['d_lhcp_dbi']:+.2f}\ \mathrm{{dBi}}$  |  $\eta_{{\mathrm{{rad}}}} = {dm['eta_rad_pct']:.1f}\%$" + "\n"
        rf"$\mathrm{{AR}} = {dm['ar_db']:.2f}\ \mathrm{{dB}}$  |  $\mathrm{{XPD}} = {dm['xpd_db']:.1f}\ \mathrm{{dB}}$"
    )
    ax1.annotate(
        info_text,
        xy=(0.96, 0.93),
        xycoords='axes fraction',
        verticalalignment='top',
        horizontalalignment='right',
        fontsize=9.0,
        bbox=dict(boxstyle="round,pad=0.45", fc="#f0f7ff", ec="#0055d4", alpha=0.92)
    )

    # Rozsahy a popisky horního panelu
    y_min_g = max(min(g_rhcp.min(), -25.0) - 2.0, -32.0)
    y_max_g = max(g_tot.max(), g_lhcp.max()) + 1.8
    ax1.set_ylim([y_min_g, y_max_g])
    ax1.set_ylabel("Realizovaný zisk [dBi]", fontsize=11, fontweight='bold')
    ax1.set_title(r"Zisk antény v ose vyzařování ($+Z$, $\theta = 0^\circ$) vs. frekvence",
                  fontsize=12, fontweight='bold', pad=10)
    ax1.grid(True, linestyle=':', alpha=0.7)
    ax1.legend(loc='lower left', fontsize=9.0, framealpha=0.9)

    # --- SPODNÍ PANEL: Osový poměr AR a potlačení křížové polarizace XPD ---
    ax2.plot(freqs, ar_db, color='#7b1fa2', lw=2.2, label=r'Osový poměr $\mathrm{AR}$')
    ax2.axhline(3.0, color='red', linestyle='--', lw=1.5, label='Mez 3 dB (kruhová polarizace)')
    ax2.axhspan(0.0, 3.0, color='#4caf50', alpha=0.18, label=r'Oblast CP ($\mathrm{AR} \leq 3\ \mathrm{dB}$)')

    if freqs.min() <= design_f <= freqs.max():
        ax2.axvline(design_f, color='gray', linestyle='-.', lw=1.3, alpha=0.85)
        ax2.scatter([design_f], [dm['ar_db']], color='#7b1fa2', s=45, zorder=5)

    ar_max_lim = max(6.0, float(np.ceil(np.max(ar_db) + 1.0)))
    ax2.set_ylim([0.0, ar_max_lim])
    ax2.set_ylabel(r"Osový poměr $\mathrm{AR}$ [dB]", fontsize=11, fontweight='bold', color='#4a148c')
    ax2.tick_params(axis='y', labelcolor='#4a148c')
    ax2.grid(True, linestyle=':', alpha=0.7)

    # Vedlejší osa pro XPD
    ax2_twin = ax2.twinx()
    ax2_twin.plot(freqs, xpd_db, color='#00838f', ls='-.', lw=1.9,
                  label=r'Potlačení kříž. pol. $\mathrm{XPD} = G_{\mathrm{LHCP}} - G_{\mathrm{RHCP}}$')
    
    if freqs.min() <= design_f <= freqs.max():
        ax2_twin.scatter([design_f], [dm['xpd_db']], color='#00838f', s=40, zorder=5)

    xpd_min_lim = max(0.0, float(np.floor(np.min(xpd_db) - 2.0)))
    xpd_max_lim = float(np.ceil(np.max(xpd_db) + 3.0))
    ax2_twin.set_ylim([xpd_min_lim, xpd_max_lim])
    ax2_twin.set_ylabel(r"Potlačení křížové polarizace $\mathrm{XPD}$ [dB]",
                        fontsize=11, fontweight='bold', color='#00695c')
    ax2_twin.tick_params(axis='y', labelcolor='#00695c')

    # Společná legenda pro spodní panel
    lines_ar, labels_ar = ax2.get_legend_handles_labels()
    lines_xpd, labels_xpd = ax2_twin.get_legend_handles_labels()
    ax2.legend(lines_ar + lines_xpd, labels_ar + labels_xpd, loc='upper right', fontsize=8.8, framealpha=0.92)

    ax2.set_xlabel("Frekvence [GHz]", fontsize=11, fontweight='bold')
    ax2.set_xlim([freqs.min(), freqs.max()])

    plt.tight_layout()
    plt.savefig(output_png, dpi=200)
    plt.close(fig)
    print(f"Uložen přehledový graf zisku v ose: {output_png}")

    # Uložení kopií do složek grafy/
    grafy_dirs = set()
    out_dir = os.path.dirname(output_png)
    grafy_dirs.add(os.path.join(out_dir, "grafy"))
    grafy_dirs.add(os.path.join(target_dir, "grafy"))

    try:
        _, env_data_dir = load_env()
        if os.path.exists(env_data_dir):
            grafy_dirs.add(os.path.join(env_data_dir, "grafy"))
            # Také hlavní kopie do data_dir pokud se liší
            main_copy = os.path.join(env_data_dir, "graf_zisk_frekvence.png")
            if os.path.abspath(main_copy) != os.path.abspath(output_png):
                shutil.copy2(output_png, main_copy)
    except Exception:
        pass

    for g_dir in grafy_dirs:
        try:
            os.makedirs(g_dir, exist_ok=True)
            dst_p = os.path.join(g_dir, "graf_zisk_frekvence.png")
            if os.path.abspath(dst_p) != os.path.abspath(output_png):
                shutil.copy2(output_png, dst_p)
                print(f"Kopie grafu uložena do: {dst_p}")
        except Exception as e:
            print(f"Upozornění při ukládání kopie do {g_dir}: {e}")

    # Výpis klíčových hodnot do konzole
    print("=" * 68)
    print("PŘEHLED ZISKU A SMĚROVOSTI V OSE VYZAŘOVÁNÍ (+Z):")
    print(f"  Návrhová frekvence:       {design_f:.4f} GHz")
    print(f"  Celkový realizovaný zisk: G_tot  = {dm['g_tot_dbi']:+.2f} dBi")
    print(f"  Hlavní polarizace (LHCP): G_LHCP = {dm['g_lhcp_dbi']:+.2f} dBi")
    print(f"  Křížová polarizace (RHCP):G_RHCP = {dm['g_rhcp_dbi']:+.2f} dBi")
    print(f"  Směrovost hlavní pol.:    D_LHCP = {dm['d_lhcp_dbi']:+.2f} dBi")
    print(f"  Směrovost celková:        D_tot  = {dm['d_tot_dbi']:+.2f} dBi")
    print(f"  Vyzařovací účinnost:      eta    = {dm['eta_rad_pct']:.1f}%")
    print(f"  Osový poměr v ose:        AR     = {dm['ar_db']:.2f} dB (hranice CP <= 3 dB)")
    print(f"  Potlačení kříž. pol.:     XPD    = {dm['xpd_db']:.1f} dB")
    print(f"  Maximum LHCP zisku:       {g_max:.2f} dBi při {f_max:.3f} GHz")
    print("=" * 68)

    data['output_png'] = output_png
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Výpočet a vykreslení závislosti zisku v ose vyzařování a polarizační čistoty na frekvenci z farfield-rE.csv"
    )
    parser.add_argument(
        "target_dir",
        nargs="?",
        default=None,
        help="Cesta k exportní složce se simulací (výchozí: DATA_DIR/postpro nebo DATA_DIR z .env)",
    )
    parser.add_argument(
        "--output",
        "-o",
        dest="output",
        default=None,
        help="Cesta k výstupnímu obrázku (výchozí: data/graf_zisk_frekvence.png)",
    )
    args = parser.parse_args()

    target = args.target_dir
    if target is None:
        try:
            _, data_dir = load_env()
            postpro_dir = os.path.join(data_dir, "postpro")
            if os.path.exists(os.path.join(postpro_dir, "farfield-rE.csv")):
                target = postpro_dir
            elif os.path.exists(os.path.join(data_dir, "farfield-rE.csv")):
                target = data_dir
            else:
                target = "."
        except Exception:
            target = "."

    res = plot_gain_frequency(target, output_png=args.output)
    if res is None:
        sys.exit(1)
