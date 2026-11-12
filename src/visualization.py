"""
visualization.py - 2D a detailní vizualizace geometrie patch antény v rovině XY.
Generuje:
  1. 'geometrie_shora.png' (a 'geometry_iso.png'): Přehledný 2D pohled shora na celou anténu na substrátu.
  2. 'obrazky/geometrie_detail_transformatoru.png': Zvětšený detail čtvrtvlnného transformátoru w_T a zářezu y_0.
"""

import os
import sys
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import Polygon
import numpy as np

from geometry_v4 import compute_model4_routing, compute_curved_ribbon_outline


def _t_junction_polygon_pts(x_port, x_T, y_T, w_50, w_feed, t_fillet_r, arc_samples=18):
    """Vrátí 2D obrysové body pro vodorovný 50 Ohm kmen zleva a otočený blok T-článku včetně zaoblení."""
    hw_50 = w_50 / 2.0
    hw_f = w_feed / 2.0
    r_f = max(0.0, float(t_fillet_r))
    d_t = hw_50 + r_f
    x_bar_l = x_T - hw_f
    x_bar_r = x_T + hw_f

    if r_f <= 1e-6:
        return [
            (x_port, y_T - hw_50),
            (x_bar_r, y_T - hw_50),
            (x_bar_r, y_T + hw_50),
            (x_port, y_T + hw_50),
        ]

    x_fs = x_bar_l - r_f
    pts = [(x_port, y_T - hw_50), (x_fs, y_T - hw_50)]
    # Dolní oblouk: střed (x_fs, y_T - d_t), úhly od pi/2 do 0
    for ang in np.linspace(0.5 * np.pi, 0.0, arc_samples):
        pts.append((x_fs + r_f * np.cos(ang), (y_T - d_t) + r_f * np.sin(ang)))
    pts.extend([(x_bar_r, y_T - d_t), (x_bar_r, y_T + d_t), (x_bar_l, y_T + d_t)])
    # Horní oblouk: střed (x_fs, y_T + d_t), úhly od 0 do -pi/2
    for ang in np.linspace(0.0, -0.5 * np.pi, arc_samples):
        pts.append((x_fs + r_f * np.cos(ang), (y_T + d_t) + r_f * np.sin(ang)))
    pts.append((x_port, y_T + hw_50))
    return pts


def _draw_model4_top_view(ax, params, is_detail=False):
    """Vykreslí geometrii finálního Modelu 4 (otočený levý 50 Ohm T-článek bez meandru) v rovině XY."""
    info = compute_model4_routing(params)
    L, W = info['L'], info['W']
    W_sub, L_sub = info['W_sub'], info['L_sub']
    w_50, w_feed = info['w_50'], info['w_feed']
    w_T_b, w_T_l = info['w_T_b'], info['w_T_l']
    l_T_b, l_T_l = info['l_T_b'], info['l_T_l']
    inset_b, inset_l = info['inset_b'], info['inset_l']
    gap_b, gap_l = info['inset_gap_b'], info['inset_gap_l']
    bend_r = info['bend_radius']
    t_fillet_r = info['t_fillet_r']
    x_T, y_T = info['x_T'], info['y_T']
    x_port, y_port = info['x_port'], info['y_port']
    y_bot = info['y_bot']
    y_junc_b, x_junc_l = info['y_junc_b'], info['x_junc_l']

    # 1. Substrát
    ax.add_patch(patches.Rectangle(
        (-W_sub / 2.0, -L_sub / 2.0), W_sub, L_sub,
        linewidth=1.2, edgecolor='#2E7D32', facecolor='#E8F5E9',
        zorder=1, label=rf'Substrát ({W_sub:.1f} $\times$ {L_sub:.1f} mm)'
    ))

    # 2. Flíček se zářezy
    notch_b_w = w_T_b + 2.0 * gap_b if inset_b > 0 else 0.0
    notch_l_h = w_T_l + 2.0 * gap_l if inset_l > 0 else 0.0
    x_l, x_r, y_b, y_t = -W / 2.0, W / 2.0, -L / 2.0, L / 2.0
    verts_patch = [
        (notch_b_w / 2.0, y_b), (x_r, y_b), (x_r, y_t), (x_l, y_t),
        (x_l, notch_l_h / 2.0), (x_l + inset_l, notch_l_h / 2.0),
        (x_l + inset_l, -notch_l_h / 2.0), (x_l, -notch_l_h / 2.0),
        (x_l, y_b), (-notch_b_w / 2.0, y_b),
        (-notch_b_w / 2.0, y_b + inset_b), (notch_b_w / 2.0, y_b + inset_b),
    ]
    ax.add_patch(Polygon(
        verts_patch, closed=True,
        facecolor='#E67E22', edgecolor='#935116',
        linewidth=1.3, zorder=3, label=rf'Vyzařující flíček ({W:.1f} $\times$ {L:.1f} mm)'
    ))

    # 3. Transformátory u flíčku
    ax.add_patch(patches.Rectangle(
        (-w_T_b / 2.0, y_junc_b), w_T_b, l_T_b,
        linewidth=0.8, edgecolor='#B7770D', facecolor='#F1C40F',
        zorder=5, label=rf'Transformátor $w_T$ ({w_T_b:.2f} mm)'
    ))
    ax.add_patch(patches.Rectangle(
        (x_junc_l, -w_T_l / 2.0), l_T_l, w_T_l,
        linewidth=0.8, edgecolor='#B7770D', facecolor='#F1C40F',
        zorder=5
    ))

    # 4. Zakřivené 100 Ohm větve (1 oblouk na Ex, 2 oblouky na Ey, bez meandru)
    arm_l_poly = compute_curved_ribbon_outline(info['arm_l_build_waypoints'], w_feed, bend_r)
    arm_b_poly = compute_curved_ribbon_outline(info['arm_b_build_waypoints'], w_feed, bend_r)
    ax.add_patch(Polygon(
        arm_l_poly, closed=True, facecolor='#D35400', edgecolor='#78281F',
        linewidth=0.8, zorder=4, label=rf'Zakřivené větve $100\ \Omega$ ($w={w_feed:.2f}$ mm, $R={bend_r:.1f}$ mm)'
    ))
    ax.add_patch(Polygon(
        arm_b_poly, closed=True, facecolor='#D35400', edgecolor='#78281F',
        linewidth=0.8, zorder=4
    ))

    # 5. Vodorovný levý 50 Ohm přívod a otočený T-článek se zaoblením
    trunk_pts = _t_junction_polygon_pts(x_port, x_T, y_T, w_50, w_feed, t_fillet_r)
    ax.add_patch(Polygon(
        trunk_pts, closed=True, facecolor='#C0392B', edgecolor='#641E16',
        linewidth=0.9, zorder=5, label=rf'Přívod $50\ \Omega$ + T-článek ($w_1={w_50:.2f}$ mm)'
    ))

    # 6. Výstupní 50 Ohm port na levé hraně substrátu
    port_hw = max(w_50 * 0.75, 1.5)
    ax.add_patch(patches.Rectangle(
        (x_port - 0.8, y_port - port_hw), 0.8, 2.0 * port_hw,
        facecolor='red', edgecolor='darkred', lw=1.2, zorder=6, label=r'Port 1 ($50\ \Omega$)'
    ))

    if not is_detail:
        ax.text(
            0.0, 2.5,
            "Vyzařující flíček\n" + rf"($W={W:.1f} \times L={L:.1f}\ \mathrm{{mm}}$)",
            ha='center', va='center', fontsize=9.5, fontweight='bold', color='#5D2E08',
            bbox=dict(boxstyle="round,pad=0.3", fc="#FFF8EB", ec="#E67E22", alpha=0.92),
            zorder=7,
        )
        ax.annotate(
            rf"Větev $E_x$ ($100\ \Omega$, $0^\circ$)" + "\n"
            + rf"($1$ oblouk, $L_{{100,l}}={info['L_100_l']:.2f}\ \mathrm{{mm}}$)",
            xy=(x_T, min(-4.0, 0.35 * y_T)),
            xytext=(max(-W_sub / 2.0 + 18.0, x_T + 8.0), L / 2.0 + 9.0),
            arrowprops=dict(arrowstyle="->", color="#78281F", lw=1.3),
            ha='center', va='center', fontsize=8.5, fontweight='bold', color='#78281F',
            bbox=dict(boxstyle="round,pad=0.25", fc="#FEF9E7", ec="#D35400", alpha=0.93),
            zorder=8,
        )
        ax.annotate(
            rf"Větev $E_y$ ($100\ \Omega$, $-90^\circ$)" + "\n"
            + rf"($2$ oblouky, $L_{{100,b}}={info['L_100_b']:.2f}\ \mathrm{{mm}}$, $\Delta L={info['feed_delta_l']:.2f}\ \mathrm{{mm}}$)",
            xy=(0.45 * x_T, y_bot),
            xytext=(min(W_sub / 2.0 - 22.0, max(16.0, W / 2.0 + 10.0)), y_bot + 10.5),
            arrowprops=dict(arrowstyle="->", color="#78281F", lw=1.3),
            ha='center', va='center', fontsize=8.5, fontweight='bold', color='#78281F',
            bbox=dict(boxstyle="round,pad=0.25", fc="#FEF9E7", ec="#D35400", alpha=0.93),
            zorder=8,
        )
        ax.annotate(
            rf"T-článek $50\ \Omega \to 100\parallel 100\ \Omega$" + "\n"
            + rf"($R_{{\mathrm{{obl}}}}={bend_r:.1f}\ \mathrm{{mm}}$, $L_{{50}}={info['feed_50_len']:.2f}\ \mathrm{{mm}}$)",
            xy=(x_T, y_T),
            xytext=(min(-12.0, x_T + 18.5), y_T + 2.5),
            arrowprops=dict(arrowstyle="->", color="#641E16", lw=1.4),
            ha='center', va='center', fontsize=8.5, fontweight='bold', color='#641E16',
            bbox=dict(boxstyle="round,pad=0.28", fc="#FDEDEC", ec="#C0392B", alpha=0.93),
            zorder=8,
        )
        ax.annotate(
            rf"Levý port ($50\ \Omega$)" + "\n" + rf"($x={x_port:.2f}\ \mathrm{{mm}}$)",
            xy=(x_port - 0.2, y_port),
            xytext=(x_port + 0.8, y_port + 11.0),
            arrowprops=dict(arrowstyle="->", color="red", lw=1.3),
            ha='left', va='bottom', fontsize=8.8, fontweight='bold', color='darkred',
            bbox=dict(boxstyle="round,pad=0.22", fc="#FDEDEC", ec="red", alpha=0.93),
            zorder=8,
        )


def _draw_model3_top_view(ax, params, is_detail=False):
    """
    Vykreslí geometrii Modelu 3 (Hybridní dvoustupňové přizpůsobení) v rovině XY.
    """
    L = float(params.get('patch_L', 29.95))
    W = float(params.get('patch_W', L))
    L_sub = float(params.get('sub_L', params.get('sub_l', 100.0)))
    W_sub = float(params.get('sub_W', params.get('sub_w', 100.0)))

    w_feed = float(params.get('w_feed', params.get('w2', 0.694)))
    w_T_b = float(params.get('trans_w_b', params.get('w_T_b', params.get('trans_w', params.get('w_T', 0.30)))))
    w_T_l = float(params.get('trans_w_l', params.get('w_T_l', params.get('trans_w', params.get('w_T', 0.30)))))
    l_T_b = float(params.get('trans_l_b', params.get('l_T_b', params.get('trans_l', params.get('l_T', 19.0)))))
    l_T_l = float(params.get('trans_l_l', params.get('l_T_l', params.get('trans_l', params.get('l_T', 19.0)))))
    inset_b = float(params.get('feed_inset_b', params.get('inset_b', params.get('y0b', 2.5))))
    inset_l = float(params.get('feed_inset_l', params.get('inset_l', params.get('y0l', 2.5))))
    gap_b = float(params.get('inset_gap_b', params.get('feed_inset_gap_b', 0.5)))
    gap_l = float(params.get('inset_gap_l', params.get('feed_inset_gap_l', 0.5)))

    y_port = float(params.get('y_port', -L_sub / 2.0))
    x_port = float(params.get('x_port', -W_sub / 2.0))
    feed_delta_l = float(params.get('feed_delta_l', params.get('delta_l', 18.66)))

    y_junc_b = -L / 2.0 + inset_b - l_T_b
    x_junc_l = -W / 2.0 + inset_l - l_T_l

    # 1. Substrát (světle zelená)
    sub_rect = patches.Rectangle(
        (-W_sub / 2.0, -L_sub / 2.0), W_sub, L_sub,
        linewidth=1.2, edgecolor='#2E7D32', facecolor='#E8F5E9',
        zorder=1, label=rf'Substrát ({W_sub:.1f} $\times$ {L_sub:.1f} mm)'
    )
    ax.add_patch(sub_rect)

    # 2. Polygon vyzařujícího flíčku se zářezy
    notch_b_w = w_T_b + 2.0 * gap_b if inset_b > 0 else 0.0
    notch_l_h = w_T_l + 2.0 * gap_l if inset_l > 0 else 0.0

    x_l = -W / 2.0
    x_r = W / 2.0
    y_b = -L / 2.0
    y_t = L / 2.0

    verts_patch = [
        (notch_b_w / 2.0, y_b),
        (x_r, y_b),
        (x_r, y_t),
        (x_l, y_t),
        (x_l, notch_l_h / 2.0),
        (x_l + inset_l, notch_l_h / 2.0),
        (x_l + inset_l, -notch_l_h / 2.0),
        (x_l, -notch_l_h / 2.0),
        (x_l, y_b),
        (-notch_b_w / 2.0, y_b),
        (-notch_b_w / 2.0, y_b + inset_b),
        (notch_b_w / 2.0, y_b + inset_b),
    ]

    patch_poly = Polygon(
        verts_patch, closed=True,
        facecolor='#E67E22', edgecolor='#935116',
        linewidth=1.3, zorder=3, label=rf'Vyzařující flíček ({W:.1f} $\times$ {L:.1f} mm)'
    )
    ax.add_patch(patch_poly)

    # 3. Spodní rameno (Port 1, pole Ey):
    # - Vnější 100 Ohm vedení
    feed1_len = y_junc_b - y_port
    rect_feed1 = patches.Rectangle(
        (-w_feed / 2.0, y_port), w_feed, feed1_len,
        linewidth=0.8, edgecolor='#78281F', facecolor='#D35400',
        zorder=4, label=rf'Napaječ 100 $\Omega$ ($w={w_feed:.2f}$ mm)'
    )
    ax.add_patch(rect_feed1)

    # - Čtvrtvlnný transformátor
    rect_trans1 = patches.Rectangle(
        (-w_T_b / 2.0, y_junc_b), w_T_b, l_T_b,
        linewidth=0.8, edgecolor='#B7770D', facecolor='#F1C40F',
        zorder=5, label=rf'Transformátor $w_T$ ({w_T_b:.2f} mm)'
    )
    ax.add_patch(rect_trans1)

    # 4. Levé rameno (Port 2, pole Ex):
    # - Vnější 100 Ohm vedení
    feed2_len = x_junc_l - x_port
    rect_feed2 = patches.Rectangle(
        (x_port, -w_feed / 2.0), feed2_len, w_feed,
        linewidth=0.8, edgecolor='#78281F', facecolor='#D35400',
        zorder=4
    )
    ax.add_patch(rect_feed2)

    # - Čtvrtvlnný transformátor
    rect_trans2 = patches.Rectangle(
        (x_junc_l, -w_T_l / 2.0), l_T_l, w_T_l,
        linewidth=0.8, edgecolor='#B7770D', facecolor='#F1C40F',
        zorder=5
    )
    ax.add_patch(rect_trans2)

    # 5. Vyznačení portů na hranách substrátu
    port_hw = max(w_feed * 1.5, 1.2)
    p1_marker = patches.Rectangle(
        (-port_hw, y_port - 0.6), 2.0 * port_hw, 0.6,
        facecolor='red', edgecolor='darkred', lw=1.2, zorder=6, label='Port 1 (spodní, $E_y$)'
    )
    p2_marker = patches.Rectangle(
        (x_port - 0.6, -port_hw), 0.6, 2.0 * port_hw,
        facecolor='crimson', edgecolor='darkred', lw=1.2, zorder=6, label='Port 2 (levý, $E_x$)'
    )
    ax.add_patch(p1_marker)
    ax.add_patch(p2_marker)

    # 6. Referenční roviny (RP1, RP2, RP3)
    ax.axhline(y_port, color='blue', linestyle=':', lw=0.9, alpha=0.6)
    ax.axhline(y_junc_b, color='darkgoldenrod', linestyle=':', lw=0.9, alpha=0.7)
    ax.axhline(y_b, color='brown', linestyle=':', lw=0.9, alpha=0.6)

    ax.axvline(x_port, color='blue', linestyle=':', lw=0.9, alpha=0.6)
    ax.axvline(x_junc_l, color='darkgoldenrod', linestyle=':', lw=0.9, alpha=0.7)
    ax.axvline(x_l, color='brown', linestyle=':', lw=0.9, alpha=0.6)

    if not is_detail:
        # Přehledové popisky
        ax.annotate(
            "Vyzařující flíček\n" + rf"($W={W:.1f} \times L={L:.1f}\ \mathrm{{mm}}$)",
            xy=(0, 0), xytext=(12, 12),
            arrowprops=dict(arrowstyle="->", color="#935116", lw=1.5),
            fontsize=10, fontweight='bold', color='#935116',
            bbox=dict(boxstyle="round,pad=0.3", fc="#FDEDEC", ec="#E67E22", alpha=0.9)
        )

        ax.annotate(
            rf"Transformátor $w_T={w_T_b:.2f}\ \mathrm{{mm}}$" + "\n" + rf"($l_T={l_T_b:.1f}\ \mathrm{{mm}} \approx \lambda_g/4$)",
            xy=(0, y_junc_b + l_T_b * 0.45), xytext=(8, y_junc_b + l_T_b * 0.45),
            arrowprops=dict(arrowstyle="->", color="#B7770D", lw=1.5),
            fontsize=9.5, fontweight='bold', color='#7D6608',
            bbox=dict(boxstyle="round,pad=0.3", fc="#FEF9E7", ec="#F1C40F", alpha=0.9)
        )

        ax.annotate(
            rf"Napaječ $100\ \Omega$ ($w={w_feed:.2f}\ \mathrm{{mm}}$)",
            xy=(0, (y_port + y_junc_b) / 2.0), xytext=(8, (y_port + y_junc_b) / 2.0),
            arrowprops=dict(arrowstyle="->", color="#78281F", lw=1.5),
            fontsize=9.5, fontweight='bold', color='#78281F',
            bbox=dict(boxstyle="round,pad=0.3", fc="#FDEDEC", ec="#D35400", alpha=0.9)
        )

        ax.annotate(
            rf"Zářez $y_0={inset_b:.2f}\ \mathrm{{mm}}$",
            xy=(notch_b_w / 2.0, y_b + inset_b / 2.0), xytext=(10, y_b + inset_b / 2.0),
            arrowprops=dict(arrowstyle="->", color="#A04000", lw=1.2),
            fontsize=9, color='#A04000',
            bbox=dict(boxstyle="round,pad=0.25", fc="#FBEEE6", ec="#E59866", alpha=0.85)
        )

        # Popisky referenčních rovin
        ax.text(-W_sub/2.0 + 2.0, y_port + 1.2, "RP1 (Port 1)", fontsize=8.5, color='blue', fontweight='bold')
        ax.text(-W_sub/2.0 + 2.0, y_junc_b + 1.2, "RP2 (Svorka)", fontsize=8.5, color='darkgoldenrod', fontweight='bold')
        ax.text(-W_sub/2.0 + 2.0, y_b + 1.2, "RP3 (Flíček)", fontsize=8.5, color='brown', fontweight='bold')

        # Porty
        ax.text(0, y_port - 2.5, "Port 1 (Spodní, Ey, -90°)", fontsize=9.5, fontweight='bold', color='red', ha='center')
        ax.text(x_port - 2.0, 0, "Port 2 (Levý, Ex, ref 0°)", fontsize=9.5, fontweight='bold', color='crimson',
                va='center', rotation=90)


def _draw_model2_top_view(ax, params):
    """Vykreslí geometrii Modelu 2 (Dvouportový 100 Ohm přímý přívod) v rovině XY."""
    L = float(params.get('patch_L', 28.8))
    W = float(params.get('patch_W', L))
    L_sub = float(params.get('sub_L', params.get('sub_l', 100.0)))
    W_sub = float(params.get('sub_W', params.get('sub_w', 100.0)))
    w_feed = float(params.get('w_feed', params.get('w2', 0.694)))
    inset_b = float(params.get('feed_inset_b', params.get('inset_b', 0.0)))
    inset_l = float(params.get('feed_inset_l', params.get('inset_l', 0.0)))
    y_port = float(params.get('y_port', -L_sub / 2.0))
    x_port = float(params.get('x_port', -W_sub / 2.0))

    # Substrát
    sub_rect = patches.Rectangle(
        (-W_sub / 2.0, -L_sub / 2.0), W_sub, L_sub,
        linewidth=1.2, edgecolor='#2E7D32', facecolor='#E8F5E9', zorder=1,
        label=rf'Substrát ({W_sub:.1f} $\times$ {L_sub:.1f} mm)'
    )
    ax.add_patch(sub_rect)

    # Patch
    patch_rect = patches.Rectangle(
        (-W / 2.0, -L / 2.0), W, L,
        linewidth=1.3, edgecolor='#935116', facecolor='#E67E22', zorder=3,
        label=rf'Vyzařující flíček ({W:.1f} $\times$ {L:.1f} mm)'
    )
    ax.add_patch(patch_rect)

    # Spodní a levé vedení 100 Ohm
    dy_bottom = (-L / 2.0 + inset_b) - y_port
    ax.add_patch(patches.Rectangle((-w_feed / 2.0, y_port), w_feed, dy_bottom,
                                   edgecolor='#78281F', facecolor='#D35400', zorder=4,
                                   label=rf'Napaječ 100 $\Omega$ ($w={w_feed:.2f}$ mm)'))
    dx_left = (-W / 2.0 + inset_l) - x_port
    ax.add_patch(patches.Rectangle((x_port, -w_feed / 2.0), dx_left, w_feed,
                                   edgecolor='#78281F', facecolor='#D35400', zorder=4))

    ax.annotate("Vyzařující flíček", xy=(0, 0), xytext=(12, 12),
                arrowprops=dict(arrowstyle="->", color="#935116"), fontsize=10, fontweight='bold', color='#935116')
    ax.annotate(rf"Přívod 100 $\Omega$ ($w={w_feed:.2f}\ \mathrm{{mm}}$)", xy=(0, y_port + dy_bottom / 2.0),
                xytext=(8, y_port + dy_bottom / 2.0), arrowprops=dict(arrowstyle="->", color="#78281F"),
                fontsize=9.5, fontweight='bold', color='#78281F')


def _draw_model1_top_view(ax, params):
    """Vykreslí geometrii Modelu 1 (T-dělič) v rovině XY."""
    L = float(params.get('patch_L', 28.8))
    W = float(params.get('patch_W', L))
    L_sub = float(params.get('sub_L', params.get('sub_l', 100.0)))
    W_sub = float(params.get('sub_W', params.get('sub_w', 100.0)))
    w1 = float(params.get('w1', 2.98))
    w2 = float(params.get('w2', 0.69))
    w3 = float(params.get('w3', w2))
    l2 = float(params.get('l2', 20.0))
    l3 = float(params.get('l3', 10.0))
    l4 = float(params.get('l4', 15.0))
    l5 = float(params.get('l5', 10.0))
    l6 = float(params.get('l6', 18.0))
    l7 = float(params.get('l7', 15.0))
    l8 = float(params.get('l8', 15.0))
    inset = float(params.get('inset', params.get('feed_inset', 0.0)))
    x_T = float(params.get('feed_x_T', -(l2 + l3)))
    y_T = float(params.get('feed_y_T', -L / 2.0 + inset - l4))
    y_port = -L_sub / 2.0

    # Substrát
    ax.add_patch(patches.Rectangle((-W_sub / 2.0, -L_sub / 2.0), W_sub, L_sub,
                                   linewidth=1.2, edgecolor='#2E7D32', facecolor='#E8F5E9', zorder=1,
                                   label=rf'Substrát ({W_sub:.1f} $\times$ {L_sub:.1f} mm)'))
    # Patch
    ax.add_patch(patches.Rectangle((-W / 2.0, -L / 2.0), W, L,
                                   linewidth=1.3, edgecolor='#935116', facecolor='#E67E22', zorder=3,
                                   label=rf'Vyzařující flíček ({W:.1f} $\times$ {L:.1f} mm)'))

    # T-dělič a ramena
    ax.add_patch(patches.Rectangle((x_T - w1 / 2.0, y_port), w1, abs(y_T - y_port) + w2 / 2.0,
                                   edgecolor='#78281F', facecolor='#D35400', zorder=4,
                                   label=rf'Napaječ 50 $\Omega$ ($w_1={w1:.2f}$ mm)'))
    ax.add_patch(patches.Rectangle((x_T - w2 / 2.0, y_T - w2 / 2.0), l2 + w2 / 2.0, w2,
                                   edgecolor='#B7770D', facecolor='#F1C40F', zorder=4,
                                   label=rf'Větve T-děliče 100 $\Omega$ ($w_2={w2:.2f}$ mm)'))
    ax.add_patch(patches.Rectangle((x_T + l2, y_T - w3 / 2.0), l3 + w3 / 2.0, w3,
                                   edgecolor='#78281F', facecolor='#D35400', zorder=4))
    ax.add_patch(patches.Rectangle((-w3 / 2.0, y_T - w3 / 2.0), w3, l4 + w3 / 2.0,
                                   edgecolor='#78281F', facecolor='#D35400', zorder=4))
    ax.add_patch(patches.Rectangle((x_T - l5 - w2 / 2.0, y_T - w2 / 2.0), l5 + w2 / 2.0, w2,
                                   edgecolor='#B7770D', facecolor='#F1C40F', zorder=4))
    ax.add_patch(patches.Rectangle((x_T - l5 - w2 / 2.0, y_T - w2 / 2.0), w2, l6 + w2 / 2.0,
                                   edgecolor='#B7770D', facecolor='#F1C40F', zorder=4))
    ax.add_patch(patches.Rectangle((x_T - l5 - w3 / 2.0, y_T + l6), w3, l7 + w3 / 2.0,
                                   edgecolor='#78281F', facecolor='#D35400', zorder=4))
    ax.add_patch(patches.Rectangle((x_T - l5 - w3 / 2.0, -w3 / 2.0), l8 + w3 / 2.0, w3,
                                   edgecolor='#78281F', facecolor='#D35400', zorder=4))


def plot_geometry(params, filename="data/geometry_iso.png"):
    """
    Vykreslí přehledný 2D pohled shora (rovina XY) i detailní výřez transformátoru.
    Ukládá:
      - filename (např. 'data/geometry_iso.png')
      - '<dir>/obrazky/geometrie_shora.png'
      - '<dir>/obrazky/geometrie_detail_transformatoru.png'
    """
    model_version = int(params.get('antenna_model', 3))
    out_dir = os.path.dirname(os.path.abspath(filename)) or "."
    obrazky_dir = os.path.join(out_dir, "obrazky")
    os.makedirs(obrazky_dir, exist_ok=True)

    L = float(params.get('patch_L', 29.95))
    W = float(params.get('patch_W', L))
    L_sub = float(params.get('sub_L', params.get('sub_l', 100.0)))
    W_sub = float(params.get('sub_W', params.get('sub_w', 100.0)))

    # =========================================================================
    # 1. HLAVNÍ 2D POHLED SHORA (rovina XY)
    # =========================================================================
    fig, ax = plt.subplots(figsize=(11, 10))
    ax.set_aspect('equal')

    if model_version == 4:
        info_m4 = compute_model4_routing(params)
        L_sub = info_m4['L_sub']
        W_sub = info_m4['W_sub']
        _draw_model4_top_view(ax, params, is_detail=False)
        plot_title = (
            f"Model 4: Finální model ($50\\ \\Omega$ T-článek + oblouky) — 2D pohled shora (rovina XY)\n"
            f"Flíček $W={W:.1f}\\times L={L:.1f}\\ \\mathrm{{mm}}$, "
            f"$w_T={info_m4['w_T_b']:.2f}\\ \\mathrm{{mm}}$, $y_0={info_m4['inset_b']:.2f}\\ \\mathrm{{mm}}$, "
            f"$R_{{\\mathrm{{obl}}}}={info_m4['bend_radius']:.1f}\\ \\mathrm{{mm}}$, $\\Delta L={info_m4['feed_delta_l']:.2f}\\ \\mathrm{{mm}}$"
        )
    elif model_version == 3:
        _draw_model3_top_view(ax, params, is_detail=False)
        w_T = float(params.get('trans_w_b', params.get('w_T_b', params.get('trans_w', 0.30))))
        l_T = float(params.get('trans_l_b', params.get('l_T_b', params.get('trans_l', 19.0))))
        y0 = float(params.get('feed_inset_b', params.get('inset_b', 2.5)))
        plot_title = (
            f"Model 3: Hybridní dvoustupňové přizpůsobení — 2D pohled shora (rovina XY)\n"
            f"Flíček $W={W:.1f}\\times L={L:.1f}\\ \\mathrm{{mm}}$, "
            f"Transformátor $w_T={w_T:.2f}\\ \\mathrm{{mm}}$, $l_T={l_T:.1f}\\ \\mathrm{{mm}}$, "
            f"Zářez $y_0={y0:.2f}\\ \\mathrm{{mm}}$"
        )
    elif model_version == 2:
        _draw_model2_top_view(ax, params)
        plot_title = f"Model 2: Dvouportové buzení 100 $\\Omega$ LHCP — 2D pohled shora (rovina XY)\nFlíček $W={W:.1f}\\times L={L:.1f}\\ \\mathrm{{mm}}$"
    else:
        _draw_model1_top_view(ax, params)
        plot_title = f"Model 1: LHCP anténa s T-děličem — 2D pohled shora (rovina XY)\nFlíček $W={W:.1f}\\times L={L:.1f}\\ \\mathrm{{mm}}$"

    margin_view = 6.0
    ax.set_xlim([-W_sub / 2.0 - margin_view, W_sub / 2.0 + margin_view])
    ax.set_ylim([-L_sub / 2.0 - margin_view, L_sub / 2.0 + margin_view])
    ax.set_xlabel('X [mm]', fontsize=11, fontweight='bold')
    ax.set_ylabel('Y [mm]', fontsize=11, fontweight='bold')
    ax.set_title(plot_title, fontsize=12, fontweight='bold', pad=12)
    ax.grid(True, linestyle=':', alpha=0.55)
    if ax.get_legend_handles_labels()[0]:
        ax.legend(loc='upper right', fontsize=9, framealpha=0.92)

    plt.tight_layout()
    plt.savefig(filename, dpi=250)
    # Také uložíme do podsložky obrazky/geometrie_shora.png
    p_shora = os.path.join(obrazky_dir, "geometrie_shora.png")
    plt.savefig(p_shora, dpi=250)
    plt.close(fig)
    print(f"2D náhled geometrie shora byl uložen do: {filename} a {p_shora}")

    # =========================================================================
    # 2. DETAILNÍ VÝŘEZ: ČTVRTVLVNNÝ TRANSFORMÁTOR A ZÁŘEZ y_0 (+ T-ČLÁNEK PRO M4)
    # =========================================================================
    if model_version == 4:
        fig_det, (ax_det, ax_t) = plt.subplots(
            1, 2, figsize=(16, 7.8), gridspec_kw={'width_ratios': [1.0, 1.35]}
        )
        ax_det.set_aspect('equal')
        ax_t.set_aspect('equal')
        info_m4 = compute_model4_routing(params)
    else:
        fig_det, ax_det = plt.subplots(figsize=(10, 8.5))
        ax_det.set_aspect('equal')

    if model_version in (3, 4):
        if model_version == 4:
            w_feed = info_m4['w_feed']
            w_T = info_m4['w_T_b']
            l_T = info_m4['l_T_b']
            inset_b = info_m4['inset_b']
            gap_b = info_m4['inset_gap_b']
        else:
            w_feed = float(params.get('w_feed', params.get('w2', 0.694)))
            w_T = float(params.get('trans_w_b', params.get('w_T_b', params.get('trans_w', 0.30))))
            l_T = float(params.get('trans_l_b', params.get('l_T_b', params.get('trans_l', 19.0))))
            inset_b = float(params.get('feed_inset_b', params.get('inset_b', 2.5)))
            gap_b = float(params.get('inset_gap_b', 0.5))
        y_b = -L / 2.0
        y_junc_b = y_b + inset_b - l_T

        # Kreslení podkladu a detailních prvků
        # 1. Substrát
        ax_det.add_patch(patches.Rectangle(
            (-20, y_junc_b - 10), 40, (y_b + inset_b + 10) - (y_junc_b - 10),
            facecolor='#E8F5E9', edgecolor='#2E7D32', lw=1.0, zorder=1
        ))

        # 2. Tělo flíčku kolem spodního zářezu
        notch_w = w_T + 2.0 * gap_b
        patch_pts = [
            (-15, y_b),
            (-notch_w / 2.0, y_b),
            (-notch_w / 2.0, y_b + inset_b),
            (notch_w / 2.0, y_b + inset_b),
            (notch_w / 2.0, y_b),
            (15, y_b),
            (15, y_b + inset_b + 8),
            (-15, y_b + inset_b + 8),
        ]
        ax_det.add_patch(Polygon(patch_pts, closed=True, facecolor='#E67E22', edgecolor='#935116', lw=1.5, zorder=3))

        # 3. Vnější 100 Ohm vedení
        ax_det.add_patch(patches.Rectangle(
            (-w_feed / 2.0, y_junc_b - 8), w_feed, 8,
            facecolor='#D35400', edgecolor='#78281F', lw=1.2, zorder=4
        ))

        # 4. Čtvrtvlnný transformátor
        ax_det.add_patch(patches.Rectangle(
            (-w_T / 2.0, y_junc_b), w_T, l_T,
            facecolor='#F1C40F', edgecolor='#B7770D', lw=1.2, zorder=5
        ))

        # 5. Referenční roviny RP2 a RP3
        ax_det.axhline(y_junc_b, color='darkgoldenrod', linestyle='--', lw=1.2, zorder=6)
        ax_det.text(3.5, y_junc_b, "Rovina RP2 (svorka transformátoru)", color='darkgoldenrod',
                    fontsize=9.5, fontweight='bold', va='center')

        ax_det.axhline(y_b, color='brown', linestyle='--', lw=1.2, zorder=6)
        ax_det.text(3.5, y_b, "Hrana flíčku", color='brown', fontsize=9.5, fontweight='bold', va='center')

        ax_det.axhline(y_b + inset_b, color='red', linestyle='--', lw=1.2, zorder=6)
        ax_det.text(3.5, y_b + inset_b, "Rovina RP3 (vstup do flíčku)", color='red',
                    fontsize=9.5, fontweight='bold', va='center')

        # Kótování a šipky
        # Kóta šířky w_feed
        ax_det.annotate("", xy=(-w_feed / 2.0, y_junc_b - 4), xytext=(w_feed / 2.0, y_junc_b - 4),
                        arrowprops=dict(arrowstyle="<->", color="black", lw=1.2))
        ax_det.text(0, y_junc_b - 5.5, rf"$w_{{feed}}={w_feed:.2f}\ \mathrm{{mm}}$ ($100\ \Omega$)",
                    fontsize=9, ha='center', fontweight='bold',
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="gray", alpha=0.9))

        # Kóta šířky w_T (vpravo od transformátoru, mimo kótu délky l_T vlevo)
        y_mid_trans = (y_junc_b + y_b) / 2.0
        ax_det.annotate("", xy=(-w_T / 2.0, y_mid_trans), xytext=(w_T / 2.0, y_mid_trans),
                        arrowprops=dict(arrowstyle="<->", color="black", lw=1.2))
        ax_det.text(1.6, y_mid_trans, rf"$w_T={w_T:.2f}\ \mathrm{{mm}}$" + "\n" + r"($Z_T \approx 119\ \Omega$)",
                    fontsize=9, ha='left', va='center', fontweight='bold',
                    bbox=dict(boxstyle="round,pad=0.2", fc="lightyellow", ec="goldenrod", alpha=0.95))

        # Kóta délky transformátoru l_T
        ax_det.annotate("", xy=(-2.8, y_junc_b), xytext=(-2.8, y_b + inset_b),
                        arrowprops=dict(arrowstyle="<->", color="darkgoldenrod", lw=1.5))
        ax_det.text(-3.2, (y_junc_b + y_b + inset_b) / 2.0, rf"$l_T={l_T:.1f}\ \mathrm{{mm}}$" + "\n" + r"($\approx \lambda_g/4$)",
                    fontsize=9, ha='right', va='center', color='darkgoldenrod', fontweight='bold',
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="goldenrod", alpha=0.9))

        # Kóta zářezu y_0
        ax_det.annotate("", xy=(1.5, y_b), xytext=(1.5, y_b + inset_b),
                        arrowprops=dict(arrowstyle="<->", color="darkred", lw=1.5))
        ax_det.text(1.8, y_b + inset_b / 2.0, rf"Zářez $y_0={inset_b:.2f}\ \mathrm{{mm}}$",
                    fontsize=9, ha='left', va='center', color='darkred', fontweight='bold',
                    bbox=dict(boxstyle="round,pad=0.2", fc="#FDEDEC", ec="crimson", alpha=0.9))

        # Kóta mezery gap
        ax_det.annotate("Mezera\n" + rf"$g={gap_b:.2f}\ \mathrm{{mm}}$",
                        xy=((w_T / 2.0 + notch_w / 2.0) / 2.0, y_b + inset_b * 0.4),
                        xytext=(2.8, y_b - 3.5),
                        arrowprops=dict(arrowstyle="->", color="navy", lw=1.2),
                        fontsize=8.5, color='navy', fontweight='bold',
                        bbox=dict(boxstyle="round,pad=0.2", fc="#EBF5FB", ec="#5DADE2", alpha=0.9))

        ax_det.set_xlim([-8.0, 10.0])
        ax_det.set_ylim([y_junc_b - 8.0, y_b + inset_b + 5.0])
        ax_det.set_xlabel('X [mm]', fontsize=11, fontweight='bold')
        ax_det.set_ylabel('Y [mm]', fontsize=11, fontweight='bold')
        ax_det.set_title(
            rf"Detail transformátoru $w_T={w_T:.2f}\ \mathrm{{mm}}$ a zářezu $y_0={inset_b:.2f}\ \mathrm{{mm}}$" + "\n"
            r"$100\ \Omega$ napaječ $\to$ $\lambda_g/4$ transformátor $\to$ zářez flíčku",
            fontsize=10.5 if model_version == 4 else 11.5, fontweight='bold', pad=10
        )
        ax_det.grid(True, linestyle=':', alpha=0.6)

        if model_version == 4:
            _draw_model4_top_view(ax_t, params, is_detail=True)
            x_t = info_m4['x_T']
            y_t = info_m4['y_T']
            x_p = info_m4['x_port']
            y_b_arm = info_m4['y_bot']
            w50_m4 = info_m4['w_50']
            wf_m4 = info_m4['w_feed']
            d_t_m4 = info_m4['d_t']
            r_b_m4 = info_m4['bend_radius']
            x_bar_l = x_t - wf_m4 / 2.0

            x_lim_min = x_p - 4.5
            x_lim_max = max(info_m4['x_junc_l'] + 5.0, x_t + 14.0)
            y_lim_min = min(y_b_arm - 6.0, -info_m4['L_sub'] / 2.0 - 1.5)
            y_lim_max = y_t + 10.5
            ax_t.set_xlim([x_lim_min, x_lim_max])
            ax_t.set_ylim([y_lim_min, y_lim_max])

            # Přehledné kóty a popisky v detailu otočeného T-článku (bez překryvů)
            y_dim_l50 = y_t + d_t_m4 + 2.6
            ax_t.annotate(
                "", xy=(x_bar_l, y_dim_l50), xytext=(x_p, y_dim_l50),
                arrowprops=dict(arrowstyle="<->", color="#B71C1C", lw=1.3), zorder=8
            )
            ax_t.text(
                0.5 * (x_p + x_bar_l), y_dim_l50 + 0.7,
                rf"$L_{{50}}={info_m4['feed_50_len']:.2f}\ \mathrm{{mm}}$",
                fontsize=8.5, fontweight='bold', color="#B71C1C", ha='center', va='bottom',
                bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="#B71C1C", lw=0.7, alpha=0.92), zorder=9
            )

            ax_t.plot(x_t, y_t, "o", color="#111827", ms=4.0, zorder=8)
            ax_t.annotate(
                rf"T-uzel $({x_t:.2f}, {y_t:.2f})$" + "\n" + rf"($r_f={info_m4['t_fillet_r']:.2f}\ \mathrm{{mm}}$)",
                xy=(x_t, y_t), xytext=(x_t + 2.5, y_t + 3.2),
                arrowprops=dict(arrowstyle="->", color="#641E16", lw=1.1),
                fontsize=8.3, fontweight='bold', color="#641E16", ha='left', va='bottom',
                bbox=dict(boxstyle="round,pad=0.2", fc="#FDEDEC", ec="#C0392B", lw=0.7, alpha=0.93), zorder=9
            )

            ax_t.annotate(
                rf"Port $50\ \Omega$ ($w_{{50}}={w50_m4:.2f}\ \mathrm{{mm}}$)" + "\n" + rf"$x_{{\mathrm{{port}}}}={x_p:.2f}\ \mathrm{{mm}}$",
                xy=(x_p, y_t - 0.5 * w50_m4), xytext=(x_p + 0.4, y_t - 7.8),
                arrowprops=dict(arrowstyle="->", color="darkred", lw=1.1),
                fontsize=8.2, fontweight='bold', color="darkred", ha='left', va='top',
                bbox=dict(boxstyle="round,pad=0.2", fc="#FDEDEC", ec="red", lw=0.7, alpha=0.93), zorder=9
            )

            ax_t.annotate(
                rf"Větev $E_y$ ($2$ oblouky)" + "\n" + rf"$R={r_b_m4:.2f}\ \mathrm{{mm}}$, $y_{{\mathrm{{bot}}}}={y_b_arm:.2f}$",
                xy=(x_t + r_b_m4 * 0.45, y_b_arm + r_b_m4 * 0.15),
                xytext=(x_t + r_b_m4 + 1.8, y_t - 6.8),
                arrowprops=dict(arrowstyle="->", color="#0F766E", lw=1.1),
                fontsize=8.2, fontweight='bold', color="#0F766E", ha='left', va='center',
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#0F766E", lw=0.7, alpha=0.93), zorder=9
            )

            ax_t.set_xlabel('X [mm]', fontsize=11, fontweight='bold')
            ax_t.set_ylabel('Y [mm]', fontsize=11, fontweight='bold')
            ax_t.set_title(
                rf"Detail otočeného $50\ \Omega$ T-článku a oblouků ($R={r_b_m4:.1f}\ \mathrm{{mm}}$)" + "\n"
                rf"$w_{{50}}={w50_m4:.2f}\ \mathrm{{mm}}$, $w_{{100}}={wf_m4:.2f}\ \mathrm{{mm}}$, $\Delta L={info_m4['feed_delta_l']:.2f}\ \mathrm{{mm}}$",
                fontsize=11, fontweight='bold', pad=12
            )
            ax_t.grid(True, linestyle=':', alpha=0.6)

    elif model_version == 1:
        _draw_model1_top_view(ax_det, params)
        l2 = float(params.get('l2', 20.0))
        l3 = float(params.get('l3', 10.0))
        l4 = float(params.get('l4', 15.0))
        l5 = float(params.get('l5', 10.0))
        l6 = float(params.get('l6', 18.0))
        inset = float(params.get('inset', params.get('feed_inset', 0.0)))
        x_T = float(params.get('feed_x_T', -(l2 + l3)))
        y_T = float(params.get('feed_y_T', -L / 2.0 + inset - l4))
        y_port = -L_sub / 2.0
        x_min = min(x_T - l5 - 8.0, -W / 2.0 - 5.0)
        x_max = 10.0
        y_min = min(y_T - 10.0, max(y_port - 3.0, y_T - 22.0))
        y_max = max(8.0, y_T + l6 + 5.0)
        ax_det.set_xlim([x_min, x_max])
        ax_det.set_ylim([y_min, y_max])
        ax_det.set_xlabel('X [mm]', fontsize=11, fontweight='bold')
        ax_det.set_ylabel('Y [mm]', fontsize=11, fontweight='bold')
        ax_det.set_title("Detail napájecí sítě s T-děličem a vstupů do flíčku (rovina XY)", fontsize=11, fontweight='bold')
        ax_det.grid(True, linestyle=':', alpha=0.6)

    else:
        # Fallback detail pro Model 2
        _draw_model2_top_view(ax_det, params)
        ax_det.set_xlim([-15, 15])
        ax_det.set_ylim([-25, 10])
        ax_det.set_title("Detail přívodu a vstupu do flíčku (rovina XY)", fontsize=11, fontweight='bold')
        ax_det.grid(True, linestyle=':', alpha=0.6)

    plt.tight_layout()
    p_detail = os.path.join(obrazky_dir, "geometrie_detail_transformatoru.png")
    plt.savefig(p_detail, dpi=250)
    plt.close(fig_det)
    print(f"Detail transformátoru a zářezu byl uložen do: {p_detail}")


if __name__ == "__main__":
    import argparse

    _SRC_DIR = os.path.dirname(os.path.abspath(__file__))
    if _SRC_DIR not in sys.path:
        sys.path.insert(0, _SRC_DIR)
    from postpro_utils import load_env

    parser = argparse.ArgumentParser(description="2D a detailní vizualizace geometrie patch antény")
    parser.add_argument(
        "target_path",
        nargs="?",
        default=None,
        help="Cesta ke složce se simulací, souboru params.json nebo výstupnímu PNG (výchozí: DATA_DIR z .env)",
    )
    args = parser.parse_args()

    _, data_dir = load_env()
    target_path = args.target_path
    loaded_params = {}

    if target_path is None:
        p_json = os.path.join(data_dir, "params.json")
        if os.path.exists(p_json):
            with open(p_json, 'r', encoding='utf-8') as f:
                loaded_params = json.load(f)
        out_png = os.path.join(data_dir, "geometry_iso.png")
    elif os.path.isdir(target_path):
        p_json = os.path.join(target_path, "params.json")
        if os.path.exists(p_json):
            with open(p_json, 'r', encoding='utf-8') as f:
                loaded_params = json.load(f)
        out_png = os.path.join(target_path, "geometry_iso.png")
    elif os.path.isfile(target_path):
        if target_path.endswith(".json"):
            with open(target_path, 'r', encoding='utf-8') as f:
                loaded_params = json.load(f)
            out_png = os.path.join(os.path.dirname(target_path), "geometry_iso.png")
        else:
            out_png = target_path
    else:
        if target_path.lower().endswith(".png"):
            out_png = target_path
        else:
            out_png = os.path.join(data_dir, "geometry_iso.png")

    if not loaded_params:
        loaded_params = {
            'antenna_model': 3,
            'patch_L': 29.95,
            'patch_W': 29.95,
            'sub_h': 1.52,
            'sub_W': 80.0,
            'sub_L': 117.3,
            'w_feed': 0.694,
            'w_T': 0.30,
            'trans_w': 0.30,
            'l_T': 19.0,
            'feed_inset_b': 2.5,
            'feed_inset_l': 2.5,
            'inset_gap_b': 0.5,
            'inset_gap_l': 0.5,
            'y_port': -58.65,
            'x_port': -40.0,
        }

    plot_geometry(loaded_params, filename=out_png)
