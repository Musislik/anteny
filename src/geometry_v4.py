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

from antenna_geometry import (
    calc_curved_path_length,
    compute_curved_ribbon_outline,
    compute_model4_routing,
    compute_t_junction_polygon,
    calc_microstrip_eps_eff,
    calc_quarter_wave_length,
    synth_microstrip_w,
    DESIGN_FREQ_GHZ,
    PORT_Z0,
    COORD_TOL,
)


def _unit_vec(p_from, p_to):
    dx = float(p_to[0] - p_from[0])
    dy = float(p_to[1] - p_from[1])
    length = float(np.hypot(dx, dy))
    if length <= COORD_TOL:
        raise ValueError(f"Segment mezi {p_from} a {p_to} má nulovou délku.")
    return np.array([dx / length, dy / length], dtype=float), length


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
