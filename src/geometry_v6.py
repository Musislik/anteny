"""
geometry_v6.py - Model 6: Two-port model with two independent 100 Ohm internal ports
directly at the ends of the curved branches (derived from Model 4).

Architecture:
  - Removed 50 Ohm feed trunk and T-junction.
  - Both 100 Ohm feed branches have IDENTICAL routing to Model 4
    (they stay on x = x_T and do not turn out to the substrate edge).
  - Directly at the ends of both branches, two internal 100 Ohm lumped ports are created:
      * Port 1 (bottom branch, Ey field, Delta L phasing): vertical surface in XZ plane at y = y_T - d_t,
        x in [x_T - w_feed/2, x_T + w_feed/2], z in [0, h], Tag 4, Direction "+Z", R = 100 Ohm.
      * Port 2 (left branch, Ex field, reference phase 0 deg): vertical surface in XZ plane at y = y_T + d_t,
        x in [x_T - w_feed/2, x_T + w_feed/2], z in [0, h], Tag 6, Direction "+Z", R = 100 Ohm.
  - Branch length difference strictly satisfies (L_100_b - d_t) - (L_100_l - d_t) == feed_delta_l.
  - Substrate retains dimensions from Model 4.
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
from geometry_v4 import (
    calc_curved_path_length,
    compute_curved_ribbon_outline,
    build_curved_trace_occ,
)

COORD_TOL = 1e-9


def compute_model6_routing(params):
    """
    Compute all RF and geometric coordinates for the two-port Model 6 (without starting Gmsh).
    Based on Model 4, except the feeds terminate at y = y_T ± d_t where the internal ports are placed.
    """
    L = float(params.get('patch_L', 28.8))
    W = float(params.get('patch_W', L))
    h = float(params.get('sub_h', 1.52))
    eps_r = float(params.get('eps_r', 4.3))
    f_design = float(params.get('design_freq_ghz', DESIGN_FREQ_GHZ))
    port_z0 = float(params.get('port_impedance', 100.0))

    # 1. Widths of 50 Ohm reference (for d_t and substrate size from Model 4) and 100 Ohm branches
    raw_w_50 = next((params[k] for k in ('feed_50_w', 'w_50', 'w1') if params.get(k) is not None), None)
    w_50 = float(raw_w_50) if raw_w_50 is not None else synth_microstrip_w(PORT_Z0, h, eps_r)

    raw_w_100 = next(
        (params[k] for k in ('feed_100_w', 'w_feed', 'w_100', 'w2') if params.get(k) is not None),
        None,
    )
    w_feed = float(raw_w_100) if raw_w_100 is not None else synth_microstrip_w(port_z0, h, eps_r)

    eps_eff_feed = calc_microstrip_eps_eff(w_feed, h, eps_r)
    lambda_g_4_feed = calc_quarter_wave_length(f_design, eps_eff_feed)

    # 2. Quarter-wave transformer parameters (identical to Model 4 and 3)
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

    # 3. Shallow inset and gaps
    inset_b = float(params.get('feed_inset_b', params.get('inset_b', params.get('y0b', params.get('y0', params.get('feed_inset', 2.5))))))
    inset_l = float(params.get('feed_inset_l', params.get('inset_l', params.get('y0l', params.get('y0', params.get('feed_inset', 2.5))))))
    if inset_b < 0.0 or inset_l < 0.0:
        raise ValueError(f"Inset depth must be non-negative: inset_b={inset_b}, inset_l={inset_l}")

    inset_gap_b = float(params.get('inset_gap_b', params.get('feed_inset_gap_b', params.get('gap_b', params.get('inset_gap', params.get('feed_inset_gap', 0.5))))))
    inset_gap_l = float(params.get('inset_gap_l', params.get('feed_inset_gap_l', params.get('gap_l', params.get('inset_gap', params.get('feed_inset_gap', 0.5))))))

    # 4. Phasing extension delta_L in 100 Ohm line
    raw_delta_l = params.get('feed_delta_l', params.get('delta_l', params.get('phase_delay_mm', params.get('feed_delta'))))
    feed_delta_l = float(raw_delta_l) if raw_delta_l is not None else lambda_g_4_feed

    # 5. Arc and reference T-junction parameters (identical to Model 4)
    bend_radius = float(params.get('feed_bend_radius', params.get('bend_radius', 3.0)))
    if bend_radius <= (w_feed / 2.0) + 0.1:
        raise ValueError(
            f"Arc radius feed_bend_radius={bend_radius:.3f} mm must be greater than w_feed/2 + 0.1 ({w_feed/2.0 + 0.1:.3f} mm)."
        )

    t_fillet_r = float(params.get('feed_t_fillet_r', params.get('t_fillet_r', 0.8)))
    if t_fillet_r < 0.0:
        raise ValueError(f"Fillet radius feed_t_fillet_r={t_fillet_r:.3f} mm must be non-negative.")

    raw_feed_50_len = next((params[k] for k in ('feed_50_len', 'l1') if params.get(k) is not None), None)
    feed_50_len = float(raw_feed_50_len) if raw_feed_50_len is not None else 9.0

    raw_end_straight = next((params[k] for k in ('feed_end_straight', 'end_straight') if params.get(k) is not None), None)
    end_straight = float(raw_end_straight) if raw_end_straight is not None else 4.6
    if end_straight < 0.5:
        raise ValueError(f"Terminal straight section feed_end_straight={end_straight:.2f} mm must be >= 0.5 mm.")

    raw_arm_offset = next((params[k] for k in ('feed_arm_offset', 'arm_offset') if params.get(k) is not None), None)
    if raw_arm_offset is not None:
        arm_offset = float(raw_arm_offset)
        if arm_offset <= bend_radius + 0.5:
            raise ValueError(
                f"Left arm offset feed_arm_offset={arm_offset:.2f} mm must be > feed_bend_radius + 0.5 ({bend_radius + 0.5:.2f} mm)."
            )
    else:
        arm_offset = end_straight + bend_radius

    raw_sub_margin = params.get('sub_margin')
    sub_margin = float(raw_sub_margin) if raw_sub_margin is not None else max(8.0, 5.0 * h)

    # 6. Transformer entry positions and outer reference branch axes
    y_junc_b = -L / 2.0 + inset_b - l_T_b
    x_junc_l = -W / 2.0 + inset_l - l_T_l
    x_left_vert = x_junc_l - arm_offset
    y_bot_default = y_junc_b - end_straight - bend_radius

    # 7. T-junction position (x_T, y_T) and d_t
    d_t = (w_50 / 2.0) + t_fillet_r
    raw_x_T = params.get('feed_x_T', params.get('x_T'))
    x_T = float(raw_x_T) if raw_x_T is not None else x_left_vert

    s_end_l = x_junc_l - x_T - bend_radius
    if s_end_l < 0.5 - 1e-6:
        raise ValueError(
            f"T-junction position x_T={x_T:.2f} mm leaves insufficient room for arc R={bend_radius:.2f} mm before left "
            f"transformer x_junc_l={x_junc_l:.2f} mm (straight section {s_end_l:.2f} mm < 0.5 mm)."
        )

    s_horiz_b = -x_T - 2.0 * bend_radius
    if s_horiz_b < -1e-6:
        raise ValueError(
            f"Horizontal section of bottom branch (-x_T = {-x_T:.2f} mm) is insufficient for two arcs R={bend_radius:.2f} mm "
            f"(-x_T - 2*R = {s_horiz_b:.2f} mm < 0)."
        )

    raw_y_T = params.get('feed_y_T', params.get('y_T'))
    if raw_y_T is None:
        y_bot = y_bot_default
        # Analytical solution of equation L_100_b(y_T) - L_100_l(y_T) == feed_delta_l
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
                f"Specified feed_y_T={y_T:.2f} mm requires y_bot={y_bot:.2f} mm for phasing ΔL={feed_delta_l:.2f} mm, "
                f"which shortens the section before the bottom transformer to {s_end_b_check:.2f} mm (< {end_straight:.2f} mm)."
            )

    s_end_b = y_junc_b - y_bot - bend_radius
    s_T_up = -y_T - d_t - bend_radius
    if s_T_up < 0.5 - 1e-6:
        raise ValueError(
            f"Upper straight section past port s_T_up={s_T_up:.2f} mm (y_T={y_T:.2f} mm, d_t={d_t:.2f} mm, "
            f"R={bend_radius:.2f} mm) must be >= 0.5 mm."
        )

    s_T_down = (y_T - y_bot) - d_t - bend_radius
    if s_T_down < 0.5 - 1e-6:
        raise ValueError(
            f"Lower straight section past port s_T_down={s_T_down:.2f} mm (y_T={y_T:.2f} mm, y_bot={y_bot:.2f} mm, "
            f"d_t={d_t:.2f} mm, R={bend_radius:.2f} mm) must be >= 0.5 mm."
        )

    # 8. Exact centerline paths from Model 4
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

    # Build waypoints directly from internal ports at (x_T, y_T ± d_t)
    arm_l_build_waypoints = [(x_T, y_T + d_t)] + arm_l_waypoints_full[1:]
    arm_b_build_waypoints = [(x_T, y_T - d_t)] + arm_b_waypoints_full[1:]

    # Physical length of the branches themselves from ports to transformers:
    L_100_l_eff = L_100_l - d_t
    L_100_b_eff = L_100_b - d_t

    # 9. Preserve substrate dimensions exactly from Model 4
    x_port_base = x_T - (w_feed / 2.0) - feed_50_len
    min_W_sub = 2.0 * max(abs(x_port_base), W / 2.0 + sub_margin)
    min_L_sub = 2.0 * max(abs(y_bot) + w_feed / 2.0 + sub_margin, L / 2.0 + sub_margin)

    raw_W_sub = params.get('sub_W', params.get('sub_w'))
    raw_L_sub = params.get('sub_L', params.get('sub_l'))

    W_sub = max(float(raw_W_sub), min_W_sub) if raw_W_sub is not None else min_W_sub
    L_sub = max(float(raw_L_sub), min_L_sub) if raw_L_sub is not None else min_L_sub

    # Port positions (XZ internal surfaces)
    port1_x = x_T
    port1_y = y_T - d_t
    port2_x = x_T
    port2_y = y_T + d_t

    # Reference x_port from Model 4 (for compatibility / export)
    x_port = -W_sub / 2.0
    y_port = y_T

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
        'feed_50_len': feed_50_len,
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
        'port1_x': port1_x,
        'port1_y': port1_y,
        'port2_x': port2_x,
        'port2_y': port2_y,
        'x_port': x_port,
        'y_port': y_port,
        'W_sub': W_sub,
        'L_sub': L_sub,
        'L_100_l': L_100_l,
        'L_100_b': L_100_b,
        'L_100_l_eff': L_100_l_eff,
        'L_100_b_eff': L_100_b_eff,
        'arm_l_waypoints': [(float(round(p[0], 4)), float(round(p[1], 4))) for p in arm_l_waypoints_full],
        'arm_b_waypoints': [(float(round(p[0], 4)), float(round(p[1], 4))) for p in arm_b_waypoints_full],
        'arm_l_build_waypoints': arm_l_build_waypoints,
        'arm_b_build_waypoints': arm_b_build_waypoints,
    }


def build_model_v6(params):
    """
    Create the 3D CAD model of the two-port Model 6 in OpenCASCADE and prepare entities for meshing.
    """
    info = compute_model6_routing(params)

    L = info['L']
    W = info['W']
    h = info['h']
    margin = float(params.get('air_margin', 30.0))

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
    d_t = info['d_t']
    x_T = info['x_T']
    y_T = info['y_T']
    port1_y = info['port1_y']
    port2_y = info['port2_y']
    W_sub = info['W_sub']
    L_sub = info['L_sub']
    y_junc_b = info['y_junc_b']
    x_junc_l = info['x_junc_l']

    # Store computed parameters back into params
    params['antenna_model'] = 6
    params['port_impedance'] = float(params.get('port_impedance', 100.0))

    params['w_50'] = float(np.round(w_50, 4))
    params['feed_50_w'] = params['w_50']
    params['w1'] = params['w_50']

    params['w_feed'] = float(np.round(w_feed, 4))
    params['feed_100_w'] = params['w_feed']
    params['port_w'] = params['w_feed']
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
    params['d_t'] = float(np.round(d_t, 4))
    params['feed_50_len'] = float(np.round(info['feed_50_len'], 3))
    params['feed_arm_offset'] = float(np.round(info['arm_offset'], 3))
    params['feed_end_straight'] = float(np.round(info['end_straight'], 3))
    params['sub_margin'] = float(np.round(info['sub_margin'], 3))

    params['L_100_b'] = float(np.round(info['L_100_b'], 4))
    params['L_100_l'] = float(np.round(info['L_100_l'], 4))
    params['L_100_b_eff'] = float(np.round(info['L_100_b_eff'], 4))
    params['L_100_l_eff'] = float(np.round(info['L_100_l_eff'], 4))
    params['feed_len_b'] = float(np.round(l_T_b + info['L_100_b_eff'], 4))
    params['feed_len_l'] = float(np.round(l_T_l + info['L_100_l_eff'], 4))

    params['feed_x_T'] = float(np.round(x_T, 4))
    params['feed_y_T'] = float(np.round(y_T, 4))
    params['port1_x'] = float(np.round(x_T, 4))
    params['port1_y'] = float(np.round(port1_y, 4))
    params['port2_x'] = float(np.round(x_T, 4))
    params['port2_y'] = float(np.round(port2_y, 4))
    params['port_x'] = params['port1_x']
    params['port_y'] = params['port1_y']
    params['y_port_1'] = params['port1_y']
    params['y_port_2'] = params['port2_y']
    params['y_bot'] = float(np.round(info['y_bot'], 4))
    params['x_left_vert'] = float(np.round(info['x_left_vert'], 4))

    params['sub_W'] = float(np.round(W_sub, 3))
    params['sub_w'] = params['sub_W']
    params['sub_L'] = float(np.round(L_sub, 3))
    params['sub_l'] = params['sub_L']
    params['lambda_g_4_feed'] = float(np.round(info['lambda_g_4_feed'], 3))
    params['arm_l_waypoints'] = info['arm_l_waypoints']
    params['arm_b_waypoints'] = info['arm_b_waypoints']
    params['arm_l_build_waypoints'] = info['arm_l_build_waypoints']
    params['arm_b_build_waypoints'] = info['arm_b_build_waypoints']

    # 1. Initialize Gmsh and base volumes (Substrate and Air box)
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1)
    gmsh.model.add("lhcp_antenna_model6")

    sub_tag = gmsh.model.occ.addBox(-W_sub / 2.0, -L_sub / 2.0, 0.0, W_sub, L_sub, h)
    air_tag = gmsh.model.occ.addBox(
        -W_sub / 2.0 - margin,
        -L_sub / 2.0 - margin,
        -margin,
        W_sub + 2.0 * margin,
        L_sub + 2.0 * margin,
        h + 2.0 * margin,
    )

    # 2. Radiating patch with shallow inset notches at z = h
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

    # 3. Quarter-wave transformers at the patch (z = h)
    trans_b = gmsh.model.occ.addRectangle(-w_T_b / 2.0, y_junc_b, h, w_T_b, l_T_b)
    trans_l = gmsh.model.occ.addRectangle(x_junc_l, -w_T_l / 2.0, h, l_T_l, w_T_l)

    # 4. Curved 100 Ohm lines for both branches (z = h)
    arm_l_tag = build_curved_trace_occ(info['arm_l_build_waypoints'], w_feed, bend_radius, h)
    arm_b_tag = build_curved_trace_occ(info['arm_b_build_waypoints'], w_feed, bend_radius, h)

    metal_surfs = [patch_tag, trans_b, trans_l, arm_l_tag, arm_b_tag]
    gmsh.model.occ.synchronize()

    # 5. Two internal 100 Ohm lumped ports in XZ plane at the ends of the branches
    hw_f = w_feed / 2.0
    x_min = x_T - hw_f
    x_max = x_T + hw_f

    # Port 1 (bottom branch, Ey field, Delta L phasing): vertical surface at y = y_T - d_t
    p1_1 = gmsh.model.occ.addPoint(x_min, port1_y, 0.0)
    p1_2 = gmsh.model.occ.addPoint(x_max, port1_y, 0.0)
    p1_3 = gmsh.model.occ.addPoint(x_max, port1_y, h)
    p1_4 = gmsh.model.occ.addPoint(x_min, port1_y, h)
    l1_1 = gmsh.model.occ.addLine(p1_1, p1_2)
    l1_2 = gmsh.model.occ.addLine(p1_2, p1_3)
    l1_3 = gmsh.model.occ.addLine(p1_3, p1_4)
    l1_4 = gmsh.model.occ.addLine(p1_4, p1_1)
    cl1 = gmsh.model.occ.addCurveLoop([l1_1, l1_2, l1_3, l1_4])
    port1_tag = gmsh.model.occ.addPlaneSurface([cl1])

    # Port 2 (left branch, Ex field, reference phase 0 deg): vertical surface at y = y_T + d_t
    p2_1 = gmsh.model.occ.addPoint(x_min, port2_y, 0.0)
    p2_2 = gmsh.model.occ.addPoint(x_max, port2_y, 0.0)
    p2_3 = gmsh.model.occ.addPoint(x_max, port2_y, h)
    p2_4 = gmsh.model.occ.addPoint(x_min, port2_y, h)
    l2_1 = gmsh.model.occ.addLine(p2_1, p2_2)
    l2_2 = gmsh.model.occ.addLine(p2_2, p2_3)
    l2_3 = gmsh.model.occ.addLine(p2_3, p2_4)
    l2_4 = gmsh.model.occ.addLine(p2_4, p2_1)
    cl2 = gmsh.model.occ.addCurveLoop([l2_1, l2_2, l2_3, l2_4])
    port2_tag = gmsh.model.occ.addPlaneSurface([cl2])

    # 6. Ground plane GND (z = 0)
    gnd_tag = gmsh.model.occ.addRectangle(-W_sub / 2.0, -L_sub / 2.0, 0.0, W_sub, L_sub)

    gmsh.model.occ.synchronize()

    # 7. Conformal fragmentation of volumes and surfaces (Boolean Fragments)
    vols = gmsh.model.occ.getEntities(3)
    input_surfs = [(2, s) for s in metal_surfs] + [(2, gnd_tag), (2, port1_tag), (2, port2_tag)]

    _, out_map = gmsh.model.occ.fragment(vols, input_surfs)
    gmsh.model.occ.synchronize()

    pec_tags = []
    port1_tags = []
    port2_tags = []
    for idx, (_, s_tag) in enumerate(input_surfs):
        frag_entities = out_map[len(vols) + idx]
        frag_tags = [tag for d, tag in frag_entities if d == 2]
        if s_tag == port1_tag:
            port1_tags.extend(frag_tags)
        elif s_tag == port2_tag:
            port2_tags.extend(frag_tags)
        else:
            pec_tags.extend(frag_tags)

    params['port1_tags'] = list(set(port1_tags))
    params['port2_tags'] = list(set(port2_tags))
    params['port1_surface_tag'] = port1_tags[0] if port1_tags else None
    params['port2_surface_tag'] = port2_tags[0] if port2_tags else None
    params['port_tags'] = list(set(port1_tags + port2_tags))
    params['pec_tags'] = list(set(pec_tags))

    return sub_tag, air_tag


build_model = build_model_v6
