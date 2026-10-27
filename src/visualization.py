import os
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np

def add_rect(ax, x0, y0, w_rect, h_rect, z_val, color='orange', alpha=0.9, edgecolor='k'):
    rx = [x0, x0 + w_rect, x0 + w_rect, x0]
    ry = [y0, y0, y0 + h_rect, y0 + h_rect]
    rz = [z_val, z_val, z_val, z_val]
    ax.add_collection3d(Poly3DCollection([list(zip(rx, ry, rz))], facecolors=color, alpha=alpha, edgecolors=edgecolor))

def plot_geometry(params, filename="data/geometry_iso.png"):
    model_version = int(params.get('antenna_model', 1))

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')
    
    L = params['patch_L']
    W = params['patch_W']
    h = params['sub_h']
    L_sub = params.get('sub_L', params.get('sub_l', 100.0))
    W_sub = params.get('sub_W', params.get('sub_w', 100.0))
    margin = params['air_margin']
    
    # Kreslení substrátu (poloprůhledná zelená)
    sub_x = [-W_sub/2, W_sub/2, W_sub/2, -W_sub/2]
    sub_y = [-L_sub/2, -L_sub/2, L_sub/2, L_sub/2]
    sub_z = [h, h, h, h]
    sub_z0 = [0, 0, 0, 0]
    
    verts_sub = [
        list(zip(sub_x, sub_y, sub_z0)),
        list(zip(sub_x, sub_y, sub_z))
    ]
    ax.add_collection3d(Poly3DCollection(verts_sub, facecolors='green', alpha=0.2, edgecolors='g'))
    
    # Patch (měď - oranžová)
    add_rect(ax, -W/2, -L/2, W, L, h, color='orange', alpha=0.9)

    if model_version == 2:
        # MODEL 2: Dva nezávislé přímé přívody (100 Ohm)
        w = float(params.get('w_feed', params.get('w2', 0.69)))
        inset_b = float(params.get('feed_inset_b', params.get('inset_b', 0.0)))
        inset_l = float(params.get('feed_inset_l', params.get('inset_l', 0.0)))
        y_port = float(params.get('y_port', -L_sub / 2.0))
        x_port = float(params.get('x_port', -W_sub / 2.0))

        # Spodní přívod (Port 1, zpožděný o lambda_g/4 pro LHCP)
        dy_bottom = (-L / 2.0 + inset_b) - y_port
        add_rect(ax, -w/2, y_port, w, dy_bottom, h, color='gold', alpha=0.95)

        # Levý přívod (Port 2, referenční)
        dx_left = (-W / 2.0 + inset_l) - x_port
        add_rect(ax, x_port, -w/2, dx_left, w, h, color='darkorange', alpha=0.95)

        # Port 1 (spodní hrana substrátu, XZ rovina)
        port1_verts = [[
            (-w/2, y_port, 0), (+w/2, y_port, 0),
            (+w/2, y_port, h), (-w/2, y_port, h)
        ]]
        ax.add_collection3d(Poly3DCollection(port1_verts, facecolors='red', alpha=0.9, edgecolors='k'))

        # Port 2 (levá hrana substrátu, YZ rovina)
        port2_verts = [[
            (x_port, -w/2, 0), (x_port, +w/2, 0),
            (x_port, +w/2, h), (x_port, -w/2, h)
        ]]
        ax.add_collection3d(Poly3DCollection(port2_verts, facecolors='crimson', alpha=0.9, edgecolors='k'))

        plot_title = f'Model 2 (2-Port LHCP): L={L:.1f}mm, ib={inset_b:.2f}mm, il={inset_l:.2f}mm'

    else:
        # MODEL 1: Původní geometrie s T-děličem
        w1 = params.get('w1', 2.98)
        w2 = params.get('w2', 0.69)
        w3 = params.get('w3', w2)

        l1 = float(params.get('l1', 15.0))
        l2 = float(params.get('l2', 20.0))
        l3 = float(params.get('l3', 10.0))
        l4 = float(params.get('l4', 15.0))
        l5 = float(params.get('l5', 10.0))
        l6 = float(params.get('l6', 18.0))
        l7 = float(params.get('l7', 15.0))
        l8 = float(params.get('l8', 15.0))

        inset = float(params.get('inset', params.get('feed_inset', 0.0)))
        x_T = float(params.get('feed_x_T', -(l2 + l3)))
        y_T = float(params.get('feed_y_T', -L/2 + inset - l4))

        y_port = -L_sub / 2.0
        # Hlavní přívod
        add_rect(ax, x_T - w1/2, y_port, w1, abs(y_T - y_port) + w2/2, h, color='darkorange', alpha=0.9)
        # Spodní větev
        add_rect(ax, x_T - w2/2, y_T - w2/2, l2 + w2/2, w2, h, color='gold', alpha=0.9)
        add_rect(ax, x_T + l2, y_T - w3/2, l3 + w3/2, w3, h, color='orange', alpha=0.95)
        add_rect(ax, -w3/2, y_T - w3/2, w3, l4 + w3/2 + 0.1, h, color='orange', alpha=0.95)
        # Levá větev
        add_rect(ax, x_T - l5 - w2/2, y_T - w2/2, l5 + w2/2, w2, h, color='gold', alpha=0.9)
        add_rect(ax, x_T - l5 - w2/2, y_T - w2/2, w2, l6 + w2/2, h, color='gold', alpha=0.9)
        add_rect(ax, x_T - l5 - w3/2, y_T + l6, w3, l7 + w3/2, h, color='orange', alpha=0.95)
        add_rect(ax, x_T - l5 - w3/2, -w3/2, l8 + w3/2 + 0.1, w3, h, color='orange', alpha=0.95)

        # Port na hraně substrátu
        w_port_entry = w1
        port_verts = [[(x_T - w_port_entry/2, y_port, 0), (x_T + w_port_entry/2, y_port, 0),
                       (x_T + w_port_entry/2, y_port, h), (x_T - w_port_entry/2, y_port, h)]]
        ax.add_collection3d(Poly3DCollection(port_verts, facecolors='red', alpha=0.9, edgecolors='k'))

        plot_title = f'Model 1 (T-dělič): L={L:.1f}mm, inset={inset:.2f}mm'

    # Vzduchový box (čáry pro přehlednost)
    ax.plot([-W_sub/2-margin, W_sub/2+margin, W_sub/2+margin, -W_sub/2-margin, -W_sub/2-margin],
            [-L_sub/2-margin, -L_sub/2-margin, L_sub/2+margin, L_sub/2+margin, -L_sub/2-margin],
            [-margin, -margin, -margin, -margin, -margin], color='blue', alpha=0.3, linestyle='--')
    ax.plot([-W_sub/2-margin, W_sub/2+margin, W_sub/2+margin, -W_sub/2-margin, -W_sub/2-margin],
            [-L_sub/2-margin, -L_sub/2-margin, L_sub/2+margin, L_sub/2+margin, -L_sub/2-margin],
            [h+margin, h+margin, h+margin, h+margin, h+margin], color='blue', alpha=0.3, linestyle='--')
    
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
    
    ax.view_init(elev=30, azim=45)
    plt.title(plot_title)
    
    os.makedirs(os.path.dirname(os.path.abspath(filename)) or ".", exist_ok=True)
    try:
        plt.savefig(filename, dpi=150)
        print(f"Isometrický nákres byl uložen do {filename}")
    except Exception as e:
        print(f"Upozornění: Náhled geometrie se nepodařilo uložit do {filename}: {e}")
    finally:
        plt.close()
