"""
geometry_v3.py - Model 3: Hybrid two-stage matching for microstrip patch antenna (LHCP).
Path B:
  - Square radiating patch L × W (e.g., 28.80 × 28.80 mm).
  - Shallow inset notch on both arms (y0b, y0l ≈ 2.5 mm, gap g ≈ 0.5 mm) to lower the edge impedance to ~140 Ohm.
  - Inner quarter-wave transformer at the patch (width w_T ≈ 0.42 mm, length l_T ≈ 18.9 mm, Z_T ≈ 118.7 Ohm)
    transforming ~140 Ohm patch impedance directly to 100 Ohm.
  - Outer 100 Ohm microstrip line (width w_feed ≈ 0.694 mm).
  - Phasing extension delta_L (~18.66 mm = lambda_g/4 in 100 Ohm line) placed in the already-matched
    100 Ohm section of Port 1 (bottom arm Ey), eliminating undesired impedance inversion.
  - Two independent 100 Ohm lumped ports (Port 1 on bottom edge, Port 2 on left edge).
"""

import gmsh
import numpy as np

from rf_calc import (
    synth_microstrip_w,
    calc_microstrip_eps_eff,
    calc_quarter_wave_length,
    DESIGN_FREQ_GHZ,
)


def build_model_v3(params):
    """
    Create the 3D CAD model of Model 3 in OpenCASCADE and prepare entities for meshing.
    """
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1)
    gmsh.model.add("lhcp_antenna_model3")

    L = float(params['patch_L'])
    W = float(params.get('patch_W', L))
    h = float(params['sub_h'])
    eps_r = float(params['eps_r'])
    margin = float(params['air_margin'])
    f_design = float(params.get('design_freq_ghz', DESIGN_FREQ_GHZ))

    # 1. Outer 100 Ohm microstrip synthesis
    w_feed = synth_microstrip_w(100.0, h, eps_r)
    eps_eff_feed = calc_microstrip_eps_eff(w_feed, h, eps_r)
    lambda_g_4_feed = calc_quarter_wave_length(f_design, eps_eff_feed)

    # 2. Quarter-wave impedance transformer parameters (Stage 1 at the patch)
    # Default width w_T = 0.42 mm (corresponds to Z_T ≈ 118.7 Ohm on FR-4 h=1.52mm)
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

    # 3. Shallow insets and gaps
    # Default inset depth y0b = y0l = 2.5 mm, gap g = 0.5 mm
    inset_b = float(params.get('feed_inset_b', params.get('inset_b', params.get('y0b', params.get('y0', params.get('feed_inset', 2.5))))))
    inset_l = float(params.get('feed_inset_l', params.get('inset_l', params.get('y0l', params.get('y0', params.get('feed_inset', 2.5))))))

    if inset_b < 0.0 or inset_l < 0.0:
        raise ValueError(f"Inset depth must be non-negative: inset_b={inset_b}, inset_l={inset_l}")

    inset_gap_b = float(params.get('inset_gap_b', params.get('feed_inset_gap_b', params.get('gap_b', params.get('inset_gap', params.get('feed_inset_gap', 0.5))))))
    inset_gap_l = float(params.get('inset_gap_l', params.get('feed_inset_gap_l', params.get('gap_l', params.get('inset_gap', params.get('feed_inset_gap', 0.5))))))

    # 4. Phasing extension delta_L in 100 Ohm line
    raw_delta_l = params.get('feed_delta_l', params.get('delta_l', params.get('phase_delay_mm', params.get('feed_delta'))))
    if raw_delta_l is not None:
        feed_delta_l = float(raw_delta_l)
    else:
        feed_delta_l = lambda_g_4_feed

    # 5. Feed length and substrate sizing
    min_w_sub = W + 2.0 * max(15.0, 10.0 * h)
    W_sub_base = float(params.get('sub_W', params.get('sub_w', 80.0)))
    if W_sub_base < min_w_sub:
        W_sub_base = float(np.round(min_w_sub, 1))

    raw_len_l = params.get('feed_len_l', params.get('feed_length_l', params.get('L_feed_l', params.get('l_feed_l'))))
    raw_len_b = params.get('feed_len_b', params.get('feed_length_b', params.get('L_feed_b', params.get('l_feed_b'))))

    # Base length of outer 100 Ohm section on left arm
    L_feed_default_l = (W_sub_base / 2.0) - (W / 2.0) + inset_l
    if raw_len_l is not None:
        feed_len_l = float(raw_len_l)
        L_100_l = feed_len_l - l_T_l
        if L_100_l <= 0.0:
            raise ValueError(f"feed_len_l={feed_len_l:.2f} mm must be greater than transformer length l_T_l={l_T_l:.2f} mm!")
    else:
        # Ensure at least 8 mm of outer 100 Ohm section
        L_100_l = max(8.0, L_feed_default_l - l_T_l)
        feed_len_l = l_T_l + L_100_l

    # Bottom arm (includes added feed_delta_l section in 100 Ohm line)
    if raw_len_b is not None:
        feed_len_b = float(raw_len_b)
        L_100_b = feed_len_b - l_T_b
        if L_100_b <= 0.0:
            raise ValueError(f"feed_len_b={feed_len_b:.2f} mm must be greater than transformer length l_T_b={l_T_b:.2f} mm!")
        if raw_len_l is not None or raw_delta_l is None:
            feed_delta_l = feed_len_b - feed_len_l
    else:
        L_100_b = L_100_l + feed_delta_l
        feed_len_b = l_T_b + L_100_b

    # Port positions on substrate edges
    # Left port (Port 2, Ex field): x_port = -W/2 + inset_l - feed_len_l
    # Bottom port (Port 1, Ey field): y_port = -L/2 + inset_b - feed_len_b
    x_port = -W / 2.0 + inset_l - feed_len_l
    y_port = -L / 2.0 + inset_b - feed_len_b

    W_sub = 2.0 * abs(x_port)
    L_sub = 2.0 * abs(y_port)

    # Store derived parameters in params
    params['antenna_model'] = 3
    params['w_feed'] = float(np.round(w_feed, 4))
    params['feed_W'] = params['w_feed']
    params['port_w'] = params['w_feed']
    params['w1'] = params['w_feed']
    params['w2'] = params['w_feed']
    params['w3'] = params['w_feed']

    params['trans_w'] = float(np.round(w_T_default, 4))
    params['w_T'] = params['trans_w']
    params['w_trans'] = params['trans_w']
    params['trans_w_b'] = float(np.round(w_T_b, 4))
    params['trans_w_l'] = float(np.round(w_T_l, 4))
    params['w_T_b'] = params['trans_w_b']
    params['w_T_l'] = params['trans_w_l']

    params['trans_l'] = float(np.round(resolved_trans_l, 4))
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

    params['feed_delta_l'] = float(np.round(feed_delta_l, 3))
    params['delta_l'] = params['feed_delta_l']
    params['phase_delay_mm'] = params['feed_delta_l']

    params['feed_len_b'] = float(np.round(feed_len_b, 3))
    params['feed_len_l'] = float(np.round(feed_len_l, 3))
    params['feed_length_b'] = params['feed_len_b']
    params['feed_length_l'] = params['feed_len_l']
    params['L_feed_b'] = params['feed_len_b']
    params['L_feed_l'] = params['feed_len_l']

    params['L_100_b'] = float(np.round(L_100_b, 3))
    params['L_100_l'] = float(np.round(L_100_l, 3))

    params['sub_W'] = float(np.round(W_sub, 3))
    params['sub_w'] = params['sub_W']
    params['sub_L'] = float(np.round(L_sub, 3))
    params['sub_l'] = params['sub_L']

    params['x_port'] = float(np.round(x_port, 3))
    params['y_port'] = float(np.round(y_port, 3))
    params['lambda_g_4_feed'] = float(np.round(lambda_g_4_feed, 3))

    # 6. Create volumes (Substrate and Air box)
    sub_tag = gmsh.model.occ.addBox(-W_sub/2, -L_sub/2, 0, W_sub, L_sub, h)
    air_tag = gmsh.model.occ.addBox(
        -W_sub/2 - margin, -L_sub/2 - margin, -margin,
        W_sub + 2*margin, L_sub + 2*margin, h + 2*margin
    )

    # 7. Patch surface geometry with notches (z = h)
    patch_base = gmsh.model.occ.addRectangle(-W/2, -L/2, h, W, L)

    tool_notches = []
    # Bottom notch notch_b (along x = 0, y from -L/2 to -L/2 + inset_b)
    if inset_b > 0.0:
        notch_b_w = w_T_b + 2.0 * inset_gap_b
        notch_b = gmsh.model.occ.addRectangle(-notch_b_w/2, -L/2 - 0.05, h, notch_b_w, inset_b + 0.05)
        tool_notches.append((2, notch_b))

    # Left notch notch_l (along y = 0, x from -W/2 to -W/2 + inset_l)
    if inset_l > 0.0:
        notch_l_h = w_T_l + 2.0 * inset_gap_l
        notch_l = gmsh.model.occ.addRectangle(-W/2 - 0.05, -notch_l_h/2, h, inset_l + 0.05, notch_l_h)
        tool_notches.append((2, notch_l))

    if tool_notches:
        cut_surfs, _ = gmsh.model.occ.cut([(2, patch_base)], tool_notches)
        patch_tag = cut_surfs[0][1]
    else:
        patch_tag = patch_base

    # 8. Two-stage microstrip feeds
    # Bottom arm (Port 1, Ey field):
    # - Inner transformer: from y = y_junc_b to y = -L/2 + inset_b
    y_junc_b = -L / 2.0 + inset_b - l_T_b
    trans_b = gmsh.model.occ.addRectangle(-w_T_b/2, y_junc_b, h, w_T_b, l_T_b)
    # - Outer 100 Ohm line: from y = y_port to y = y_junc_b
    dy_100_b = y_junc_b - y_port
    feed_b = gmsh.model.occ.addRectangle(-w_feed/2, y_port, h, w_feed, dy_100_b)

    # Left arm (Port 2, Ex field):
    # - Inner transformer: from x = x_junc_l to x = -W/2 + inset_l
    x_junc_l = -W / 2.0 + inset_l - l_T_l
    trans_l = gmsh.model.occ.addRectangle(x_junc_l, -w_T_l/2, h, l_T_l, w_T_l)
    # - Outer 100 Ohm line: from x = x_port to x = x_junc_l
    dx_100_l = x_junc_l - x_port
    feed_l = gmsh.model.occ.addRectangle(x_port, -w_feed/2, h, dx_100_l, w_feed)

    metal_surfs = [patch_tag, trans_b, feed_b, trans_l, feed_l]

    gmsh.model.occ.synchronize()

    # 9. Port surfaces (LumpedPorts on substrate edge, z = 0 to h)
    # Port 1 (bottom): XZ plane at y = y_port, x from -w_feed/2 to +w_feed/2
    p1_1 = gmsh.model.occ.addPoint(-w_feed/2, y_port, 0)
    p1_2 = gmsh.model.occ.addPoint(+w_feed/2, y_port, 0)
    p1_3 = gmsh.model.occ.addPoint(+w_feed/2, y_port, h)
    p1_4 = gmsh.model.occ.addPoint(-w_feed/2, y_port, h)
    l1_1 = gmsh.model.occ.addLine(p1_1, p1_2)
    l1_2 = gmsh.model.occ.addLine(p1_2, p1_3)
    l1_3 = gmsh.model.occ.addLine(p1_3, p1_4)
    l1_4 = gmsh.model.occ.addLine(p1_4, p1_1)
    cl1 = gmsh.model.occ.addCurveLoop([l1_1, l1_2, l1_3, l1_4])
    port1_tag = gmsh.model.occ.addPlaneSurface([cl1])

    # Port 2 (left): YZ plane at x = x_port, y from -w_feed/2 to +w_feed/2
    p2_1 = gmsh.model.occ.addPoint(x_port, -w_feed/2, 0)
    p2_2 = gmsh.model.occ.addPoint(x_port, +w_feed/2, 0)
    p2_3 = gmsh.model.occ.addPoint(x_port, +w_feed/2, h)
    p2_4 = gmsh.model.occ.addPoint(x_port, -w_feed/2, h)
    l2_1 = gmsh.model.occ.addLine(p2_1, p2_2)
    l2_2 = gmsh.model.occ.addLine(p2_2, p2_3)
    l2_3 = gmsh.model.occ.addLine(p2_3, p2_4)
    l2_4 = gmsh.model.occ.addLine(p2_4, p2_1)
    cl2 = gmsh.model.occ.addCurveLoop([l2_1, l2_2, l2_3, l2_4])
    port2_tag = gmsh.model.occ.addPlaneSurface([cl2])

    # 10. Ground plane GND (z = 0)
    gnd_tag = gmsh.model.occ.addRectangle(-W_sub/2, -L_sub/2, 0, W_sub, L_sub)

    gmsh.model.occ.synchronize()

    # 11. Topological fragmentation (Boolean Fragments) for conformal mesh
    vols = gmsh.model.occ.getEntities(3)
    input_surfs = [(2, s) for s in metal_surfs] + [(2, gnd_tag), (2, port1_tag), (2, port2_tag)]

    _, out_map = gmsh.model.occ.fragment(vols, input_surfs)
    gmsh.model.occ.synchronize()

    # 12. Fragment tracking for physical groups
    pec_tags = []
    port1_tags = []
    port2_tags = []

    for idx, (dim, s_tag) in enumerate(input_surfs):
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
    params['port_tags'] = list(set(port1_tags + port2_tags))
    params['pec_tags'] = list(set(pec_tags))

    return sub_tag, air_tag


build_model = build_model_v3
