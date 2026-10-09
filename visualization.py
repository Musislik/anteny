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
    
    # Patch (měď - oranžová)
    patch_x = [-W/2, W/2, W/2, -W/2]
    patch_y = [-L/2, -L/2, L/2, L/2]
    patch_z = [h, h, h, h]
    verts_patch = [list(zip(patch_x, patch_y, patch_z))]
    ax.add_collection3d(Poly3DCollection(verts_patch, facecolors='orange', alpha=0.9, edgecolors='k'))
    
    # Feed left
    fl_x = [-W_sub/2, -W/2, -W/2, -W_sub/2]
    fl_y = [-feed_W/2, -feed_W/2, feed_W/2, feed_W/2]
    verts_fl = [list(zip(fl_x, fl_y, patch_z))]
    ax.add_collection3d(Poly3DCollection(verts_fl, facecolors='orange', alpha=0.9, edgecolors='k'))
    
    # Feed bottom
    fb_x = [-feed_W/2, feed_W/2, feed_W/2, -feed_W/2]
    fb_y = [-L_sub/2, -L_sub/2, -L/2, -L/2]
    verts_fb = [list(zip(fb_x, fb_y, patch_z))]
    ax.add_collection3d(Poly3DCollection(verts_fb, facecolors='orange', alpha=0.9, edgecolors='k'))
    
    # Ground plane (spodní měď)
    verts_gnd = [list(zip(sub_x, sub_y, sub_z0))]
    ax.add_collection3d(Poly3DCollection(verts_gnd, facecolors='orange', alpha=0.5, edgecolors='k'))
    
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
