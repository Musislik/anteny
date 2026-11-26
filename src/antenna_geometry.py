"""
antenna_geometry.py - Pure-Python module for analytical calculations, routing, and geometry of Model 4.
Independent of Gmsh and system NumPy (uses only the Python standard library: math, dataclasses).
Shared between the Gmsh 3D CAD model (geometry_v4.py) and the KiCad 10 generator (kicad_generator.py).
"""

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Fundamental physical and RF constants
C_0_MM_GHZ = 299.792458       # Speed of light in vacuum [mm * GHz]
ETA_0 = 376.7303135           # Free-space wave impedance [Ohm]
DESIGN_FREQ_GHZ = 2.3325      # SDARS center design frequency [GHz]
PORT_Z0 = 50.0                # Nominal port impedance [Ohm]
COORD_TOL = 1e-9
OVERLAP_DELTA = 0.05          # Intentional 50 µm overlap to eliminate DRC micro-gaps in KiCad
MASK_CLEARANCE = 0.30         # Default solder mask clearance [mm]
SMA_GAP = 0.70                # Default G-S-G gap between 50 Ohm trace and SMA GND pads [mm]
SMA_PAD_LEN = 3.50            # Default SMA GND pad length [mm]
SMA_PAD_W = 1.50              # Default SMA GND pad width [mm]


# ==============================================================================
# 1. PURE RF CALCULATIONS (STANDALONE RF FORMULAS)
# ==============================================================================

def calc_microstrip_eps_eff(w: float, h: float, eps_r: float) -> float:
    """Compute effective permittivity of a microstrip line (Hammerstad & Jensen)."""
    u = float(w) / float(h)
    eps_eff = (eps_r + 1.0) / 2.0 + ((eps_r - 1.0) / 2.0) * (1.0 / math.sqrt(1.0 + 12.0 / u))
    return float(eps_eff)


def calc_microstrip_z0(w: float, h: float, eps_r: float) -> float:
    """Compute characteristic impedance Z0 of a microstrip line."""
    u = float(w) / float(h)
    eps_eff = calc_microstrip_eps_eff(w, h, eps_r)
    if u <= 1.0:
        z0 = (60.0 / math.sqrt(eps_eff)) * math.log(8.0 / u + 0.25 * u)
    else:
        z0 = (120.0 * math.pi / math.sqrt(eps_eff)) / (u + 1.393 + 0.667 * math.log(u + 1.444))
    return float(z0)


def synth_microstrip_w(z0_target: float, h: float, eps_r: float) -> float:
    """Synthesize microstrip width w for target characteristic impedance Z0 (Wheeler/Bahl)."""
    z0 = float(z0_target)
    h_f = float(h)
    er = float(eps_r)
    a = (z0 / 60.0) * math.sqrt((er + 1.0) / 2.0) + ((er - 1.0) / (er + 1.0)) * (0.23 + 0.11 / er)
    b = (377.0 * math.pi) / (2.0 * z0 * math.sqrt(er))

    if a > 1.52:
        u = 8.0 * math.exp(a) / (math.exp(2.0 * a) - 2.0)
    else:
        u = (2.0 / math.pi) * (
            b - 1.0 - math.log(2.0 * b - 1.0) + ((er - 1.0) / (2.0 * er)) * (math.log(b - 1.0) + 0.39 - 0.61 / er)
        )

    w = u * h_f
    for _ in range(5):
        current_z0 = calc_microstrip_z0(w, h_f, er)
        diff = current_z0 - z0
        if abs(diff) < 1e-4:
            break
        dw = 1e-4
        z0_plus = calc_microstrip_z0(w + dw, h_f, er)
        dz_dw = (z0_plus - current_z0) / dw
        if abs(dz_dw) > 1e-12:
            w -= diff / dz_dw

    return float(w)


def calc_quarter_wave_length(freq_ghz: float, eps_eff: float) -> float:
    """Compute quarter-wavelength lambda_g / 4 in mm."""
    lambda_0 = C_0_MM_GHZ / float(freq_ghz)
    lambda_g = lambda_0 / math.sqrt(float(eps_eff))
    return float(lambda_g / 4.0)


# ==============================================================================
# 2. VECTOR AND ROUTING CALCULATIONS FOR CURVED TRACES
# ==============================================================================

def _unit_vec(p_from: Tuple[float, float], p_to: Tuple[float, float]) -> Tuple[Tuple[float, float], float]:
    """Unit direction vector and segment length."""
    dx = float(p_to[0] - p_from[0])
    dy = float(p_to[1] - p_from[1])
    length = float(math.hypot(dx, dy))
    if length <= COORD_TOL:
        raise ValueError(f"Segment between {p_from} and {p_to} has zero length.")
    return (dx / length, dy / length), length


def calc_curved_path_length(waypoints: List[Any], bend_radius: float) -> float:
    """
    Compute the exact centerline length of an orthogonal polyline after replacing all 90 deg corners
    with circular arcs of radius bend_radius.
    """
    pts = [(float(p[0]), float(p[1])) for p in waypoints]
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
                f"Segment {idx} ({pts[idx]} -> {pts[idx + 1]}) has length "
                f"{seg_len:.3f} mm, which is insufficient for arcs R={r:.3f} mm."
            )
        total_len += max(0.0, straight_len)

    # Each internal corner contributes a quarter-circle arc length pi * R / 2
    total_len += (len(pts) - 2) * (0.5 * math.pi * r)
    return float(total_len)


def compute_curved_ribbon_outline(
    waypoints: List[Any],
    width: float,
    bend_radius: float,
    arc_samples: int = 16,
) -> List[Tuple[float, float]]:
    """
    Return closed 2D outline [(x, y), ...] of a trace of width `width` along `waypoints`
    with smooth arcs of radius `bend_radius`.
    """
    pts = [(float(p[0]), float(p[1])) for p in waypoints]
    half_w = float(width) / 2.0
    r = float(bend_radius)
    n_pts = len(pts)

    dirs = []
    norms = []
    for i in range(n_pts - 1):
        u, _ = _unit_vec(pts[i], pts[i + 1])
        dirs.append(u)
        norms.append((-u[1], u[0]))

    left_pts = [(pts[0][0] + half_w * norms[0][0], pts[0][1] + half_w * norms[0][1])]
    right_pts = [(pts[0][0] - half_w * norms[0][0], pts[0][1] - half_w * norms[0][1])]

    for i in range(1, n_pts - 1):
        u_in = dirs[i - 1]
        u_out = dirs[i]
        n_in = norms[i - 1]
        n_out = norms[i]
        cross = float(u_in[0] * u_out[1] - u_in[1] * u_out[0])
        if abs(abs(cross) - 1.0) > 1e-5:
            raise ValueError(f"Corner {i} is not orthogonal (cross={cross:.4f}).")

        c = (
            pts[i][0] - r * u_in[0] + r * u_out[0],
            pts[i][1] - r * u_in[1] + r * u_out[1],
        )
        a = (pts[i][0] - r * u_in[0], pts[i][1] - r * u_in[1])
        b = (pts[i][0] + r * u_out[0], pts[i][1] + r * u_out[1])

        l_in = (a[0] + half_w * n_in[0], a[1] + half_w * n_in[1])
        l_out = (b[0] + half_w * n_out[0], b[1] + half_w * n_out[1])
        r_in = (a[0] - half_w * n_in[0], a[1] - half_w * n_in[1])
        r_out = (b[0] - half_w * n_out[0], b[1] - half_w * n_out[1])

        # Arc sampling for left and right edges
        for rail_list, p_start, p_end in (
            (left_pts, l_in, l_out),
            (right_pts, r_in, r_out),
        ):
            v_s = (p_start[0] - c[0], p_start[1] - c[1])
            v_e = (p_end[0] - c[0], p_end[1] - c[1])
            rad = math.hypot(v_s[0], v_s[1])
            ang_s = math.atan2(v_s[1], v_s[0])
            ang_e = math.atan2(v_e[1], v_e[0])
            d_ang = ang_e - ang_s
            while d_ang > math.pi:
                d_ang -= 2.0 * math.pi
            while d_ang < -math.pi:
                d_ang += 2.0 * math.pi
            for s in range(arc_samples + 1):
                t = float(s) / float(arc_samples)
                ang = ang_s + t * d_ang
                rail_list.append((c[0] + rad * math.cos(ang), c[1] + rad * math.sin(ang)))

    left_pts.append((pts[-1][0] + half_w * norms[-1][0], pts[-1][1] + half_w * norms[-1][1]))
    right_pts.append((pts[-1][0] - half_w * norms[-1][0], pts[-1][1] - half_w * norms[-1][1]))

    outline = left_pts + list(reversed(right_pts))
    return [(float(p[0]), float(p[1])) for p in outline]


def compute_t_junction_polygon(
    x_port: float,
    x_T: float,
    y_T: float,
    w_50: float,
    w_feed: float,
    t_fillet_r: float,
    arc_samples: int = 16,
) -> List[Tuple[float, float]]:
    """
    Return closed 2D outline [(x, y), ...] of the horizontal 50 Ohm feed trunk from (x_port, y_T)
    to the rotated vertical T-junction crossbar at x_T with smooth inner circular fillets.
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
        return [
            (x_left, y_center - hw_50),
            (x_bar_left, y_center - hw_50),
            (x_bar_left, y_center - d_t),
            (x_bar_right, y_center - d_t),
            (x_bar_right, y_center + d_t),
            (x_bar_left, y_center + d_t),
            (x_bar_left, y_center + hw_50),
            (x_left, y_center + hw_50),
        ]

    x_fillet_start = x_bar_left - r_f
    if x_fillet_start <= x_left + 1e-4:
        raise ValueError(
            f"50 Ohm line length (x_bar_left - x_port = {x_bar_left - x_left:.2f} mm) "
            f"is insufficient for T-junction fillet radius r={r_f:.2f} mm."
        )

    pts: List[Tuple[float, float]] = []
    # 1. Bottom edge of 50 Ohm feed
    pts.append((x_left, y_center - hw_50))
    pts.append((x_fillet_start, y_center - hw_50))

    # 2. Bottom fillet (center: x_fillet_start, y_center - d_t, angle: +pi/2 -> 0)
    c_bot = (x_fillet_start, y_center - d_t)
    for s in range(1, arc_samples + 1):
        ang = (math.pi / 2.0) * (1.0 - float(s) / float(arc_samples))
        pts.append((c_bot[0] + r_f * math.cos(ang), c_bot[1] + r_f * math.sin(ang)))

    # 3. Bottom and right edges of vertical crossbar
    pts.append((x_bar_right, y_center - d_t))
    pts.append((x_bar_right, y_center + d_t))

    # 4. Top edge of crossbar
    pts.append((x_bar_left, y_center + d_t))

    # 5. Top fillet (center: x_fillet_start, y_center + d_t, angle: 0 -> -pi/2)
    c_top = (x_fillet_start, y_center + d_t)
    for s in range(1, arc_samples + 1):
        ang = -(math.pi / 2.0) * (float(s) / float(arc_samples))
        pts.append((c_top[0] + r_f * math.cos(ang), c_top[1] + r_f * math.sin(ang)))

    # 6. Top edge of 50 Ohm feed and closing at left edge
    pts.append((x_left, y_center + hw_50))

    return [(float(p[0]), float(p[1])) for p in pts]


def compute_patch_with_insets_polygon(
    W: float,
    L: float,
    inset_b: float,
    inset_l: float,
    w_T_b: float,
    w_T_l: float,
    gap_b: float,
    gap_l: float,
) -> List[Tuple[float, float]]:
    """
    Return closed 2D outline [(x, y), ...] of the square radiating patch W x L
    with rectangular notches for inset transformers on the bottom and left sides.
    """
    half_W = float(W) / 2.0
    half_L = float(L) / 2.0
    notch_b_w = float(w_T_b) + 2.0 * float(gap_b)
    notch_l_h = float(w_T_l) + 2.0 * float(gap_l)

    pts: List[Tuple[float, float]] = []
    # 1. Top-right corner
    pts.append((half_W, half_L))
    # 2. Top-left corner
    pts.append((-half_W, half_L))

    # 3. Left edge with left notch
    if inset_l > 1e-6:
        pts.append((-half_W, notch_l_h / 2.0))
        pts.append((-half_W + inset_l, notch_l_h / 2.0))
        pts.append((-half_W + inset_l, -notch_l_h / 2.0))
        pts.append((-half_W, -notch_l_h / 2.0))

    # 4. Bottom-left corner
    pts.append((-half_W, -half_L))

    # 5. Bottom edge with bottom notch
    if inset_b > 1e-6:
        pts.append((-notch_b_w / 2.0, -half_L))
        pts.append((-notch_b_w / 2.0, -half_L + inset_b))
        pts.append((notch_b_w / 2.0, -half_L + inset_b))
        pts.append((notch_b_w / 2.0, -half_L))

    # 6. Bottom-right corner
    pts.append((half_W, -half_L))

    return [(float(p[0]), float(p[1])) for p in pts]


# ==============================================================================
# 3. ROUTING ANALYSIS AND PARAMETER COMPUTATION FOR MODEL 4
# ==============================================================================

def compute_model4_routing(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute all RF and geometric coordinates of Model 4 in pure Python,
    including exact routing waypoints of both 100 Ohm branches and substrate dimensions.
    """
    L = float(params['patch_L'])
    W = float(params.get('patch_W', L))
    h = float(params['sub_h'])
    eps_r = float(params['eps_r'])
    f_design = float(params.get('design_freq_ghz', DESIGN_FREQ_GHZ))
    port_z0 = float(params.get('port_impedance', PORT_Z0))

    # 1. Widths of 50 Ohm feed and 100 Ohm divider branches
    raw_w_50 = next((params[k] for k in ('feed_50_w', 'w_50', 'w1') if params.get(k) is not None), None)
    w_50 = float(raw_w_50) if raw_w_50 is not None else synth_microstrip_w(port_z0, h, eps_r)

    raw_w_100 = next(
        (params[k] for k in ('feed_100_w', 'w_feed', 'w_100', 'w2') if params.get(k) is not None),
        None,
    )
    w_feed = float(raw_w_100) if raw_w_100 is not None else synth_microstrip_w(2.0 * port_z0, h, eps_r)

    eps_eff_feed = calc_microstrip_eps_eff(w_feed, h, eps_r)
    lambda_g_4_feed = calc_quarter_wave_length(f_design, eps_eff_feed)

    # 2. Quarter-wave transformer parameters
    w_T_default = float(params.get('trans_w', params.get('w_T', params.get('w_trans', 0.42))))
    eps_eff_trans_def = calc_microstrip_eps_eff(w_T_default, h, eps_r)
    l_T_default = calc_quarter_wave_length(f_design, eps_eff_trans_def)

    w_T_b = float(params.get('trans_w_b', params.get('w_T_b', params.get('w_trans_b', w_T_default))))
    w_T_l = float(params.get('trans_w_l', params.get('w_T_l', params.get('w_trans_l', w_T_default))))

    raw_l_T_b = next((params[k] for k in ('trans_l_b', 'l_T_b', 'l_trans_b') if params.get(k) is not None), None)
    raw_l_T_l = next((params[k] for k in ('trans_l_l', 'l_T_l', 'l_trans_l') if params.get(k) is not None), None)
    raw_l_T_common = next((params[k] for k in ('trans_l', 'l_T', 'l_trans') if params.get(k) is not None), None)

    def _resolve_branch_trans_l(raw_branch: Optional[Any], w_branch: float) -> float:
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

    # 5. Arc and rotated T-junction parameters
    bend_radius = float(params.get('feed_bend_radius', params.get('bend_radius', 3.0)))
    if bend_radius <= (w_feed / 2.0) + 0.1:
        raise ValueError(
            f"Arc radius feed_bend_radius={bend_radius:.3f} mm must be greater than w_feed/2 + 0.1 ({w_feed/2.0 + 0.1:.3f} mm)."
        )

    t_fillet_r = float(params.get('feed_t_fillet_r', params.get('t_fillet_r', 0.8)))
    if t_fillet_r < 0.0:
        raise ValueError(f"T-junction fillet radius feed_t_fillet_r={t_fillet_r:.3f} mm must be non-negative.")

    raw_feed_50_len = next((params[k] for k in ('feed_50_len', 'l1') if params.get(k) is not None), None)
    feed_50_len = float(raw_feed_50_len) if raw_feed_50_len is not None else 9.0
    if feed_50_len <= t_fillet_r + 0.5:
        raise ValueError(
            f"50 Ohm feed length feed_50_len={feed_50_len:.2f} mm must be > feed_t_fillet_r + 0.5 ({t_fillet_r + 0.5:.2f} mm)."
        )

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

    raw_mask_clearance = params.get('mask_clearance', params.get('feed_mask_clearance'))
    mask_clearance = float(raw_mask_clearance) if raw_mask_clearance is not None else MASK_CLEARANCE

    # 6. Transformer entry positions and outer reference axes
    y_junc_b = -L / 2.0 + inset_b - l_T_b
    x_junc_l = -W / 2.0 + inset_l - l_T_l
    x_left_vert = x_junc_l - arm_offset
    y_bot_default = y_junc_b - end_straight - bend_radius

    # 7. Rotated T-junction position (x_T, y_T)
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
        # Analytical solution of equation L_100_b(y_T) - L_100_l(y_T) == feed_delta_l (no meander)
        y_T = 0.5 * (
            feed_delta_l
            + 2.0 * y_bot
            - y_junc_b
            + x_junc_l
            - (0.5 * math.pi - 2.0) * bend_radius
        )
    else:
        y_T = float(raw_y_T)
        y_bot = y_T - 0.5 * (
            feed_delta_l
            - y_junc_b
            + x_junc_l
            - (0.5 * math.pi - 2.0) * bend_radius
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
            f"Upper straight section past T-junction block s_T_up={s_T_up:.2f} mm (y_T={y_T:.2f} mm, d_t={d_t:.2f} mm, "
            f"R={bend_radius:.2f} mm) must be >= 0.5 mm."
        )

    s_T_down = (y_T - y_bot) - d_t - bend_radius
    if s_T_down < 0.5 - 1e-6:
        raise ValueError(
            f"Lower straight section past T-junction block s_T_down={s_T_down:.2f} mm (y_T={y_T:.2f} mm, y_bot={y_bot:.2f} mm, "
            f"d_t={d_t:.2f} mm, R={bend_radius:.2f} mm) must be >= 0.5 mm."
        )

    # 8. Waypoints from T-junction axis (x_T, y_T) to transformers
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

    # Build waypoints for overlap-free connection to the T-junction block (y_T ± d_t)
    arm_l_build_waypoints = [(x_T, y_T + d_t)] + arm_l_waypoints_full[1:]
    arm_b_build_waypoints = [(x_T, y_T - d_t)] + arm_b_waypoints_full[1:]

    # 9. Left 50 Ohm port position and symmetric substrate dimensions
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
        'mask_clearance': mask_clearance,
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
        'arm_l_waypoints': [(round(p[0], 4), round(p[1], 4)) for p in arm_l_waypoints_full],
        'arm_b_waypoints': [(round(p[0], 4), round(p[1], 4)) for p in arm_b_waypoints_full],
        'arm_l_build_waypoints': arm_l_build_waypoints,
        'arm_b_build_waypoints': arm_b_build_waypoints,
    }


# ==============================================================================
# 4. KICAD GEOMETRY AND COORDINATE TRANSFORMATIONS
# ==============================================================================

def transform_cad_to_kicad(pt: Tuple[float, float], origin_x: float, origin_y: float) -> Tuple[float, float]:
    """
    Convert a Cartesian CAD point (OpenCASCADE: +X right, +Y up)
    into KiCad coordinates (+X right, +Y down).
    x_kicad = origin_x + x_cad
    y_kicad = origin_y - y_cad
    Ensures strict preservation of LHCP polarization (prevents vertical flip).
    """
    return (float(origin_x + pt[0]), float(origin_y - pt[1]))


def transform_poly_to_kicad(
    poly: List[Tuple[float, float]],
    origin_x: float,
    origin_y: float,
) -> List[Tuple[float, float]]:
    """Transform an entire 2D polygon from CAD to KiCad coordinates."""
    return [transform_cad_to_kicad(p, origin_x, origin_y) for p in poly]


@dataclass
class KiCadGeometryData:
    """Complete geometry representation for KiCad 10 export."""
    origin_x: float
    origin_y: float
    W_sub: float
    L_sub: float
    edge_cuts_rect: Tuple[float, float, float, float]  # (x_min, y_min, x_max, y_max)
    rf_polygons: List[List[Tuple[float, float]]]       # F.Cu Net 2 (RF_IN)
    gnd_polygons_top: List[List[Tuple[float, float]]]   # F.Cu Net 1 (GND)
    gnd_polygon_bottom: List[Tuple[float, float]]       # B.Cu Net 1 (GND)
    vias: List[Dict[str, Any]]                          # GND vias
    mask_openings: List[List[Tuple[float, float]]]      # F.Mask openings
    mask_openings_bottom: List[List[Tuple[float, float]]] # B.Mask openings
    sma_top_pad_center: Tuple[float, float]
    sma_bot_pad_center: Tuple[float, float]
    sma_pad_size: Tuple[float, float]                   # (dx, dy) = (sma_pad_len, sma_pad_w)
    routing_info: Dict[str, Any]
    tight_pcb: bool = True
    sma_gap: float = SMA_GAP
    sma_mask_size: Tuple[float, float] = (4.0, 8.0)     # (dx, dy) = (sma_mask_len, 2 * sma_mask_half_h)
    mfg_corner_marks: List[List[Tuple[float, float]]] = field(default_factory=list)
    mfg_ident_polygons: List[List[Tuple[float, float]]] = field(default_factory=list)
    is_mirrored: bool = False


def compute_mfg_corner_marks(
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    mark_len: float = 8.0,
    mark_w: float = 2.0,
) -> List[List[Tuple[float, float]]]:
    """
    Compute 8 corner cut marks (2 rectangles per corner for all 4 corners) in CAD coordinates.
    Marks abut the outer edges of rectangle [x_min, x_max] x [y_min, y_max]
    per BUT antenna manufacturing guidelines (Manufacturing of antennas - instructions.pdf).
    All polygons are oriented counter-clockwise (CCW).
    """
    x1 = float(min(x_min, x_max))
    x2 = float(max(x_min, x_max))
    y1 = float(min(y_min, y_max))
    y2 = float(max(y_min, y_max))
    lm = float(mark_len)
    wm = float(mark_w)

    marks = [
        # 1. Top-Left: horizontal bar above edge, vertical bar left of edge
        [(x1, y2), (x1 + lm, y2), (x1 + lm, y2 + wm), (x1, y2 + wm)],
        [(x1 - wm, y2 - lm), (x1, y2 - lm), (x1, y2), (x1 - wm, y2)],
        # 2. Top-Right: horizontal bar above edge, vertical bar right of edge
        [(x2 - lm, y2), (x2, y2), (x2, y2 + wm), (x2 - lm, y2 + wm)],
        [(x2, y2 - lm), (x2 + wm, y2 - lm), (x2 + wm, y2), (x2, y2)],
        # 3. Bottom-Left: horizontal bar below edge, vertical bar left of edge
        [(x1, y1 - wm), (x1 + lm, y1 - wm), (x1 + lm, y1), (x1, y1)],
        [(x1 - wm, y1), (x1, y1), (x1, y1 + lm), (x1 - wm, y1 + lm)],
        # 4. Bottom-Right: horizontal bar below edge, vertical bar right of edge
        [(x2 - lm, y1 - wm), (x2, y1 - wm), (x2, y1), (x2 - lm, y1)],
        [(x2, y1), (x2 + wm, y1), (x2 + wm, y1 + lm), (x2, y1 + lm)],
    ]
    return marks


def compute_mfg_ident_polygons(
    text: str = "PM.",
    center_x: float = 0.0,
    base_y: float = 35.0,
    height: float = 5.0,
    stroke_w: float = 0.8,
    mirror: bool = False,
) -> List[List[Tuple[float, float]]]:
    """
    Create 2D polygons for the identification mark (default 'PM.') in CAD coordinates.
    When mirror=True, mirrors across the Y-axis (x -> -x) per item 4 of the manufacturing guidelines.
    """
    H = float(height)
    ws = float(stroke_w)
    by = float(base_y)

    polys: List[List[Tuple[float, float]]] = []

    clean_text = str(text).strip().upper()
    if clean_text in ("PM.", "PM"):
        # Stroke layout for 'P', 'M', and '.'
        wp = 3.2 * (H / 5.0)
        wm = 4.2 * (H / 5.0)
        spacing = 1.0 * (H / 5.0)
        w_dot = ws
        total_w = wp + spacing + wm + (spacing + w_dot if clean_text.endswith(".") else 0.0)
        start_x = float(center_x) - total_w / 2.0

        # P
        xp = start_x
        p_stem = [(xp, by), (xp + ws, by), (xp + ws, by + H), (xp, by + H)]
        p_top = [(xp + ws, by + H - ws), (xp + wp, by + H - ws), (xp + wp, by + H), (xp + ws, by + H)]
        p_mid = [
            (xp + ws, by + H * 0.45),
            (xp + wp, by + H * 0.45),
            (xp + wp, by + H * 0.45 + ws),
            (xp + ws, by + H * 0.45 + ws),
        ]
        p_right = [
            (xp + wp - ws, by + H * 0.45),
            (xp + wp, by + H * 0.45),
            (xp + wp, by + H),
            (xp + wp - ws, by + H),
        ]

        # M
        xm = xp + wp + spacing
        m_stem_l = [(xm, by), (xm + ws, by), (xm + ws, by + H), (xm, by + H)]
        m_stem_r = [(xm + wm - ws, by), (xm + wm, by), (xm + wm, by + H), (xm + wm - ws, by + H)]
        mid_x = xm + wm / 2.0
        y_apex = by + H * 0.25
        m_diag_l = [
            (xm + ws, by + H),
            (mid_x, y_apex + ws),
            (mid_x, y_apex),
            (xm + ws, by + H - ws * 1.4),
        ]
        m_diag_r = [
            (xm + wm - ws, by + H),
            (xm + wm - ws, by + H - ws * 1.4),
            (mid_x, y_apex),
            (mid_x, y_apex + ws),
        ]

        polys = [p_stem, p_top, p_mid, p_right, m_stem_l, m_stem_r, m_diag_l, m_diag_r]

        # Dot
        if clean_text.endswith("."):
            x_dot = xm + wm + spacing
            dot = [(x_dot, by), (x_dot + w_dot, by), (x_dot + w_dot, by + w_dot), (x_dot, by + w_dot)]
            polys.append(dot)
    else:
        # Generic simplified fallback for any other monogram
        tw = 8.0 * (H / 5.0)
        sx = float(center_x) - tw / 2.0
        polys = [[(sx, by), (sx + tw, by), (sx + tw, by + H), (sx, by + H)]]

    if mirror:
        # Mirror x -> -x and preserve CCW orientation by reversing vertex order
        polys = [[(-x, y) for (x, y) in poly][::-1] for poly in polys]

    return polys


def get_model4_kicad_geometry(
    params: Dict[str, Any],
    origin_x: Optional[float] = None,
    origin_y: Optional[float] = None,
    is_footprint: bool = False,
    overlap_delta: float = OVERLAP_DELTA,
    mask_clearance: Optional[float] = None,
    tight_pcb: Optional[bool] = None,
    sma_gap: Optional[float] = None,
    sma_pad_len: Optional[float] = None,
    sma_pad_w: Optional[float] = None,
    mfg_vut: Optional[bool] = None,
    ident_symbol: Optional[str] = None,
    mirror_x: Optional[bool] = None,
) -> KiCadGeometryData:
    """
    Create the complete set of KiCad 10 geometric elements (F.Cu, B.Cu, F.Mask, B.Mask, Edge.Cuts, Vias)
    including 50 µm overlaps to eliminate DRC micro-gaps, solder mask clearance, and SMA G-S-G interface.
    Supports compact board cropping (tight_pcb=True, default) saving ~40% of substrate area.
    """
    info = compute_model4_routing(params)

    W_sub = info['W_sub']
    L_sub = info['L_sub']
    W = info['W']
    L = info['L']
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
    x_port = info['x_port']
    y_bot = info['y_bot']
    x_junc_l = info['x_junc_l']
    y_junc_b = info['y_junc_b']

    if tight_pcb is None:
        raw_tp = params.get('tight_pcb', params.get('crop_pcb', True))
        if isinstance(raw_tp, str):
            tight_pcb = raw_tp.strip().lower() not in ('0', 'false', 'no', 'off')
        else:
            tight_pcb = bool(raw_tp)
    else:
        tight_pcb = bool(tight_pcb)

    margin_right = float(params.get('tight_margin_right', params.get('margin_right', params.get('crop_margin_right', 10.0))))
    margin_top = float(params.get('tight_margin_top', params.get('margin_top', params.get('crop_margin_top', 10.0))))
    margin_bottom = float(params.get('tight_margin_bottom', params.get('margin_bottom', params.get('crop_margin_bottom', 5.0))))

    if tight_pcb:
        cad_x_min = x_port
        cad_x_max = W / 2.0 + margin_right
        cad_y_min = y_bot - margin_bottom
        cad_y_max = L / 2.0 + margin_top
        effective_W_sub = cad_x_max - cad_x_min
        effective_L_sub = cad_y_max - cad_y_min
    else:
        cad_x_min = -W_sub / 2.0
        cad_x_max = W_sub / 2.0
        cad_y_min = -L_sub / 2.0
        cad_y_max = L_sub / 2.0
        effective_W_sub = W_sub
        effective_L_sub = L_sub

    info['tight_pcb'] = tight_pcb
    info['effective_W_sub'] = effective_W_sub
    info['effective_L_sub'] = effective_L_sub
    info['cad_x_min'] = cad_x_min
    info['cad_x_max'] = cad_x_max
    info['cad_y_min'] = cad_y_min
    info['cad_y_max'] = cad_y_max

    if mask_clearance is None:
        raw_mc = params.get('mask_clearance', info.get('mask_clearance', MASK_CLEARANCE))
        mask_clearance = float(raw_mc) if raw_mc is not None else MASK_CLEARANCE
    else:
        mask_clearance = float(mask_clearance)

    # Coordinate origin setup:
    # For footprint: (0, 0) is the center of the radiating patch
    # For PCB: shift by 25 mm margin for positive board coordinates
    if is_footprint:
        ox = float(origin_x) if origin_x is not None else 0.0
        oy = float(origin_y) if origin_y is not None else 0.0
    else:
        ox = float(origin_x) if origin_x is not None else (25.0 - cad_x_min)
        oy = float(origin_y) if origin_y is not None else (25.0 + cad_y_max)

    # 1. Edge.Cuts rectangle
    edge_x_min = ox + cad_x_min
    edge_x_max = ox + cad_x_max
    edge_y_min = oy - cad_y_max
    edge_y_max = oy - cad_y_min
    edge_cuts_rect = (edge_x_min, edge_y_min, edge_x_max, edge_y_max)

    # 2. RF segments (all on Net 2 "RF_IN") with overlap_delta = 50 µm
    delta = float(overlap_delta)

    # A) Radiating patch with inset notches
    patch_cad = compute_patch_with_insets_polygon(
        W, L, inset_b, inset_l, w_T_b, w_T_l, inset_gap_b, inset_gap_l
    )
    patch_kicad = transform_poly_to_kicad(patch_cad, ox, oy)

    # B) Bottom quarter-wave transformer
    # Y range in CAD: from (y_junc_b - delta) to (-L/2 + inset_b + delta)
    # X range in CAD: from -w_T_b/2 to +w_T_b/2
    y_trans_b_start = y_junc_b - delta
    y_trans_b_end = -L / 2.0 + inset_b + delta
    trans_b_cad = [
        (-w_T_b / 2.0, y_trans_b_start),
        (w_T_b / 2.0, y_trans_b_start),
        (w_T_b / 2.0, y_trans_b_end),
        (-w_T_b / 2.0, y_trans_b_end),
    ]
    trans_b_kicad = transform_poly_to_kicad(trans_b_cad, ox, oy)

    # C) Left quarter-wave transformer
    # X range in CAD: from (x_junc_l - delta) to (-W/2 + inset_l + delta)
    # Y range in CAD: from -w_T_l/2 to +w_T_l/2
    x_trans_l_start = x_junc_l - delta
    x_trans_l_end = -W / 2.0 + inset_l + delta
    trans_l_cad = [
        (x_trans_l_start, -w_T_l / 2.0),
        (x_trans_l_end, -w_T_l / 2.0),
        (x_trans_l_end, w_T_l / 2.0),
        (x_trans_l_start, w_T_l / 2.0),
    ]
    trans_l_kicad = transform_poly_to_kicad(trans_l_cad, ox, oy)

    # D) Left curved 100 Ohm branch (arm_l) with overlap
    arm_l_wps = [
        (x_T, y_T + d_t - delta),
        (x_T, 0.0),
        (x_junc_l + delta, 0.0),
    ]
    arm_l_cad = compute_curved_ribbon_outline(arm_l_wps, w_feed, bend_radius)
    arm_l_kicad = transform_poly_to_kicad(arm_l_cad, ox, oy)

    # E) Bottom curved 100 Ohm branch (arm_b) with overlap
    arm_b_wps = [
        (x_T, y_T - d_t + delta),
        (x_T, y_bot),
        (0.0, y_bot),
        (0.0, y_junc_b + delta),
    ]
    arm_b_cad = compute_curved_ribbon_outline(arm_b_wps, w_feed, bend_radius)
    arm_b_kicad = transform_poly_to_kicad(arm_b_cad, ox, oy)

    # F) T-junction and 50 Ohm feed trunk
    # Trunk starts at x_port = -W_sub/2 (left board edge / center of SMA signal pad)
    t_junc_cad = compute_t_junction_polygon(x_port, x_T, y_T, w_50, w_feed, t_fillet_r)
    t_junc_kicad = transform_poly_to_kicad(t_junc_cad, ox, oy)

    rf_polygons = [
        patch_kicad,
        trans_b_kicad,
        trans_l_kicad,
        arm_l_kicad,
        arm_b_kicad,
        t_junc_kicad,
    ]

    # 3. SMA Interface (Cinch Johnson 142-0701-801) - G-S-G (parametric w.r.t. w_50)
    # Signal pad is integrated into the 50 Ohm feed of width w_50 starting at x_port.
    # Top and bottom ground pads are dynamically placed with sma_gap clearance from the 50 Ohm trace edges.
    if sma_gap is None:
        raw_sma_gap = next(
            (params[k] for k in ('sma_gap', 'sma_gsg_gap', 'feed_sma_gap') if params.get(k) is not None),
            None,
        )
        sma_gap_val = float(raw_sma_gap) if raw_sma_gap is not None else SMA_GAP
    else:
        sma_gap_val = float(sma_gap)

    if sma_pad_len is None:
        raw_sma_pad_len = next(
            (params[k] for k in ('sma_pad_len', 'sma_gnd_pad_len', 'sma_pad_length') if params.get(k) is not None),
            None,
        )
        sma_pad_len_val = float(raw_sma_pad_len) if raw_sma_pad_len is not None else SMA_PAD_LEN
    else:
        sma_pad_len_val = float(sma_pad_len)

    if sma_pad_w is None:
        raw_sma_pad_w = next(
            (params[k] for k in ('sma_pad_w', 'sma_gnd_pad_w', 'sma_pad_width') if params.get(k) is not None),
            None,
        )
        sma_pad_w_val = float(raw_sma_pad_w) if raw_sma_pad_w is not None else SMA_PAD_W
    else:
        sma_pad_w_val = float(sma_pad_w)

    if sma_gap_val <= 0.0:
        raise ValueError(f"SMA G-S-G gap sma_gap={sma_gap_val:.4f} mm must be positive (> 0).")
    if sma_pad_len_val <= 0.0:
        raise ValueError(f"SMA GND pad length sma_pad_len={sma_pad_len_val:.4f} mm must be positive (> 0).")
    if sma_pad_w_val <= 0.0:
        raise ValueError(f"SMA GND pad width sma_pad_w={sma_pad_w_val:.4f} mm must be positive (> 0).")

    sma_gnd_inner = w_50 / 2.0 + sma_gap_val
    sma_gnd_outer = sma_gnd_inner + sma_pad_w_val
    sma_gnd_center_y = sma_gnd_inner + sma_pad_w_val / 2.0
    sma_mask_len = max(4.0, sma_pad_len_val + 0.5)
    sma_mask_half_h = max(4.0, sma_gnd_outer + max(mask_clearance, 0.31))

    # Solder mask dam in the G-S-G gap between RF_IN and GND on F.Mask
    # Prevents solder bridging when soldering the SMA connector and eliminates KiCad DRC solder_mask_bridge error
    sma_mask_dam = min(0.15, 0.25 * sma_gap_val)
    sma_gnd_mask_inner = min(
        sma_gnd_inner,
        max(w_50 / 2.0 + mask_clearance + sma_mask_dam, sma_gnd_inner - mask_clearance),
    )

    info['mask_clearance'] = mask_clearance
    info['sma_gap'] = sma_gap_val
    info['sma_pad_len'] = sma_pad_len_val
    info['sma_pad_w'] = sma_pad_w_val
    info['sma_gnd_inner'] = sma_gnd_inner
    info['sma_gnd_outer'] = sma_gnd_outer
    info['sma_gnd_center_y'] = sma_gnd_center_y
    info['sma_mask_len'] = sma_mask_len
    info['sma_mask_half_h'] = sma_mask_half_h
    info['sma_mask_dam'] = sma_mask_dam
    info['sma_gnd_mask_inner'] = sma_gnd_mask_inner

    gnd_top_cad = [
        (x_port, y_T + sma_gnd_inner),
        (x_port + sma_pad_len_val, y_T + sma_gnd_inner),
        (x_port + sma_pad_len_val, y_T + sma_gnd_outer),
        (x_port, y_T + sma_gnd_outer),
    ]
    gnd_bot_cad = [
        (x_port, y_T - sma_gnd_outer),
        (x_port + sma_pad_len_val, y_T - sma_gnd_outer),
        (x_port + sma_pad_len_val, y_T - sma_gnd_inner),
        (x_port, y_T - sma_gnd_inner),
    ]
    gnd_polygons_top = [
        transform_poly_to_kicad(gnd_top_cad, ox, oy),
        transform_poly_to_kicad(gnd_bot_cad, ox, oy),
    ]

    # Centers of SMA GND pads in KiCad coordinates (for footprint pads)
    top_center_cad = (x_port + sma_pad_len_val / 2.0, y_T + sma_gnd_center_y)
    bot_center_cad = (x_port + sma_pad_len_val / 2.0, y_T - sma_gnd_center_y)
    sma_top_pad_center = transform_cad_to_kicad(top_center_cad, ox, oy)
    sma_bot_pad_center = transform_cad_to_kicad(bot_center_cad, ox, oy)
    sma_pad_size = (sma_pad_len_val, sma_pad_w_val)

    # 4. Bottom solid ground plane on B.Cu (Net 1 "GND")
    b_cu_gnd_cad = [
        (cad_x_min, cad_y_min),
        (cad_x_max, cad_y_min),
        (cad_x_max, cad_y_max),
        (cad_x_min, cad_y_max),
    ]
    gnd_polygon_bottom = transform_poly_to_kicad(b_cu_gnd_cad, ox, oy)

    # 5. Ground vias (via stitching: 2x3 vias centered in SMA GND pads)
    vias: List[Dict[str, Any]] = []
    if sma_pad_len_val > 1.0:
        via_x_min = 1.0 if sma_pad_len_val >= 3.0 else 0.5
        via_x_max = sma_pad_len_val - 0.5
        via_x_offsets = [
            via_x_min,
            0.5 * (via_x_min + via_x_max),
            via_x_max,
        ]
    else:
        via_x_offsets = [
            0.25 * sma_pad_len_val,
            0.50 * sma_pad_len_val,
            0.75 * sma_pad_len_val,
        ]

    for x_off in via_x_offsets:
        # Top via
        pt_top = transform_cad_to_kicad((x_port + x_off, y_T + sma_gnd_center_y), ox, oy)
        vias.append({
            'x': round(pt_top[0], 4),
            'y': round(pt_top[1], 4),
            'drill': 0.30,
            'size': 0.60,
            'net': 1,
            'net_name': "GND",
        })
        # Bottom via
        pt_bot = transform_cad_to_kicad((x_port + x_off, y_T - sma_gnd_center_y), ox, oy)
        vias.append({
            'x': round(pt_bot[0], 4),
            'y': round(pt_bot[1], 4),
            'drill': 0.30,
            'size': 0.60,
            'net': 1,
            'net_name': "GND",
        })

    # 6. Solder mask openings with defined clearance
    # A) Separate F.Mask openings over top and bottom SMA GND pads (with mask dam from 50 Ohm RF_IN)
    #    50 Ohm RF_IN feed has its own F.Mask opening in t_junc_mask_kicad -> clean dam without solder_mask_bridge
    sma_gnd_mask_top_cad = [
        (x_port, y_T + sma_gnd_mask_inner),
        (x_port + sma_mask_len, y_T + sma_gnd_mask_inner),
        (x_port + sma_mask_len, y_T + sma_mask_half_h),
        (x_port, y_T + sma_mask_half_h),
    ]
    sma_gnd_mask_bot_cad = [
        (x_port, y_T - sma_mask_half_h),
        (x_port + sma_mask_len, y_T - sma_mask_half_h),
        (x_port + sma_mask_len, y_T - sma_gnd_mask_inner),
        (x_port, y_T - sma_gnd_mask_inner),
    ]
    sma_gnd_mask_top_kicad = transform_poly_to_kicad(sma_gnd_mask_top_cad, ox, oy)
    sma_gnd_mask_bot_kicad = transform_poly_to_kicad(sma_gnd_mask_bot_cad, ox, oy)

    # B) Mask opening over radiating patch for ENIG gold plating with mask_clearance on each side
    patch_mask_cad = [
        (-W / 2.0 - mask_clearance, -L / 2.0 - mask_clearance),
        (W / 2.0 + mask_clearance, -L / 2.0 - mask_clearance),
        (W / 2.0 + mask_clearance, L / 2.0 + mask_clearance),
        (-W / 2.0 - mask_clearance, L / 2.0 + mask_clearance),
    ]
    patch_mask_kicad = transform_poly_to_kicad(patch_mask_cad, ox, oy)

    # C) Bottom quarter-wave transformer expanded by mask_clearance in both width and length
    trans_b_mask_cad = [
        (-w_T_b / 2.0 - mask_clearance, y_trans_b_start - mask_clearance),
        (w_T_b / 2.0 + mask_clearance, y_trans_b_start - mask_clearance),
        (w_T_b / 2.0 + mask_clearance, y_trans_b_end + mask_clearance),
        (-w_T_b / 2.0 - mask_clearance, y_trans_b_end + mask_clearance),
    ]
    trans_b_mask_kicad = transform_poly_to_kicad(trans_b_mask_cad, ox, oy)

    # D) Left quarter-wave transformer expanded by mask_clearance in both width and length
    trans_l_mask_cad = [
        (x_trans_l_start - mask_clearance, -w_T_l / 2.0 - mask_clearance),
        (x_trans_l_end + mask_clearance, -w_T_l / 2.0 - mask_clearance),
        (x_trans_l_end + mask_clearance, w_T_l / 2.0 + mask_clearance),
        (x_trans_l_start - mask_clearance, w_T_l / 2.0 + mask_clearance),
    ]
    trans_l_mask_kicad = transform_poly_to_kicad(trans_l_mask_cad, ox, oy)

    # E) Left curved 100 Ohm branch (arm_l) with width w_feed + 2 * mask_clearance
    arm_l_mask_cad = compute_curved_ribbon_outline(
        arm_l_wps, w_feed + 2.0 * mask_clearance, bend_radius
    )
    arm_l_mask_kicad = transform_poly_to_kicad(arm_l_mask_cad, ox, oy)

    # F) Bottom curved 100 Ohm branch (arm_b) with width w_feed + 2 * mask_clearance
    arm_b_mask_cad = compute_curved_ribbon_outline(
        arm_b_wps, w_feed + 2.0 * mask_clearance, bend_radius
    )
    arm_b_mask_kicad = transform_poly_to_kicad(arm_b_mask_cad, ox, oy)

    # G) T-junction with expanded widths w_50 + 2 * mask_clearance and w_feed + 2 * mask_clearance
    t_junc_mask_cad = compute_t_junction_polygon(
        x_port,
        x_T,
        y_T,
        w_50 + 2.0 * mask_clearance,
        w_feed + 2.0 * mask_clearance,
        t_fillet_r,
    )
    t_junc_mask_kicad = transform_poly_to_kicad(t_junc_mask_cad, ox, oy)

    # Complete set of top mask openings on F.Mask
    mask_openings = [
        sma_gnd_mask_top_kicad,
        sma_gnd_mask_bot_kicad,
        patch_mask_kicad,
        trans_b_mask_kicad,
        trans_l_mask_kicad,
        arm_l_mask_kicad,
        arm_b_mask_kicad,
        t_junc_mask_kicad,
    ]

    # H) Bottom solder mask opening on B.Mask for SMA connector (dynamic per G-S-G width)
    sma_mask_bot_cad = [
        (x_port, y_T - sma_mask_half_h),
        (x_port + sma_mask_len, y_T - sma_mask_half_h),
        (x_port + sma_mask_len, y_T + sma_mask_half_h),
        (x_port, y_T + sma_mask_half_h),
    ]
    mask_openings_bottom = [
        transform_poly_to_kicad(sma_mask_bot_cad, ox, oy),
    ]

    # I) Manufacturing features per BUT guidelines (Manufacturing of antennas - instructions.pdf)
    if mfg_vut is None:
        raw_mfg = params.get('mfg_vut', params.get('mfg', False))
        mfg_vut = (raw_mfg.strip().lower() not in ('0', 'false', 'no', 'off')) if isinstance(raw_mfg, str) else bool(raw_mfg)

    if ident_symbol is None:
        ident_symbol = str(params.get('ident_symbol', 'PM.'))

    if mirror_x is None:
        raw_mir = params.get('mirror_x', params.get('mirror', False))
        mirror_x = (raw_mir.strip().lower() not in ('0', 'false', 'no', 'off')) if isinstance(raw_mir, str) else bool(raw_mir)

    mfg_corner_marks: List[List[Tuple[float, float]]] = []
    mfg_ident_polygons: List[List[Tuple[float, float]]] = []

    if mfg_vut:
        # 1. 8 corner cut marks at substrate outline corners
        marks_cad = compute_mfg_corner_marks(cad_x_min, cad_x_max, cad_y_min, cad_y_max)
        mfg_corner_marks = [transform_poly_to_kicad(p, ox, oy) for p in marks_cad]

        # 2. Identification mark (default 'PM.') above top substrate edge
        ident_cad = compute_mfg_ident_polygons(
            text=ident_symbol,
            center_x=(cad_x_min + cad_x_max) / 2.0,
            base_y=cad_y_max + 4.0,
            height=5.0,
            mirror=False,
        )
        mfg_ident_polygons = [transform_poly_to_kicad(p, ox, oy) for p in ident_cad]

    # Global horizontal reflection (x -> -x) for photolithography film preparation (mirror_x=True)
    if mirror_x:
        x_reflect = edge_x_min + edge_x_max

        def _mirror_poly(poly: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
            return [(x_reflect - p[0], p[1]) for p in poly][::-1]

        rf_polygons = [_mirror_poly(p) for p in rf_polygons]
        gnd_polygons_top = [_mirror_poly(p) for p in gnd_polygons_top]
        gnd_polygon_bottom = _mirror_poly(gnd_polygon_bottom)
        mask_openings = [_mirror_poly(p) for p in mask_openings]
        mask_openings_bottom = [_mirror_poly(p) for p in mask_openings_bottom]
        if mfg_corner_marks:
            mfg_corner_marks = [_mirror_poly(p) for p in mfg_corner_marks]
        if mfg_ident_polygons:
            mfg_ident_polygons = [_mirror_poly(p) for p in mfg_ident_polygons]

        vias = [
            {'x': x_reflect - v['x'], 'y': v['y'], 'size': v['size'], 'drill': v['drill']}
            for v in vias
        ]
        sma_top_pad_center = (x_reflect - sma_top_pad_center[0], sma_top_pad_center[1])
        sma_bot_pad_center = (x_reflect - sma_bot_pad_center[0], sma_bot_pad_center[1])

    return KiCadGeometryData(
        origin_x=ox,
        origin_y=oy,
        W_sub=effective_W_sub,
        L_sub=effective_L_sub,
        edge_cuts_rect=edge_cuts_rect,
        rf_polygons=rf_polygons,
        gnd_polygons_top=gnd_polygons_top,
        gnd_polygon_bottom=gnd_polygon_bottom,
        vias=vias,
        mask_openings=mask_openings,
        mask_openings_bottom=mask_openings_bottom,
        sma_top_pad_center=sma_top_pad_center,
        sma_bot_pad_center=sma_bot_pad_center,
        sma_pad_size=sma_pad_size,
        routing_info=info,
        tight_pcb=tight_pcb,
        sma_gap=sma_gap_val,
        sma_mask_size=(sma_mask_len, 2.0 * sma_mask_half_h),
        mfg_corner_marks=mfg_corner_marks,
        mfg_ident_polygons=mfg_ident_polygons,
        is_mirrored=bool(mirror_x),
    )
