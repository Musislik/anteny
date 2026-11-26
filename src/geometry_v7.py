"""
geometry_v7.py - Model 7: Mirrored Model 4 for generating opposite polarization (RHCP).
Architecture:
  - Derived from final Model 4 via exact spatial reflection across the Y-axis (x -> -x).
  - Horizontal 50 Ohm feed trunk and rotated T-junction are located on the right side (x_T > 0, x_port = +W_sub/2).
  - Right branch (Ex excitation on right patch edge x = +W/2, reference phase 0 deg):
      trace with 1 arc from the upper arm of the T-junction to the right quarter-wave transformer.
  - Bottom branch (Ey excitation on bottom patch edge y = -L/2, -90 deg delay):
      trace with 2 arcs from the lower arm of the T-junction to the bottom transformer (delta_L ≈ lambda_g/4).
  - Due to spatial mirroring x -> -x, the sense of rotation of the electric field vector reverses:
      the original left-hand circular polarization (LHCP) of Model 4 becomes pure right-hand circular polarization (RHCP).
  - Impedance ratios, matching (S11), resonant frequency, and axial ratio (AR) remain identical to Model 4.
"""

import os
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
    compute_model4_routing,
)

COORD_TOL = 1e-9


def compute_model7_routing(params):
    """
    Compute all RF and geometric coordinates of the mirrored Model 7 (without starting Gmsh).
    Reuses the analytical path calculation from Model 4 and mirrors coordinates across the Y-axis (x -> -x).
    """
    # If the user passed a positive x_T for Model 7, convert it to negative for internal Model 4 calculation
    params_m4 = dict(params)
    raw_x_T = params_m4.get('feed_x_T', params_m4.get('x_T'))
    if raw_x_T is not None and float(raw_x_T) > 0:
        params_m4['feed_x_T'] = -float(raw_x_T)

    info4 = compute_model4_routing(params_m4)

    # Mirror coordinates across Y-axis: x -> -x, y -> y
    x_T = -float(info4['x_T'])
    x_junc_r = -float(info4['x_junc_l'])
    x_port = -float(info4['x_port'])
    x_right_vert = -float(info4['x_left_vert'])

    arm_r_waypoints_full = [(-float(p[0]), float(p[1])) for p in info4['arm_l_waypoints']]
    arm_b_waypoints_full = [(-float(p[0]), float(p[1])) for p in info4['arm_b_waypoints']]

    arm_r_build_waypoints = [(-float(p[0]), float(p[1])) for p in info4['arm_l_build_waypoints']]
    arm_b_build_waypoints = [(-float(p[0]), float(p[1])) for p in info4['arm_b_build_waypoints']]

    # Path lengths and phase difference are identical to Model 4 (isometry)
    L_100_r = float(info4['L_100_l'])
    L_100_b = float(info4['L_100_b'])

    res = dict(info4)
    res.update({
        'antenna_model': 7,
        'polarization_type': 'RHCP',
        'x_T': x_T,
        'x_junc_r': x_junc_r,
        'x_junc_l': -x_junc_r,  # for compatibility
        'x_port': x_port,
        'x_right_vert': x_right_vert,
        'x_left_vert': -x_right_vert,
        'arm_r_waypoints': [(float(round(p[0], 4)), float(round(p[1], 4))) for p in arm_r_waypoints_full],
        'arm_b_waypoints': [(float(round(p[0], 4)), float(round(p[1], 4))) for p in arm_b_waypoints_full],
        'arm_r_build_waypoints': arm_r_build_waypoints,
        'arm_b_build_waypoints': arm_b_build_waypoints,
        'arm_l_waypoints': [(float(round(p[0], 4)), float(round(p[1], 4))) for p in arm_r_waypoints_full],
        'arm_l_build_waypoints': arm_r_build_waypoints,
        'L_100_r': L_100_r,
        'L_100_l': L_100_r,
        'L_100_b': L_100_b,
        'w_T_r': info4['w_T_l'],
        'l_T_r': info4['l_T_l'],
        'inset_r': info4['inset_l'],
        'inset_gap_r': info4['inset_gap_l'],
        's_end_r': info4['s_end_l'],
    })
    return res


def build_t_junction_trunk_occ_v7(x_port, x_T, y_T, w_50, w_feed, t_fillet_r, z):
    """
    Create the surface of the horizontal 50 Ohm feed trunk from the right port (x_port, y_T)
    leftward to the rotated vertical T-junction crossbar at x_T ([x_T - hw_f, x_T + hw_f],
    y in [y_T - d_t, y_T + d_t]), with inner corner fillets of radius t_fillet_r.
    """
    hw_50 = float(w_50) / 2.0
    hw_f = float(w_feed) / 2.0
    r_f = float(t_fillet_r)
    d_t = hw_50 + r_f

    x_right = float(x_port)
    y_center = float(y_T)
    x_bar_left = float(x_T) - hw_f
    x_bar_right = float(x_T) + hw_f

    if r_f <= 1e-6:
        trunk_rect = gmsh.model.occ.addRectangle(
            x_bar_left, y_center - hw_50, z, x_right - x_bar_left, float(w_50)
        )
        return trunk_rect, d_t

    x_fillet_start = x_bar_right + r_f
    if x_fillet_start >= x_right - 1e-4:
        raise ValueError(
            f"50 Ohm line length (x_port - x_bar_right = {x_right - x_bar_right:.2f} mm) "
            f"is insufficient for T-junction fillet radius r={r_f:.2f} mm."
        )

    p_br_port = gmsh.model.occ.addPoint(x_right, y_center - hw_50, z)
    p_bf_s = gmsh.model.occ.addPoint(x_fillet_start, y_center - hw_50, z)
    p_bc = gmsh.model.occ.addPoint(x_fillet_start, y_center - d_t, z)
    p_bf_e = gmsh.model.occ.addPoint(x_bar_right, y_center - d_t, z)
    p_bl = gmsh.model.occ.addPoint(x_bar_left, y_center - d_t, z)
    p_tl = gmsh.model.occ.addPoint(x_bar_left, y_center + d_t, z)
    p_tf_e = gmsh.model.occ.addPoint(x_bar_right, y_center + d_t, z)
    p_tc = gmsh.model.occ.addPoint(x_fillet_start, y_center + d_t, z)
    p_tf_s = gmsh.model.occ.addPoint(x_fillet_start, y_center + hw_50, z)
    p_tr_port = gmsh.model.occ.addPoint(x_right, y_center + hw_50, z)

    curves = [
        gmsh.model.occ.addLine(p_br_port, p_bf_s),
        gmsh.model.occ.addCircleArc(p_bf_s, p_bc, p_bf_e),
        gmsh.model.occ.addLine(p_bf_e, p_bl),
        gmsh.model.occ.addLine(p_bl, p_tl),
        gmsh.model.occ.addLine(p_tl, p_tf_e),
        gmsh.model.occ.addCircleArc(p_tf_e, p_tc, p_tf_s),
        gmsh.model.occ.addLine(p_tf_s, p_tr_port),
        gmsh.model.occ.addLine(p_tr_port, p_br_port),
    ]
    cl = gmsh.model.occ.addCurveLoop(curves)
    return gmsh.model.occ.addPlaneSurface([cl]), d_t


def build_model_v7(params):
    """
    Create the 3D CAD model of Model 7 (mirrored Model 4 for RHCP) in OpenCASCADE.
    """
    info = compute_model7_routing(params)

    L = info['L']
    W = info['W']
    h = info['h']
    margin = float(params['air_margin'])

    w_50 = info['w_50']
    w_feed = info['w_feed']
    w_T_b = info['w_T_b']
    w_T_r = info['w_T_r']
    l_T_b = info['l_T_b']
    l_T_r = info['l_T_r']
    inset_b = info['inset_b']
    inset_r = info['inset_r']
    inset_gap_b = info['inset_gap_b']
    inset_gap_r = info['inset_gap_r']
    bend_radius = info['bend_radius']
    t_fillet_r = info['t_fillet_r']
    x_T = info['x_T']
    y_T = info['y_T']
    x_port = info['x_port']
    y_port = info['y_port']
    W_sub = info['W_sub']
    L_sub = info['L_sub']
    y_junc_b = info['y_junc_b']
    x_junc_r = info['x_junc_r']

    # Store computed parameters back into params
    params['antenna_model'] = 7
    params['polarization_type'] = 'RHCP'
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
    params['trans_w_r'] = float(np.round(w_T_r, 4))
    params['trans_w_l'] = params['trans_w_r']
    params['w_T_b'] = params['trans_w_b']
    params['w_T_r'] = params['trans_w_r']
    params['w_T_l'] = params['trans_w_r']

    params['trans_l'] = float(np.round(info['resolved_trans_l'], 4))
    params['l_T'] = params['trans_l']
    params['l_trans'] = params['trans_l']
    params['trans_l_b'] = float(np.round(l_T_b, 4))
    params['trans_l_r'] = float(np.round(l_T_r, 4))
    params['trans_l_l'] = params['trans_l_r']
    params['l_T_b'] = params['trans_l_b']
    params['l_T_r'] = params['trans_l_r']
    params['l_T_l'] = params['trans_l_r']

    params['feed_inset_b'] = float(np.round(inset_b, 3))
    params['feed_inset_r'] = float(np.round(inset_r, 3))
    params['feed_inset_l'] = params['feed_inset_r']
    params['inset_b'] = params['feed_inset_b']
    params['inset_r'] = params['feed_inset_r']
    params['inset_l'] = params['feed_inset_r']
    params['y0b'] = params['feed_inset_b']
    params['y0r'] = params['feed_inset_r']
    params['y0l'] = params['feed_inset_r']

    params['feed_inset_gap_b'] = float(np.round(inset_gap_b, 3))
    params['feed_inset_gap_r'] = float(np.round(inset_gap_r, 3))
    params['feed_inset_gap_l'] = params['feed_inset_gap_r']
    params['inset_gap_b'] = params['feed_inset_gap_b']
    params['inset_gap_r'] = params['feed_inset_gap_r']
    params['inset_gap_l'] = params['feed_inset_gap_r']

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
    params['L_100_r'] = float(np.round(info['L_100_r'], 4))
    params['L_100_l'] = params['L_100_r']
    params['feed_len_b'] = float(np.round(l_T_b + info['L_100_b'], 4))
    params['feed_len_r'] = float(np.round(l_T_r + info['L_100_r'], 4))
    params['feed_len_l'] = params['feed_len_r']

    params['feed_x_T'] = float(np.round(x_T, 4))
    params['feed_y_T'] = float(np.round(y_T, 4))
    params['x_port'] = float(np.round(x_port, 4))
    params['y_port'] = float(np.round(y_port, 4))
    params['port_x'] = params['x_port']
    params['port_y'] = params['y_port']
    params['y_bot'] = float(np.round(info['y_bot'], 4))
    params['x_right_vert'] = float(np.round(info['x_right_vert'], 4))

    params['sub_W'] = float(np.round(W_sub, 3))
    params['sub_w'] = params['sub_W']
    params['sub_L'] = float(np.round(L_sub, 3))
    params['sub_l'] = params['sub_L']
    params['lambda_g_4_feed'] = float(np.round(info['lambda_g_4_feed'], 3))
    params['arm_r_waypoints'] = info['arm_r_waypoints']
    params['arm_b_waypoints'] = info['arm_b_waypoints']
    params['arm_l_waypoints'] = info['arm_r_waypoints']

    # 1. Initialize Gmsh and base volumes (Substrate and Air box)
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1)
    gmsh.model.add("rhcp_antenna_model7")

    sub_tag = gmsh.model.occ.addBox(-W_sub / 2.0, -L_sub / 2.0, 0.0, W_sub, L_sub, h)
    air_tag = gmsh.model.occ.addBox(
        -W_sub / 2.0 - margin,
        -L_sub / 2.0 - margin,
        -margin,
        W_sub + 2.0 * margin,
        L_sub + 2.0 * margin,
        h + 2.0 * margin,
    )

    # 2. Radiating patch with inset notches on bottom and right edges (z = h)
    patch_base = gmsh.model.occ.addRectangle(-W / 2.0, -L / 2.0, h, W, L)
    tool_notches = []
    if inset_b > 0.0:
        notch_b_w = w_T_b + 2.0 * inset_gap_b
        notch_b = gmsh.model.occ.addRectangle(-notch_b_w / 2.0, -L / 2.0 - 0.05, h, notch_b_w, inset_b + 0.05)
        tool_notches.append((2, notch_b))
    if inset_r > 0.0:
        notch_r_h = w_T_r + 2.0 * inset_gap_r
        notch_r = gmsh.model.occ.addRectangle(W / 2.0 - inset_r, -notch_r_h / 2.0, h, inset_r + 0.05, notch_r_h)
        tool_notches.append((2, notch_r))

    if tool_notches:
        cut_surfs, _ = gmsh.model.occ.cut([(2, patch_base)], tool_notches)
        patch_tag = cut_surfs[0][1]
    else:
        patch_tag = patch_base

    # 3. Quarter-wave transformers at the patch (z = h)
    trans_b = gmsh.model.occ.addRectangle(-w_T_b / 2.0, y_junc_b, h, w_T_b, l_T_b)
    trans_r = gmsh.model.occ.addRectangle(W / 2.0 - inset_r, -w_T_r / 2.0, h, l_T_r, w_T_r)

    # 4. Curved 100 Ohm lines and rotated 50 Ohm T-junction on the right (merged via occ.fuse)
    trunk_tag, _ = build_t_junction_trunk_occ_v7(x_port, x_T, y_T, w_50, w_feed, t_fillet_r, h)
    arm_r_tag = build_curved_trace_occ(info['arm_r_build_waypoints'], w_feed, bend_radius, h)
    arm_b_tag = build_curved_trace_occ(info['arm_b_build_waypoints'], w_feed, bend_radius, h)

    fused_feed, _ = gmsh.model.occ.fuse([(2, trunk_tag)], [(2, arm_r_tag), (2, arm_b_tag)])
    feed_net_tags = [tag for dim, tag in fused_feed if dim == 2]

    metal_surfs = [patch_tag, trans_b, trans_r] + feed_net_tags
    gmsh.model.occ.synchronize()

    # 5. Output 50 Ohm lumped port (YZ plane on right substrate edge x = x_port = +W_sub/2)
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

    # 6. Ground plane GND (z = 0)
    gnd_tag = gmsh.model.occ.addRectangle(-W_sub / 2.0, -L_sub / 2.0, 0.0, W_sub, L_sub)

    gmsh.model.occ.synchronize()

    # 7. Conformal fusion of volumes and surfaces (Boolean Fragments)
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


build_model = build_model_v7
