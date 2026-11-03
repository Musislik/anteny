"""
plot_radiation_pattern.py - Vykreslení 2D polárních řezů a 3D vyzařovacího diagramu
z datového souboru farfield-rE.csv (Palace FEM řešič).
"""

import os
import sys
import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree

def compute_farfield_metrics(sub_df):
    """
    Vypočte sférické složky E-pole, LHCP/RHCP polarizaci, směrovost v dBi a osový poměr (AR).
    """
    th_deg = sub_df.iloc[:, 2].values
    ph_deg = sub_df.iloc[:, 3].values
    
    th = np.deg2rad(th_deg)
    ph = np.deg2rad(ph_deg)
    
    ex = sub_df.iloc[:, 4].values + 1j * sub_df.iloc[:, 5].values
    ey = sub_df.iloc[:, 6].values + 1j * sub_df.iloc[:, 7].values
    ez = sub_df.iloc[:, 8].values + 1j * sub_df.iloc[:, 9].values
    
    # Sférické složky vektoru E
    e_th = (ex * np.cos(ph) + ey * np.sin(ph)) * np.cos(th) - ez * np.sin(th)
    e_ph = -ex * np.sin(ph) + ey * np.cos(ph)
    
    # Kruhová polarizace dle IEEE standardu (+r šíření):
    # LHCP = (E_theta + j * E_phi) / sqrt(2)
    # RHCP = (E_theta - j * E_phi) / sqrt(2)
    e_lhcp = (e_th + 1j * e_ph) / np.sqrt(2.0)
    e_rhcp = (e_th - 1j * e_ph) / np.sqrt(2.0)
    
    u_tot = np.abs(e_th)**2 + np.abs(e_ph)**2
    u_lhcp = np.abs(e_lhcp)**2
    u_rhcp = np.abs(e_rhcp)**2
    
    # Průměrná vyzařovací intenzita (vzorky jsou rovnoměrně rozprostřeny po kouli)
    u_avg = np.mean(u_tot)
    
    d_tot_dbi = 10.0 * np.log10(np.maximum(u_tot / u_avg, 1e-4))
    d_lhcp_dbi = 10.0 * np.log10(np.maximum(u_lhcp / u_avg, 1e-4))
    d_rhcp_dbi = 10.0 * np.log10(np.maximum(u_rhcp / u_avg, 1e-4))
    
    # Osový poměr (Axial Ratio v dB)
    mag_l = np.abs(e_lhcp)
    mag_r = np.abs(e_rhcp)
    major = mag_l + mag_r
    minor = np.maximum(np.abs(mag_l - mag_r), 1e-6)
    ar_db = 20.0 * np.log10(major / minor)
    
    # Kartézské souřadnice bodů na jednotkové kouli pro rychlé prostorové dotazování
    xs = np.sin(th) * np.cos(ph)
    ys = np.sin(th) * np.sin(ph)
    zs = np.cos(th)
    
    return {
        'th_deg': th_deg, 'ph_deg': ph_deg,
        'xs': xs, 'ys': ys, 'zs': zs,
        'd_tot': d_tot_dbi, 'd_lhcp': d_lhcp_dbi, 'd_rhcp': d_rhcp_dbi,
        'ar_db': ar_db, 'u_avg': u_avg
    }

def interpolate_cut(tree, metric_vals, target_points):
    """Interpoluje hodnoty podél řezu pomocí váženého k-NN z cKDTree."""
    dists, idxs = tree.query(target_points, k=4)
    # Vážený průměr podle převrácené vzdálenosti (IDW)
    weights = 1.0 / np.maximum(dists, 1e-6)
    weights /= np.sum(weights, axis=1, keepdims=True)
    return np.sum(metric_vals[idxs] * weights, axis=1)

def plot_radiation_pattern_2d(export_dir, freq_target=None, output_png=None):
    csv_path = os.path.join(export_dir, "farfield-rE.csv")
    if not os.path.exists(csv_path):
        print(f"Soubor {csv_path} neexistuje.")
        return
        
    print(f"Načítám dálkové pole z {csv_path}...")
    df = pd.read_csv(csv_path)
    
    freq_col = df.columns[0]
    freqs = np.unique(df[freq_col].values)
    
    if freq_target is None:
        # Výchozí: 2.333 GHz nebo střed pásma
        eval_f = 2.333 if any(np.isclose(freqs, 2.333, atol=1e-4)) else freqs[len(freqs)//2]
    else:
        eval_f = freqs[np.argmin(np.abs(freqs - float(freq_target)))]
        
    print(f"Vykresluji diagram pro frekvenci: {eval_f:.3f} GHz (z dostupných {freqs.min():.3f} - {freqs.max():.3f} GHz)")
    sub = df[np.isclose(df[freq_col], eval_f, atol=1e-5)]
    
    m = compute_farfield_metrics(sub)
    tree = cKDTree(np.column_stack([m['xs'], m['ys'], m['zs']]))
    
    # Generování úhlů pro řezy: theta od -180° do +180°
    # V polárním diagramu: 0° je osa +Z (Zenith / Boresight), +/-90° je horizont, 180° je nadir (-Z)
    angles_deg = np.linspace(-180, 180, 361)
    angles_rad = np.deg2rad(angles_deg)
    
    # 1. Řez X-Z (Phi = 0° pro kladné úhly, Phi = 180° pro záporné úhly)
    xz_pts = np.column_stack([
        np.sin(angles_rad),               # X
        np.zeros_like(angles_rad),         # Y
        np.cos(angles_rad)                # Z
    ])
    d_lhcp_xz = interpolate_cut(tree, m['d_lhcp'], xz_pts)
    d_rhcp_xz = interpolate_cut(tree, m['d_rhcp'], xz_pts)
    d_tot_xz  = interpolate_cut(tree, m['d_tot'],  xz_pts)
    ar_xz     = interpolate_cut(tree, m['ar_db'],   xz_pts)
    
    # 2. Řez Y-Z (Phi = 90° pro kladné úhly, Phi = 270° pro záporné úhly)
    yz_pts = np.column_stack([
        np.zeros_like(angles_rad),         # X
        np.sin(angles_rad),               # Y
        np.cos(angles_rad)                # Z
    ])
    d_lhcp_yz = interpolate_cut(tree, m['d_lhcp'], yz_pts)
    d_rhcp_yz = interpolate_cut(tree, m['d_rhcp'], yz_pts)
    d_tot_yz  = interpolate_cut(tree, m['d_tot'],  yz_pts)
    ar_yz     = interpolate_cut(tree, m['ar_db'],   yz_pts)
    
    # Vykreslení grafu: 2 polární diagramy + 1 kartézský pro Axial Ratio
    fig = plt.figure(figsize=(15, 6))
    
    # Polární plot X-Z
    ax1 = fig.add_subplot(131, projection='polar')
    ax1.set_theta_zero_location('N')       # 0° (Zenith / +Z) nahoře
    ax1.set_theta_direction(-1)            # Po směru hodinových ručiček
    
    r_min = -25
    r_max = np.ceil(np.max(d_tot_xz) + 1)
    
    ax1.plot(angles_rad, np.clip(d_lhcp_xz, r_min, r_max), 'b-', lw=2.2, label='LHCP (hlavní)')
    ax1.plot(angles_rad, np.clip(d_rhcp_xz, r_min, r_max), 'r--', lw=1.8, label='RHCP (křížová)')
    ax1.plot(angles_rad, np.clip(d_tot_xz,  r_min, r_max), 'k:',  lw=1.2, label='Celková směrovost')
    ax1.set_ylim([r_min, r_max])
    ax1.set_title(rf"Řez rovinou X-Z ($\phi = 0^\circ$)" + f"\nf = {eval_f:.3f} GHz", fontsize=12, fontweight='bold', pad=15)
    ax1.legend(loc='lower left', bbox_to_anchor=(-0.1, -0.2), fontsize=9)
    ax1.grid(True, linestyle=':', alpha=0.7)
    
    # Polární plot Y-Z
    ax2 = fig.add_subplot(132, projection='polar')
    ax2.set_theta_zero_location('N')
    ax2.set_theta_direction(-1)
    ax2.plot(angles_rad, np.clip(d_lhcp_yz, r_min, r_max), 'b-', lw=2.2, label='LHCP (hlavní)')
    ax2.plot(angles_rad, np.clip(d_rhcp_yz, r_min, r_max), 'r--', lw=1.8, label='RHCP (křížová)')
    ax2.plot(angles_rad, np.clip(d_tot_yz,  r_min, r_max), 'k:',  lw=1.2, label='Celková směrovost')
    ax2.set_ylim([r_min, r_max])
    ax2.set_title(rf"Řez rovinou Y-Z ($\phi = 90^\circ$)" + f"\nf = {eval_f:.3f} GHz", fontsize=12, fontweight='bold', pad=15)
    ax2.legend(loc='lower left', bbox_to_anchor=(-0.1, -0.2), fontsize=9)
    ax2.grid(True, linestyle=':', alpha=0.7)
    
    # Kartézský plot Axial Ratio pro horní poloprostor (-90° až +90°)
    ax3 = fig.add_subplot(133)
    mask_hemi = (angles_deg >= -90) & (angles_deg <= 90)
    theta_hemi = angles_deg[mask_hemi]
    ax3.plot(theta_hemi, ar_xz[mask_hemi], 'b-', lw=2.0, label='AR (řez X-Z)')
    ax3.plot(theta_hemi, ar_yz[mask_hemi], 'm--', lw=2.0, label='AR (řez Y-Z)')
    ax3.axhline(3.0, color='red', linestyle=':', lw=1.5, label='Mez 3 dB (čistá kruhová)')
    ax3.set_ylim([0, 15])
    ax3.set_xlim([-90, 90])
    ax3.set_xlabel(r"Úhel od kolmice $\theta$ [$^\circ$]", fontsize=11)
    ax3.set_ylabel("Osový poměr AR [dB]", fontsize=11)
    ax3.set_title(f"Osový poměr AR (Axial Ratio)\nf = {eval_f:.3f} GHz", fontsize=12, fontweight='bold')
    ax3.grid(True, linestyle=':', alpha=0.7)
    ax3.legend(loc='upper right', fontsize=9)
    
    # Vypíšeme hodnoty v zenitu (theta = 0)
    zenith_idx = np.argmin(np.abs(angles_deg))
    ax3.annotate(f"Zenith AR: {ar_xz[zenith_idx]:.2f} dB\nMax LHCP: {np.max(d_lhcp_xz):.2f} dBi",
                 xy=(0, ar_xz[zenith_idx]), xytext=(10, ar_xz[zenith_idx] + 2),
                 arrowprops=dict(arrowstyle="->", color="black"),
                 fontsize=10, bbox=dict(boxstyle="round,pad=0.3", fc="yellow", alpha=0.4))
    
    plt.tight_layout()
    if output_png is None:
        output_png = os.path.join(export_dir, "vyzarovaci_diagram_2d.png")
    plt.savefig(output_png, dpi=200)
    plt.close()
    print(f"Uložen 2D vyzařovací diagram: {output_png}")

def plot_radiation_pattern_3d(export_dir, freq_target=None, output_png=None):
    csv_path = os.path.join(export_dir, "farfield-rE.csv")
    if not os.path.exists(csv_path):
        return
        
    df = pd.read_csv(csv_path)
    freq_col = df.columns[0]
    freqs = np.unique(df[freq_col].values)
    
    eval_f = 2.333 if any(np.isclose(freqs, 2.333, atol=1e-4)) else freqs[len(freqs)//2]
    if freq_target is not None:
        eval_f = freqs[np.argmin(np.abs(freqs - float(freq_target)))]
        
    sub = df[np.isclose(df[freq_col], eval_f, atol=1e-5)]
    m = compute_farfield_metrics(sub)
    tree = cKDTree(np.column_stack([m['xs'], m['ys'], m['zs']]))
    
    # Sférická mřížka pro 3D povrch
    u = np.linspace(0, np.pi, 60)      # theta
    v = np.linspace(0, 2 * np.pi, 120)  # phi
    u_grid, v_grid = np.meshgrid(u, v)
    
    pts_x = np.sin(u_grid) * np.cos(v_grid)
    pts_y = np.sin(u_grid) * np.sin(v_grid)
    pts_z = np.cos(u_grid)
    
    query_pts = np.column_stack([pts_x.ravel(), pts_y.ravel(), pts_z.ravel()])
    d_lhcp_flat = interpolate_cut(tree, m['d_lhcp'], query_pts)
    d_lhcp_surf = d_lhcp_flat.reshape(u_grid.shape)
    
    # Poloměr pro 3D graf: lineární škálování od r_min
    r_floor = -15.0
    r_vals = np.maximum(d_lhcp_surf - r_floor, 0.0)
    
    surf_x = r_vals * pts_x
    surf_y = r_vals * pts_y
    surf_z = r_vals * pts_z
    
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')
    
    norm = plt.Normalize(vmin=r_floor, vmax=np.max(d_lhcp_surf))
    colors = plt.cm.jet(norm(d_lhcp_surf))
    
    surf = ax.plot_surface(surf_x, surf_y, surf_z, facecolors=colors,
                           rstride=1, cstride=1, antialiased=True, alpha=0.9)
                           
    mappable = plt.cm.ScalarMappable(cmap=plt.cm.jet, norm=norm)
    mappable.set_array(d_lhcp_surf)
    cbar = plt.colorbar(mappable, ax=ax, shrink=0.6, pad=0.1)
    cbar.set_label('LHCP Směrovost [dBi]', fontsize=11)
    
    ax.set_title(f"3D Vyzařovací diagram (LHCP)\nf = {eval_f:.3f} GHz | Max: {np.max(d_lhcp_surf):.2f} dBi",
                 fontsize=13, fontweight='bold')
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_zlabel('Z (+Zenith)')
    
    # Nastavení pohledu
    ax.view_init(elev=25, azim=45)
    
    plt.tight_layout()
    if output_png is None:
        output_png = os.path.join(export_dir, "vyzarovaci_diagram_3d.png")
    plt.savefig(output_png, dpi=200)
    plt.close()
    print(f"Uložen 3D vyzařovací diagram: {output_png}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vykreslení vyzařovacích diagramů antény z farfield-rE.csv")
    parser.add_argument("export_dir", nargs="?", default=r"D:\code\anteny\export\antena3_1_1", help="Cesta k exportní složce")
    parser.add_argument("--freq", type=float, default=2.333, help="Frekvence pro vyhodnocení v GHz")
    args = parser.parse_args()
    
    plot_radiation_pattern_2d(args.export_dir, freq_target=args.freq)
    plot_radiation_pattern_3d(args.export_dir, freq_target=args.freq)
