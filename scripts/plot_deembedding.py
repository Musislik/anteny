"""
plot_deembedding.py - Analytical de-embedding of impedance discontinuities and evaluation of reference planes.
Generates diagnostic plot 'plot_deembedding.png':
  - Rule 1: One measurement plane = one impedance plot (Re and Im) and one reflection coefficient plot (|Gamma| in dB).
    * RP1 (Port): Zin plot (Re and Im with zero axis and 100 Ohm reference) + S11 in dB (with -10 dB limit and S21 isolation curve).
    * RP2 (Transformer terminal): Z_RP2 plot (Re and Im with 100 Ohm reference and zero) + local |Gamma_RP2| in dB.
    * RP3 (Patch input): Z_patch plot (Re and Im with 140 Ohm reference and zero for resonance f0) + local |Gamma_patch| in dB.
  - Rule 2: If only a single port is driven (DRIVEN_PORT=1 or 2):
    * Plot ONLY the active path! The passive port is NOT shown in impedance or de-embedding plots.
    * The only data shown from the second port is the crosstalk/isolation curve S21 in dB in the RP1 plot for energy leakage overview.
  - Rule 3: If both ports are driven (DRIVEN_PORT=all):
    * Separate display of ports organized into clear columns (Port 1 on left, Port 2 on right), or cleanly separated curves.
"""

import os
import sys
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Ensure access to src modules (rf_calc, postpro_utils)
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_CURRENT_DIR, ".."))
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
for p in (_CURRENT_DIR, _SRC_DIR, _ROOT_DIR):
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

try:
    import _env  # noqa: F401
except ImportError:
    pass

from postpro_utils import load_env, load_port_v_voltages
from rf_calc import calculate_deembedding_model3, DESIGN_FREQ_GHZ


def _load_simulation_s_params(export_dir, driven_port=None):
    """
    Search for and load S-parameters or port voltages/currents from simulation files
    (port-S.csv or port-V.csv) in the given directory or postpro subdirectory.
    Returns: (freqs, s11_complex, s22_complex, iso_complex, detected_driven_port)
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

    # Normalize driven_port parameter
    dp_hint = str(driven_port).lower().strip() if driven_port is not None else None

    # 1. Try loading from port-S.csv
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

            # Fallback only when both reflection columns are missing and generic columns exist
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
            print(f"Warning while loading {s_path}: {e}")

    # 2. Try loading from port-V.csv (if S-parameters are unavailable)
    if (s11_complex is None and s22_complex is None) and v_path:
        try:
            v_freqs, v_s11, v_s22, v_s21, v_s12 = load_port_v_voltages(v_path)
            if v_freqs is not None:
                if freqs is None:
                    freqs = v_freqs
                s11_complex = v_s11
                s22_complex = v_s22
                s21_complex = v_s21
                s12_complex = v_s12
        except Exception as e:
            print(f"Warning while loading {v_path}: {e}")

    # Select crosstalk/isolation curve (reciprocity S21 approx. S12)
    iso_complex = s21_complex if s21_complex is not None else s12_complex

    # Auto-detect driven port
    if s11_complex is not None and s22_complex is not None:
        if dp_hint in ("1", "2"):
            detected_driven_port = dp_hint
        else:
            detected_driven_port = "all"
    elif s22_complex is not None:
        detected_driven_port = "2"
    else:
        detected_driven_port = "1"

    # Rule 2: If only a single port is driven, do not return the passive port
    if detected_driven_port == "1":
        s22_complex = None
    elif detected_driven_port == "2":
        s11_complex = None

    return freqs, s11_complex, s22_complex, iso_complex, detected_driven_port


def _resolve_deembedding_params(export_dir, explicit_params=None):
    """
    Safely resolve model parameters from an explicit dictionary, params.json,
    config.json, or default design values.
    """
    params = {}
    if explicit_params:
        params.update(explicit_params)

    # 1. Try loading params.json
    params_candidates = [
        os.path.join(export_dir, "params.json"),
        os.path.join(export_dir, "..", "params.json"),
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

    # 2. Try loading config.json / config_resolved.json
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

    # 3. Defaults (Model 3, or 50 Ohm for Model 1)
    model_hint = int(params.get('antenna_model', 3) or 3)
    default_z0 = 100.0 if model_hint in (2, 3, 5, 6) else 50.0
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
        'port_impedance': default_z0,
        'driven_port': os.getenv('DRIVEN_PORT', None),
    }
    for k, v in defaults.items():
        if k not in params or params[k] is None:
            params[k] = v

    return params


def _detect_resonance(freqs, im_z):
    """
    Detect zero crossing of Im{Z}=0 (patch resonance) via linear interpolation.
    Returns f0 in GHz or None.
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
    Compute and plot the structured impedance de-embedding diagnostic figure.
    - Rule 1: 1 reference plane = 1 impedance plot (Re and Im) + 1 reflection coefficient plot (|Gamma| in dB).
    - Rule 2: If only a single port is driven (1 or 2), plot ONLY the active path.
              The passive port is omitted; only the crosstalk curve S21 is shown in RP1.
    - Rule 3: When both ports are driven ('all'), ports are cleanly separated (two columns: Port 1 left, Port 2 right).

    :param export_dir: Directory with simulation results
    :param params: Model parameter dictionary (optional)
    :param output_png: Output PNG plot path (optional)
    :param layout: "split" (3x4 for all) or "compact" (3x2 for all)
    :return: Path to the generated plot file
    """
    if output_png is None:
        output_png = os.path.join(export_dir, "plot_deembedding.png")
    output_png = os.path.abspath(os.path.normpath(output_png))

    resolved_params = _resolve_deembedding_params(export_dir, explicit_params=params)
    hint_dp = resolved_params.get('driven_port')

    freqs, s11_complex, s22_complex, iso_complex, driven_mode = _load_simulation_s_params(export_dir, driven_port=hint_dp)

    if freqs is None or (s11_complex is None and s22_complex is None) or len(freqs) == 0:
        print(f"[De-embedding] Neither port-S.csv nor port-V.csv data was found in {export_dir}!")
        return None

    resolved_params['driven_port'] = driven_mode

    # Analytical cascaded de-embedding
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
    z0_ref_rp1 = float(rp1['z0_ref'])
    z0_ref_rp2 = float(np.mean(rp2['z0_ref']))
    z0_ref_rp3 = rp3['z0_ref']

    iso_db = 20.0 * np.log10(np.clip(np.abs(iso_complex), 1e-10, 10.0)) if iso_complex is not None else None

    # Style and colors
    c_p1_re = 'royalblue'
    c_p1_im = 'deepskyblue'
    c_p2_re = 'firebrick'
    c_p2_im = 'coral'
    c_iso = 'purple'
    c_limit = 'red'

    m_info = f"Model {model}"
    if model == 6:
        m_info += f" (Two-port curved $100\\ \\Omega$ with internal ports: $w_T={p_used.get('w_T_b', 0.42):.2f}\\ \\mathrm{{mm}}$, $l_T={p_used.get('l_T_b', 18.9):.2f}\\ \\mathrm{{mm}}$)"
    elif model == 5:
        m_info += f" (Two-port curved $100\\ \\Omega$: $w_T={p_used.get('w_T_b', 0.42):.2f}\\ \\mathrm{{mm}}$, $l_T={p_used.get('l_T_b', 18.9):.2f}\\ \\mathrm{{mm}}$)"
    elif model == 4:
        m_info += f" (Final $50\\ \\Omega$ T-junction + bends: $L_{{50}}={p_used.get('feed_50_len', 9.0):.1f}\\ \\mathrm{{mm}}$, $w_T={p_used.get('w_T_b', 0.42):.2f}\\ \\mathrm{{mm}}$)"
    elif model == 3:
        m_info += f" (Hybrid two-stage matching: $w_T={p_used.get('w_T_b', 0.42):.2f}\\ \\mathrm{{mm}}$, $l_T={p_used.get('l_T_b', 18.9):.2f}\\ \\mathrm{{mm}}$)"
    elif model == 2:
        m_info += " (Two-port $100\\ \\Omega$ without transformer)"

    # =========================================================================
    # MODE 1: SINGLE PORT EXCITATION (Rule 1 and Rule 2)
    # =========================================================================
    if driven_mode in ("1", "2"):
        active_p = int(driven_mode)
        if model == 4:
            p_name = r"Port ($50\ \Omega$ T-junction)"
        else:
            p_name = r"Port 1 ($E_y$, bottom)" if active_p == 1 else r"Port 2 ($E_x$, left)"
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
        # ROW 1: RP1 (Port)
        # ---------------------------------------------------------------------
        # Zin plot (Re and Im with zero axis)
        ax1_imp = axes[0, 0]
        ax1_imp.plot(freqs, z_rp1.real, label=rf"$\mathrm{{Re}}\{{Z_{{in}}\}}$ ({p_name})", color=c_re, lw=2.2)
        ax1_imp.plot(freqs, z_rp1.imag, label=rf"$\mathrm{{Im}}\{{Z_{{in}}\}}$ ({p_name})", color=c_im, lw=1.8, linestyle='--')
        ax1_imp.axhline(z0_ref_rp1, color='gray', linestyle='--', alpha=0.7, label=rf"Target $Z_0 = {z0_ref_rp1:.0f}\ \Omega$")
        ax1_imp.axhline(0.0, color='black', linestyle='-', alpha=0.4, label=r"$\mathrm{Im}\{Z\} = 0\ \Omega$")
        ax1_imp.set_title(rf"1. RP1 (Port): Input Impedance $Z_{{in}}$ — {p_name}", fontsize=11, fontweight='bold')
        ax1_imp.set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
        ax1_imp.grid(True, linestyle=':', alpha=0.6)
        ax1_imp.legend(loc='best', fontsize=8, ncol=2)

        # S11 plot in dB (with -10 dB limit and S21 isolation curve)
        ax1_gam = axes[0, 1]
        ax1_gam.plot(freqs, gamma_rp1_db, label=rf"$|{s_lbl}|$ ({p_name})", color=c_re, lw=2.2)
        min_g1_idx = np.argmin(gamma_rp1_db)
        ax1_gam.plot(freqs[min_g1_idx], gamma_rp1_db[min_g1_idx], 'o', color=c_re,
                     label=f"Min $|{s_lbl}|$: {gamma_rp1_db[min_g1_idx]:.2f} dB @ {freqs[min_g1_idx]:.3f} GHz")
        ax1_gam.axhline(-10.0, color=c_limit, linestyle='--', lw=1.5, label='-10 dB Criterion')
        if iso_db is not None:
            ax1_gam.plot(freqs, iso_db, label=rf"Isolation / crosstalk $|{iso_lbl}|$", color=c_iso, lw=1.8, linestyle=':')
        ax1_gam.set_title(rf"2. RP1 (Port): Reflection $|{s_lbl}|$ and Crosstalk $|{iso_lbl}|$", fontsize=11, fontweight='bold')
        ax1_gam.set_ylabel(r"Magnitude [dB]", fontsize=10)
        ax1_gam.grid(True, linestyle=':', alpha=0.6)
        ax1_gam.legend(loc='best', fontsize=8)

        # ---------------------------------------------------------------------
        # ROW 2: RP2 (Transformer terminal)
        # ---------------------------------------------------------------------
        # Z_RP2 plot (Re and Im with reference)
        ax2_imp = axes[1, 0]
        ax2_imp.plot(freqs, z_rp2.real, label=rf"$\mathrm{{Re}}\{{Z_{{RP2}}\}}$", color=c_re, lw=2.2)
        ax2_imp.plot(freqs, z_rp2.imag, label=rf"$\mathrm{{Im}}\{{Z_{{RP2}}\}}$", color=c_im, lw=1.8, linestyle='--')
        ax2_imp.axhline(z0_ref_rp2, color='gray', linestyle='--', alpha=0.7, label=rf"Reference ${z0_ref_rp2:.0f}\ \Omega$")
        ax2_imp.axhline(0.0, color='black', linestyle='-', alpha=0.4, label=r"$\mathrm{Im}\{Z\} = 0\ \Omega$")
        ax2_imp.set_title(rf"3. {rp2['name']}: Impedance $Z_{{RP2}}$", fontsize=11, fontweight='bold')
        ax2_imp.set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
        ax2_imp.grid(True, linestyle=':', alpha=0.6)
        ax2_imp.legend(loc='best', fontsize=8, ncol=2)

        # Local |Gamma_RP2| in dB
        ax2_gam = axes[1, 1]
        ax2_gam.plot(freqs, gamma_rp2_db, label=rf"Local $|\Gamma_{{RP2}}|$ (ref ${z0_ref_rp2:.0f}\ \Omega$)", color=c_re, lw=2.2)
        min_g2_idx = np.argmin(gamma_rp2_db)
        ax2_gam.plot(freqs[min_g2_idx], gamma_rp2_db[min_g2_idx], 'o', color=c_re,
                     label=rf"Min $|\Gamma_{{RP2}}|: {gamma_rp2_db[min_g2_idx]:.2f}$ dB @ {freqs[min_g2_idx]:.3f} GHz")
        ax2_gam.axhline(-10.0, color=c_limit, linestyle='--', lw=1.5, label='-10 dB Criterion')
        ax2_gam.set_title(rf"4. {rp2['name']}: Local Reflection Coefficient $|\Gamma_{{RP2}}| ({z0_ref_rp2:.0f}\ \Omega)$", fontsize=11, fontweight='bold')
        ax2_gam.set_ylabel(r"Magnitude [dB]", fontsize=10)
        ax2_gam.grid(True, linestyle=':', alpha=0.6)
        ax2_gam.legend(loc='best', fontsize=8)

        # ---------------------------------------------------------------------
        # ROW 3: RP3 (Patch input / T-junction branch)
        # ---------------------------------------------------------------------
        # Z_patch plot (Re and Im with reference and zero for resonance f0)
        ax3_imp = axes[2, 0]
        rp3_z_sym = r"Z_{branch}" if model == 4 else r"Z_{patch}"
        rp3_gam_sym = r"\Gamma_{branch}" if model == 4 else r"\Gamma_{patch}"
        ax3_imp.plot(freqs, z_rp3.real, label=rf"$\mathrm{{Re}}\{{{rp3_z_sym}\}}$", color=c_re, lw=2.2)
        ax3_imp.plot(freqs, z_rp3.imag, label=rf"$\mathrm{{Im}}\{{{rp3_z_sym}\}}$", color=c_im, lw=1.8, linestyle='--')
        ax3_imp.axhline(z0_ref_rp3, color='mediumvioletred', linestyle='--', alpha=0.8,
                        label=rf"Target $R \approx {z0_ref_rp3:.1f}\ \Omega$")
        ax3_imp.axhline(0.0, color='black', linestyle='-', alpha=0.5, label=r"Resonance $\mathrm{Im}\{Z\}=0$")

        # Detect and annotate intrinsic resonance f0
        f0_patch = _detect_resonance(freqs, z_rp3.imag)
        if f0_patch is not None and (freqs[0] <= f0_patch <= freqs[-1]):
            r_at_f0 = float(np.interp(f0_patch, freqs, z_rp3.real))
            ax3_imp.plot(f0_patch, 0.0, 'ro', markersize=7, label=rf"Resonance $f_0={f0_patch:.3f}\ \mathrm{{GHz}}$")
            y_offset = max(20.0, float(np.max(z_rp3.real)) * 0.15)
            ax3_imp.annotate(rf"$f_0={f0_patch:.3f}\ \mathrm{{GHz}}$" + "\n" + rf"$R={r_at_f0:.1f}\ \Omega$",
                             xy=(f0_patch, 0.0), xytext=(f0_patch, y_offset),
                             arrowprops=dict(arrowstyle="->", color='crimson', lw=1.5),
                             fontsize=9, fontweight='bold', color='crimson')

        ax3_imp.set_title(rf"5. {rp3['name']}: Impedance ${rp3_z_sym}$", fontsize=11, fontweight='bold')
        ax3_imp.set_xlabel("Frequency [GHz]", fontsize=10)
        ax3_imp.set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
        ax3_imp.grid(True, linestyle=':', alpha=0.6)
        ax3_imp.legend(loc='best', fontsize=8, ncol=2)

        # Local |Gamma_patch| in dB
        ax3_gam = axes[2, 1]
        ax3_gam.plot(freqs, gamma_rp3_db, label=rf"Local $|{rp3_gam_sym}|$ (ref {z0_ref_rp3:.0f} $\Omega$)", color=c_re, lw=2.2)
        min_g3_idx = np.argmin(gamma_rp3_db)
        ax3_gam.plot(freqs[min_g3_idx], gamma_rp3_db[min_g3_idx], 'o', color=c_re,
                     label=rf"Min $|{rp3_gam_sym}|: {gamma_rp3_db[min_g3_idx]:.2f}$ dB @ {freqs[min_g3_idx]:.3f} GHz")
        ax3_gam.axhline(-10.0, color=c_limit, linestyle='--', lw=1.5, label='-10 dB Criterion')
        ax3_gam.set_title(rf"6. {rp3['name']}: Local Reflection Coefficient $|{rp3_gam_sym}| ({z0_ref_rp3:.0f}\ \Omega)$",
                          fontsize=11, fontweight='bold')
        ax3_gam.set_xlabel("Frequency [GHz]", fontsize=10)
        ax3_gam.set_ylabel(r"Magnitude [dB]", fontsize=10)
        ax3_gam.grid(True, linestyle=':', alpha=0.6)
        ax3_gam.legend(loc='best', fontsize=8)

        # Global suptitle
        plt.suptitle(f"Analytical Feed-Network De-Embedding — {m_info}\n"
                     f"Active excitation: {p_name} — RP1 (Port) $\\to$ RP2 (Terminal) $\\to$ RP3 (Patch)",
                     fontsize=12, fontweight='bold', y=0.98)
        plt.tight_layout(rect=[0, 0, 1, 0.95])

    # =========================================================================
    # MODE 2: TWO-PORT EXCITATION (Rule 3)
    # =========================================================================
    else:
        # Layout choice: "split" = two separate column blocks (Port 1 left, Port 2 right)
        if layout == "split":
            fig, axes = plt.subplots(3, 4, figsize=(20, 11), sharex=True)

            # --- ROW 1: RP1 (Port) ---
            # Port 1: Zin1
            axes[0, 0].plot(freqs, rp1['z1'].real, label=r"$\mathrm{Re}\{Z_{in1}\}$", color=c_p1_re, lw=2.2)
            axes[0, 0].plot(freqs, rp1['z1'].imag, label=r"$\mathrm{Im}\{Z_{in1}\}$", color=c_p1_im, lw=1.8, linestyle='--')
            axes[0, 0].axhline(z0_ref_rp1, color='gray', linestyle='--', alpha=0.7, label=rf"Target ${z0_ref_rp1:.0f}\ \Omega$")
            axes[0, 0].axhline(0.0, color='black', linestyle='-', alpha=0.4)
            axes[0, 0].set_title(r"RP1 (Port 1, $E_y$): Impedance $Z_{in1}$", fontsize=11, fontweight='bold')
            axes[0, 0].set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
            axes[0, 0].grid(True, linestyle=':', alpha=0.6)
            axes[0, 0].legend(loc='best', fontsize=8)

            # Port 1: S11 and S21
            axes[0, 1].plot(freqs, rp1['gamma1_db'], label=r"$|S_{11}|$", color=c_p1_re, lw=2.2)
            min1_idx = np.argmin(rp1['gamma1_db'])
            axes[0, 1].plot(freqs[min1_idx], rp1['gamma1_db'][min1_idx], 'o', color=c_p1_re,
                            label=f"Min $|S_{{11}}|: {rp1['gamma1_db'][min1_idx]:.2f} dB")
            if iso_db is not None:
                axes[0, 1].plot(freqs, iso_db, label=r"Isolation $|S_{21}|$", color=c_iso, lw=1.8, linestyle=':')
            axes[0, 1].axhline(-10.0, color=c_limit, linestyle='--', lw=1.5, label='-10 dB')
            axes[0, 1].set_title(r"RP1 (Port 1): Reflection $|S_{11}|$ & Crosstalk", fontsize=11, fontweight='bold')
            axes[0, 1].set_ylabel(r"Magnitude [dB]", fontsize=10)
            axes[0, 1].grid(True, linestyle=':', alpha=0.6)
            axes[0, 1].legend(loc='best', fontsize=8)

            # Port 2: Zin2
            axes[0, 2].plot(freqs, rp1['z2'].real, label=r"$\mathrm{Re}\{Z_{in2}\}$", color=c_p2_re, lw=2.2)
            axes[0, 2].plot(freqs, rp1['z2'].imag, label=r"$\mathrm{Im}\{Z_{in2}\}$", color=c_p2_im, lw=1.8, linestyle='--')
            axes[0, 2].axhline(z0_ref_rp1, color='gray', linestyle='--', alpha=0.7, label=rf"Target ${z0_ref_rp1:.0f}\ \Omega$")
            axes[0, 2].axhline(0.0, color='black', linestyle='-', alpha=0.4)
            axes[0, 2].set_title(r"RP1 (Port 2, $E_x$): Impedance $Z_{in2}$", fontsize=11, fontweight='bold')
            axes[0, 2].set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
            axes[0, 2].grid(True, linestyle=':', alpha=0.6)
            axes[0, 2].legend(loc='best', fontsize=8)

            # Port 2: S22 and S12
            axes[0, 3].plot(freqs, rp1['gamma2_db'], label=r"$|S_{22}|$", color=c_p2_re, lw=2.2)
            min2_idx = np.argmin(rp1['gamma2_db'])
            axes[0, 3].plot(freqs[min2_idx], rp1['gamma2_db'][min2_idx], 'o', color=c_p2_re,
                            label=f"Min $|S_{{22}}|: {rp1['gamma2_db'][min2_idx]:.2f} dB")
            if iso_db is not None:
                axes[0, 3].plot(freqs, iso_db, label=r"Isolation $|S_{12}|$", color=c_iso, lw=1.8, linestyle=':')
            axes[0, 3].axhline(-10.0, color=c_limit, linestyle='--', lw=1.5, label='-10 dB')
            axes[0, 3].set_title(r"RP1 (Port 2): Reflection $|S_{22}|$ & Crosstalk", fontsize=11, fontweight='bold')
            axes[0, 3].set_ylabel(r"Magnitude [dB]", fontsize=10)
            axes[0, 3].grid(True, linestyle=':', alpha=0.6)
            axes[0, 3].legend(loc='best', fontsize=8)

            # --- ROW 2: RP2 (Transformer terminal) ---
            # Port 1: Z_RP2_1
            axes[1, 0].plot(freqs, rp2['z1'].real, label=r"$\mathrm{Re}\{Z_{RP2,1}\}$", color=c_p1_re, lw=2.2)
            axes[1, 0].plot(freqs, rp2['z1'].imag, label=r"$\mathrm{Im}\{Z_{RP2,1}\}$", color=c_p1_im, lw=1.8, linestyle='--')
            axes[1, 0].axhline(z0_ref_rp2, color='gray', linestyle='--', alpha=0.7, label=rf"Ref ${z0_ref_rp2:.0f}\ \Omega$")
            axes[1, 0].axhline(0.0, color='black', linestyle='-', alpha=0.4)
            axes[1, 0].set_title(r"RP2 (Port 1): Impedance $Z_{RP2}$", fontsize=11, fontweight='bold')
            axes[1, 0].set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
            axes[1, 0].grid(True, linestyle=':', alpha=0.6)
            axes[1, 0].legend(loc='best', fontsize=8)

            # Port 1: |Gamma_RP2_1|
            axes[1, 1].plot(freqs, rp2['gamma1_db'], label=r"$|\Gamma_{RP2,1}|$", color=c_p1_re, lw=2.2)
            axes[1, 1].axhline(-10.0, color=c_limit, linestyle='--', lw=1.5, label='-10 dB')
            axes[1, 1].set_title(rf"RP2 (Port 1): Reflection Coefficient $|\Gamma_{{RP2}}| ({z0_ref_rp2:.0f}\ \Omega)$", fontsize=11, fontweight='bold')
            axes[1, 1].set_ylabel(r"Magnitude [dB]", fontsize=10)
            axes[1, 1].grid(True, linestyle=':', alpha=0.6)
            axes[1, 1].legend(loc='best', fontsize=8)

            # Port 2: Z_RP2_2
            axes[1, 2].plot(freqs, rp2['z2'].real, label=r"$\mathrm{Re}\{Z_{RP2,2}\}$", color=c_p2_re, lw=2.2)
            axes[1, 2].plot(freqs, rp2['z2'].imag, label=r"$\mathrm{Im}\{Z_{RP2,2}\}$", color=c_p2_im, lw=1.8, linestyle='--')
            axes[1, 2].axhline(z0_ref_rp2, color='gray', linestyle='--', alpha=0.7, label=rf"Ref ${z0_ref_rp2:.0f}\ \Omega$")
            axes[1, 2].axhline(0.0, color='black', linestyle='-', alpha=0.4)
            axes[1, 2].set_title(r"RP2 (Port 2): Impedance $Z_{RP2}$", fontsize=11, fontweight='bold')
            axes[1, 2].set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
            axes[1, 2].grid(True, linestyle=':', alpha=0.6)
            axes[1, 2].legend(loc='best', fontsize=8)

            # Port 2: |Gamma_RP2_2|
            axes[1, 3].plot(freqs, rp2['gamma2_db'], label=r"$|\Gamma_{RP2,2}|$", color=c_p2_re, lw=2.2)
            axes[1, 3].axhline(-10.0, color=c_limit, linestyle='--', lw=1.5, label='-10 dB')
            axes[1, 3].set_title(rf"RP2 (Port 2): Reflection Coefficient $|\Gamma_{{RP2}}| ({z0_ref_rp2:.0f}\ \Omega)$", fontsize=11, fontweight='bold')
            axes[1, 3].set_ylabel(r"Magnitude [dB]", fontsize=10)
            axes[1, 3].grid(True, linestyle=':', alpha=0.6)
            axes[1, 3].legend(loc='best', fontsize=8)

            # --- ROW 3: RP3 (Patch input) ---
            # Port 1: Z_patch1
            axes[2, 0].plot(freqs, rp3['z1'].real, label=r"$\mathrm{Re}\{Z_{patch1}\}$", color=c_p1_re, lw=2.2)
            axes[2, 0].plot(freqs, rp3['z1'].imag, label=r"$\mathrm{Im}\{Z_{patch1}\}$", color=c_p1_im, lw=1.8, linestyle='--')
            axes[2, 0].axhline(z0_ref_rp3, color='mediumvioletred', linestyle='--', alpha=0.7,
                            label=rf"Target {z0_ref_rp3:.0f} $\Omega$")
            axes[2, 0].axhline(0.0, color='black', linestyle='-', alpha=0.4)
            f0_p1 = _detect_resonance(freqs, rp3['z1'].imag)
            if f0_p1 is not None and (freqs[0] <= f0_p1 <= freqs[-1]):
                axes[2, 0].plot(f0_p1, 0.0, 'ro', markersize=6)
                axes[2, 0].annotate(rf"$f_{{0,1}}={f0_p1:.3f}$", xy=(f0_p1, 0.0), xytext=(f0_p1, 15),
                                   arrowprops=dict(arrowstyle="->", color='crimson'), fontsize=8, color='crimson')
            axes[2, 0].set_title(r"RP3 (Port 1): Patch Impedance $Z_{patch}$", fontsize=11, fontweight='bold')
            axes[2, 0].set_xlabel("Frequency [GHz]", fontsize=10)
            axes[2, 0].set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
            axes[2, 0].grid(True, linestyle=':', alpha=0.6)
            axes[2, 0].legend(loc='best', fontsize=8)

            # Port 1: |Gamma_patch1|
            axes[2, 1].plot(freqs, rp3['gamma1_db'], label=rf"$|\Gamma_{{patch1}}|$", color=c_p1_re, lw=2.2)
            axes[2, 1].axhline(-10.0, color=c_limit, linestyle='--', lw=1.5, label='-10 dB')
            axes[2, 1].set_title(rf"RP3 (Port 1): Reflection $|\Gamma_{{patch}}| ({z0_ref_rp3:.0f}\ \Omega)$", fontsize=11, fontweight='bold')
            axes[2, 1].set_xlabel("Frequency [GHz]", fontsize=10)
            axes[2, 1].set_ylabel(r"Magnitude [dB]", fontsize=10)
            axes[2, 1].grid(True, linestyle=':', alpha=0.6)
            axes[2, 1].legend(loc='best', fontsize=8)

            # Port 2: Z_patch2
            axes[2, 2].plot(freqs, rp3['z2'].real, label=r"$\mathrm{Re}\{Z_{patch2}\}$", color=c_p2_re, lw=2.2)
            axes[2, 2].plot(freqs, rp3['z2'].imag, label=r"$\mathrm{Im}\{Z_{patch2}\}$", color=c_p2_im, lw=1.8, linestyle='--')
            axes[2, 2].axhline(z0_ref_rp3, color='mediumvioletred', linestyle='--', alpha=0.7,
                            label=rf"Target {z0_ref_rp3:.0f} $\Omega$")
            axes[2, 2].axhline(0.0, color='black', linestyle='-', alpha=0.4)
            f0_p2 = _detect_resonance(freqs, rp3['z2'].imag)
            if f0_p2 is not None and (freqs[0] <= f0_p2 <= freqs[-1]):
                axes[2, 2].plot(f0_p2, 0.0, 'ro', markersize=6)
                axes[2, 2].annotate(rf"$f_{{0,2}}={f0_p2:.3f}$", xy=(f0_p2, 0.0), xytext=(f0_p2, 15),
                                   arrowprops=dict(arrowstyle="->", color='crimson'), fontsize=8, color='crimson')
            axes[2, 2].set_title(r"RP3 (Port 2): Patch Impedance $Z_{patch}$", fontsize=11, fontweight='bold')
            axes[2, 2].set_xlabel("Frequency [GHz]", fontsize=10)
            axes[2, 2].set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
            axes[2, 2].grid(True, linestyle=':', alpha=0.6)
            axes[2, 2].legend(loc='best', fontsize=8)

            # Port 2: |Gamma_patch2|
            axes[2, 3].plot(freqs, rp3['gamma2_db'], label=rf"$|\Gamma_{{patch2}}|$", color=c_p2_re, lw=2.2)
            axes[2, 3].axhline(-10.0, color=c_limit, linestyle='--', lw=1.5, label='-10 dB')
            axes[2, 3].set_title(rf"RP3 (Port 2): Reflection $|\Gamma_{{patch}}| ({z0_ref_rp3:.0f}\ \Omega)$", fontsize=11, fontweight='bold')
            axes[2, 3].set_xlabel("Frequency [GHz]", fontsize=10)
            axes[2, 3].set_ylabel(r"Magnitude [dB]", fontsize=10)
            axes[2, 3].grid(True, linestyle=':', alpha=0.6)
            axes[2, 3].legend(loc='best', fontsize=8)

            # Global suptitle
            plt.suptitle(f"Analytical Feed-Network De-Embedding — {m_info}\n"
                         r"Two-port view: Port 1 ($E_y$) left vs. Port 2 ($E_x$) right",
                         fontsize=12, fontweight='bold', y=0.98)
            plt.tight_layout(rect=[0, 0, 1, 0.95])

        else:
            # Compact 3x2 layout with cleanly separated curves
            fig, axes = plt.subplots(3, 2, figsize=(14, 11), sharex=True)

            # ROW 1: RP1
            ax0 = axes[0, 0]
            ax0.plot(freqs, rp1['z1'].real, label=r"$\mathrm{Re}\{Z_{in1}\}$ (P1, $E_y$)", color=c_p1_re, lw=2.2)
            ax0.plot(freqs, rp1['z1'].imag, label=r"$\mathrm{Im}\{Z_{in1}\}$ (P1)", color=c_p1_im, lw=1.8, linestyle='--')
            ax0.plot(freqs, rp1['z2'].real, label=r"$\mathrm{Re}\{Z_{in2}\}$ (P2, $E_x$)", color=c_p2_re, lw=2.2)
            ax0.plot(freqs, rp1['z2'].imag, label=r"$\mathrm{Im}\{Z_{in2}\}$ (P2)", color=c_p2_im, lw=1.8, linestyle='--')
            ax0.axhline(z0_ref_rp1, color='gray', linestyle='--', alpha=0.7, label=rf"Target ${z0_ref_rp1:.0f}\ \Omega$")
            ax0.axhline(0.0, color='black', linestyle='-', alpha=0.4)
            ax0.set_title(r"1. RP1 (Port): Input Impedance $Z_{in}$ (Port 1 vs Port 2)", fontsize=11, fontweight='bold')
            ax0.set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
            ax0.grid(True, linestyle=':', alpha=0.6)
            ax0.legend(loc='best', fontsize=8, ncol=2)

            ax1 = axes[0, 1]
            ax1.plot(freqs, rp1['gamma1_db'], label=r"$|S_{11}|$ (Port 1)", color=c_p1_re, lw=2.2)
            ax1.plot(freqs, rp1['gamma2_db'], label=r"$|S_{22}|$ (Port 2)", color=c_p2_re, lw=2.2, linestyle='--')
            if iso_db is not None:
                ax1.plot(freqs, iso_db, label=r"Isolation $|S_{21}|$", color=c_iso, lw=1.8, linestyle=':')
            ax1.axhline(-10.0, color=c_limit, linestyle='--', lw=1.5, label='-10 dB Criterion')
            ax1.set_title(r"2. RP1 (Port): Reflection Coefficients & Crosstalk", fontsize=11, fontweight='bold')
            ax1.set_ylabel(r"Magnitude [dB]", fontsize=10)
            ax1.grid(True, linestyle=':', alpha=0.6)
            ax1.legend(loc='best', fontsize=8)

            # ROW 2: RP2
            ax2 = axes[1, 0]
            ax2.plot(freqs, rp2['z1'].real, label=r"$\mathrm{Re}\{Z_{RP2,1}\}$ (P1)", color=c_p1_re, lw=2.2)
            ax2.plot(freqs, rp2['z1'].imag, label=r"$\mathrm{Im}\{Z_{RP2,1}\}$ (P1)", color=c_p1_im, lw=1.8, linestyle='--')
            ax2.plot(freqs, rp2['z2'].real, label=r"$\mathrm{Re}\{Z_{RP2,2}\}$ (P2)", color=c_p2_re, lw=2.2)
            ax2.plot(freqs, rp2['z2'].imag, label=r"$\mathrm{Im}\{Z_{RP2,2}\}$ (P2)", color=c_p2_im, lw=1.8, linestyle='--')
            ax2.axhline(z0_ref_rp2, color='gray', linestyle='--', alpha=0.7, label=rf"Ref ${z0_ref_rp2:.0f}\ \Omega$")
            ax2.axhline(0.0, color='black', linestyle='-', alpha=0.4)
            ax2.set_title(r"3. RP2 (Terminal): Impedance $Z_{RP2}$", fontsize=11, fontweight='bold')
            ax2.set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
            ax2.grid(True, linestyle=':', alpha=0.6)
            ax2.legend(loc='best', fontsize=8, ncol=2)

            ax3 = axes[1, 1]
            ax3.plot(freqs, rp2['gamma1_db'], label=r"$|\Gamma_{RP2,1}|$ (Port 1)", color=c_p1_re, lw=2.2)
            ax3.plot(freqs, rp2['gamma2_db'], label=r"$|\Gamma_{RP2,2}|$ (Port 2)", color=c_p2_re, lw=2.2, linestyle='--')
            ax3.axhline(-10.0, color=c_limit, linestyle='--', lw=1.5, label='-10 dB Criterion')
            ax3.set_title(rf"4. RP2 (Terminal): Local Reflection Coefficient $|\Gamma_{{RP2}}| ({z0_ref_rp2:.0f}\ \Omega)$", fontsize=11, fontweight='bold')
            ax3.set_ylabel(r"Magnitude [dB]", fontsize=10)
            ax3.grid(True, linestyle=':', alpha=0.6)
            ax3.legend(loc='best', fontsize=8)

            # ROW 3: RP3
            ax4 = axes[2, 0]
            ax4.plot(freqs, rp3['z1'].real, label=r"$\mathrm{Re}\{Z_{patch1}\}$ (P1)", color=c_p1_re, lw=2.2)
            ax4.plot(freqs, rp3['z1'].imag, label=r"$\mathrm{Im}\{Z_{patch1}\}$ (P1)", color=c_p1_im, lw=1.8, linestyle='--')
            ax4.plot(freqs, rp3['z2'].real, label=r"$\mathrm{Re}\{Z_{patch2}\}$ (P2)", color=c_p2_re, lw=2.2)
            ax4.plot(freqs, rp3['z2'].imag, label=r"$\mathrm{Im}\{Z_{patch2}\}$ (P2)", color=c_p2_im, lw=1.8, linestyle='--')
            ax4.axhline(z0_ref_rp3, color='mediumvioletred', linestyle='--', alpha=0.7, label=rf"Target {z0_ref_rp3:.0f} $\Omega$")
            ax4.axhline(0.0, color='black', linestyle='-', alpha=0.4)
            ax4.set_title(r"5. RP3 (Patch): Patch Impedance $Z_{patch}$", fontsize=11, fontweight='bold')
            ax4.set_xlabel("Frequency [GHz]", fontsize=10)
            ax4.set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
            ax4.grid(True, linestyle=':', alpha=0.6)
            ax4.legend(loc='best', fontsize=8, ncol=2)

            ax5 = axes[2, 1]
            ax5.plot(freqs, rp3['gamma1_db'], label=r"$|\Gamma_{patch1}|$ (Port 1)", color=c_p1_re, lw=2.2)
            ax5.plot(freqs, rp3['gamma2_db'], label=r"$|\Gamma_{patch2}|$ (Port 2)", color=c_p2_re, lw=2.2, linestyle='--')
            ax5.axhline(-10.0, color=c_limit, linestyle='--', lw=1.5, label='-10 dB Criterion')
            ax5.set_title(rf"6. RP3 (Patch): Local Reflection Coefficient $|\Gamma_{{patch}}| ({z0_ref_rp3:.0f}\ \Omega)$", fontsize=11, fontweight='bold')
            ax5.set_xlabel("Frequency [GHz]", fontsize=10)
            ax5.set_ylabel(r"Magnitude [dB]", fontsize=10)
            ax5.grid(True, linestyle=':', alpha=0.6)
            ax5.legend(loc='best', fontsize=8)

            plt.suptitle(f"Analytical Feed-Network De-Embedding — {m_info}\n"
                         r"Two-port excitation: RP1 (Port) $\to$ RP2 (Terminal) $\to$ RP3 (Patch)",
                         fontsize=12, fontweight='bold', y=0.98)
            plt.tight_layout(rect=[0, 0, 1, 0.95])

    os.makedirs(os.path.dirname(output_png) or ".", exist_ok=True)
    plt.savefig(output_png, dpi=200)
    plt.close()
    print(f"[De-embedding] Impedance discontinuity plot successfully saved to: {output_png}")

    # Save standalone plots for reference planes RP1, RP2, RP3 into the plots/ subfolder
    _save_individual_rp_plots(
        export_dir=export_dir,
        output_png=output_png,
        freqs=freqs,
        rp1=rp1,
        rp2=rp2,
        rp3=rp3,
        iso_db=iso_db,
        driven_mode=driven_mode,
        z0_ref_rp3=z0_ref_rp3,
        m_info=m_info
    )

    return output_png


def _save_individual_rp_plots(export_dir, output_png, freqs, rp1, rp2, rp3, iso_db, driven_mode, z0_ref_rp3, m_info):
    """Save standalone impedance and reflection coefficient plots for RP1, RP2, and RP3 into plots/."""
    z0_ref_rp1 = float(rp1['z0_ref'])
    z0_ref_rp2 = float(np.mean(rp2['z0_ref']))
    plots_dirs = [os.path.join(export_dir, "plots")]
    out_dir = os.path.dirname(output_png) if output_png else None
    if out_dir and os.path.abspath(out_dir) != os.path.abspath(export_dir):
        plots_dirs.append(os.path.join(out_dir, "plots"))

    c_p1_re = 'royalblue'
    c_p1_im = 'deepskyblue'
    c_p2_re = 'crimson'
    c_p2_im = 'coral'
    c_iso = 'purple'
    c_limit = 'red'

    for p_dir in plots_dirs:
        os.makedirs(p_dir, exist_ok=True)

        # -------------------------------------------------------------
        # 1. Reference Plane RP1: Feed Port
        # -------------------------------------------------------------
        fig1, (ax1_z, ax1_s) = plt.subplots(1, 2, figsize=(13, 5))
        if driven_mode == "1":
            ax1_z.plot(freqs, rp1['z1'].real, label=r"$\mathrm{Re}\{Z_{in1}\}$ (Port 1, $E_y$)", color=c_p1_re, lw=2.2)
            ax1_z.plot(freqs, rp1['z1'].imag, label=r"$\mathrm{Im}\{Z_{in1}\}$ (Port 1)", color=c_p1_im, lw=1.8, linestyle='--')
        elif driven_mode == "2":
            ax1_z.plot(freqs, rp1['z2'].real, label=r"$\mathrm{Re}\{Z_{in2}\}$ (Port 2, $E_x$)", color=c_p2_re, lw=2.2)
            ax1_z.plot(freqs, rp1['z2'].imag, label=r"$\mathrm{Im}\{Z_{in2}\}$ (Port 2)", color=c_p2_im, lw=1.8, linestyle='--')
        else:
            ax1_z.plot(freqs, rp1['z1'].real, label=r"$\mathrm{Re}\{Z_{in1}\}$ (P1, $E_y$)", color=c_p1_re, lw=2.2)
            ax1_z.plot(freqs, rp1['z1'].imag, label=r"$\mathrm{Im}\{Z_{in1}\}$ (P1)", color=c_p1_im, lw=1.8, linestyle='--')
            ax1_z.plot(freqs, rp1['z2'].real, label=r"$\mathrm{Re}\{Z_{in2}\}$ (P2, $E_x$)", color=c_p2_re, lw=2.2)
            ax1_z.plot(freqs, rp1['z2'].imag, label=r"$\mathrm{Im}\{Z_{in2}\}$ (P2)", color=c_p2_im, lw=1.8, linestyle='--')
        ax1_z.axhline(z0_ref_rp1, color='gray', linestyle='--', alpha=0.7, label=rf"Target $Z_0 = {z0_ref_rp1:.0f}\ \Omega$")
        ax1_z.axhline(0.0, color='black', linestyle='-', alpha=0.4, label=r"$\mathrm{Im}\{Z\} = 0\ \Omega$")
        ax1_z.set_title(r"Input Impedance $Z_{in}$ at Reference Plane RP1", fontsize=11, fontweight='bold')
        ax1_z.set_xlabel("Frequency [GHz]", fontsize=10)
        ax1_z.set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
        ax1_z.grid(True, linestyle=':', alpha=0.6)
        ax1_z.legend(loc='best', fontsize=8, ncol=2)

        if driven_mode == "1":
            ax1_s.plot(freqs, rp1['gamma1_db'], label=r"$|S_{11}|$ (Port 1)", color=c_p1_re, lw=2.2)
            m1 = np.argmin(rp1['gamma1_db'])
            ax1_s.plot(freqs[m1], rp1['gamma1_db'][m1], 'bo', label=f"Min $|S_{{11}}|: {rp1['gamma1_db'][m1]:.2f}$ dB")
            if iso_db is not None:
                ax1_s.plot(freqs, iso_db, label=r"Isolation $|S_{21}|$", color=c_iso, lw=1.8, linestyle=':')
        elif driven_mode == "2":
            ax1_s.plot(freqs, rp1['gamma2_db'], label=r"$|S_{22}|$ (Port 2)", color=c_p2_re, lw=2.2)
            m2 = np.argmin(rp1['gamma2_db'])
            ax1_s.plot(freqs[m2], rp1['gamma2_db'][m2], 'ro', label=f"Min $|S_{{22}}|: {rp1['gamma2_db'][m2]:.2f}$ dB")
            if iso_db is not None:
                ax1_s.plot(freqs, iso_db, label=r"Isolation $|S_{12}|$", color=c_iso, lw=1.8, linestyle=':')
        else:
            ax1_s.plot(freqs, rp1['gamma1_db'], label=r"$|S_{11}|$ (Port 1)", color=c_p1_re, lw=2.2)
            ax1_s.plot(freqs, rp1['gamma2_db'], label=r"$|S_{22}|$ (Port 2)", color=c_p2_re, lw=2.2, linestyle='--')
            if iso_db is not None:
                ax1_s.plot(freqs, iso_db, label=r"Isolation $|S_{21}|$", color=c_iso, lw=1.8, linestyle=':')
        ax1_s.axhline(-10.0, color=c_limit, linestyle='--', lw=1.5, label='-10 dB Criterion')
        ax1_s.set_title(r"Reflection Coefficient at RP1 (Port)", fontsize=11, fontweight='bold')
        ax1_s.set_xlabel("Frequency [GHz]", fontsize=10)
        ax1_s.set_ylabel(r"Magnitude [dB]", fontsize=10)
        ax1_s.grid(True, linestyle=':', alpha=0.6)
        ax1_s.legend(loc='best', fontsize=8)
        fig1.suptitle(f"Reference Plane RP1 (Feed Port) — {m_info}", fontsize=12, fontweight='bold')
        fig1.tight_layout()
        plt.savefig(os.path.join(p_dir, "plot_impedance_rp1.png"), dpi=200)
        plt.close(fig1)

        # -------------------------------------------------------------
        # 2. Reference Plane RP2: Transformer Terminal
        # -------------------------------------------------------------
        fig2, (ax2_z, ax2_s) = plt.subplots(1, 2, figsize=(13, 5))
        if driven_mode == "1":
            ax2_z.plot(freqs, rp2['z1'].real, label=r"$\mathrm{Re}\{Z_{RP2,1}\}$", color=c_p1_re, lw=2.2)
            ax2_z.plot(freqs, rp2['z1'].imag, label=r"$\mathrm{Im}\{Z_{RP2,1}\}$", color=c_p1_im, lw=1.8, linestyle='--')
        elif driven_mode == "2":
            ax2_z.plot(freqs, rp2['z2'].real, label=r"$\mathrm{Re}\{Z_{RP2,2}\}$", color=c_p2_re, lw=2.2)
            ax2_z.plot(freqs, rp2['z2'].imag, label=r"$\mathrm{Im}\{Z_{RP2,2}\}$", color=c_p2_im, lw=1.8, linestyle='--')
        else:
            ax2_z.plot(freqs, rp2['z1'].real, label=r"$\mathrm{Re}\{Z_{RP2,1}\}$ (P1)", color=c_p1_re, lw=2.2)
            ax2_z.plot(freqs, rp2['z1'].imag, label=r"$\mathrm{Im}\{Z_{RP2,1}\}$ (P1)", color=c_p1_im, lw=1.8, linestyle='--')
            ax2_z.plot(freqs, rp2['z2'].real, label=r"$\mathrm{Re}\{Z_{RP2,2}\}$ (P2)", color=c_p2_re, lw=2.2)
            ax2_z.plot(freqs, rp2['z2'].imag, label=r"$\mathrm{Im}\{Z_{RP2,2}\}$ (P2)", color=c_p2_im, lw=1.8, linestyle='--')
        ax2_z.axhline(z0_ref_rp2, color='gray', linestyle='--', alpha=0.7, label=rf"Reference ${z0_ref_rp2:.0f}\ \Omega$")
        ax2_z.axhline(0.0, color='black', linestyle='-', alpha=0.4, label=r"$\mathrm{Im}\{Z\} = 0\ \Omega$")
        ax2_z.set_title(r"Impedance $Z_{RP2}$ at Transformer Terminal", fontsize=11, fontweight='bold')
        ax2_z.set_xlabel("Frequency [GHz]", fontsize=10)
        ax2_z.set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
        ax2_z.grid(True, linestyle=':', alpha=0.6)
        ax2_z.legend(loc='best', fontsize=8, ncol=2)

        if driven_mode == "1":
            ax2_s.plot(freqs, rp2['gamma1_db'], label=r"$|\Gamma_{RP2,1}|$", color=c_p1_re, lw=2.2)
        elif driven_mode == "2":
            ax2_s.plot(freqs, rp2['gamma2_db'], label=r"$|\Gamma_{RP2,2}|$", color=c_p2_re, lw=2.2)
        else:
            ax2_s.plot(freqs, rp2['gamma1_db'], label=r"$|\Gamma_{RP2,1}|$ (Port 1)", color=c_p1_re, lw=2.2)
            ax2_s.plot(freqs, rp2['gamma2_db'], label=r"$|\Gamma_{RP2,2}|$ (Port 2)", color=c_p2_re, lw=2.2, linestyle='--')
        ax2_s.axhline(-10.0, color=c_limit, linestyle='--', lw=1.5, label='-10 dB Criterion')
        ax2_s.set_title(rf"Local Reflection Coefficient $|\Gamma_{{RP2}}| ({z0_ref_rp2:.0f}\ \Omega)$", fontsize=11, fontweight='bold')
        ax2_s.set_xlabel("Frequency [GHz]", fontsize=10)
        ax2_s.set_ylabel(r"Magnitude [dB]", fontsize=10)
        ax2_s.grid(True, linestyle=':', alpha=0.6)
        ax2_s.legend(loc='best', fontsize=8)
        fig2.suptitle(f"Reference Plane RP2 (Transformer Terminal) — {m_info}", fontsize=12, fontweight='bold')
        fig2.tight_layout()
        plt.savefig(os.path.join(p_dir, "plot_impedance_rp2.png"), dpi=200)
        plt.close(fig2)

        # -------------------------------------------------------------
        # 3. Reference Plane RP3: Patch Input
        # -------------------------------------------------------------
        fig3, (ax3_z, ax3_s) = plt.subplots(1, 2, figsize=(13, 5))
        if driven_mode == "1":
            ax3_z.plot(freqs, rp3['z1'].real, label=r"$\mathrm{Re}\{Z_{patch1}\}$", color=c_p1_re, lw=2.2)
            ax3_z.plot(freqs, rp3['z1'].imag, label=r"$\mathrm{Im}\{Z_{patch1}\}$", color=c_p1_im, lw=1.8, linestyle='--')
            f0_1 = _detect_resonance(freqs, rp3['z1'].imag)
            if f0_1 is not None and (freqs[0] <= f0_1 <= freqs[-1]):
                r0 = float(np.interp(f0_1, freqs, rp3['z1'].real))
                ax3_z.plot(f0_1, 0.0, 'ro', markersize=7, label=rf"Resonance $f_0={f0_1:.3f}\ \mathrm{{GHz}}$ ($R={r0:.1f}\ \Omega$)")
        elif driven_mode == "2":
            ax3_z.plot(freqs, rp3['z2'].real, label=r"$\mathrm{Re}\{Z_{patch2}\}$", color=c_p2_re, lw=2.2)
            ax3_z.plot(freqs, rp3['z2'].imag, label=r"$\mathrm{Im}\{Z_{patch2}\}$", color=c_p2_im, lw=1.8, linestyle='--')
            f0_2 = _detect_resonance(freqs, rp3['z2'].imag)
            if f0_2 is not None and (freqs[0] <= f0_2 <= freqs[-1]):
                r0 = float(np.interp(f0_2, freqs, rp3['z2'].real))
                ax3_z.plot(f0_2, 0.0, 'ro', markersize=7, label=rf"Resonance $f_0={f0_2:.3f}\ \mathrm{{GHz}}$ ($R={r0:.1f}\ \Omega$)")
        else:
            ax3_z.plot(freqs, rp3['z1'].real, label=r"$\mathrm{Re}\{Z_{patch1}\}$ (P1)", color=c_p1_re, lw=2.2)
            ax3_z.plot(freqs, rp3['z1'].imag, label=r"$\mathrm{Im}\{Z_{patch1}\}$ (P1)", color=c_p1_im, lw=1.8, linestyle='--')
            ax3_z.plot(freqs, rp3['z2'].real, label=r"$\mathrm{Re}\{Z_{patch2}\}$ (P2)", color=c_p2_re, lw=2.2)
            ax3_z.plot(freqs, rp3['z2'].imag, label=r"$\mathrm{Im}\{Z_{patch2}\}$ (P2)", color=c_p2_im, lw=1.8, linestyle='--')
            f0_1 = _detect_resonance(freqs, rp3['z1'].imag)
            if f0_1 is not None and (freqs[0] <= f0_1 <= freqs[-1]):
                ax3_z.plot(f0_1, 0.0, 'bo', markersize=6, label=rf"$f_{{0,1}}={f0_1:.3f}\ \mathrm{{GHz}}$")
            f0_2 = _detect_resonance(freqs, rp3['z2'].imag)
            if f0_2 is not None and (freqs[0] <= f0_2 <= freqs[-1]):
                ax3_z.plot(f0_2, 0.0, 'ro', markersize=6, label=rf"$f_{{0,2}}={f0_2:.3f}\ \mathrm{{GHz}}$")
        ax3_z.axhline(z0_ref_rp3, color='mediumvioletred', linestyle='--', alpha=0.8, label=rf"Target $R_{{patch}} \approx {z0_ref_rp3:.1f}\ \Omega$")
        ax3_z.axhline(0.0, color='black', linestyle='-', alpha=0.5, label=r"$\mathrm{Im}\{Z\} = 0\ \Omega$")
        ax3_z.set_title(r"Patch Impedance $Z_{patch}$ at Reference Plane RP3", fontsize=11, fontweight='bold')
        ax3_z.set_xlabel("Frequency [GHz]", fontsize=10)
        ax3_z.set_ylabel(r"Impedance [$\Omega$]", fontsize=10)
        ax3_z.grid(True, linestyle=':', alpha=0.6)
        ax3_z.legend(loc='best', fontsize=8, ncol=2)

        if driven_mode == "1":
            ax3_s.plot(freqs, rp3['gamma1_db'], label=rf"Local $|\Gamma_{{patch1}}|$", color=c_p1_re, lw=2.2)
        elif driven_mode == "2":
            ax3_s.plot(freqs, rp3['gamma2_db'], label=rf"Local $|\Gamma_{{patch2}}|$", color=c_p2_re, lw=2.2)
        else:
            ax3_s.plot(freqs, rp3['gamma1_db'], label=r"$|\Gamma_{patch1}|$ (Port 1)", color=c_p1_re, lw=2.2)
            ax3_s.plot(freqs, rp3['gamma2_db'], label=r"$|\Gamma_{patch2}|$ (Port 2)", color=c_p2_re, lw=2.2, linestyle='--')
        ax3_s.axhline(-10.0, color=c_limit, linestyle='--', lw=1.5, label='-10 dB Criterion')
        ax3_s.set_title(rf"Local Reflection Coefficient $|\Gamma_{{patch}}| ({z0_ref_rp3:.0f}\ \Omega)$", fontsize=11, fontweight='bold')
        ax3_s.set_xlabel("Frequency [GHz]", fontsize=10)
        ax3_s.set_ylabel(r"Magnitude [dB]", fontsize=10)
        ax3_s.grid(True, linestyle=':', alpha=0.6)
        ax3_s.legend(loc='best', fontsize=8)
        fig3.suptitle(f"Reference Plane RP3 (Patch Input) — {m_info}", fontsize=12, fontweight='bold')
        fig3.tight_layout()
        plt.savefig(os.path.join(p_dir, "plot_impedance_rp3.png"), dpi=200)
        plt.close(fig3)


def _has_port_csv(directory):
    return any(
        os.path.exists(os.path.join(directory, fn)) and os.path.getsize(os.path.join(directory, fn)) > 0
        for fn in ("port-S.csv", "port-V.csv")
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Analytical de-embedding of patch antenna feed-network impedance discontinuities")
    parser.add_argument("export_dir", nargs="?", default=None,
                        help="Path to the export directory with simulation results (default: DATA_DIR/postpro or DATA_DIR from .env)")
    parser.add_argument("--output", "-o", default=None,
                        help="Path to output PNG plot (default: <export_dir>/plot_deembedding.png)")
    parser.add_argument("--layout", choices=["split", "compact"], default="split",
                        help="Layout for two-port excitation (split=3x4 port columns, compact=3x2)")
    args = parser.parse_args()

    target_dir = args.export_dir
    if target_dir is None:
        _, data_dir = load_env()
        postpro_dir = os.path.join(data_dir, "postpro")
        if _has_port_csv(postpro_dir):
            target_dir = postpro_dir
        elif _has_port_csv(data_dir):
            target_dir = data_dir
        else:
            print(f"[ERROR] Neither port-S.csv nor port-V.csv was found in {postpro_dir} or {data_dir}.")
            print("Provide the export directory path as an argument or run the simulation first.")
            parser.print_help()
            sys.exit(1)

    res = plot_impedance_deembedding(target_dir, output_png=args.output, layout=args.layout)
    if res is None:
        parser.print_help()
        sys.exit(1)
