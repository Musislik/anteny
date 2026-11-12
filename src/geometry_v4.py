"""
geometry_v4.py - Model 4 (Finální model): Dokončení Modelu 3 s otočeným levým 50 Ohm T-článkem a plynulými oblouky.
Architektura:
  - Čtvercový vyzařující flíček L × W s mělkými zářezy (výchozí parametry převzaty z Modelu 3).
  - Vnitřní čtvrtvlnné transformátory (w_T, l_T) převádějící ~140 Ohm flíčku na 100 Ohm.
  - Dvě 100 Ohm mikropáskové větve s plynulými kruhovými oblouky bez meandru (pouze 3 oblouky celkem):
      * Levá větev (Ex, referenční fáze 0°): vedení s 1 obloukem z horního ramene T-článku do levého transformátoru.
      * Spodní větev (Ey, zpoždění -90°): vedení se 2 oblouky ze spodního ramene T-článku do spodního transformátoru,
        kde poloha T-uzlu y_T přirozeně zajišťuje prodloužení dráhy o delta_L ≈ lambda_g/4 oproti levé větvi.
  - Otočený symetrický T-článek (100 Ohm || 100 Ohm = 50 Ohm) s plynulým zaoblením vnitřních rohů.
  - Jediný výstupní 50 Ohm lumped port na levé hraně substrátu (x = -W_sub/2, y = y_T).
"""

import gmsh
import numpy as np

from rf_calc import (
    synth_microstrip_w,
    calc_microstrip_eps_eff,
    calc_quarter_wave_length,
    DESIGN_FREQ_GHZ,
    PORT_Z0,
)

COORD_TOL = 1e-9


def _unit_vec(p_from, p_to):
    dx = float(p_to[0] - p_from[0])
    dy = float(p_to[1] - p_from[1])
    length = float(np.hypot(dx, dy))
    if length <= COORD_TOL:
        raise ValueError(f"Segment mezi {p_from} a {p_to} má nulovou délku.")
    return np.array([dx / length, dy / length], dtype=float), length


def calc_curved_path_length(waypoints, bend_radius):
    """
    Vypočte přesnou délku střednice ortogonální lomené čáry po nahrazení všech 90° rohů
    kruhovými oblouky o poloměru bend_radius.
    """
    pts = [np.asarray(p, dtype=float) for p in waypoints]
    if len(pts) < 2:
        return 0.0

    r = float(bend_radius)
    total_len = 0.0
    n_segs = len(pts) - 1

    for idx in range(n_segs):
        _, seg_len = _unit_vec(pts[idx], pts[idx + 1])
        trim_start = r if idx > 0 else 0.0
        trim_end = r if idx < n_segs - 1 else 0.0
        straight_len = seg_len - trim_start - trim_end
        if straight_len < -1e-7:
            raise ValueError(
                f"Segment {idx} ({pts[idx].tolist()} -> {pts[idx + 1].tolist()}) má délku "
                f"{seg_len:.3f} mm, což nestačí pro oblouky R={r:.3f} mm."
            )
        total_len += max(0.0, straight_len)

    # Každý vnitřní roh přispívá délkou čtvrtkruhu pi * R / 2
    total_len += (len(pts) - 2) * (0.5 * np.pi * r)
    return float(total_len)


def compute_curved_ribbon_outline(waypoints, width, bend_radius, arc_samples=16):
    """
    Vrátí uzavřený 2D obrys [(x, y), ...] pásku o šířce `width` podél `waypoints`
    s plynulými oblouky o poloměru `bend_radius` (pro 2D vizualizaci v Matplotlibu).
    """
    pts = [np.asarray(p, dtype=float) for p in waypoints]
    half_w = float(width) / 2.0
    r = float(bend_radius)
    n_pts = len(pts)

    dirs = []
    norms = []
    for i in range(n_pts - 1):
        u, _ = _unit_vec(pts[i], pts[i + 1])
        dirs.append(u)
        norms.append(np.array([-u[1], u[0]], dtype=float))

    left_pts = [pts[0] + half_w * norms[0]]
    right_pts = [pts[0] - half_w * norms[0]]

    for i in range(1, n_pts - 1):
        u_in = dirs[i - 1]
        u_out = dirs[i]
        n_in = norms[i - 1]
        n_out = norms[i]
        cross = float(u_in[0] * u_out[1] - u_in[1] * u_out[0])
        if abs(abs(cross) - 1.0) > 1e-5:
            raise ValueError(f"Roh {i} není ortogonální (cross={cross:.4f}).")

        c = pts[i] - r * u_in + r * u_out
        a = pts[i] - r * u_in
        b = pts[i] + r * u_out

        l_in = a + half_w * n_in
        l_out = b + half_w * n_out
        r_in = a - half_w * n_in
        r_out = b - half_w * n_out

        # Vzorkování oblouku pro levou a pravou hranu
        for rail_list, p_start, p_end in (
            (left_pts, l_in, l_out),
            (right_pts, r_in, r_out),
        ):
            v_s = p_start - c
            v_e = p_end - c
            rad = float(np.hypot(v_s[0], v_s[1]))
            ang_s = float(np.arctan2(v_s[1], v_s[0]))
            ang_e = float(np.arctan2(v_e[1], v_e[0]))
            d_ang = ang_e - ang_s
            while d_ang > np.pi:
                d_ang -= 2.0 * np.pi
            while d_ang < -np.pi:
                d_ang += 2.0 * np.pi
            for t in np.linspace(0.0, 1.0, arc_samples + 1):
                ang = ang_s + t * d_ang
                rail_list.append(c + rad * np.array([np.cos(ang), np.sin(ang)]))

    left_pts.append(pts[-1] + half_w * norms[-1])
    right_pts.append(pts[-1] - half_w * norms[-1])

    outline = left_pts + list(reversed(right_pts))
    return [(float(p[0]), float(p[1])) for p in outline]


def build_curved_trace_occ(waypoints, width, bend_radius, z):
    """
    Vytvoří jednu spojitou 2D plochu v OpenCASCADE (gmsh.model.occ) podél ortogonálních
    `waypoints` o šířce `width`, kde každý 90° ohyb má soustředné kruhové oblouky
    (vnitřní poloměr `R - w/2`, vnější `R + w/2`).
    """
    pts = [np.asarray(p, dtype=float) for p in waypoints]
    half_w = float(width) / 2.0
    r = float(bend_radius)
    if r <= half_w + 1e-4:
        raise ValueError(f"Poloměr oblouku bend_radius={r:.3f} mm musí být větší než polovina šířky vedení ({half_w:.3f} mm).")

    n_pts = len(pts)
    dirs = []
    norms = []
    for i in range(n_pts - 1):
        u, seg_len = _unit_vec(pts[i], pts[i + 1])
        trim_s = r if i > 0 else 0.0
        trim_e = r if i < n_pts - 2 else 0.0
        if seg_len - trim_s - trim_e < -1e-7:
            raise ValueError(
                f"Segment {i} je příliš krátký ({seg_len:.3f} mm) pro poloměr oblouku R={r:.3f} mm."
            )
        dirs.append(u)
        norms.append(np.array([-u[1], u[0]], dtype=float))

    def _add_pt(xy):
        return gmsh.model.occ.addPoint(float(xy[0]), float(xy[1]), float(z))

    def _add_line_if_needed(p_tag_a, xy_a, p_tag_b, xy_b, curves_out):
        if float(np.hypot(xy_b[0] - xy_a[0], xy_b[1] - xy_a[1])) > COORD_TOL:
            curves_out.append(gmsh.model.occ.addLine(p_tag_a, p_tag_b))
            return p_tag_b
        return p_tag_a

    # Sestavení uzlů a křivek levé a pravé hrany pásku
    l_start_xy = pts[0] + half_w * norms[0]
    r_start_xy = pts[0] - half_w * norms[0]
    l_start_tag = _add_pt(l_start_xy)
    r_start_tag = _add_pt(r_start_xy)

    left_curves = []
    right_segments = []  # (kind, args) pro zpětné sestavení smyčky

    curr_l_tag, curr_l_xy = l_start_tag, l_start_xy
    curr_r_tag, curr_r_xy = r_start_tag, r_start_xy

    for i in range(1, n_pts - 1):
        u_in = dirs[i - 1]
        u_out = dirs[i]
        n_in = norms[i - 1]
        n_out = norms[i]
        cross = float(u_in[0] * u_out[1] - u_in[1] * u_out[0])
        if abs(abs(cross) - 1.0) > 1e-5:
            raise ValueError(f"Roh {i} není ortogonální (cross={cross:.4f}).")

        c_xy = pts[i] - r * u_in + r * u_out
        c_tag = _add_pt(c_xy)
        a_xy = pts[i] - r * u_in
        b_xy = pts[i] + r * u_out

        l_in_xy = a_xy + half_w * n_in
        l_out_xy = b_xy + half_w * n_out
        r_in_xy = a_xy - half_w * n_in
        r_out_xy = b_xy - half_w * n_out

        # Levá hrana: rovný úsek -> oblouk
        if float(np.hypot(l_in_xy[0] - curr_l_xy[0], l_in_xy[1] - curr_l_xy[1])) > COORD_TOL:
            l_in_tag = _add_pt(l_in_xy)
            left_curves.append(gmsh.model.occ.addLine(curr_l_tag, l_in_tag))
        else:
            l_in_tag = curr_l_tag
        l_out_tag = _add_pt(l_out_xy)
        left_curves.append(gmsh.model.occ.addCircleArc(l_in_tag, c_tag, l_out_tag))
        curr_l_tag, curr_l_xy = l_out_tag, l_out_xy

        # Pravá hrana: zapíšeme pro pozpátku jdoucí smyčku
        if float(np.hypot(r_in_xy[0] - curr_r_xy[0], r_in_xy[1] - curr_r_xy[1])) > COORD_TOL:
            r_in_tag = _add_pt(r_in_xy)
            right_segments.append(("line", curr_r_tag, r_in_tag))
        else:
            r_in_tag = curr_r_tag
        r_out_tag = _add_pt(r_out_xy)
        right_segments.append(("arc", r_in_tag, c_tag, r_out_tag))
        curr_r_tag, curr_r_xy = r_out_tag, r_out_xy

    l_end_xy = pts[-1] + half_w * norms[-1]
    r_end_xy = pts[-1] - half_w * norms[-1]
    l_end_tag = _add_pt(l_end_xy)
    r_end_tag = _add_pt(r_end_xy)

    curr_l_tag = _add_line_if_needed(curr_l_tag, curr_l_xy, l_end_tag, l_end_xy, left_curves)
    end_cap = gmsh.model.occ.addLine(curr_l_tag, r_end_tag)

    right_curves_rev = []
    if float(np.hypot(r_end_xy[0] - curr_r_xy[0], r_end_xy[1] - curr_r_xy[1])) > COORD_TOL:
        right_curves_rev.append(gmsh.model.occ.addLine(r_end_tag, curr_r_tag))
    for seg in reversed(right_segments):
        if seg[0] == "line":
            _, t_a, t_b = seg
            right_curves_rev.append(gmsh.model.occ.addLine(t_b, t_a))
        else:
            _, t_in, t_c, t_out = seg
            right_curves_rev.append(gmsh.model.occ.addCircleArc(t_out, t_c, t_in))

    start_cap = gmsh.model.occ.addLine(r_start_tag, l_start_tag)
    loop_curves = left_curves + [end_cap] + right_curves_rev + [start_cap]
    cl = gmsh.model.occ.addCurveLoop(loop_curves)
    return gmsh.model.occ.addPlaneSurface([cl])


def build_t_junction_trunk_occ(x_port, x_T, y_T, w_50, w_feed, t_fillet_r, z):
    """
    Vytvoří plochu vodorovného 50 Ohm přívodního kmene z levého portu (x_port, y_T)
    doprava k otočené svislé příčce T-článku na x_T ([x_T - hw_f, x_T + hw_f],
    y in [y_T - d_t, y_T + d_t], kde d_t = w_50/2 + t_fillet_r), s plynulými
    vnitřními kruhovými zaobleními (pokud t_fillet_r > 0).
    """
    hw_50 = float(w_50) / 2.0
    hw_f = float(w_feed) / 2.0
    r_f = float(t_fillet_r)
    d_t = hw_50 + r_f

    x_left = float(x_port)
    y_center = float(y_T)
    x_bar_left = float(x_T) - hw_f
    x_bar_right = float(x_T) + hw_f

    if r_f <= 1e-6:
        trunk_rect = gmsh.model.occ.addRectangle(
            x_left, y_center - hw_50, z, x_bar_right - x_left, float(w_50)
        )
        return trunk_rect, d_t

    x_fillet_start = x_bar_left - r_f
    if x_fillet_start <= x_left + 1e-4:
        raise ValueError(
            f"Délka 50 Ohm vedení (x_bar_left - x_port = {x_bar_left - x_left:.2f} mm) "
            f"nestačí pro zaoblení T-článku r={r_f:.2f} mm."
        )

    p_bl = gmsh.model.occ.addPoint(x_left, y_center - hw_50, z)
    p_bf_s = gmsh.model.occ.addPoint(x_fillet_start, y_center - hw_50, z)
    p_bc = gmsh.model.occ.addPoint(x_fillet_start, y_center - d_t, z)
    p_bf_e = gmsh.model.occ.addPoint(x_bar_left, y_center - d_t, z)
    p_br = gmsh.model.occ.addPoint(x_bar_right, y_center - d_t, z)
    p_tr = gmsh.model.occ.addPoint(x_bar_right, y_center + d_t, z)
    p_tf_e = gmsh.model.occ.addPoint(x_bar_left, y_center + d_t, z)
    p_tc = gmsh.model.occ.addPoint(x_fillet_start, y_center + d_t, z)
    p_tf_s = gmsh.model.occ.addPoint(x_fillet_start, y_center + hw_50, z)
    p_tl = gmsh.model.occ.addPoint(x_left, y_center + hw_50, z)

    curves = [
        gmsh.model.occ.addLine(p_bl, p_bf_s),
        gmsh.model.occ.addCircleArc(p_bf_s, p_bc, p_bf_e),
        gmsh.model.occ.addLine(p_bf_e, p_br),
        gmsh.model.occ.addLine(p_br, p_tr),
        gmsh.model.occ.addLine(p_tr, p_tf_e),
        gmsh.model.occ.addCircleArc(p_tf_e, p_tc, p_tf_s),
        gmsh.model.occ.addLine(p_tf_s, p_tl),
        gmsh.model.occ.addLine(p_tl, p_bl),
    ]
    cl = gmsh.model.occ.addCurveLoop(curves)
    return gmsh.model.occ.addPlaneSurface([cl]), d_t


def compute_model4_routing(params):
    """
    Vypočte veškeré RF a geometrické souřadnice finálního Modelu 4 (bez spuštění Gmsh),
    včetně přesných trasovacích bodů (waypoints) obou zakřivených 100 Ohm větví.
    """
    L = float(params['patch_L'])
    W = float(params.get('patch_W', L))
    h = float(params['sub_h'])
    eps_r = float(params['eps_r'])
    f_design = float(params.get('design_freq_ghz', DESIGN_FREQ_GHZ))
    port_z0 = float(params.get('port_impedance', PORT_Z0))

    # 1. Šířky 50 Ohm přívodu a 100 Ohm větví děliče
    raw_w_50 = next((params[k] for k in ('feed_50_w', 'w_50', 'w1') if params.get(k) is not None), None)
    w_50 = float(raw_w_50) if raw_w_50 is not None else synth_microstrip_w(port_z0, h, eps_r)

    raw_w_100 = next(
        (params[k] for k in ('feed_100_w', 'w_feed', 'w_100', 'w2') if params.get(k) is not None),
        None,
    )
    w_feed = float(raw_w_100) if raw_w_100 is not None else synth_microstrip_w(2.0 * port_z0, h, eps_r)

    eps_eff_feed = calc_microstrip_eps_eff(w_feed, h, eps_r)
    lambda_g_4_feed = calc_quarter_wave_length(f_design, eps_eff_feed)

    # 2. Parametry čtvrtvlnného transformátoru (převzato z Modelu 3)
    w_T_default = float(params.get('trans_w', params.get('w_T', params.get('w_trans', 0.42))))
    eps_eff_trans_def = calc_microstrip_eps_eff(w_T_default, h, eps_r)
    l_T_default = calc_quarter_wave_length(f_design, eps_eff_trans_def)

    w_T_b = float(params.get('trans_w_b', params.get('w_T_b', params.get('w_trans_b', w_T_default))))
    w_T_l = float(params.get('trans_w_l', params.get('w_T_l', params.get('w_trans_l', w_T_default))))

    raw_l_T_b = next((params[k] for k in ('trans_l_b', 'l_T_b', 'l_trans_b') if params.get(k) is not None), None)
    raw_l_T_l = next((params[k] for k in ('trans_l_l', 'l_T_l', 'l_trans_l') if params.get(k) is not None), None)
    raw_l_T_common = next((params[k] for k in ('trans_l', 'l_T', 'l_trans') if params.get(k) is not None), None)

    def _resolve_branch_trans_l(raw_branch, w_branch):
        if raw_branch is not None:
            return float(raw_branch)
        if raw_l_T_common is not None:
            return float(raw_l_T_common)
        eps_eff_branch = calc_microstrip_eps_eff(w_branch, h, eps_r)
        return calc_quarter_wave_length(f_design, eps_eff_branch)

    l_T_b = _resolve_branch_trans_l(raw_l_T_b, w_T_b)
    l_T_l = _resolve_branch_trans_l(raw_l_T_l, w_T_l)
    resolved_trans_l = (
        float(raw_l_T_common)
        if raw_l_T_common is not None
        else (l_T_b if abs(l_T_b - l_T_l) < 1e-9 else l_T_default)
    )

    # 3. Mělký zářez a mezery (převzato z Modelu 3)
    inset_b = float(params.get('feed_inset_b', params.get('inset_b', params.get('y0b', params.get('y0', params.get('feed_inset', 2.5))))))
    inset_l = float(params.get('feed_inset_l', params.get('inset_l', params.get('y0l', params.get('y0', params.get('feed_inset', 2.5))))))
    if inset_b < 0.0 or inset_l < 0.0:
        raise ValueError(f"Hloubka zanoření (inset) musí být nezáporná: inset_b={inset_b}, inset_l={inset_l}")

    inset_gap_b = float(params.get('inset_gap_b', params.get('feed_inset_gap_b', params.get('gap_b', params.get('inset_gap', params.get('feed_inset_gap', 0.5))))))
    inset_gap_l = float(params.get('inset_gap_l', params.get('feed_inset_gap_l', params.get('gap_l', params.get('inset_gap', params.get('feed_inset_gap', 0.5))))))

    # 4. Fázovací prodloužení delta_L v 100 Ohm vedení
    raw_delta_l = params.get('feed_delta_l', params.get('delta_l', params.get('phase_delay_mm', params.get('feed_delta'))))
    feed_delta_l = float(raw_delta_l) if raw_delta_l is not None else lambda_g_4_feed

    # 5. Parametry oblouků a otočeného levého T-článku (parametrizováno do .env)
    bend_radius = float(params.get('feed_bend_radius', params.get('bend_radius', 3.0)))
    if bend_radius <= (w_feed / 2.0) + 0.1:
        raise ValueError(
            f"Poloměr oblouku feed_bend_radius={bend_radius:.3f} mm musí být větší než w_feed/2 + 0.1 ({w_feed/2.0 + 0.1:.3f} mm)."
        )

    t_fillet_r = float(params.get('feed_t_fillet_r', params.get('t_fillet_r', 0.8)))
    if t_fillet_r < 0.0:
        raise ValueError(f"Poloměr zaoblení T-článku feed_t_fillet_r={t_fillet_r:.3f} mm musí být nezáporný.")

    raw_feed_50_len = next((params[k] for k in ('feed_50_len', 'l1') if params.get(k) is not None), None)
    feed_50_len = float(raw_feed_50_len) if raw_feed_50_len is not None else 9.0
    if feed_50_len <= t_fillet_r + 0.5:
        raise ValueError(
            f"Délka 50 Ohm přívodu feed_50_len={feed_50_len:.2f} mm musí být > feed_t_fillet_r + 0.5 ({t_fillet_r + 0.5:.2f} mm)."
        )

    raw_end_straight = next((params[k] for k in ('feed_end_straight', 'end_straight') if params.get(k) is not None), None)
    end_straight = float(raw_end_straight) if raw_end_straight is not None else 4.6
    if end_straight < 0.5:
        raise ValueError(f"Koncový rovný úsek feed_end_straight={end_straight:.2f} mm musí být >= 0.5 mm.")

    raw_arm_offset = next((params[k] for k in ('feed_arm_offset', 'arm_offset') if params.get(k) is not None), None)
    if raw_arm_offset is not None:
        arm_offset = float(raw_arm_offset)
        if arm_offset <= bend_radius + 0.5:
            raise ValueError(
                f"Odsazení levého ramene feed_arm_offset={arm_offset:.2f} mm musí být > feed_bend_radius + 0.5 ({bend_radius + 0.5:.2f} mm)."
            )
    else:
        arm_offset = end_straight + bend_radius

    raw_sub_margin = params.get('sub_margin')
    sub_margin = float(raw_sub_margin) if raw_sub_margin is not None else max(8.0, 5.0 * h)

    # 6. Pozice vstupů transformátorů a vnějších referenčních os větví
    y_junc_b = -L / 2.0 + inset_b - l_T_b
    x_junc_l = -W / 2.0 + inset_l - l_T_l
    x_left_vert = x_junc_l - arm_offset
    y_bot_default = y_junc_b - end_straight - bend_radius

    # 7. Poloha otočeného T-článku (x_T, y_T)
    d_t = (w_50 / 2.0) + t_fillet_r
    raw_x_T = params.get('feed_x_T', params.get('x_T'))
    x_T = float(raw_x_T) if raw_x_T is not None else x_left_vert

    s_end_l = x_junc_l - x_T - bend_radius
    if s_end_l < 0.5 - 1e-6:
        raise ValueError(
            f"Poloha T-uzlu x_T={x_T:.2f} mm nedává prostor pro oblouk R={bend_radius:.2f} mm před levým "
            f"transformátorem x_junc_l={x_junc_l:.2f} mm (rovný úsek {s_end_l:.2f} mm < 0.5 mm)."
        )

    s_horiz_b = -x_T - 2.0 * bend_radius
    if s_horiz_b < -1e-6:
        raise ValueError(
            f"Vodorovný úsek spodní větve (-x_T = {-x_T:.2f} mm) nestačí pro dva oblouky R={bend_radius:.2f} mm "
            f"(-x_T - 2*R = {s_horiz_b:.2f} mm < 0)."
        )

    raw_y_T = params.get('feed_y_T', params.get('y_T'))
    if raw_y_T is None:
        y_bot = y_bot_default
        # Analytické řešení rovnice L_100_b(y_T) - L_100_l(y_T) == feed_delta_l (bez meandru)
        y_T = 0.5 * (
            feed_delta_l
            + 2.0 * y_bot
            - y_junc_b
            + x_junc_l
            - (0.5 * np.pi - 2.0) * bend_radius
        )
    else:
        y_T = float(raw_y_T)
        y_bot = y_T - 0.5 * (
            feed_delta_l
            - y_junc_b
            + x_junc_l
            - (0.5 * np.pi - 2.0) * bend_radius
        )
        s_end_b_check = y_junc_b - y_bot - bend_radius
        if s_end_b_check < end_straight - 1e-6:
            raise ValueError(
                f"Zadané feed_y_T={y_T:.2f} mm vyžaduje y_bot={y_bot:.2f} mm pro fázování ΔL={feed_delta_l:.2f} mm, "
                f"což zkracuje úsek před spodním transformátorem na {s_end_b_check:.2f} mm (< {end_straight:.2f} mm)."
            )

    s_end_b = y_junc_b - y_bot - bend_radius
    s_T_up = -y_T - d_t - bend_radius
    if s_T_up < 0.5 - 1e-6:
        raise ValueError(
            f"Horní rovný úsek za blokem T-článku s_T_up={s_T_up:.2f} mm (y_T={y_T:.2f} mm, d_t={d_t:.2f} mm, "
            f"R={bend_radius:.2f} mm) musí být >= 0.5 mm (a y_T musí ležet pod osou y=0)."
        )

    s_T_down = (y_T - y_bot) - d_t - bend_radius
    if s_T_down < 0.5 - 1e-6:
        raise ValueError(
            f"Dolní rovný úsek za blokem T-článku s_T_down={s_T_down:.2f} mm (y_T={y_T:.2f} mm, y_bot={y_bot:.2f} mm, "
            f"d_t={d_t:.2f} mm, R={bend_radius:.2f} mm) musí být >= 0.5 mm."
        )

    # 8. Přesné střednicové trasy (waypoints) od osy T-článku (x_T, y_T) k transformátorům
    arm_l_waypoints_full = [
        (x_T, y_T),
        (x_T, 0.0),
        (x_junc_l, 0.0),
    ]
    L_100_l = calc_curved_path_length(arm_l_waypoints_full, bend_radius)

    arm_b_waypoints_full = [
        (x_T, y_T),
        (x_T, y_bot),
        (0.0, y_bot),
        (0.0, y_junc_b),
    ]
    L_100_b = calc_curved_path_length(arm_b_waypoints_full, bend_radius)

    # Stavební waypoints navazující bez překryvu na blok T-článku (y_T ± d_t)
    arm_l_build_waypoints = [(x_T, y_T + d_t)] + arm_l_waypoints_full[1:]
    arm_b_build_waypoints = [(x_T, y_T - d_t)] + arm_b_waypoints_full[1:]

    # 9. Poloha levého 50 Ohm portu a symetrické rozměry substrátu kolem (0, 0)
    x_port_base = x_T - (w_feed / 2.0) - feed_50_len
    min_W_sub = 2.0 * max(abs(x_port_base), W / 2.0 + sub_margin)
    min_L_sub = 2.0 * max(abs(y_bot) + w_feed / 2.0 + sub_margin, L / 2.0 + sub_margin)

    raw_W_sub = params.get('sub_W', params.get('sub_w'))
    raw_L_sub = params.get('sub_L', params.get('sub_l'))

    W_sub = max(float(raw_W_sub), min_W_sub) if raw_W_sub is not None else min_W_sub
    L_sub = max(float(raw_L_sub), min_L_sub) if raw_L_sub is not None else min_L_sub

    x_port = -W_sub / 2.0
    y_port = y_T
    effective_feed_50_len = (x_T - w_feed / 2.0) - x_port

    return {
        'L': L,
        'W': W,
        'h': h,
        'eps_r': eps_r,
        'f_design': f_design,
        'port_z0': port_z0,
        'w_50': w_50,
        'w_feed': w_feed,
        'eps_eff_feed': eps_eff_feed,
        'lambda_g_4_feed': lambda_g_4_feed,
        'w_T_default': w_T_default,
        'w_T_b': w_T_b,
        'w_T_l': w_T_l,
        'l_T_b': l_T_b,
        'l_T_l': l_T_l,
        'resolved_trans_l': resolved_trans_l,
        'inset_b': inset_b,
        'inset_l': inset_l,
        'inset_gap_b': inset_gap_b,
        'inset_gap_l': inset_gap_l,
        'feed_delta_l': feed_delta_l,
        'bend_radius': bend_radius,
        't_fillet_r': t_fillet_r,
        'd_t': d_t,
        'feed_50_len': effective_feed_50_len,
        'arm_offset': arm_offset,
        'end_straight': end_straight,
        'sub_margin': sub_margin,
        's_end_l': s_end_l,
        's_end_b': s_end_b,
        's_T_up': s_T_up,
        's_T_down': s_T_down,
        's_horiz_b': s_horiz_b,
        'x_junc_l': x_junc_l,
        'y_junc_b': y_junc_b,
        'x_left_vert': x_left_vert,
        'y_bot': y_bot,
        'x_T': x_T,
        'y_T': y_T,
        'x_port': x_port,
        'y_port': y_port,
        'W_sub': W_sub,
        'L_sub': L_sub,
        'L_100_l': L_100_l,
        'L_100_b': L_100_b,
        'arm_l_waypoints': [(float(round(p[0], 4)), float(round(p[1], 4))) for p in arm_l_waypoints_full],
        'arm_b_waypoints': [(float(round(p[0], 4)), float(round(p[1], 4))) for p in arm_b_waypoints_full],
        'arm_l_build_waypoints': arm_l_build_waypoints,
        'arm_b_build_waypoints': arm_b_build_waypoints,
    }


def build_model_v4(params):
    """
    Vytvoří 3D CAD model finálního Modelu 4 v OpenCASCADE a připraví entity pro síťování.
    """
    info = compute_model4_routing(params)

    L = info['L']
    W = info['W']
    h = info['h']
    margin = float(params['air_margin'])

    w_50 = info['w_50']
    w_feed = info['w_feed']
    w_T_b = info['w_T_b']
    w_T_l = info['w_T_l']
    l_T_b = info['l_T_b']
    l_T_l = info['l_T_l']
    inset_b = info['inset_b']
    inset_l = info['inset_l']
    inset_gap_b = info['inset_gap_b']
    inset_gap_l = info['inset_gap_l']
    bend_radius = info['bend_radius']
    t_fillet_r = info['t_fillet_r']
    x_T = info['x_T']
    y_T = info['y_T']
    x_port = info['x_port']
    y_port = info['y_port']
    W_sub = info['W_sub']
    L_sub = info['L_sub']
    y_junc_b = info['y_junc_b']
    x_junc_l = info['x_junc_l']

    # Uložení vypočtených parametrů zpět do params
    params['antenna_model'] = 4
    params['w_50'] = float(np.round(w_50, 4))
    params['feed_50_w'] = params['w_50']
    params['port_w'] = params['w_50']
    params['w1'] = params['w_50']

    params['w_feed'] = float(np.round(w_feed, 4))
    params['feed_100_w'] = params['w_feed']
    params['feed_W'] = params['w_50']
    params['w2'] = params['w_feed']
    params['w3'] = params['w_feed']

    params['trans_w'] = float(np.round(info['w_T_default'], 4))
    params['w_T'] = params['trans_w']
    params['w_trans'] = params['trans_w']
    params['trans_w_b'] = float(np.round(w_T_b, 4))
    params['trans_w_l'] = float(np.round(w_T_l, 4))
    params['w_T_b'] = params['trans_w_b']
    params['w_T_l'] = params['trans_w_l']

    params['trans_l'] = float(np.round(info['resolved_trans_l'], 4))
    params['l_T'] = params['trans_l']
    params['l_trans'] = params['trans_l']
    params['trans_l_b'] = float(np.round(l_T_b, 4))
    params['trans_l_l'] = float(np.round(l_T_l, 4))
    params['l_T_b'] = params['trans_l_b']
    params['l_T_l'] = params['trans_l_l']

    params['feed_inset_b'] = float(np.round(inset_b, 3))
    params['feed_inset_l'] = float(np.round(inset_l, 3))
    params['inset_b'] = params['feed_inset_b']
    params['inset_l'] = params['feed_inset_l']
    params['y0b'] = params['feed_inset_b']
    params['y0l'] = params['feed_inset_l']

    params['feed_inset_gap_b'] = float(np.round(inset_gap_b, 3))
    params['feed_inset_gap_l'] = float(np.round(inset_gap_l, 3))
    params['inset_gap_b'] = params['feed_inset_gap_b']
    params['inset_gap_l'] = params['feed_inset_gap_l']

    params['feed_delta_l'] = float(np.round(info['feed_delta_l'], 4))
    params['delta_l'] = params['feed_delta_l']
    params['phase_delay_mm'] = params['feed_delta_l']

    params['feed_bend_radius'] = float(np.round(bend_radius, 3))
    params['bend_radius'] = params['feed_bend_radius']
    params['feed_t_fillet_r'] = float(np.round(t_fillet_r, 3))
    params['t_fillet_r'] = params['feed_t_fillet_r']
    params['feed_50_len'] = float(np.round(info['feed_50_len'], 3))
    params['feed_arm_offset'] = float(np.round(info['arm_offset'], 3))
    params['feed_end_straight'] = float(np.round(info['end_straight'], 3))
    params['sub_margin'] = float(np.round(info['sub_margin'], 3))

    params['L_100_b'] = float(np.round(info['L_100_b'], 4))
    params['L_100_l'] = float(np.round(info['L_100_l'], 4))
    params['feed_len_b'] = float(np.round(l_T_b + info['L_100_b'], 4))
    params['feed_len_l'] = float(np.round(l_T_l + info['L_100_l'], 4))

    params['feed_x_T'] = float(np.round(x_T, 4))
    params['feed_y_T'] = float(np.round(y_T, 4))
    params['x_port'] = float(np.round(x_port, 4))
    params['y_port'] = float(np.round(y_port, 4))
    params['port_x'] = params['x_port']
    params['port_y'] = params['y_port']
    params['y_bot'] = float(np.round(info['y_bot'], 4))
    params['x_left_vert'] = float(np.round(info['x_left_vert'], 4))

    params['sub_W'] = float(np.round(W_sub, 3))
    params['sub_w'] = params['sub_W']
    params['sub_L'] = float(np.round(L_sub, 3))
    params['sub_l'] = params['sub_L']
    params['lambda_g_4_feed'] = float(np.round(info['lambda_g_4_feed'], 3))
    params['arm_l_waypoints'] = info['arm_l_waypoints']
    params['arm_b_waypoints'] = info['arm_b_waypoints']

    # 1. Inicializace Gmsh a základní objemy (Substrát a Vzduchový box)
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1)
    gmsh.model.add("lhcp_antenna_model4")

    sub_tag = gmsh.model.occ.addBox(-W_sub / 2.0, -L_sub / 2.0, 0.0, W_sub, L_sub, h)
    air_tag = gmsh.model.occ.addBox(
        -W_sub / 2.0 - margin,
        -L_sub / 2.0 - margin,
        -margin,
        W_sub + 2.0 * margin,
        L_sub + 2.0 * margin,
        h + 2.0 * margin,
    )

    # 2. Vyzařující flíček s mělkými zářezy na z = h
    patch_base = gmsh.model.occ.addRectangle(-W / 2.0, -L / 2.0, h, W, L)
    tool_notches = []
    if inset_b > 0.0:
        notch_b_w = w_T_b + 2.0 * inset_gap_b
        notch_b = gmsh.model.occ.addRectangle(-notch_b_w / 2.0, -L / 2.0 - 0.05, h, notch_b_w, inset_b + 0.05)
        tool_notches.append((2, notch_b))
    if inset_l > 0.0:
        notch_l_h = w_T_l + 2.0 * inset_gap_l
        notch_l = gmsh.model.occ.addRectangle(-W / 2.0 - 0.05, -notch_l_h / 2.0, h, inset_l + 0.05, notch_l_h)
        tool_notches.append((2, notch_l))

    if tool_notches:
        cut_surfs, _ = gmsh.model.occ.cut([(2, patch_base)], tool_notches)
        patch_tag = cut_surfs[0][1]
    else:
        patch_tag = patch_base

    # 3. Čtvrtvlnné transformátory u flíčku (z = h)
    trans_b = gmsh.model.occ.addRectangle(-w_T_b / 2.0, y_junc_b, h, w_T_b, l_T_b)
    trans_l = gmsh.model.occ.addRectangle(x_junc_l, -w_T_l / 2.0, h, l_T_l, w_T_l)

    # 4. Zakřivená 100 Ohm vedení a otočený 50 Ohm T-článek (sloučeno bez překryvů přes occ.fuse)
    trunk_tag, _ = build_t_junction_trunk_occ(x_port, x_T, y_T, w_50, w_feed, t_fillet_r, h)
    arm_l_tag = build_curved_trace_occ(info['arm_l_build_waypoints'], w_feed, bend_radius, h)
    arm_b_tag = build_curved_trace_occ(info['arm_b_build_waypoints'], w_feed, bend_radius, h)

    fused_feed, _ = gmsh.model.occ.fuse([(2, trunk_tag)], [(2, arm_l_tag), (2, arm_b_tag)])
    feed_net_tags = [tag for dim, tag in fused_feed if dim == 2]

    metal_surfs = [patch_tag, trans_b, trans_l] + feed_net_tags
    gmsh.model.occ.synchronize()

    # 5. Výstupní 50 Ohm lumped port (YZ rovina na levé hraně substrátu x = x_port)
    p1 = gmsh.model.occ.addPoint(x_port, y_T - w_50 / 2.0, 0.0)
    p2 = gmsh.model.occ.addPoint(x_port, y_T + w_50 / 2.0, 0.0)
    p3 = gmsh.model.occ.addPoint(x_port, y_T + w_50 / 2.0, h)
    p4 = gmsh.model.occ.addPoint(x_port, y_T - w_50 / 2.0, h)
    l1 = gmsh.model.occ.addLine(p1, p2)
    l2 = gmsh.model.occ.addLine(p2, p3)
    l3 = gmsh.model.occ.addLine(p3, p4)
    l4 = gmsh.model.occ.addLine(p4, p1)
    cl = gmsh.model.occ.addCurveLoop([l1, l2, l3, l4])
    port_tag = gmsh.model.occ.addPlaneSurface([cl])

    # 6. Zemní plocha GND (z = 0)
    gnd_tag = gmsh.model.occ.addRectangle(-W_sub / 2.0, -L_sub / 2.0, 0.0, W_sub, L_sub)

    gmsh.model.occ.synchronize()

    # 7. Konformní fúze objemů a ploch (Boolean Fragments)
    vols = gmsh.model.occ.getEntities(3)
    input_surfs = [(2, s) for s in metal_surfs] + [(2, gnd_tag), (2, port_tag)]

    _, out_map = gmsh.model.occ.fragment(vols, input_surfs)
    gmsh.model.occ.synchronize()

    pec_tags = []
    port_tags = []
    for idx, (_, s_tag) in enumerate(input_surfs):
        frag_entities = out_map[len(vols) + idx]
        frag_tags = [tag for d, tag in frag_entities if d == 2]
        if s_tag == port_tag:
            port_tags.extend(frag_tags)
        else:
            pec_tags.extend(frag_tags)

    params['port_tags'] = list(set(port_tags))
    params['pec_tags'] = list(set(pec_tags))

    return sub_tag, air_tag


build_model = build_model_v4
