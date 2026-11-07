"""
plot_deembedding.py - Analytický de-embedding impedančních skoků a vyhodnocení referenčních rovin
Generuje komplexní 2x2 diagnostický graf 'graf_impedance_skoky.png':
  - Panel 1: Re{Z} v referenčních rovinách RP1 (port), RP2 (svorka transformátoru) a RP3 (flíček).
  - Panel 2: Im{Z} a okamžité určení vlastní rezonance flíčku (Im{Z}=0).
  - Panel 3: Lokální |Gamma| [dB] v jednotlivých rovinách.
  - Panel 4: Porovnání symetrie Port 1 vs Port 2 přímo na vstupu do flíčku (RP3).
"""

import os
import sys
import json
import numpy as np
import matplotlib.pyplot as plt

# Zajištění přístupu k src modulům (rf_calc)
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_CURRENT_DIR, ".."))
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
for p in (_ROOT_DIR, _SRC_DIR, _CURRENT_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from rf_calc import calculate_deembedding_model3, DESIGN_FREQ_GHZ


def _load_simulation_s_params(export_dir):
    """
    Vyhledá a načte S-parametry nebo napětí/proudy ze simulačních souborů
    (port-S.csv nebo port-V.csv) v zadaném adresáři nebo podsložce postpro.
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

            s11_idx = find_idx(["|s[1][1]|", "s[1][1]", "s[1,1]", "|s11|", "s11"])
            s11_deg_idx = find_idx(["arg(s[1][1])", "arg(s[1,1])", "arg(s11)", "phase(s[1][1])"])
            s22_idx = find_idx(["|s[2][2]|", "s[2][2]", "s[2,2]", "|s22|", "s22"])
            s22_deg_idx = find_idx(["arg(s[2][2])", "arg(s[2,2])", "arg(s22)", "phase(s[2][2])"])

            if s11_idx is None and data.shape[1] >= 2:
                s11_idx = 1
                if data.shape[1] >= 3:
                    s11_deg_idx = 2

            if s11_idx is not None and s11_idx < data.shape[1]:
                s11_db = data[:, s11_idx]
                deg1 = data[:, s11_deg_idx] if s11_deg_idx is not None and s11_deg_idx < data.shape[1] else np.zeros_like(s11_db)
                s11_complex = (10.0 ** (s11_db / 20.0)) * np.exp(1j * np.deg2rad(deg1))

            if s22_idx is not None and s22_idx < data.shape[1]:
                s22_db = data[:, s22_idx]
                deg2 = data[:, s22_deg_idx] if s22_deg_idx is not None and s22_deg_idx < data.shape[1] else np.zeros_like(s22_db)
                s22_complex = (10.0 ** (s22_db / 20.0)) * np.exp(1j * np.deg2rad(deg2))
        except Exception as e:
            print(f"Upozornění při načítání {s_path}: {e}")

    # 2. Pokus z port-V.csv (pokud chybí s22 nebo port-S nebyl kompletní)
    if (s11_complex is None or s22_complex is None) and v_path:
        try:
            v_data = np.loadtxt(v_path, delimiter=',', skiprows=1)
            if v_data.ndim == 1:
                v_data = v_data.reshape(1, -1)

            freqs_v = v_data[:, 0]
            if freqs is None:
                freqs = freqs_v

            # port-V: f, V_inc[1], V_inc[2], Re{V[1]}, Im{V[1]}, Re{V[2]}, Im{V[2]}
            if v_data.shape[1] >= 5 and s11_complex is None:
                v_inc1 = v_data[:, 1]
                v1 = v_data[:, 3] + 1j * v_data[:, 4]
                s11_complex = (v1 - v_inc1) / np.where(np.abs(v_inc1) < 1e-12, 1e-12, v_inc1)

            if v_data.shape[1] >= 7 and s22_complex is None:
                v_inc2 = v_data[:, 2]
                v2 = v_data[:, 5] + 1j * v_data[:, 6]
                s22_complex = (v2 - v_inc2) / np.where(np.abs(v_inc2) < 1e-12, 1e-12, v_inc2)
        except Exception as e:
            print(f"Upozornění při načítání {v_path}: {e}")

    return freqs, s11_complex, s22_complex


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

                # Materiál z Domains.Materials
                mats = cfg.get("Domains", {}).get("Materials", [])
                for m in mats:
                    if "Permittivity" in m and "eps_r" not in params:
                        params["eps_r"] = float(m["Permittivity"])
                    if "LossTan" in m and "tan_delta" not in params:
                        params["tan_delta"] = float(m["LossTan"])

                # Impedance portu z Boundaries.LumpedPort
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
    }
    for k, v in defaults.items():
        if k not in params or params[k] is None:
            params[k] = v

    return params


def plot_impedance_deembedding(export_dir, params=None, output_png=None):
    """
    Vypočte a vykreslí 2x2 analytický de-embedding impedančních skoků.
    :param export_dir: Adresář s výsledky simulace
    :param params: Slovník parametrů modelu (volitelné)
    :param output_png: Cesta k výslednému PNG grafu (volitelné)
    :return: Cesta k vygenerovanému souboru grafu
    """
    if output_png is None:
        output_png = os.path.join(export_dir, "graf_impedance_skoky.png")

    freqs, s11_complex, s22_complex = _load_simulation_s_params(export_dir)

    # Bezpečná kontrola existence dat
    if freqs is None or s11_complex is None or len(freqs) == 0:
        print(f"[De-embedding] V {export_dir} nebyla nalezena data port-S.csv ani port-V.csv!")
        return None

    resolved_params = _resolve_deembedding_params(export_dir, explicit_params=params)

    # Analytický de-embedding
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

    fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharex=True)
    ax1, ax2 = axes[0, 0], axes[0, 1]
    ax3, ax4 = axes[1, 0], axes[1, 1]

    # --- PANEL 1: Re{Z} v rovinách RP1, RP2, RP3 ---
    ax1.plot(freqs, rp1['z1'].real, label=r'RP1: Port 1 ($E_y$)', color='royalblue', lw=2)
    if rp1['z2'] is not None:
        ax1.plot(freqs, rp1['z2'].real, label=r'RP1: Port 2 ($E_x$)', color='cornflowerblue', lw=1.8, linestyle='--')

    ax1.plot(freqs, rp2['z1'].real, label=r'RP2: Po $100\ \Omega$ (Port 1)', color='forestgreen', lw=2)
    if rp2['z2'] is not None:
        ax1.plot(freqs, rp2['z2'].real, label=r'RP2: Po $100\ \Omega$ (Port 2)', color='mediumseagreen', lw=1.8, linestyle='--')

    ax1.plot(freqs, rp3['z1'].real, label=r'RP3: Na flíčku (Port 1)', color='crimson', lw=2.2)
    if rp3['z2'] is not None:
        ax1.plot(freqs, rp3['z2'].real, label=r'RP3: Na flíčku (Port 2)', color='coral', lw=2.0, linestyle='--')

    ax1.axhline(100.0, color='gray', linestyle='--', alpha=0.7, label=r'Cíl $100\ \Omega$ (RP1, RP2)')
    if model == 3:
        ax1.axhline(rp3['z0_ref'], color='purple', linestyle=':', alpha=0.8, lw=1.6, label=f'Cíl {rp3["z0_ref"]:.1f} $\\Omega$ (RP3)')
    ax1.set_title(r"1. Reálná složka impedance $\mathrm{Re}\{Z\}$ v rovinách", fontsize=12, fontweight='bold')
    ax1.set_ylabel(r"$\mathrm{Re}\{Z\}\ [\Omega]$", fontsize=11)
    ax1.grid(True, linestyle=':', alpha=0.6)
    ax1.legend(loc='best', fontsize=8, ncol=2)

    # --- PANEL 2: Im{Z} a určení rezonance flíčku ---
    ax2.plot(freqs, rp1['z1'].imag, label=r'RP1: Port 1 ($E_y$)', color='royalblue', lw=2)
    if rp1['z2'] is not None:
        ax2.plot(freqs, rp1['z2'].imag, label=r'RP1: Port 2 ($E_x$)', color='cornflowerblue', lw=1.8, linestyle='--')

    ax2.plot(freqs, rp2['z1'].imag, label=r'RP2: Svorka (Port 1)', color='forestgreen', lw=2)
    if rp2['z2'] is not None:
        ax2.plot(freqs, rp2['z2'].imag, label=r'RP2: Svorka (Port 2)', color='mediumseagreen', lw=1.8, linestyle='--')

    ax2.plot(freqs, rp3['z1'].imag, label=r'RP3: Na flíčku (Port 1)', color='crimson', lw=2.2)
    if rp3['z2'] is not None:
        ax2.plot(freqs, rp3['z2'].imag, label=r'RP3: Na flíčku (Port 2)', color='coral', lw=2.0, linestyle='--')

    ax2.axhline(0.0, color='black', linestyle='-', alpha=0.5, lw=1.2, label=r'Rezonance $\mathrm{Im}\{Z\}=0$')

    # Detekce průchodu nulou Im{Z}=0 pro RP3 (vlastní rezonance flíčku)
    im_rp3 = rp3['z1'].imag
    sign_changes = np.where(np.diff(np.sign(im_rp3)))[0]
    if len(sign_changes) > 0:
        idx0 = sign_changes[0]
        f_zero = freqs[idx0] - im_rp3[idx0] * (freqs[idx0+1] - freqs[idx0]) / (im_rp3[idx0+1] - im_rp3[idx0] + 1e-12)
        ax2.plot(f_zero, 0.0, 'ro', markersize=6)
        ax2.annotate(f"$f_0(\\mathrm{{flíček}})={f_zero:.3f}\\ \\mathrm{{GHz}}$",
                     xy=(f_zero, 0.0), xytext=(f_zero, 15),
                     arrowprops=dict(arrowstyle="->", color='crimson'),
                     fontsize=9, fontweight='bold', color='crimson')

    ax2.set_title(r"2. Imaginární složka $\mathrm{Im}\{Z\}$ a vlastní rezonance flíčku", fontsize=12, fontweight='bold')
    ax2.set_ylabel(r"$\mathrm{Im}\{Z\}\ [\Omega]$", fontsize=11)
    ax2.grid(True, linestyle=':', alpha=0.6)
    ax2.legend(loc='best', fontsize=8, ncol=2)

    # --- PANEL 3: Lokální |Gamma| [dB] ---
    ax3.plot(freqs, rp1['gamma1_db'], label=r'RP1: Port 1 ($100\ \Omega$)', color='royalblue', lw=2)
    if rp1['gamma2_db'] is not None:
        ax3.plot(freqs, rp1['gamma2_db'], label=r'RP1: Port 2 ($100\ \Omega$)', color='cornflowerblue', lw=1.8, linestyle='--')

    ax3.plot(freqs, rp2['gamma1_db'], label=r'RP2: Svorka ($100\ \Omega$)', color='forestgreen', lw=2)
    if rp2['gamma2_db'] is not None:
        ax3.plot(freqs, rp2['gamma2_db'], label=r'RP2: Svorka ($100\ \Omega$)', color='mediumseagreen', lw=1.8, linestyle='--')

    ref_str = f"{rp3['z0_ref']:.0f}" if isinstance(rp3['z0_ref'], (int, float)) else "140"
    ax3.plot(freqs, rp3['gamma1_db'], label=f'RP3: Flíček 1 ({ref_str} $\\Omega$)', color='crimson', lw=2.2)
    if rp3['gamma2_db'] is not None:
        ax3.plot(freqs, rp3['gamma2_db'], label=f'RP3: Flíček 2 ({ref_str} $\\Omega$)', color='coral', lw=2.0, linestyle='--')

    ax3.axhline(-10.0, color='red', linestyle=':', lw=1.5, label='Kritérium -10 dB')
    ax3.set_title(r"3. Lokální činitel odrazu $|\Gamma|\ [\mathrm{dB}]$ v rovinách", fontsize=12, fontweight='bold')
    ax3.set_xlabel("Frekvence [GHz]", fontsize=11)
    ax3.set_ylabel(r"$|\Gamma|\ [\mathrm{dB}]$", fontsize=11)
    ax3.grid(True, linestyle=':', alpha=0.6)
    ax3.legend(loc='best', fontsize=8, ncol=2)

    # --- PANEL 4: Porovnání symetrie Port 1 vs Port 2 na RP3 ---
    ax4.plot(freqs, rp3['z1'].real, label=r'$\mathrm{Re}\{Z_1\}$ (Port 1, $E_y$)', color='navy', lw=2.2)
    if rp3['z2'] is not None:
        ax4.plot(freqs, rp3['z2'].real, label=r'$\mathrm{Re}\{Z_2\}$ (Port 2, $E_x$)', color='crimson', lw=2.2, linestyle='--')
        delta_re = np.abs(rp3['z1'].real - rp3['z2'].real)
    else:
        delta_re = None

    ax4.plot(freqs, rp3['z1'].imag, label=r'$\mathrm{Im}\{Z_1\}$ (Port 1, $E_y$)', color='navy', lw=1.8, linestyle=':')
    if rp3['z2'] is not None:
        ax4.plot(freqs, rp3['z2'].imag, label=r'$\mathrm{Im}\{Z_2\}$ (Port 2, $E_x$)', color='crimson', lw=1.8, linestyle='-.')

    ax4.axhline(rp3['z0_ref'], color='purple', linestyle='--', alpha=0.6, label=f'Cíl $R_{{patch}} = {rp3["z0_ref"]:.1f}\\ \\Omega$')
    ax4.axhline(0.0, color='black', linestyle='-', alpha=0.4)

    if delta_re is not None:
        ax4_twin = ax4.twinx()
        ax4_twin.plot(freqs, delta_re, color='dimgray', lw=1.3, linestyle='dotted', label=r'$|\Delta\mathrm{Re}\{Z\}|$')
        ax4_twin.set_ylabel(r'$|\Delta\mathrm{Re}\{Z\}|\ [\Omega]$', color='dimgray', fontsize=10)
        ax4_twin.tick_params(axis='y', labelcolor='dimgray')
        ax4_twin.set_ylim(bottom=0)

    ax4.set_title(r"4. Symetrie na vstupu do flíčku (RP3: Port 1 vs Port 2)", fontsize=12, fontweight='bold')
    ax4.set_xlabel("Frekvence [GHz]", fontsize=11)
    ax4.set_ylabel(r"Impedance flíčku $Z_{patch}\ [\Omega]$", fontsize=11)
    ax4.grid(True, linestyle=':', alpha=0.6)
    ax4.legend(loc='best', fontsize=8, ncol=2)

    # Globální záhlaví
    m_info = f"Model {model}"
    if model == 3:
        m_info += f" (Hybrid Matching: $w_T={p_used.get('w_T_b', 0.42):.2f}\\ \\mathrm{{mm}}$, $l_T={p_used.get('l_T_b', 18.9):.2f}\\ \\mathrm{{mm}}$)"
    elif model == 2:
        m_info += " (Dvouportový $100\\ \\Omega$ bez transformátoru)"

    plt.suptitle(f"Analytický de-embedding impedančních skoků napájecí sítě — {m_info}\nRP1 (Port) $\\to$ RP2 (Svorka) $\\to$ RP3 (Flíček)",
                 fontsize=13, fontweight='bold', y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.95])

    os.makedirs(os.path.dirname(os.path.abspath(output_png)) or ".", exist_ok=True)
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
    args = parser.parse_args()

    plot_impedance_deembedding(args.export_dir, output_png=args.output)
