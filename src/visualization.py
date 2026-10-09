import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np

def plot_geometry(params, filename="geometry_iso.png"):
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')
    
    L = params['patch_L']
    W = params['patch_W']
    h = params['sub_h']
    L_sub = params['sub_L']
    W_sub = params['sub_W']
    margin = params['air_margin']
    feed_W = params['feed_W']
    
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
        calc_quarter_wave_transformer_z,
        synth_microstrip_w,
        calc_patch_edge_impedance,
        DESIGN_FREQ_GHZ,
        PORT_Z0,
    )
    eps_r = params.get('eps_r', 4.3)
    f_design = params.get('design_freq_ghz', DESIGN_FREQ_GHZ)
    port_z0 = params.get('port_impedance', PORT_Z0)
    eps_eff_feed = calc_microstrip_eps_eff(feed_W, h, eps_r)
    lambda_g_4 = calc_quarter_wave_length(f_design, eps_eff_feed)

    z_t_node = port_z0 / 2.0
    z_t_trans = calc_quarter_wave_transformer_z(port_z0, z_t_node)
    w_t_trans = synth_microstrip_w(z_t_trans, h, eps_r)
    eps_eff_t_trans = calc_microstrip_eps_eff(w_t_trans, h, eps_r)
    lambda_t_trans_4 = calc_quarter_wave_length(f_design, eps_eff_t_trans)

    r_edge = calc_patch_edge_impedance(W, L, h, eps_r)
    z_p_trans = calc_quarter_wave_transformer_z(port_z0, r_edge)
    w_p_trans = synth_microstrip_w(z_p_trans, h, eps_r)
    eps_eff_p_trans = calc_microstrip_eps_eff(w_p_trans, h, eps_r)
    lambda_p_trans_4 = calc_quarter_wave_length(f_design, eps_eff_p_trans)

    default_feed_offset = float(np.round(lambda_p_trans_4 + 6.0, 1))
    feed_offset_x = params.get('feed_offset_x', default_feed_offset)
    feed_offset_y = params.get('feed_offset_y', default_feed_offset)
    x_T = params.get('feed_x_T', -W/2 - feed_offset_x)
    y_T = params.get('feed_y_T', -L/2 - feed_offset_y)
    delay_offset = lambda_g_4 / 2.0
    y_delay = y_T - delay_offset

    # Hlavní přívod (port k T-uzlu)
    y_trans_start = y_T - lambda_t_trans_4
    if y_trans_start > -L_sub/2:
        add_rect(ax, x_T - feed_W/2, -L_sub/2, feed_W, y_trans_start - (-L_sub/2) + feed_W/2, h)
        add_rect(ax, x_T - w_t_trans/2, y_trans_start, w_t_trans, lambda_t_trans_4 + feed_W/2, h, color='darkorange')
    else:
        add_rect(ax, x_T - w_t_trans/2, -L_sub/2, w_t_trans, L_sub/2 + y_T + feed_W/2, h, color='darkorange')

    # Levá větev (fáze 0 deg)
    add_rect(ax, x_T - feed_W/2, y_T - feed_W/2, feed_W, abs(y_T) + feed_W/2, h)
    x_p_trans_l = -W/2 - min(lambda_p_trans_4, abs(x_T - (-W/2)))
    if x_p_trans_l > x_T:
        add_rect(ax, x_T - feed_W/2, -feed_W/2, x_p_trans_l - x_T + feed_W/2, feed_W, h)
        add_rect(ax, x_p_trans_l, -w_p_trans/2, abs(x_p_trans_l) - W/2 + feed_W/2, w_p_trans, h, color='gold')
    else:
        add_rect(ax, x_T - feed_W/2, -feed_W/2, abs(x_T) - W/2 + feed_W, feed_W, h)

    # Spodní větev (fáze -90 deg - LHCP zpoždění)
    add_rect(ax, x_T - feed_W/2, y_delay - feed_W/2, feed_W, delay_offset + feed_W, h)
    add_rect(ax, x_T - feed_W/2, y_delay - feed_W/2, abs(x_T) + feed_W, feed_W, h)
    y_p_trans_b = -L/2 - min(lambda_p_trans_4, abs(y_delay - (-L/2)))
    if y_p_trans_b > y_delay:
        add_rect(ax, -feed_W/2, y_delay - feed_W/2, feed_W, y_p_trans_b - y_delay + feed_W/2, h)
        add_rect(ax, -w_p_trans/2, y_p_trans_b, w_p_trans, abs(y_p_trans_b) - L/2 + feed_W/2, h, color='gold')
    else:
        add_rect(ax, -feed_W/2, y_delay - feed_W/2, feed_W, abs(y_delay) - L/2 + feed_W, h)

    # Zvýraznění portu na hraně substrátu
    w_port_entry = feed_W if y_trans_start > -L_sub/2 else w_t_trans
    port_verts = [[(x_T - w_port_entry/2, -L_sub/2, 0), (x_T + w_port_entry/2, -L_sub/2, 0),
                   (x_T + w_port_entry/2, -L_sub/2, h), (x_T - w_port_entry/2, -L_sub/2, h)]]
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
    plt.savefig(filename, dpi=150)
    plt.close()
    print(f"Isometrický nákres byl uložen do {filename}")
