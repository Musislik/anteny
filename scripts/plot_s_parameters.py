import os
import sys
import numpy as np
import matplotlib.pyplot as plt

def plot_s_parameters(export_dir, output_png=None):
    if output_png is None:
        output_png = os.path.join(export_dir, "graf_S_parametry.png")
    
    # Podpora pro vyhledání v export_dir i podsložce postpro
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
    
    # Check what data is available
    if s_path and os.path.exists(s_path) and os.path.getsize(s_path) > 0:
        # Standard Palace port-S output (1 port or full S matrix)
        data = np.loadtxt(s_path, delimiter=',', skiprows=1)
        freqs = data[:, 0]
        s11_db = data[:, 1]
        
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.plot(freqs, s11_db, label=r"$S_{11}$", color='navy', lw=2.2)
        ax.axhline(-10, color='crimson', linestyle='--', lw=1.5, label='Mez -10 dB')
        min_idx = np.argmin(s11_db)
        f0 = freqs[min_idx]
        s11_min = s11_db[min_idx]
        ax.plot(f0, s11_min, 'ro', label=f'Min: {s11_min:.2f} dB @ {f0:.3f} GHz')
        ax.set_title(r"Průběh činitele odrazu $S_{11}$", fontsize=14, fontweight='bold')
        ax.set_xlabel("Frekvence [GHz]", fontsize=12)
        ax.set_ylabel(r"$S_{11}$ [dB]", fontsize=12)
        ax.grid(True, linestyle=':', alpha=0.7)
        ax.legend(fontsize=11)
        plt.tight_layout()
        os.makedirs(os.path.dirname(os.path.abspath(output_png)) or ".", exist_ok=True)
        plt.savefig(output_png, dpi=200)
        plt.close()
        print(f"Uložen graf S-parametrů: {output_png}")
        return

    if v_path and os.path.exists(v_path) and os.path.getsize(v_path) > 0:
        v_data = np.loadtxt(v_path, delimiter=',', skiprows=1)
        freqs = v_data[:, 0]
        v_inc1 = v_data[:, 1]
        v_inc2 = v_data[:, 2]
        
        # Komplexní napětí
        v1 = v_data[:, 3] + 1j * v_data[:, 4]
        v2 = v_data[:, 5] + 1j * v_data[:, 6]
        
        # Činitele odrazu na 100 Ohm portech: Gamma = (V - V_inc) / V_inc
        gamma1 = (v1 - v_inc1) / v_inc1
        gamma2 = (v2 - v_inc2) / v_inc2
        
        s11_db = 20.0 * np.log10(np.clip(np.abs(gamma1), 1e-10, 10.0))
        s22_db = 20.0 * np.log10(np.clip(np.abs(gamma2), 1e-10, 10.0))
        
        # Impedance Zin = Z0 * (1 + Gamma) / (1 - Gamma)
        z0 = 100.0
        zin1 = z0 * (1.0 + gamma1) / (1.0 - gamma1 + 1e-12)
        zin2 = z0 * (1.0 + gamma2) / (1.0 - gamma2 + 1e-12)
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
        
        # 1. Panel: S11 a S22
        ax1.plot(freqs, s11_db, label=r"$S_{11}$ (Port 1 - spodní, $E_y$)", color='royalblue', lw=2.2)
        ax1.plot(freqs, s22_db, label=r"$S_{22}$ (Port 2 - levý, $E_x$)", color='darkorange', lw=2.2, linestyle='--')
        ax1.axhline(-10, color='red', linestyle=':', lw=1.5, label='Mez -10 dB')
        
        min1_idx = np.argmin(s11_db)
        min2_idx = np.argmin(s22_db)
        ax1.plot(freqs[min1_idx], s11_db[min1_idx], 'bo', label=f'Min $S_{{11}}$: {s11_db[min1_idx]:.2f} dB @ {freqs[min1_idx]:.3f} GHz')
        ax1.plot(freqs[min2_idx], s22_db[min2_idx], 'ro', label=f'Min $S_{{22}}$: {s22_db[min2_idx]:.2f} dB @ {freqs[min2_idx]:.3f} GHz')
        
        ax1.set_title(r"S-parametry ($S_{11}$, $S_{22}$) — Dvouportové buzení 100 $\Omega$", fontsize=13, fontweight='bold')
        ax1.set_ylabel("Magnituda [dB]", fontsize=11)
        ax1.grid(True, linestyle=':', alpha=0.7)
        ax1.legend(loc='lower left', fontsize=10)
        
        # 2. Panel: Vstupní impedance Zin
        ax2.plot(freqs, zin1.real, label=r"Re{$Z_{in1}$} (Port 1)", color='royalblue', lw=1.8)
        ax2.plot(freqs, zin1.imag, label=r"Im{$Z_{in1}$} (Port 1)", color='royalblue', lw=1.5, linestyle=':')
        ax2.plot(freqs, zin2.real, label=r"Re{$Z_{in2}$} (Port 2)", color='darkorange', lw=1.8)
        ax2.plot(freqs, zin2.imag, label=r"Im{$Z_{in2}$} (Port 2)", color='darkorange', lw=1.5, linestyle=':')
        ax2.axhline(100.0, color='gray', linestyle='--', alpha=0.7, label=r'Cíl $Z_0 = 100\ \Omega$')
        ax2.axhline(0.0, color='gray', linestyle='-', alpha=0.4)
        
        ax2.set_title(r"Vstupní impedance portů $Z_{in}$ [$\Omega$]", fontsize=13, fontweight='bold')
        ax2.set_xlabel("Frekvence [GHz]", fontsize=11)
        ax2.set_ylabel(r"Impedance [$\Omega$]", fontsize=11)
        ax2.grid(True, linestyle=':', alpha=0.7)
        ax2.legend(loc='upper right', fontsize=9, ncol=2)
        
        plt.tight_layout()
        os.makedirs(os.path.dirname(os.path.abspath(output_png)) or ".", exist_ok=True)
        plt.savefig(output_png, dpi=200)
        plt.close()
        print(f"Uložen graf S-parametrů a impedance: {output_png}")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else r"D:\code\anteny\export\antena3_1_1"
    plot_s_parameters(target)
