import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np

def plot_geometry(params, filename="data/geometry_iso.png"):
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')
    
    L = params['patch_L']
    W = params['patch_W']
    h = params['sub_h']
    L_sub = params.get('sub_L', params.get('sub_l', 100.0))
    W_sub = params.get('sub_W', params.get('sub_w', 100.0))
    margin = params['air_margin']
    feed_W = params.get('feed_W', params.get('w1', 2.98))
    
    # Kreslení substrátu (poloprůhledná zelená)
    sub_x = [-W_sub/2, W_sub/2, W_sub/2, -W_sub/2]
    sub_y = [-L_sub/2, -L_sub/2, L_sub/2, L_sub/2]
    sub_z = [h, h, h, h]
    sub_z0 = [0, 0, 0, 0]
    
    # Horní a spodní plocha substrátu
    verts_sub = [
        list(zip(sub_x, sub_y, sub_z0)),
        list(zip(sub_x, sub_y, sub_z))
    ]
    ax.add_collection3d(Poly3DCollection(verts_sub, facecolors='green', alpha=0.2, edgecolors='g'))
    
    def add_rect(ax, x0, y0, w_rect, h_rect, z_val, color='orange', alpha=0.9, edgecolor='k'):
        rx = [x0, x0 + w_rect, x0 + w_rect, x0]
        ry = [y0, y0, y0 + h_rect, y0 + h_rect]
        rz = [z_val, z_val, z_val, z_val]
        ax.add_collection3d(Poly3DCollection([list(zip(rx, ry, rz))], facecolors=color, alpha=alpha, edgecolors=edgecolor))

    # Patch (měď - oranžová)
    add_rect(ax, -W/2, -L/2, W, L, h, color='orange', alpha=0.9)
    
    # Parametry napájení shodné s geometry.py
    from rf_calc import (
        calc_microstrip_eps_eff,
        calc_quarter_wave_length,
        synth_microstrip_w,
        DESIGN_FREQ_GHZ,
        PORT_Z0,
    )
    eps_r = params.get('eps_r', 4.3)
    f_design = params.get('design_freq_ghz', DESIGN_FREQ_GHZ)
    port_z0 = params.get('port_impedance', PORT_Z0)

    w1 = params.get('w1', params.get('feed_W', synth_microstrip_w(port_z0, h, eps_r)))
    w2 = params.get('w2', synth_microstrip_w(2.0 * port_z0, h, eps_r))
    w3 = params.get('w3', w2)

    eps_eff_w2 = calc_microstrip_eps_eff(w2, h, eps_r)
    lambda_g2_4 = calc_quarter_wave_length(f_design, eps_eff_w2)

    eps_eff_w3 = calc_microstrip_eps_eff(w3, h, eps_r)
    lambda_g3_4 = calc_quarter_wave_length(f_design, eps_eff_w3)

    # Získání délek vedení l1 až l8 (musí být definovány v params)
    l1 = float(params['l1'])
    l2 = float(params['l2'])
    l3 = float(params['l3'])
    l4 = float(params['l4'])
    l5 = float(params['l5'])
    l6 = float(params['l6'])
    l7 = float(params['l7'])
    l8 = float(params['l8'])

    inset = float(params.get('inset', params.get('feed_inset', 0.0)))
    x_T = float(params.get('feed_x_T', -(l2 + l3)))
    y_T = float(params.get('feed_y_T', -L/2 + inset - l4))

    # 1. Hlavní přívod (port k T-uzlu, šířka w1, 50 Ohm, délka l1)
    y_port = -L_sub / 2.0
    add_rect(ax, x_T - w1/2, y_port, w1, abs(y_T - y_port) + w2/2, h, color='darkorange', alpha=0.9)

    # 2. Spodní větev (referenční, fáze 0 deg)
    # Segment l2 (šířka w2, délka l2)
    add_rect(ax, x_T - w2/2, y_T - w2/2, l2 + w2/2, w2, h, color='gold', alpha=0.9)
    # Segment l3 (šířka w3, délka l3)
    add_rect(ax, x_T + l2, y_T - w3/2, l3 + w3/2, w3, h, color='orange', alpha=0.95)
    # Segment l4 (šířka w3, délka l4 k dolní hraně flíčku)
    add_rect(ax, -w3/2, y_T - w3/2, w3, l4 + w3/2 + 0.1, h, color='orange', alpha=0.95)

    # 3. Levá větev (zpožďovací, fáze -90 deg - LHCP zpoždění o lambda_g/4)
    # Segment l5 (šířka w2, délka l5 doleva)
    add_rect(ax, x_T - l5 - w2/2, y_T - w2/2, l5 + w2/2, w2, h, color='gold', alpha=0.9)
    # Segment l6 (šířka w2, délka l6 nahoru)
    add_rect(ax, x_T - l5 - w2/2, y_T - w2/2, w2, l6 + w2/2, h, color='gold', alpha=0.9)
    # Segment l7 (šířka w3, délka l7 nahoru k y=0)
    add_rect(ax, x_T - l5 - w3/2, y_T + l6, w3, l7 + w3/2, h, color='orange', alpha=0.95)
    # Segment l8 (šířka w3, délka l8 doprava k levé hraně flíčku)
    add_rect(ax, x_T - l5 - w3/2, -w3/2, l8 + w3/2 + 0.1, w3, h, color='orange', alpha=0.95)

    # Zvýraznění portu na hraně substrátu
    w_port_entry = w1
    port_verts = [[(x_T - w_port_entry/2, y_port, 0), (x_T + w_port_entry/2, y_port, 0),
                   (x_T + w_port_entry/2, y_port, h), (x_T - w_port_entry/2, y_port, h)]]
    ax.add_collection3d(Poly3DCollection(port_verts, facecolors='red', alpha=0.9, edgecolors='k'))
    
    # Vzduchový box (čáry, aby to nepřekáželo výhledu)
    ax.plot([-W_sub/2-margin, W_sub/2+margin, W_sub/2+margin, -W_sub/2-margin, -W_sub/2-margin],
            [-L_sub/2-margin, -L_sub/2-margin, L_sub/2+margin, L_sub/2+margin, -L_sub/2-margin],
            [-margin, -margin, -margin, -margin, -margin], color='blue', alpha=0.3, linestyle='--')
    ax.plot([-W_sub/2-margin, W_sub/2+margin, W_sub/2+margin, -W_sub/2-margin, -W_sub/2-margin],
            [-L_sub/2-margin, -L_sub/2-margin, L_sub/2+margin, L_sub/2+margin, -L_sub/2-margin],
            [h+margin, h+margin, h+margin, h+margin, h+margin], color='blue', alpha=0.3, linestyle='--')
    
    # Vertikální čáry boxu
    for x in [-W_sub/2-margin, W_sub/2+margin]:
        for y in [-L_sub/2-margin, L_sub/2+margin]:
            ax.plot([x, x], [y, y], [-margin, h+margin], color='blue', alpha=0.3, linestyle='--')
            
    # Nastavení os
    ax.set_xlim([-W_sub/2-margin, W_sub/2+margin])
    ax.set_ylim([-L_sub/2-margin, L_sub/2+margin])
    ax.set_zlim([-margin, h+margin])
    ax.set_xlabel('X [mm]')
    ax.set_ylabel('Y [mm]')
    ax.set_zlabel('Z [mm]')
    
    # Isometrický pohled
    ax.view_init(elev=30, azim=45)
    
    plt.title('Isometrický pohled na geometrii (Substrát, Patch, Airbox)')
    import os
    os.makedirs(os.path.dirname(os.path.abspath(filename)) or ".", exist_ok=True)
    try:
        plt.savefig(filename, dpi=150)
        print(f"Isometrický nákres byl uložen do {filename}")
    except Exception as e:
        print(f"Upozornění: Náhled geometrie se nepodařilo uložit do {filename}: {e}")
    finally:
        plt.close()
