import os
import sys
import json
import argparse
import numpy as np
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

from postpro_utils import load_env, load_port_v_voltages

def plot_s_parameters(export_dir, output_png=None, params=None):
    """
    Vykreslí finální diagnostický graf S-parametrů a vstupní impedance 'graf_S_parametry.png'.
    
    Pravidlo 2: Pokud je buzen pouze jeden port (DRIVEN_PORT=1 nebo 2):
      - Kreslí se VÝHRADNĚ aktivní cesta (S11 nebo S22, Zin1 nebo Zin2).
      - Pasivní port se nezobrazuje, zobrazí se pouze křivka izolace/přeslechu S21 v dB.
    Pravidlo 3: V případě buzení oběma porty (DRIVEN_PORT=all):
      - Vykreslí se S11, S22 a S21 v dB a vstupní impedance obou portů.
    """
    if output_png is None:
        output_png = os.path.join(export_dir, "graf_S_parametry.png")
    output_png = os.path.abspath(os.path.normpath(output_png))
    
    # 1. Zjištění parametrů (params.json nebo předaný slovník)
    res_params = {}
    if params:
        res_params.update(params)
    
    params_candidates = [
        os.path.join(export_dir, "params.json"),
        os.path.join(export_dir, "..", "params.json")
    ]
    for pp in params_candidates:
        if os.path.exists(pp) and os.path.getsize(pp) > 0:
            try:
                with open(pp, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    for k, v in loaded.items():
                        if k not in res_params or res_params[k] is None:
                            res_params[k] = v
                break
            except Exception:
                pass

    model = int(res_params.get("antenna_model", 3))
    default_z0 = 100.0 if model in (2, 3) else 50.0
    z0 = float(res_params.get("port_impedance", default_z0))
    dp_hint = res_params.get("driven_port") or os.getenv("DRIVEN_PORT")
    if dp_hint is not None:
        dp_hint = str(dp_hint).lower().strip()

    # 2. Hledání simulačních souborů
    search_dirs = [export_dir, os.path.join(export_dir, "postpro")]
    v_path = None
    s_path = None
    for d in search_dirs:
        sp = os.path.join(d, "port-S.csv")
        if os.path.exists(sp) and os.path.getsize(sp) > 0 and s_path is None:
            s_path = sp
        vp = os.path.join(d, "port-V.csv")
        if os.path.exists(vp) and os.path.getsize(vp) > 0 and v_path is None:
            v_path = vp

    freqs = None
    s11_db = None
    s22_db = None
    s21_db = None
    s12_db = None
    zin1 = None
    zin2 = None

    # Načtení z port-S.csv
    if s_path and os.path.exists(s_path) and os.path.getsize(s_path) > 0:
        try:
            with open(s_path, 'r', encoding='utf-8') as f:
                s_header = [h.strip().lower() for h in f.readline().split(',')]
            data = np.loadtxt(s_path, delimiter=',', skiprows=1)
            if data.ndim == 1:
                data = data.reshape(1, -1)
            freqs = data[:, 0]

            def get_col_idx(patterns):
                for idx, col in enumerate(s_header):
                    for pat in patterns:
                        if pat in col:
                            return idx
                return None

            s11_idx = get_col_idx(["|s[1][1]|", "s[1][1]", "s[1,1]", "|s11|"])
            s11_deg_idx = get_col_idx(["arg(s[1][1])", "arg(s[1,1])", "phase(s[1][1])", "arg(s11)"])
            s22_idx = get_col_idx(["|s[2][2]|", "s[2][2]", "s[2,2]", "|s22|"])
            s22_deg_idx = get_col_idx(["arg(s[2][2])", "arg(s[2,2])", "phase(s[2][2])", "arg(s22)"])
            s21_idx = get_col_idx(["|s[2][1]|", "s[2][1]", "s[2,1]", "|s21|"])
            s12_idx = get_col_idx(["|s[1][2]|", "s[1][2]", "s[1,2]", "|s12|"])

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
                gamma1 = (10.0 ** (s11_db / 20.0)) * np.exp(1j * np.deg2rad(deg1))
                zin1 = z0 * (1.0 + gamma1) / (1.0 - gamma1 + 1e-12)

            if s22_idx is not None and s22_idx < data.shape[1]:
                s22_db = data[:, s22_idx]
                deg2 = data[:, s22_deg_idx] if s22_deg_idx is not None and s22_deg_idx < data.shape[1] else np.zeros_like(s22_db)
                gamma2 = (10.0 ** (s22_db / 20.0)) * np.exp(1j * np.deg2rad(deg2))
                zin2 = z0 * (1.0 + gamma2) / (1.0 - gamma2 + 1e-12)

            if s21_idx is not None and s21_idx < data.shape[1]:
                s21_db = data[:, s21_idx]
            if s12_idx is not None and s12_idx < data.shape[1]:
                s12_db = data[:, s12_idx]
        except Exception as e:
            print(f"Upozornění při načítání {s_path}: {e}")

    # Fallback na port-V.csv
    if (s11_db is None and s22_db is None) and v_path and os.path.exists(v_path) and os.path.getsize(v_path) > 0:
        try:
            v_freqs, s11_c, s22_c, s21_c, s12_c = load_port_v_voltages(v_path)
            if v_freqs is not None:
                freqs = v_freqs
                if s11_c is not None:
                    s11_db = 20.0 * np.log10(np.clip(np.abs(s11_c), 1e-10, 10.0))
                    zin1 = z0 * (1.0 + s11_c) / (1.0 - s11_c + 1e-12)
                if s22_c is not None:
                    s22_db = 20.0 * np.log10(np.clip(np.abs(s22_c), 1e-10, 10.0))
                    zin2 = z0 * (1.0 + s22_c) / (1.0 - s22_c + 1e-12)
                if s21_c is not None:
                    s21_db = 20.0 * np.log10(np.clip(np.abs(s21_c), 1e-10, 10.0))
                if s12_c is not None:
                    s12_db = 20.0 * np.log10(np.clip(np.abs(s12_c), 1e-10, 10.0))
        except Exception as e:
            print(f"Upozornění při načítání {v_path}: {e}")

    if freqs is None or (s11_db is None and s22_db is None):
        print(f"[Plot S-Params] Žádná data pro vykreslení v {export_dir}")
        return None

    # Izolace/přeslech
    iso_db = s21_db if s21_db is not None else s12_db

    # Auto-detekce buzení
    if s11_db is not None and s22_db is not None:
        driven_mode = "all"
    elif s22_db is not None:
        driven_mode = "2"
    else:
        driven_mode = "1"

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    # 1. Panel: S-parametry
    if s11_db is not None:
        min1_idx = np.argmin(s11_db)
        ax1.plot(freqs, s11_db, label=r"$S_{11}$ (Port 1 - spodní, $E_y$)", color='royalblue', lw=2.2)
        ax1.plot(freqs[min1_idx], s11_db[min1_idx], 'bo', label=f'Min $S_{{11}}$: {s11_db[min1_idx]:.2f} dB @ {freqs[min1_idx]:.3f} GHz')

    if s22_db is not None:
        min2_idx = np.argmin(s22_db)
        ax1.plot(freqs, s22_db, label=r"$S_{22}$ (Port 2 - levý, $E_x$)", color='crimson', lw=2.2, linestyle='--')
        ax1.plot(freqs[min2_idx], s22_db[min2_idx], 'ro', label=f'Min $S_{{22}}$: {s22_db[min2_idx]:.2f} dB @ {freqs[min2_idx]:.3f} GHz')

    if iso_db is not None:
        iso_name = "S_{21}" if (s11_db is not None or s12_db is None) else "S_{12}"
        ax1.plot(freqs, iso_db, label=rf"Izolace / přeslech ${iso_name}$", color='purple', lw=1.8, linestyle=':')

    ax1.axhline(-10.0, color='red', linestyle='--', lw=1.5, label='Kritérium -10 dB')
    
    if s11_db is not None and s22_db is not None:
        title_s = rf"S-parametry ($S_{{11}}$, $S_{{22}}$) — $Z_0 = {z0:.0f}\ \Omega$"
    elif driven_mode == "1":
        title_s = r"S-parametry — Buzení Portu 1 ($E_y$, spodní rameno)"
    else:
        title_s = r"S-parametry — Buzení Portu 2 ($E_x$, levé rameno)"

    ax1.set_title(title_s, fontsize=12, fontweight='bold')
    ax1.set_ylabel("Magnituda [dB]", fontsize=11)
    ax1.grid(True, linestyle=':', alpha=0.7)
    ax1.legend(loc='best', fontsize=9)

    # 2. Panel: Vstupní impedance Zin
    if zin1 is not None:
        ax2.plot(freqs, zin1.real, label=r"$\mathrm{Re}\{Z_{in1}\}$ (Port 1)", color='royalblue', lw=2.0)
        ax2.plot(freqs, zin1.imag, label=r"$\mathrm{Im}\{Z_{in1}\}$ (Port 1)", color='deepskyblue', lw=1.6, linestyle='--')

    if zin2 is not None:
        ax2.plot(freqs, zin2.real, label=r"$\mathrm{Re}\{Z_{in2}\}$ (Port 2)", color='crimson', lw=2.0)
        ax2.plot(freqs, zin2.imag, label=r"$\mathrm{Im}\{Z_{in2}\}$ (Port 2)", color='coral', lw=1.6, linestyle='--')

    ax2.axhline(z0, color='gray', linestyle='--', alpha=0.7, label=rf"Cíl $Z_0 = {z0:.0f}\ \Omega$")
    ax2.axhline(0.0, color='black', linestyle='-', alpha=0.4, label=r"$\mathrm{Im}\{Z\} = 0\ \Omega$")

    ax2.set_title(rf"Vstupní impedance portů $Z_{{in}}$ [$\Omega$] (Reference $Z_0 = {z0:.0f}\ \Omega$)", fontsize=12, fontweight='bold')
    ax2.set_xlabel("Frekvence [GHz]", fontsize=11)
    ax2.set_ylabel(r"Impedance [$\Omega$]", fontsize=11)
    ax2.grid(True, linestyle=':', alpha=0.7)
    ax2.legend(loc='best', fontsize=9, ncol=2)

    plt.tight_layout()
    os.makedirs(os.path.dirname(output_png) or ".", exist_ok=True)
    plt.savefig(output_png, dpi=200)
    plt.close()
    print(f"[Plot S-Params] Uložen graf S-parametrů a impedance: {output_png}")

    # Uložení samostatných dílčích grafů do podsložky grafy/
    grafy_dirs = [os.path.join(export_dir, "grafy")]
    out_dir = os.path.dirname(output_png)
    if os.path.abspath(out_dir) != os.path.abspath(export_dir):
        grafy_dirs.append(os.path.join(out_dir, "grafy"))

    for g_dir in grafy_dirs:
        os.makedirs(g_dir, exist_ok=True)

        # 1. Samostatný graf S11 a S22
        fig_s, ax_s = plt.subplots(figsize=(8.5, 5))
        if s11_db is not None:
            min1_idx = np.argmin(s11_db)
            ax_s.plot(freqs, s11_db, label=r"$S_{11}$ (Port 1 - spodní, $E_y$)", color='royalblue', lw=2.2)
            ax_s.plot(freqs[min1_idx], s11_db[min1_idx], 'bo', label=f'Min $S_{{11}}$: {s11_db[min1_idx]:.2f} dB @ {freqs[min1_idx]:.3f} GHz')
        if s22_db is not None:
            min2_idx = np.argmin(s22_db)
            ax_s.plot(freqs, s22_db, label=r"$S_{22}$ (Port 2 - levý, $E_x$)", color='crimson', lw=2.2, linestyle='--')
            ax_s.plot(freqs[min2_idx], s22_db[min2_idx], 'ro', label=f'Min $S_{{22}}$: {s22_db[min2_idx]:.2f} dB @ {freqs[min2_idx]:.3f} GHz')

        ax_s.axhline(-10.0, color='red', linestyle='--', lw=1.5, label='Kritérium -10 dB')
        ax_s.set_title(rf"Činitel odrazu ($S_{{11}}$, $S_{{22}}$) — $Z_0 = {z0:.0f}\ \Omega$", fontsize=12, fontweight='bold')
        ax_s.set_xlabel("Frekvence [GHz]", fontsize=11)
        ax_s.set_ylabel("Magnituda [dB]", fontsize=11)
        ax_s.grid(True, linestyle=':', alpha=0.7)
        ax_s.legend(loc='best', fontsize=9)
        plt.tight_layout()
        p_s11_s22 = os.path.join(g_dir, "graf_S11_S22.png")
        plt.savefig(p_s11_s22, dpi=200)
        plt.close(fig_s)

        # 2. Samostatný graf izolace S21
        if iso_db is not None:
            fig_iso, ax_iso = plt.subplots(figsize=(8.5, 5))
            iso_name = "S_{21}" if (s11_db is not None or s12_db is None) else "S_{12}"
            ax_iso.plot(freqs, iso_db, label=rf"Izolace / přeslech ${iso_name}$", color='purple', lw=2.0)
            ax_iso.set_title(rf"Izolace mezi porty (${iso_name}$)", fontsize=12, fontweight='bold')
            ax_iso.set_xlabel("Frekvence [GHz]", fontsize=11)
            ax_iso.set_ylabel("Magnituda [dB]", fontsize=11)
            ax_iso.grid(True, linestyle=':', alpha=0.7)
            ax_iso.legend(loc='best', fontsize=9)
            plt.tight_layout()
            p_iso = os.path.join(g_dir, "graf_S21_izolace.png")
            plt.savefig(p_iso, dpi=200)
            plt.close(fig_iso)
    return output_png

def _has_port_csv(directory):
    return any(
        os.path.exists(os.path.join(directory, fn)) and os.path.getsize(os.path.join(directory, fn)) > 0
        for fn in ("port-S.csv", "port-V.csv")
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Vykreslení diagnostických grafů S-parametrů a vstupní impedance z port-S.csv nebo port-V.csv"
    )
    parser.add_argument(
        "export_dir",
        nargs="?",
        default=None,
        help="Cesta k exportní složce s výsledky simulace (výchozí: DATA_DIR/postpro nebo DATA_DIR z .env)",
    )
    args = parser.parse_args()

    target = args.export_dir
    if target is None:
        _, data_dir = load_env()
        postpro_dir = os.path.join(data_dir, "postpro")
        if _has_port_csv(postpro_dir):
            target = postpro_dir
        elif _has_port_csv(data_dir):
            target = data_dir
        else:
            print(f"[CHYBA] Soubory port-S.csv ani port-V.csv nebyly nalezeny v {postpro_dir} ani v {data_dir}.")
            print("Zadejte cestu k exportní složce jako argument nebo nejprve spusťte simulaci.")
            parser.print_help()
            sys.exit(1)

    res = plot_s_parameters(target)
    if res is None:
        parser.print_help()
        sys.exit(1)
