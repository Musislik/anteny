"""
plot_deembedding.py - Analytický de-embedding impedančních skoků a vyhodnocení referenčních rovin
Generuje diagnostický graf 'graf_impedance_skoky.png':
  - Pravidlo 1: Jedno měřicí místo = jeden graf pro impedanci (Re a Im) a jeden graf pro činitel odrazu (|Gamma| v dB).
    * RP1 (Port): Graf Zin (Re a Im s nulovou osou a 100 Ω referencí) + Graf S11 v dB (s limitem -10 dB a křivkou izolace S21).
    * RP2 (Svorka transformátoru): Graf Z_RP2 (Re a Im s referencí 100 Ω a nulou) + Graf lokálního |Gamma_RP2| v dB.
    * RP3 (Vstup do flíčku): Graf Z_patch (Re a Im s referencí 140 Ω a nulou pro rezonanci f0) + Graf lokálního |Gamma_patch| v dB.
  - Pravidlo 2: Pokud je buzen pouze jeden port (DRIVEN_PORT=1 nebo 2):
    * Kreslí se VÝHRADNĚ aktivní cesta! Pasivní port se v grafech impedance ani de-embeddingu VŮBEC nezobrazuje.
    * Jediné, co se z druhého portu zobrazí, je křivka přeslechu/izolace S21 v dB v grafu RP1 pro přehled o úniku energie.
  - Pravidlo 3: V případě buzení oběma porty (DRIVEN_PORT=all):
    * Samostatné zobrazení portů rozdělených do přehledných sloupců (Port 1 vlevo, Port 2 vpravo), případně přehledně oddělené křivky.
"""

import os
import sys
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Zajištění přístupu k src modulům (rf_calc)
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_CURRENT_DIR, ".."))
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
for p in (_ROOT_DIR, _SRC_DIR, _CURRENT_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from rf_calc import calculate_deembedding_model3, DESIGN_FREQ_GHZ


def _load_simulation_s_params(export_dir, driven_port=None):
    """
    Vyhledá a načte S-parametry nebo napětí/proudy ze simulačních souborů
    (port-S.csv nebo port-V.csv) v zadaném adresáři nebo podsložce postpro.
    Vrací: (freqs, s11_complex, s22_complex, iso_complex, detected_driven_port)
    """
    search_dirs = [export_dir, os.path.join(export_dir, "postpro")]
    s_path = None
    v_path = None

    for d in search_dirs:
        sp = os.path.join(d, "port-S.csv")
        if os.path.exists(sp) and os.path.getsize(sp) > 0 and s_path is None:
            s_path = sp
        vp = os.path.join(d, "port-V.csv")
        if os.path.exists(vp) and os.path.getsize(vp) > 0 and v_path is None:
            v_path = vp

    freqs = None
    s11_complex = None
    s22_complex = None
    s21_complex = None
    s12_complex = None

    # Normalizace parametru driven_port
    dp_hint = str(driven_port).lower().strip() if driven_port is not None else None

    # 1. Pokus z port-S.csv
    if s_path:
        try:
            with open(s_path, 'r', encoding='utf-8') as f:
                s_header = [h.strip().lower() for h in f.readline().split(',')]
            data = np.loadtxt(s_path, delimiter=',', skiprows=1)
            if data.ndim == 1:
                data = data.reshape(1, -1)
            freqs = data[:, 0]

            def find_idx(patterns):
                for idx, col in enumerate(s_header):
                    for pat in patterns:
                        if pat in col:
                            return idx
                return None

            s11_idx = find_idx(["|s[1][1]|", "s[1][1]", "s[1,1]", "|s11|"])
            s11_deg_idx = find_idx(["arg(s[1][1])", "arg(s[1,1])", "arg(s11)", "phase(s[1][1])"])
            s22_idx = find_idx(["|s[2][2]|", "s[2][2]", "s[2,2]", "|s22|"])
            s22_deg_idx = find_idx(["arg(s[2][2])", "arg(s[2,2])", "arg(s22)", "phase(s[2][2])"])
            s21_idx = find_idx(["|s[2][1]|", "s[2][1]", "s[2,1]", "|s21|"])
            s21_deg_idx = find_idx(["arg(s[2][1])", "arg(s[2,1])", "arg(s21)", "phase(s[2][1])"])
            s12_idx = find_idx(["|s[1][2]|", "s[1][2]", "s[1,2]", "|s12|"])
            s12_deg_idx = find_idx(["arg(s[1][2])", "arg(s[1,2])", "arg(s12)", "phase(s[1][2])"])

            # Fallback pouze pokud chybí oba odrazy a soubor má obecné sloupce
            if s11_idx is None and s22_idx is None and data.shape[1] >= 2:
                if dp_hint == "2":
                    s22_idx = 1
                    s22_deg_idx = 2 if data.shape[1] >= 3 else None
                else:
                    s11_idx = 1
                    s11_deg_idx = 2 if data.shape[1] >= 3 else None

            if s11_idx is not None and s11_idx < data.shape[1]:
                s11_db = data[:, s11_idx]
                deg1 = data[:, s11_deg_idx] if s11_deg_idx is not None and s11_deg_idx < data.shape[1] else np.zeros_like(s11_db)
                s11_complex = (10.0 ** (s11_db / 20.0)) * np.exp(1j * np.deg2rad(deg1))

            if s22_idx is not None and s22_idx < data.shape[1]:
                s22_db = data[:, s22_idx]
                deg2 = data[:, s22_deg_idx] if s22_deg_idx is not None and s22_deg_idx < data.shape[1] else np.zeros_like(s22_db)
                s22_complex = (10.0 ** (s22_db / 20.0)) * np.exp(1j * np.deg2rad(deg2))

            if s21_idx is not None and s21_idx < data.shape[1]:
                s21_db = data[:, s21_idx]
                deg21 = data[:, s21_deg_idx] if s21_deg_idx is not None and s21_deg_idx < data.shape[1] else np.zeros_like(s21_db)
                s21_complex = (10.0 ** (s21_db / 20.0)) * np.exp(1j * np.deg2rad(deg21))

            if s12_idx is not None and s12_idx < data.shape[1]:
                s12_db = data[:, s12_idx]
                deg12 = data[:, s12_deg_idx] if s12_deg_idx is not None and s12_deg_idx < data.shape[1] else np.zeros_like(s12_db)
                s12_complex = (10.0 ** (s12_db / 20.0)) * np.exp(1j * np.deg2rad(deg12))

        except Exception as e:
            print(f"Upozornění při načítání {s_path}: {e}")

    # 2. Pokus z port-V.csv (pokud chybí S-parametry)
    if (s11_complex is None and s22_complex is None) and v_path:
        try:
            with open(v_path, 'r', encoding='utf-8') as f:
                v_header = [h.strip().lower() for h in f.readline().split(',')]
            v_data = np.loadtxt(v_path, delimiter=',', skiprows=1)
            if v_data.ndim == 1:
                v_data = v_data.reshape(1, -1)

            if freqs is None:
                freqs = v_data[:, 0]

            has_vinc1 = any("v_inc[1]" in h for h in v_header)
            has_vinc2 = any("v_inc[2]" in h for h in v_header)

            if has_vinc1 and has_vinc2 and v_data.shape[1] >= 7:
                # Oba porty
                v_inc1 = v_data[:, 1]
                v_inc2 = v_data[:, 2]
                v1 = v_data[:, 3] + 1j * v_data[:, 4]
                v2 = v_data[:, 5] + 1j * v_data[:, 6]
                s11_complex = (v1 - v_inc1) / np.where(np.abs(v_inc1) < 1e-12, 1e-12, v_inc1)
                s22_complex = (v2 - v_inc2) / np.where(np.abs(v_inc2) < 1e-12, 1e-12, v_inc2)
            elif has_vinc1 and not has_vinc2 and v_data.shape[1] >= 6:
                # Jen Port 1
                v_inc1 = v_data[:, 1]
                v1 = v_data[:, 2] + 1j * v_data[:, 3]
                v2 = v_data[:, 4] + 1j * v_data[:, 5]
                s11_complex = (v1 - v_inc1) / np.where(np.abs(v_inc1) < 1e-12, 1e-12, v_inc1)
                s21_complex = v2 / np.where(np.abs(v_inc1) < 1e-12, 1e-12, v_inc1)
            elif has_vinc2 and not has_vinc1 and v_data.shape[1] >= 6:
                # Jen Port 2
                v_inc2 = v_data[:, 1]
                v1 = v_data[:, 2] + 1j * v_data[:, 3]
                v2 = v_data[:, 4] + 1j * v_data[:, 5]
                s22_complex = (v2 - v_inc2) / np.where(np.abs(v_inc2) < 1e-12, 1e-12, v_inc2)
                s12_complex = v1 / np.where(np.abs(v_inc2) < 1e-12, 1e-12, v_inc2)
        except Exception as e:
            print(f"Upozornění při načítání {v_path}: {e}")

    # Určení přeslechové/izolační křivky (reciprocita S21 ≈ S12)
    iso_complex = s21_complex if s21_complex is not None else s12_complex

    # Auto-detekce buzeného portu
    if s11_complex is not None and s22_complex is not None:
        if dp_hint in ("1", "2"):
            detected_driven_port = dp_hint
        else:
            detected_driven_port = "all"
    elif s22_complex is not None:
        detected_driven_port = "2"
    else:
        detected_driven_port = "1"

    # Pravidlo 2: Pokud je buzen pouze jeden port, druhý pasivní port se VŮBEC nevrací
    if detected_driven_port == "1":
        s22_complex = None
    elif detected_driven_port == "2":
        s11_complex = None

    return freqs, s11_complex, s22_complex, iso_complex, detected_driven_port


def _resolve_deembedding_params(export_dir, explicit_params=None):
    """
    Bezpečně odvodí parametry modelu z předaného slovníku, params.json,
    config.json nebo výchozích návrhových hodnot.
    """
    params = {}
    if explicit_params:
        params.update(explicit_params)

    # 1. Zkusit načíst params.json
    params_candidates = [
        os.path.join(export_dir, "params.json"),
        os.path.join(export_dir, "..", "params.json"),
        os.path.join(_ROOT_DIR, "data", "params.json")
    ]
    for p_path in params_candidates:
        if os.path.exists(p_path) and os.path.getsize(p_path) > 0:
            try:
                with open(p_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    for k, v in loaded.items():
                        if k not in params or params[k] is None:
                            params[k] = v
                break
            except Exception:
                pass

    # 2. Zkusit načíst config.json / config_resolved.json
    cfg_candidates = [
        os.path.join(export_dir, "config.json"),
        os.path.join(export_dir, "config_resolved.json"),
        os.path.join(_ROOT_DIR, "data", "config.json")
    ]
    for c_path in cfg_candidates:
        if os.path.exists(c_path) and os.path.getsize(c_path) > 0:
            try:
                with open(c_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)

                mats = cfg.get("Domains", {}).get("Materials", [])
                for m in mats:
                    if "Permittivity" in m and "eps_r" not in params:
                        params["eps_r"] = float(m["Permittivity"])
                    if "LossTan" in m and "tan_delta" not in params:
                        params["tan_delta"] = float(m["LossTan"])

                ports = cfg.get("Boundaries", {}).get("LumpedPort", [])
                if ports and isinstance(ports, list) and "port_impedance" not in params:
                    params["port_impedance"] = float(ports[0].get("R", 100.0))
                break
            except Exception:
                pass

    # 3. Výchozí hodnoty (Model 3)
    defaults = {
        'antenna_model': 3,
        'sub_h': 1.52,
        'eps_r': 4.3,
        'tan_delta': 0.02,
        'patch_L': 28.80,
        'patch_W': 28.80,
        'trans_w': 0.42,
        'feed_inset_b': 2.5,
        'feed_inset_l': 2.5,
        'inset_gap_b': 0.5,
        'inset_gap_l': 0.5,
        'sub_W': 80.0,
        'design_freq_ghz': DESIGN_FREQ_GHZ,
        'port_impedance': 100.0,
        'driven_port': os.getenv('DRIVEN_PORT', None),
    }
    for k, v in defaults.items():
        if k not in params or params[k] is None:
            params[k] = v

    return params


def _detect_resonance(freqs, im_z):
    """
    Detekuje přechod nulou Im{Z}=0 (rezonance flíčku) lineární interpolací.
    Vrací f0 v GHz nebo None.
    """
    if im_z is None or len(im_z) < 2:
        return None
    sign_changes = np.where(np.diff(np.sign(im_z)))[0]
    if len(sign_changes) > 0:
        idx0 = sign_changes[0]
        denom = im_z[idx0 + 1] - im_z[idx0]
        if abs(denom) > 1e-12:
            return freqs[idx0] - im_z[idx0] * (freqs[idx0 + 1] - freqs[idx0]) / denom
    return None


def plot_impedance_deembedding(export_dir, params=None, output_png=None, layout="split"):
    """
    Vypočte a vykreslí strukturovaný diagnostický graf de-embeddingu impedančních skoků.
    - Pravidlo 1: 1 měřicí místo = 1 graf pro impedanci (Re a Im) + 1 graf pro činitel odrazu (|Gamma| v dB).
    - Pravidlo 2: Pokud je buzen pouze jeden port (1 nebo 2), kreslí se VÝHRADNĚ aktivní cesta.
                  Pasivní port se nezobrazuje, zobrazí se jen přeslechová křivka S21 v grafu RP1.
    - Pravidlo 3: Při buzení oběma porty ('all') jsou porty přehledně odděleny (dva sloupce Port 1 vlevo, Port 2 vpravo).

    :param export_dir: Adresář s výsledky simulace
    :param params: Slovník parametrů modelu (volitelné)
    :param output_png: Cesta k výslednému PNG grafu (volitelné)
    :param layout: "split" (3x4 pro all) nebo "compact" (3x2 pro all)
    :return: Cesta k vygenerovanému souboru grafu
    """
    if output_png is None:
        output_png = os.path.join(export_dir, "graf_impedance_skoky.png")
    output_png = os.path.abspath(os.path.normpath(output_png))

    resolved_params = _resolve_deembedding_params(export_dir, explicit_params=params)
    hint_dp = resolved_params.get('driven_port')

    freqs, s11_complex, s22_complex, iso_complex, driven_mode = _load_simulation_s_params(export_dir, driven_port=hint_dp)

    if freqs is None or (s11_complex is None and s22_complex is None) or len(freqs) == 0:
        print(f"[De-embedding] V {export_dir} nebyla nalezena data port-S.csv ani port-V.csv!")
        return None

    resolved_params['driven_port'] = driven_mode

    # Analytický kaskádní de-embedding
    deemb = calculate_deembedding_model3(
        freqs=freqs,
        s11_complex=s11_complex,
        s22_complex=s22_complex,
        params=resolved_params
    )

    rp1 = deemb['rp1']
    rp2 = deemb['rp2']
    rp3 = deemb['rp3']
    p_used = deemb['params_used']
    model = deemb['model']
    z0_ref_rp3 = rp3['z0_ref']

    iso_db = 20.0 * np.log10(np.clip(np.abs(iso_complex), 1e-10, 10.0)) if iso_complex is not None else None

    # Styl a barvy
    c_p1_re = 'royalblue'
    c_p1_im = 'deepskyblue'
    c_p2_re = 'firebrick'
    c_p2_im = 'coral'
    c_iso = 'purple'
    c_limit = 'red'

    m_info = f"Model {model}"
    if model == 3:
        m_info += f" (Hybrid Matching: $w_T={p_used.get('w_T_b', 0.42):.2f}\\ \\mathrm{{mm}}$, $l_T={p_used.get('l_T_b', 18.9):.2f}\\ \\mathrm{{mm}}$)"
    elif model == 2:
        m_info += " (Dvouportový $100\\ \\Omega$ bez transformátoru)"

    # =========================================================================
    # REŽIM 1: BUZEN POUZE JEDEN PORT (Pravidlo 1 a Pravidlo 2)
    # =========================================================================
    if driven_mode in ("1", "2"):
        active_p = int(driven_mode)
        p_name = r"Port 1 ($E_y$, spodní)" if active_p == 1 else r"Port 2 ($E_x$, levý)"
        s_lbl = r"S_{11}" if active_p == 1 else r"S_{22}"
        iso_lbl = r"S_{21}" if active_p == 1 else r"S_{12}"
        c_re = c_p1_re if active_p == 1 else c_p2_re
        c_im = c_p1_im if active_p == 1 else c_p2_im

        z_rp1 = rp1['z1'] if active_p == 1 else rp1['z2']
        gamma_rp1_db = rp1['gamma1_db'] if active_p == 1 else rp1['gamma2_db']

        z_rp2 = rp2['z1'] if active_p == 1 else rp2['z2']
        gamma_rp2_db = rp2['gamma1_db'] if active_p == 1 else rp2['gamma2_db']

        z_rp3 = rp3['z1'] if active_p == 1 else rp3['z2']
        gamma_rp3_db = rp3['gamma1_db'] if active_p == 1 else rp3['gamma2_db']

        fig, axes = plt.subplots(3, 2, figsize=(14, 11), sharex=True)

        # ---------------------------------------------------------------------
        # ŘÁDEK 1: RP1 (Port)
        # ---------------------------------------------------------------------
        # Graf Zin (Re a Im s nulovou osou)
        ax1_imp = axes[0, 0]
        ax1_imp.plot(freqs, z_rp1.real, label=rf"$\mathrm{{Re}}\{{Z_{{in}}\}}$ ({p_name})", color=c_re, lw=2.2)
        ax1_imp.plot(freqs, z_rp1.imag, label=rf"$\mathrm{{Im}}\{{Z_{{in}}\}}$ ({p_name})", color=c_im, lw=1.8, linestyle='--')
        ax1_imp.axhline(100.0, color='gray', linestyle='--', alpha=0.7, label=r"Cíl $Z_0 = 100\ \Omega$")
        ax1_imp.axhline(0.0, color='black', linestyle='-', alpha=0.4, label=r"$\mathrm{Im}\{Z\} = 0\ \Omega$")
        ax1_imp.set_title(rf"1. RP1 (Port): Vstupní impedance $Z_{{in}}$ — {p_name}", fontsize=11, fontweight='bold')
        ax1_imp.set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
        ax1_imp.grid(True, linestyle=':', alpha=0.6)
        ax1_imp.legend(loc='best', fontsize=8, ncol=2)

        # Graf S11 v dB (s limitem -10 dB a křivkou izolace S21)
        ax1_gam = axes[0, 1]
        ax1_gam.plot(freqs, gamma_rp1_db, label=rf"$|{s_lbl}|$ ({p_name})", color=c_re, lw=2.2)
        min_g1_idx = np.argmin(gamma_rp1_db)
        ax1_gam.plot(freqs[min_g1_idx], gamma_rp1_db[min_g1_idx], 'o', color=c_re,
                     label=f"Min $|{s_lbl}|$: {gamma_rp1_db[min_g1_idx]:.2f} dB @ {freqs[min_g1_idx]:.3f} GHz")
        ax1_gam.axhline(-10.0, color=c_limit, linestyle=':', lw=1.5, label='Kritérium -10 dB')
        if iso_db is not None:
            ax1_gam.plot(freqs, iso_db, label=rf"Izolace / přeslech $|{iso_lbl}|$", color=c_iso, lw=1.8, linestyle=':')
        ax1_gam.set_title(rf"2. RP1 (Port): Činitel odrazu $|{s_lbl}|$ a přeslech $|{iso_lbl}|$", fontsize=11, fontweight='bold')
        ax1_gam.set_ylabel(r"Magnituda [dB]", fontsize=10)
        ax1_gam.grid(True, linestyle=':', alpha=0.6)
        ax1_gam.legend(loc='best', fontsize=8)

        # ---------------------------------------------------------------------
        # ŘÁDEK 2: RP2 (Svorka transformátoru)
        # ---------------------------------------------------------------------
        # Graf Z_RP2 (Re a Im s referencí 100 Ω)
        ax2_imp = axes[1, 0]
        ax2_imp.plot(freqs, z_rp2.real, label=rf"$\mathrm{{Re}}\{{Z_{{RP2}}\}}$", color=c_re, lw=2.2)
        ax2_imp.plot(freqs, z_rp2.imag, label=rf"$\mathrm{{Im}}\{{Z_{{RP2}}\}}$", color=c_im, lw=1.8, linestyle='--')
        ax2_imp.axhline(100.0, color='gray', linestyle='--', alpha=0.7, label=r"Reference $100\ \Omega$")
        ax2_imp.axhline(0.0, color='black', linestyle='-', alpha=0.4, label=r"$\mathrm{Im}\{Z\} = 0\ \Omega$")
        ax2_imp.set_title(rf"3. RP2 (Svorka transformátoru): Impedance $Z_{{RP2}}$", fontsize=11, fontweight='bold')
        ax2_imp.set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
        ax2_imp.grid(True, linestyle=':', alpha=0.6)
        ax2_imp.legend(loc='best', fontsize=8, ncol=2)

        # Graf lokálního |Gamma_RP2| v dB
        ax2_gam = axes[1, 1]
        ax2_gam.plot(freqs, gamma_rp2_db, label=r"Lokální $|\Gamma_{RP2}|$ (ref $100\ \Omega$)", color=c_re, lw=2.2)
        min_g2_idx = np.argmin(gamma_rp2_db)
        ax2_gam.plot(freqs[min_g2_idx], gamma_rp2_db[min_g2_idx], 'o', color=c_re,
                     label=rf"Min $|\Gamma_{{RP2}}|: {gamma_rp2_db[min_g2_idx]:.2f}$ dB @ {freqs[min_g2_idx]:.3f} GHz")
        ax2_gam.axhline(-10.0, color=c_limit, linestyle=':', lw=1.5, label='Kritérium -10 dB')
        ax2_gam.set_title(r"4. RP2 (Svorka): Lokální činitel odrazu $|\Gamma_{RP2}| (100\ \Omega)$", fontsize=11, fontweight='bold')
        ax2_gam.set_ylabel(r"Magnituda [dB]", fontsize=10)
        ax2_gam.grid(True, linestyle=':', alpha=0.6)
        ax2_gam.legend(loc='best', fontsize=8)

        # ---------------------------------------------------------------------
        # ŘÁDEK 3: RP3 (Vstup do flíčku)
        # ---------------------------------------------------------------------
        # Graf Z_patch (Re a Im s referencí 140 Ω a nulou pro rezonanci f0)
        ax3_imp = axes[2, 0]
        ax3_imp.plot(freqs, z_rp3.real, label=rf"$\mathrm{{Re}}\{{Z_{{patch}}\}}$", color=c_re, lw=2.2)
        ax3_imp.plot(freqs, z_rp3.imag, label=rf"$\mathrm{{Im}}\{{Z_{{patch}}\}}$", color=c_im, lw=1.8, linestyle='--')
        ax3_imp.axhline(z0_ref_rp3, color='mediumvioletred', linestyle='--', alpha=0.8,
                        label=rf"Cíl $R_{{patch}} \approx {z0_ref_rp3:.1f}\ \Omega$")
        ax3_imp.axhline(0.0, color='black', linestyle='-', alpha=0.5, label=r"Rezonance $\mathrm{Im}\{Z\}=0$")

        # Detekce a označení vlastní rezonance flíčku f0
        f0_patch = _detect_resonance(freqs, z_rp3.imag)
        if f0_patch is not None and (freqs[0] <= f0_patch <= freqs[-1]):
            r_at_f0 = float(np.interp(f0_patch, freqs, z_rp3.real))
            ax3_imp.plot(f0_patch, 0.0, 'ro', markersize=7, label=rf"Rezonance $f_0={f0_patch:.3f}\ \mathrm{{GHz}}$")
            y_offset = max(20.0, float(np.max(z_rp3.real)) * 0.15)
            ax3_imp.annotate(rf"$f_0={f0_patch:.3f}\ \mathrm{{GHz}}$" + "\n" + rf"$R={r_at_f0:.1f}\ \Omega$",
                             xy=(f0_patch, 0.0), xytext=(f0_patch, y_offset),
                             arrowprops=dict(arrowstyle="->", color='crimson', lw=1.5),
                             fontsize=9, fontweight='bold', color='crimson')

        ax3_imp.set_title(rf"5. RP3 (Vstup do flíčku): Impedance flíčku $Z_{{patch}}$", fontsize=11, fontweight='bold')
        ax3_imp.set_xlabel("Frekvence [GHz]", fontsize=10)
        ax3_imp.set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
        ax3_imp.grid(True, linestyle=':', alpha=0.6)
        ax3_imp.legend(loc='best', fontsize=8, ncol=2)

        # Graf lokálního |Gamma_patch| v dB
        ax3_gam = axes[2, 1]
        ax3_gam.plot(freqs, gamma_rp3_db, label=rf"Lokální $|\Gamma_{{patch}}|$ (ref {z0_ref_rp3:.0f} $\Omega$)", color=c_re, lw=2.2)
        min_g3_idx = np.argmin(gamma_rp3_db)
        ax3_gam.plot(freqs[min_g3_idx], gamma_rp3_db[min_g3_idx], 'o', color=c_re,
                     label=rf"Min $|\Gamma_{{patch}}|: {gamma_rp3_db[min_g3_idx]:.2f}$ dB @ {freqs[min_g3_idx]:.3f} GHz")
        ax3_gam.axhline(-10.0, color=c_limit, linestyle=':', lw=1.5, label='Kritérium -10 dB')
        ax3_gam.set_title(rf"6. RP3 (Flíček): Lokální činitel odrazu $|\Gamma_{{patch}}| ({z0_ref_rp3:.0f}\ \Omega)$",
                          fontsize=11, fontweight='bold')
        ax3_gam.set_xlabel("Frekvence [GHz]", fontsize=10)
        ax3_gam.set_ylabel(r"Magnituda [dB]", fontsize=10)
        ax3_gam.grid(True, linestyle=':', alpha=0.6)
        ax3_gam.legend(loc='best', fontsize=8)

        # Globální záhlaví
        plt.suptitle(f"Analytický de-embedding impedančních skoků — {m_info}\n"
                     f"Aktivní buzení: {p_name} — RP1 (Port) $\\to$ RP2 (Svorka) $\\to$ RP3 (Flíček)",
                     fontsize=12, fontweight='bold', y=0.98)
        plt.tight_layout(rect=[0, 0, 1, 0.95])

    # =========================================================================
    # REŽIM 2: BUZENÍ OBĚMA PORTY (Pravidlo 3)
    # =========================================================================
    else:
        # Volba rozložení: "split" = dva samostatné bloky sloupců (Port 1 vlevo, Port 2 vpravo)
        if layout == "split":
            fig, axes = plt.subplots(3, 4, figsize=(20, 11), sharex=True)

            # --- ŘÁDEK 1: RP1 (Port) ---
            # Port 1: Zin1
            axes[0, 0].plot(freqs, rp1['z1'].real, label=r"$\mathrm{Re}\{Z_{in1}\}$", color=c_p1_re, lw=2.2)
            axes[0, 0].plot(freqs, rp1['z1'].imag, label=r"$\mathrm{Im}\{Z_{in1}\}$", color=c_p1_im, lw=1.8, linestyle='--')
            axes[0, 0].axhline(100.0, color='gray', linestyle='--', alpha=0.7, label=r"Cíl $100\ \Omega$")
            axes[0, 0].axhline(0.0, color='black', linestyle='-', alpha=0.4)
            axes[0, 0].set_title(r"RP1 (Port 1, $E_y$): Impedance $Z_{in1}$", fontsize=11, fontweight='bold')
            axes[0, 0].set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
            axes[0, 0].grid(True, linestyle=':', alpha=0.6)
            axes[0, 0].legend(loc='best', fontsize=8)

            # Port 1: S11 a S21
            axes[0, 1].plot(freqs, rp1['gamma1_db'], label=r"$|S_{11}|$", color=c_p1_re, lw=2.2)
            min1_idx = np.argmin(rp1['gamma1_db'])
            axes[0, 1].plot(freqs[min1_idx], rp1['gamma1_db'][min1_idx], 'o', color=c_p1_re,
                            label=f"Min $|S_{{11}}|: {rp1['gamma1_db'][min1_idx]:.2f} dB")
            if iso_db is not None:
                axes[0, 1].plot(freqs, iso_db, label=r"Izolace $|S_{21}|$", color=c_iso, lw=1.8, linestyle=':')
            axes[0, 1].axhline(-10.0, color=c_limit, linestyle=':', lw=1.5, label='-10 dB')
            axes[0, 1].set_title(r"RP1 (Port 1): Odraz $|S_{11}|$ a přeslech", fontsize=11, fontweight='bold')
            axes[0, 1].set_ylabel(r"Magnituda [dB]", fontsize=10)
            axes[0, 1].grid(True, linestyle=':', alpha=0.6)
            axes[0, 1].legend(loc='best', fontsize=8)

            # Port 2: Zin2
            axes[0, 2].plot(freqs, rp1['z2'].real, label=r"$\mathrm{Re}\{Z_{in2}\}$", color=c_p2_re, lw=2.2)
            axes[0, 2].plot(freqs, rp1['z2'].imag, label=r"$\mathrm{Im}\{Z_{in2}\}$", color=c_p2_im, lw=1.8, linestyle='--')
            axes[0, 2].axhline(100.0, color='gray', linestyle='--', alpha=0.7, label=r"Cíl $100\ \Omega$")
            axes[0, 2].axhline(0.0, color='black', linestyle='-', alpha=0.4)
            axes[0, 2].set_title(r"RP1 (Port 2, $E_x$): Impedance $Z_{in2}$", fontsize=11, fontweight='bold')
            axes[0, 2].set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
            axes[0, 2].grid(True, linestyle=':', alpha=0.6)
            axes[0, 2].legend(loc='best', fontsize=8)

            # Port 2: S22 a S12
            axes[0, 3].plot(freqs, rp1['gamma2_db'], label=r"$|S_{22}|$", color=c_p2_re, lw=2.2)
            min2_idx = np.argmin(rp1['gamma2_db'])
            axes[0, 3].plot(freqs[min2_idx], rp1['gamma2_db'][min2_idx], 'o', color=c_p2_re,
                            label=f"Min $|S_{{22}}|: {rp1['gamma2_db'][min2_idx]:.2f} dB")
            if iso_db is not None:
                axes[0, 3].plot(freqs, iso_db, label=r"Izolace $|S_{12}|$", color=c_iso, lw=1.8, linestyle=':')
            axes[0, 3].axhline(-10.0, color=c_limit, linestyle=':', lw=1.5, label='-10 dB')
            axes[0, 3].set_title(r"RP1 (Port 2): Odraz $|S_{22}|$ a přeslech", fontsize=11, fontweight='bold')
            axes[0, 3].set_ylabel(r"Magnituda [dB]", fontsize=10)
            axes[0, 3].grid(True, linestyle=':', alpha=0.6)
            axes[0, 3].legend(loc='best', fontsize=8)

            # --- ŘÁDEK 2: RP2 (Svorka transformátoru) ---
            # Port 1: Z_RP2_1
            axes[1, 0].plot(freqs, rp2['z1'].real, label=r"$\mathrm{Re}\{Z_{RP2,1}\}$", color=c_p1_re, lw=2.2)
            axes[1, 0].plot(freqs, rp2['z1'].imag, label=r"$\mathrm{Im}\{Z_{RP2,1}\}$", color=c_p1_im, lw=1.8, linestyle='--')
            axes[1, 0].axhline(100.0, color='gray', linestyle='--', alpha=0.7, label=r"Ref $100\ \Omega$")
            axes[1, 0].axhline(0.0, color='black', linestyle='-', alpha=0.4)
            axes[1, 0].set_title(r"RP2 (Port 1): Impedance $Z_{RP2}$", fontsize=11, fontweight='bold')
            axes[1, 0].set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
            axes[1, 0].grid(True, linestyle=':', alpha=0.6)
            axes[1, 0].legend(loc='best', fontsize=8)

            # Port 1: |Gamma_RP2_1|
            axes[1, 1].plot(freqs, rp2['gamma1_db'], label=r"$|\Gamma_{RP2,1}|$", color=c_p1_re, lw=2.2)
            axes[1, 1].axhline(-10.0, color=c_limit, linestyle=':', lw=1.5, label='-10 dB')
            axes[1, 1].set_title(r"RP2 (Port 1): Činitel odrazu $|\Gamma_{RP2}| (100\ \Omega)$", fontsize=11, fontweight='bold')
            axes[1, 1].set_ylabel(r"Magnituda [dB]", fontsize=10)
            axes[1, 1].grid(True, linestyle=':', alpha=0.6)
            axes[1, 1].legend(loc='best', fontsize=8)

            # Port 2: Z_RP2_2
            axes[1, 2].plot(freqs, rp2['z2'].real, label=r"$\mathrm{Re}\{Z_{RP2,2}\}$", color=c_p2_re, lw=2.2)
            axes[1, 2].plot(freqs, rp2['z2'].imag, label=r"$\mathrm{Im}\{Z_{RP2,2}\}$", color=c_p2_im, lw=1.8, linestyle='--')
            axes[1, 2].axhline(100.0, color='gray', linestyle='--', alpha=0.7, label=r"Ref $100\ \Omega$")
            axes[1, 2].axhline(0.0, color='black', linestyle='-', alpha=0.4)
            axes[1, 2].set_title(r"RP2 (Port 2): Impedance $Z_{RP2}$", fontsize=11, fontweight='bold')
            axes[1, 2].set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
            axes[1, 2].grid(True, linestyle=':', alpha=0.6)
            axes[1, 2].legend(loc='best', fontsize=8)

            # Port 2: |Gamma_RP2_2|
            axes[1, 3].plot(freqs, rp2['gamma2_db'], label=r"$|\Gamma_{RP2,2}|$", color=c_p2_re, lw=2.2)
            axes[1, 3].axhline(-10.0, color=c_limit, linestyle=':', lw=1.5, label='-10 dB')
            axes[1, 3].set_title(r"RP2 (Port 2): Činitel odrazu $|\Gamma_{RP2}| (100\ \Omega)$", fontsize=11, fontweight='bold')
            axes[1, 3].set_ylabel(r"Magnituda [dB]", fontsize=10)
            axes[1, 3].grid(True, linestyle=':', alpha=0.6)
            axes[1, 3].legend(loc='best', fontsize=8)

            # --- ŘÁDEK 3: RP3 (Vstup do flíčku) ---
            # Port 1: Z_patch1
            axes[2, 0].plot(freqs, rp3['z1'].real, label=r"$\mathrm{Re}\{Z_{patch1}\}$", color=c_p1_re, lw=2.2)
            axes[2, 0].plot(freqs, rp3['z1'].imag, label=r"$\mathrm{Im}\{Z_{patch1}\}$", color=c_p1_im, lw=1.8, linestyle='--')
            axes[2, 0].axhline(z0_ref_rp3, color='mediumvioletred', linestyle='--', alpha=0.7,
                            label=rf"Cíl {z0_ref_rp3:.0f} $\Omega$")
            axes[2, 0].axhline(0.0, color='black', linestyle='-', alpha=0.4)
            f0_p1 = _detect_resonance(freqs, rp3['z1'].imag)
            if f0_p1 is not None and (freqs[0] <= f0_p1 <= freqs[-1]):
                axes[2, 0].plot(f0_p1, 0.0, 'ro', markersize=6)
                axes[2, 0].annotate(rf"$f_{{0,1}}={f0_p1:.3f}$", xy=(f0_p1, 0.0), xytext=(f0_p1, 15),
                                   arrowprops=dict(arrowstyle="->", color='crimson'), fontsize=8, color='crimson')
            axes[2, 0].set_title(r"RP3 (Port 1): Impedance flíčku $Z_{patch}$", fontsize=11, fontweight='bold')
            axes[2, 0].set_xlabel("Frekvence [GHz]", fontsize=10)
            axes[2, 0].set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
            axes[2, 0].grid(True, linestyle=':', alpha=0.6)
            axes[2, 0].legend(loc='best', fontsize=8)

            # Port 1: |Gamma_patch1|
            axes[2, 1].plot(freqs, rp3['gamma1_db'], label=rf"$|\Gamma_{{patch1}}|$", color=c_p1_re, lw=2.2)
            axes[2, 1].axhline(-10.0, color=c_limit, linestyle=':', lw=1.5, label='-10 dB')
            axes[2, 1].set_title(rf"RP3 (Port 1): Odraz $|\Gamma_{{patch}}| ({z0_ref_rp3:.0f}\ \Omega)$", fontsize=11, fontweight='bold')
            axes[2, 1].set_xlabel("Frekvence [GHz]", fontsize=10)
            axes[2, 1].set_ylabel(r"Magnituda [dB]", fontsize=10)
            axes[2, 1].grid(True, linestyle=':', alpha=0.6)
            axes[2, 1].legend(loc='best', fontsize=8)

            # Port 2: Z_patch2
            axes[2, 2].plot(freqs, rp3['z2'].real, label=r"$\mathrm{Re}\{Z_{patch2}\}$", color=c_p2_re, lw=2.2)
            axes[2, 2].plot(freqs, rp3['z2'].imag, label=r"$\mathrm{Im}\{Z_{patch2}\}$", color=c_p2_im, lw=1.8, linestyle='--')
            axes[2, 2].axhline(z0_ref_rp3, color='mediumvioletred', linestyle='--', alpha=0.7,
                            label=rf"Cíl {z0_ref_rp3:.0f} $\Omega$")
            axes[2, 2].axhline(0.0, color='black', linestyle='-', alpha=0.4)
            f0_p2 = _detect_resonance(freqs, rp3['z2'].imag)
            if f0_p2 is not None and (freqs[0] <= f0_p2 <= freqs[-1]):
                axes[2, 2].plot(f0_p2, 0.0, 'ro', markersize=6)
                axes[2, 2].annotate(rf"$f_{{0,2}}={f0_p2:.3f}$", xy=(f0_p2, 0.0), xytext=(f0_p2, 15),
                                   arrowprops=dict(arrowstyle="->", color='crimson'), fontsize=8, color='crimson')
            axes[2, 2].set_title(r"RP3 (Port 2): Impedance flíčku $Z_{patch}$", fontsize=11, fontweight='bold')
            axes[2, 2].set_xlabel("Frekvence [GHz]", fontsize=10)
            axes[2, 2].set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
            axes[2, 2].grid(True, linestyle=':', alpha=0.6)
            axes[2, 2].legend(loc='best', fontsize=8)

            # Port 2: |Gamma_patch2|
            axes[2, 3].plot(freqs, rp3['gamma2_db'], label=rf"$|\Gamma_{{patch2}}|$", color=c_p2_re, lw=2.2)
            axes[2, 3].axhline(-10.0, color=c_limit, linestyle=':', lw=1.5, label='-10 dB')
            axes[2, 3].set_title(rf"RP3 (Port 2): Odraz $|\Gamma_{{patch}}| ({z0_ref_rp3:.0f}\ \Omega)$", fontsize=11, fontweight='bold')
            axes[2, 3].set_xlabel("Frekvence [GHz]", fontsize=10)
            axes[2, 3].set_ylabel(r"Magnituda [dB]", fontsize=10)
            axes[2, 3].grid(True, linestyle=':', alpha=0.6)
            axes[2, 3].legend(loc='best', fontsize=8)

            # Globální záhlaví
            plt.suptitle(f"Analytický de-embedding impedančních skoků — {m_info}\n"
                         r"Dvouportové zobrazení: PORT 1 ($E_y$) vlevo vs. PORT 2 ($E_x$) vpravo",
                         fontsize=12, fontweight='bold', y=0.98)
            plt.tight_layout(rect=[0, 0, 1, 0.95])

        else:
            # Kompaktní rozložení 3x2 s přehledně oddělenými křivkami (bez slévání)
            fig, axes = plt.subplots(3, 2, figsize=(14, 11), sharex=True)

            # ŘÁDEK 1: RP1
            ax0 = axes[0, 0]
            ax0.plot(freqs, rp1['z1'].real, label=r"$\mathrm{Re}\{Z_{in1}\}$ (P1, $E_y$)", color=c_p1_re, lw=2.2)
            ax0.plot(freqs, rp1['z1'].imag, label=r"$\mathrm{Im}\{Z_{in1}\}$ (P1)", color=c_p1_im, lw=1.8, linestyle='--')
            ax0.plot(freqs, rp1['z2'].real, label=r"$\mathrm{Re}\{Z_{in2}\}$ (P2, $E_x$)", color=c_p2_re, lw=2.2)
            ax0.plot(freqs, rp1['z2'].imag, label=r"$\mathrm{Im}\{Z_{in2}\}$ (P2)", color=c_p2_im, lw=1.8, linestyle='--')
            ax0.axhline(100.0, color='gray', linestyle='--', alpha=0.7, label=r"Cíl $100\ \Omega$")
            ax0.axhline(0.0, color='black', linestyle='-', alpha=0.4)
            ax0.set_title(r"1. RP1 (Port): Vstupní impedance $Z_{in}$ (Port 1 vs Port 2)", fontsize=11, fontweight='bold')
            ax0.set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
            ax0.grid(True, linestyle=':', alpha=0.6)
            ax0.legend(loc='best', fontsize=8, ncol=2)

            ax1 = axes[0, 1]
            ax1.plot(freqs, rp1['gamma1_db'], label=r"$|S_{11}|$ (Port 1)", color=c_p1_re, lw=2.2)
            ax1.plot(freqs, rp1['gamma2_db'], label=r"$|S_{22}|$ (Port 2)", color=c_p2_re, lw=2.2, linestyle='--')
            if iso_db is not None:
                ax1.plot(freqs, iso_db, label=r"Izolace $|S_{21}|$", color=c_iso, lw=1.8, linestyle=':')
            ax1.axhline(-10.0, color=c_limit, linestyle=':', lw=1.5, label='Kritérium -10 dB')
            ax1.set_title(r"2. RP1 (Port): Činitele odrazu a přeslech", fontsize=11, fontweight='bold')
            ax1.set_ylabel(r"Magnituda [dB]", fontsize=10)
            ax1.grid(True, linestyle=':', alpha=0.6)
            ax1.legend(loc='best', fontsize=8)

            # ŘÁDEK 2: RP2
            ax2 = axes[1, 0]
            ax2.plot(freqs, rp2['z1'].real, label=r"$\mathrm{Re}\{Z_{RP2,1}\}$ (P1)", color=c_p1_re, lw=2.2)
            ax2.plot(freqs, rp2['z1'].imag, label=r"$\mathrm{Im}\{Z_{RP2,1}\}$ (P1)", color=c_p1_im, lw=1.8, linestyle='--')
            ax2.plot(freqs, rp2['z2'].real, label=r"$\mathrm{Re}\{Z_{RP2,2}\}$ (P2)", color=c_p2_re, lw=2.2)
            ax2.plot(freqs, rp2['z2'].imag, label=r"$\mathrm{Im}\{Z_{RP2,2}\}$ (P2)", color=c_p2_im, lw=1.8, linestyle='--')
            ax2.axhline(100.0, color='gray', linestyle='--', alpha=0.7, label=r"Ref $100\ \Omega$")
            ax2.axhline(0.0, color='black', linestyle='-', alpha=0.4)
            ax2.set_title(r"3. RP2 (Svorka): Impedance $Z_{RP2}$", fontsize=11, fontweight='bold')
            ax2.set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
            ax2.grid(True, linestyle=':', alpha=0.6)
            ax2.legend(loc='best', fontsize=8, ncol=2)

            ax3 = axes[1, 1]
            ax3.plot(freqs, rp2['gamma1_db'], label=r"$|\Gamma_{RP2,1}|$ (Port 1)", color=c_p1_re, lw=2.2)
            ax3.plot(freqs, rp2['gamma2_db'], label=r"$|\Gamma_{RP2,2}|$ (Port 2)", color=c_p2_re, lw=2.2, linestyle='--')
            ax3.axhline(-10.0, color=c_limit, linestyle=':', lw=1.5, label='Kritérium -10 dB')
            ax3.set_title(r"4. RP2 (Svorka): Lokální činitel odrazu $|\Gamma_{RP2}| (100\ \Omega)$", fontsize=11, fontweight='bold')
            ax3.set_ylabel(r"Magnituda [dB]", fontsize=10)
            ax3.grid(True, linestyle=':', alpha=0.6)
            ax3.legend(loc='best', fontsize=8)

            # ŘÁDEK 3: RP3
            ax4 = axes[2, 0]
            ax4.plot(freqs, rp3['z1'].real, label=r"$\mathrm{Re}\{Z_{patch1}\}$ (P1)", color=c_p1_re, lw=2.2)
            ax4.plot(freqs, rp3['z1'].imag, label=r"$\mathrm{Im}\{Z_{patch1}\}$ (P1)", color=c_p1_im, lw=1.8, linestyle='--')
            ax4.plot(freqs, rp3['z2'].real, label=r"$\mathrm{Re}\{Z_{patch2}\}$ (P2)", color=c_p2_re, lw=2.2)
            ax4.plot(freqs, rp3['z2'].imag, label=r"$\mathrm{Im}\{Z_{patch2}\}$ (P2)", color=c_p2_im, lw=1.8, linestyle='--')
            ax4.axhline(z0_ref_rp3, color='mediumvioletred', linestyle='--', alpha=0.7, label=rf"Cíl {z0_ref_rp3:.0f} $\Omega$")
            ax4.axhline(0.0, color='black', linestyle='-', alpha=0.4)
            ax4.set_title(r"5. RP3 (Flíček): Impedance flíčku $Z_{patch}$", fontsize=11, fontweight='bold')
            ax4.set_xlabel("Frekvence [GHz]", fontsize=10)
            ax4.set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
            ax4.grid(True, linestyle=':', alpha=0.6)
            ax4.legend(loc='best', fontsize=8, ncol=2)

            ax5 = axes[2, 1]
            ax5.plot(freqs, rp3['gamma1_db'], label=r"$|\Gamma_{patch1}|$ (Port 1)", color=c_p1_re, lw=2.2)
            ax5.plot(freqs, rp3['gamma2_db'], label=r"$|\Gamma_{patch2}|$ (Port 2)", color=c_p2_re, lw=2.2, linestyle='--')
            ax5.axhline(-10.0, color=c_limit, linestyle=':', lw=1.5, label='Kritérium -10 dB')
            ax5.set_title(rf"6. RP3 (Flíček): Lokální činitel odrazu $|\Gamma_{{patch}}| ({z0_ref_rp3:.0f}\ \Omega)$", fontsize=11, fontweight='bold')
            ax5.set_xlabel("Frekvence [GHz]", fontsize=10)
            ax5.set_ylabel(r"Magnituda [dB]", fontsize=10)
            ax5.grid(True, linestyle=':', alpha=0.6)
            ax5.legend(loc='best', fontsize=8)

            plt.suptitle(f"Analytický de-embedding impedančních skoků — {m_info}\n"
                         r"Dvouportové buzení: RP1 (Port) $\to$ RP2 (Svorka) $\to$ RP3 (Flíček)",
                         fontsize=12, fontweight='bold', y=0.98)
            plt.tight_layout(rect=[0, 0, 1, 0.95])

    os.makedirs(os.path.dirname(output_png) or ".", exist_ok=True)
    plt.savefig(output_png, dpi=200)
    plt.close()
    print(f"[De-embedding] Graf impedančních skoků byl úspěšně uložen do: {output_png}")
    return output_png


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Analytický de-embedding impedančních skoků napájecí sítě patch antény")
    parser.add_argument("export_dir", nargs="?", default=os.path.join(_ROOT_DIR, "export", "antena3_1_1"),
                        help="Cesta k exportní složce s výsledky simulace (výchozí: export/antena3_1_1)")
    parser.add_argument("--output", "-o", default=None,
                        help="Cesta k výstupnímu PNG grafu (výchozí: <export_dir>/graf_impedance_skoky.png)")
    parser.add_argument("--layout", choices=["split", "compact"], default="split",
                        help="Rozložení pro obouportové buzení (split=3x4 dva sloupce portů, compact=3x2)")
    args = parser.parse_args()

    plot_impedance_deembedding(args.export_dir, output_png=args.output, layout=args.layout)
