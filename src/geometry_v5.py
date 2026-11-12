"""
geometry_v5.py - Model 5: Dvouportový model se dvěma nezávislými 100 Ohm porty a zakřivenými větvemi.
Odvozeno z Modelu 4:
  - Odstraňuje 50 Ohm T-článek a 50 Ohm kmen.
  - Obě 100 Ohm napájecí větve jsou vyvedeny na dva samostatné 100 Ohm lumped porty na hraně substrátu:
      * Port 1 (spodní větev, pole Ey, fázování Delta L): vyveden na levé hraně substrátu (YZ rovina na x = x_port, y = y_port_1, Tag 4).
      * Port 2 (levá větev, pole Ex, referenční fáze): vyveden na levé hraně substrátu (YZ rovina na x = x_port, y = y_port_2, Tag 6).
  - Zachovává trasování větví z Modelu 4 včetně kruhových oblouků o poloměru R (FEED_BEND_RADIUS).
  - Přesná analytická shoda rozdílu délek drah L_100_b - L_100_l == feed_delta_l (cca lambda_g/4 pro -90° posuv).
  - Umožňuje nezávislé ladění a vyhodnocování odrazu spodní větve (S11), levé větve (S22), vzájemné vazby (S21)
    a fázového rozdílu před opětovným sloučením do 50 Ohm T-článku.
"""

import gmsh
import numpy as np

from rf_calc import (
    synth_microstrip_w,
    calc_microstrip_eps_eff,
    calc_quarter_wave_length,
    DESIGN_FREQ_GHZ,
)
from geometry_v4 import (
    calc_curved_path_length,
    compute_curved_ribbon_outline,
    build_curved_trace_occ,
)

COORD_TOL = 1e-9


def compute_model5_routing(params):
    """
    Vypočte veškeré RF a geometrické souřadnice dvouportového Modelu 5 (bez spuštění Gmsh),
    včetně přesných trasovacích bodů (waypoints) obou zakřivených 100 Ohm větví
    a poloh Portu 1 a Portu 2 na levé hraně substrátu.
    """
    L = float(params.get('patch_L', 29.95))
    W = float(params.get('patch_W', L))
    h = float(params.get('sub_h', 1.52))
    eps_r = float(params.get('eps_r', 4.3))
    f_design = float(params.get('design_freq_ghz', DESIGN_FREQ_GHZ))
    port_z0 = float(params.get('port_impedance', 100.0))

    # 1. Syntéza šířky 100 Ohm větví přívodu
    raw_w_100 = next(
        (params[k] for k in ('feed_100_w', 'w_feed', 'w_100', 'w2') if params.get(k) is not None),
        None,
    )
    w_feed = float(raw_w_100) if raw_w_100 is not None else synth_microstrip_w(port_z0, h, eps_r)

    eps_eff_feed = calc_microstrip_eps_eff(w_feed, h, eps_r)
    lambda_g_4_feed = calc_quarter_wave_length(f_design, eps_eff_feed)

    # 2. Parametry čtvrtvlnného impedančního transformátoru (výchozí: w_T = 0.30 mm, l_T = 19.00 mm)
    w_T_default = float(params.get('trans_w', params.get('w_T', params.get('w_trans', 0.30))))
    eps_eff_trans_def = calc_microstrip_eps_eff(w_T_default, h, eps_r)
    l_T_default = float(params.get('trans_l', params.get('l_T', params.get('l_trans', calc_quarter_wave_length(f_design, eps_eff_trans_def)))))

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

    # 3. Mělký zářez a mezery (výchozí y0b = y0l = 2.5 mm, gap = 0.5 mm)
    inset_b = float(params.get('feed_inset_b', params.get('inset_b', params.get('y0b', params.get('y0', params.get('feed_inset', 2.5))))))
    inset_l = float(params.get('feed_inset_l', params.get('inset_l', params.get('y0l', params.get('y0', params.get('feed_inset', 2.5))))))
    if inset_b < 0.0 or inset_l < 0.0:
        raise ValueError(f"Hloubka zanoření (inset) musí být nezáporná: inset_b={inset_b}, inset_l={inset_l}")

    inset_gap_b = float(params.get('inset_gap_b', params.get('feed_inset_gap_b', params.get('gap_b', params.get('inset_gap', params.get('feed_inset_gap', 0.5))))))
    inset_gap_l = float(params.get('inset_gap_l', params.get('feed_inset_gap_l', params.get('gap_l', params.get('inset_gap', params.get('feed_inset_gap', 0.5))))))

    # 4. Fázovací prodloužení delta_L v 100 Ohm vedení
    raw_delta_l = params.get('feed_delta_l', params.get('delta_l', params.get('phase_delay_mm', params.get('feed_delta'))))
    feed_delta_l = float(raw_delta_l) if raw_delta_l is not None else lambda_g_4_feed

    # 5. Parametry oblouků a geometrií větví
    bend_radius = float(params.get('feed_bend_radius', params.get('bend_radius', 3.0)))
    if bend_radius <= (w_feed / 2.0) + 0.1:
        raise ValueError(
            f"Poloměr oblouku feed_bend_radius={bend_radius:.3f} mm musí být větší než w_feed/2 + 0.1 ({w_feed/2.0 + 0.1:.3f} mm)."
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

    # 6. Pozice vstupů transformátorů a os větví
    y_junc_b = -L / 2.0 + inset_b - l_T_b
    x_junc_l = -W / 2.0 + inset_l - l_T_l
    x_left_vert = x_junc_l - arm_offset
    x_T = float(params.get('feed_x_T', params.get('x_T', x_left_vert)))

    y_bot_default = y_junc_b - end_straight - bend_radius
    raw_y_bot = params.get('feed_y_bot', params.get('y_bot'))
    y_bot = float(raw_y_bot) if raw_y_bot is not None else y_bot_default

    # Virtuální střed fázování y_T (referenční rovina fázového středu)
    raw_y_T = params.get('feed_y_T', params.get('y_T'))
    if raw_y_T is None:
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

    # 7. Odstup portů od virtuálního středu y_T (y_port_1 = y_T - offset, y_port_2 = y_T + offset)
    # Pro zachování L_100_b - L_100_l == delta_l musí být offset symetrický kolem y_T.
    max_safe_offset = (y_T - y_bot) - 2.0 * bend_radius - 0.4
    default_offset = min(3.0, max(1.5, max_safe_offset))
    raw_offset = params.get('feed_port_offset', params.get('port_offset'))
    port_offset = float(raw_offset) if raw_offset is not None else default_offset

    s_vert_b = (y_T - port_offset) - y_bot - 2.0 * bend_radius
    if s_vert_b < -1e-6:
        raise ValueError(
            f"Zvolený port_offset={port_offset:.2f} mm je příliš velký: svislý úsek spodní větve "
            f"({s_vert_b:.2f} mm) nestačí pro dva oblouky R={bend_radius:.2f} mm (max safe offset={max_safe_offset:.2f} mm)."
        )

    y_port_1 = y_T - port_offset  # Port 1 (spodní větev, pole Ey)
    y_port_2 = y_T + port_offset  # Port 2 (levá větev, pole Ex)

    # 8. Rozměry substrátu a pozice levých portů (x_port = -W_sub / 2)
    raw_feed_port_len = next((params[k] for k in ('feed_port_len', 'feed_50_len', 'l1') if params.get(k) is not None), None)
    feed_port_len = float(raw_feed_port_len) if raw_feed_port_len is not None else 9.0

    x_port_base = x_T - bend_radius - feed_port_len
    min_W_sub = 2.0 * max(abs(x_port_base), W / 2.0 + sub_margin)
    min_L_sub = 2.0 * max(
        abs(y_bot) + w_feed / 2.0 + sub_margin,
        abs(y_port_2) + w_feed / 2.0 + sub_margin,
        abs(y_port_1) + w_feed / 2.0 + sub_margin,
        L / 2.0 + sub_margin,
    )

    raw_W_sub = params.get('sub_W', params.get('sub_w'))
    raw_L_sub = params.get('sub_L', params.get('sub_l'))
    W_sub = max(float(raw_W_sub), min_W_sub) if raw_W_sub is not None else min_W_sub
    L_sub = max(float(raw_L_sub), min_L_sub) if raw_L_sub is not None else min_L_sub

    x_port = -W_sub / 2.0
    effective_feed_port_len = (x_T - bend_radius) - x_port

    # 9. Střednicové trasy (waypoints) pro obě zakřivené větve
    arm_l_waypoints = [
        (x_port, y_port_2),
        (x_T, y_port_2),
        (x_T, 0.0),
        (x_junc_l, 0.0),
    ]
    L_100_l = calc_curved_path_length(arm_l_waypoints, bend_radius)

    arm_b_waypoints = [
        (x_port, y_port_1),
        (x_T, y_port_1),
        (x_T, y_bot),
        (0.0, y_bot),
        (0.0, y_junc_b),
    ]
    L_100_b = calc_curved_path_length(arm_b_waypoints, bend_radius)

    s_end_l = x_junc_l - x_T - bend_radius
    s_end_b = y_junc_b - y_bot - bend_radius
    s_horiz_b = -x_T - 2.0 * bend_radius
    s_lead_l = x_T - x_port - bend_radius
    s_lead_b = x_T - x_port - bend_radius
    s_vert_l = -y_port_2 - 2.0 * bend_radius

    return {
        'L': L,
        'W': W,
        'h': h,
        'eps_r': eps_r,
        'f_design': f_design,
        'port_z0': port_z0,
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
        'port_offset': port_offset,
        'feed_port_len': effective_feed_port_len,
        'arm_offset': arm_offset,
        'end_straight': end_straight,
        'sub_margin': sub_margin,
        's_end_l': s_end_l,
        's_end_b': s_end_b,
        's_vert_l': s_vert_l,
        's_vert_b': s_vert_b,
        's_horiz_b': s_horiz_b,
        's_lead_l': s_lead_l,
        's_lead_b': s_lead_b,
        'x_junc_l': x_junc_l,
        'y_junc_b': y_junc_b,
        'x_left_vert': x_left_vert,
        'y_bot': y_bot,
        'x_T': x_T,
        'y_T': y_T,
        'x_port': x_port,
        'y_port_1': y_port_1,
        'y_port_2': y_port_2,
        'W_sub': W_sub,
        'L_sub': L_sub,
        'L_100_l': L_100_l,
        'L_100_b': L_100_b,
        'arm_l_waypoints': [(float(round(p[0], 4)), float(round(p[1], 4))) for p in arm_l_waypoints],
        'arm_b_waypoints': [(float(round(p[0], 4)), float(round(p[1], 4))) for p in arm_b_waypoints],
        'arm_l_build_waypoints': arm_l_waypoints,
        'arm_b_build_waypoints': arm_b_waypoints,
    }


def build_model_v5(params):
    """
    Vytvoří 3D CAD model dvouportového Modelu 5 v OpenCASCADE a připraví entity pro síťování v Gmsh.
    """
    info = compute_model5_routing(params)

    L = info['L']
    W = info['W']
    h = info['h']
    margin = float(params.get('air_margin', 30.0))

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
    x_T = info['x_T']
    y_T = info['y_T']
    x_port = info['x_port']
    y_port_1 = info['y_port_1']
    y_port_2 = info['y_port_2']
    W_sub = info['W_sub']
    L_sub = info['L_sub']
    y_junc_b = info['y_junc_b']
    x_junc_l = info['x_junc_l']

    # Zpětné uložení vypočtených hodnot do params
    params['antenna_model'] = 5
    params['port_impedance'] = float(params.get('port_impedance', 100.0))
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
    params['port_offset'] = float(np.round(info['port_offset'], 3))
    params['feed_port_offset'] = params['port_offset']

    params['L_100_b'] = float(np.round(info['L_100_b'], 4))
    params['L_100_l'] = float(np.round(info['L_100_l'], 4))
    params['feed_len_b'] = float(np.round(l_T_b + info['L_100_b'], 4))
    params['feed_len_l'] = float(np.round(l_T_l + info['L_100_l'], 4))

    params['feed_x_T'] = float(np.round(x_T, 4))
    params['feed_y_T'] = float(np.round(y_T, 4))
    params['x_port'] = float(np.round(x_port, 4))
    params['y_port_1'] = float(np.round(y_port_1, 4))
    params['y_port_2'] = float(np.round(y_port_2, 4))
    params['port_x'] = params['x_port']
    params['port_y'] = params['y_port_1']
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
    gmsh.model.add("lhcp_antenna_model5")

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

    # 4. Zakřivená 100 Ohm vedení pro obě větve (Model 5 nemá 50 Ohm kmen ani T-spojku)
    arm_l_tag = build_curved_trace_occ(info['arm_l_waypoints'], w_feed, bend_radius, h)
    arm_b_tag = build_curved_trace_occ(info['arm_b_waypoints'], w_feed, bend_radius, h)

    metal_surfs = [patch_tag, trans_b, trans_l, arm_l_tag, arm_b_tag]
    gmsh.model.occ.synchronize()

    # 5. Dva samostatné 100 Ohm lumped porty na levé hraně substrátu (x = x_port = -W_sub / 2)
    # Port 1: spodní větev (Ey, zpoždění Delta L), YZ rovina kolem y_port_1
    p1_1 = gmsh.model.occ.addPoint(x_port, y_port_1 - w_feed / 2.0, 0.0)
    p1_2 = gmsh.model.occ.addPoint(x_port, y_port_1 + w_feed / 2.0, 0.0)
    p1_3 = gmsh.model.occ.addPoint(x_port, y_port_1 + w_feed / 2.0, h)
    p1_4 = gmsh.model.occ.addPoint(x_port, y_port_1 - w_feed / 2.0, h)
    l1_1 = gmsh.model.occ.addLine(p1_1, p1_2)
    l1_2 = gmsh.model.occ.addLine(p1_2, p1_3)
    l1_3 = gmsh.model.occ.addLine(p1_3, p1_4)
    l1_4 = gmsh.model.occ.addLine(p1_4, p1_1)
    cl1 = gmsh.model.occ.addCurveLoop([l1_1, l1_2, l1_3, l1_4])
    port1_tag = gmsh.model.occ.addPlaneSurface([cl1])

    # Port 2: levá větev (Ex, referenční fáze 0°), YZ rovina kolem y_port_2
    p2_1 = gmsh.model.occ.addPoint(x_port, y_port_2 - w_feed / 2.0, 0.0)
    p2_2 = gmsh.model.occ.addPoint(x_port, y_port_2 + w_feed / 2.0, 0.0)
    p2_3 = gmsh.model.occ.addPoint(x_port, y_port_2 + w_feed / 2.0, h)
    p2_4 = gmsh.model.occ.addPoint(x_port, y_port_2 - w_feed / 2.0, h)
    l2_1 = gmsh.model.occ.addLine(p2_1, p2_2)
    l2_2 = gmsh.model.occ.addLine(p2_2, p2_3)
    l2_3 = gmsh.model.occ.addLine(p2_3, p2_4)
    l2_4 = gmsh.model.occ.addLine(p2_4, p2_1)
    cl2 = gmsh.model.occ.addCurveLoop([l2_1, l2_2, l2_3, l2_4])
    port2_tag = gmsh.model.occ.addPlaneSurface([cl2])

    # 6. Zemní plocha GND (z = 0)
    gnd_tag = gmsh.model.occ.addRectangle(-W_sub / 2.0, -L_sub / 2.0, 0.0, W_sub, L_sub)

    gmsh.model.occ.synchronize()

    # 7. Konformní fragmentace objemů a ploch (Boolean Fragments)
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


build_model = build_model_v5
