"""
antenna_geometry.py - Pure-Python modul pro analytické výpočty, trasování a geometrii Modelu 4.
Nezávislý na Gmsh i systémovém NumPy (využívá pouze standardní knihovnu Pythonu: math, dataclasses).
Sdílený mezi Gmsh 3D CAD modelem (geometry_v4.py) a KiCad 8 generátorem (kicad_generator.py).
"""

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Základní fyzikální a vysokofrekvenční konstanty
C_0_MM_GHZ = 299.792458       # Rychlost světla ve vakuu [mm * GHz]
ETA_0 = 376.7303135           # Vlnová impedance vakua [Ohm]
DESIGN_FREQ_GHZ = 2.3325      # Střední návrhová frekvence SDARS [GHz]
PORT_Z0 = 50.0                # Jmenovitá impedance portu [Ohm]
COORD_TOL = 1e-9
OVERLAP_DELTA = 0.05          # Záměrný přesah 50 µm pro eliminaci DRC mikro-mezer v KiCadu
MASK_CLEARANCE = 0.30         # Výchozí přesah nepájivé masky (solder mask clearance) [mm]


# ==============================================================================
# 1. ČISTÉ VYSOKOFREKVENČNÍ VÝPOČTY (STANDALONE RF FORMULAS)
# ==============================================================================

def calc_microstrip_eps_eff(w: float, h: float, eps_r: float) -> float:
    """Vypočte efektivní permitivitu mikropáskového vedení (Hammerstad & Jensen)."""
    u = float(w) / float(h)
    eps_eff = (eps_r + 1.0) / 2.0 + ((eps_r - 1.0) / 2.0) * (1.0 / math.sqrt(1.0 + 12.0 / u))
    return float(eps_eff)


def calc_microstrip_z0(w: float, h: float, eps_r: float) -> float:
    """Vypočte charakteristickou impedanci mikropáskového vedení Z0."""
    u = float(w) / float(h)
    eps_eff = calc_microstrip_eps_eff(w, h, eps_r)
    if u <= 1.0:
        z0 = (60.0 / math.sqrt(eps_eff)) * math.log(8.0 / u + 0.25 * u)
    else:
        z0 = (120.0 * math.pi / math.sqrt(eps_eff)) / (u + 1.393 + 0.667 * math.log(u + 1.444))
    return float(z0)


def synth_microstrip_w(z0_target: float, h: float, eps_r: float) -> float:
    """Syntetizuje šířku mikropásku w pro cílovou charakteristickou impedanci Z0 (Wheeler/Bahl)."""
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
    """Vypočte čtvrtvlnnou délku lambda_g / 4 v mm."""
    lambda_0 = C_0_MM_GHZ / float(freq_ghz)
    lambda_g = lambda_0 / math.sqrt(float(eps_eff))
    return float(lambda_g / 4.0)


# ==============================================================================
# 2. VEKTOROVÉ A TRASOVACÍ VÝPOČTY PRO VEDENÍ S OBLOUKY
# ==============================================================================

def _unit_vec(p_from: Tuple[float, float], p_to: Tuple[float, float]) -> Tuple[Tuple[float, float], float]:
    """Jednotkový směrový vektor a délka segmentu."""
    dx = float(p_to[0] - p_from[0])
    dy = float(p_to[1] - p_from[1])
    length = float(math.hypot(dx, dy))
    if length <= COORD_TOL:
        raise ValueError(f"Segment mezi {p_from} a {p_to} má nulovou délku.")
    return (dx / length, dy / length), length


def calc_curved_path_length(waypoints: List[Any], bend_radius: float) -> float:
    """
    Vypočte přesnou délku střednice ortogonální lomené čáry po nahrazení všech 90° rohů
    kruhovými oblouky o poloměru bend_radius.
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
                f"Segment {idx} ({pts[idx]} -> {pts[idx + 1]}) má délku "
                f"{seg_len:.3f} mm, což nestačí pro oblouky R={r:.3f} mm."
            )
        total_len += max(0.0, straight_len)

    # Každý vnitřní roh přispívá délkou čtvrtkruhu pi * R / 2
    total_len += (len(pts) - 2) * (0.5 * math.pi * r)
    return float(total_len)


def compute_curved_ribbon_outline(
    waypoints: List[Any],
    width: float,
    bend_radius: float,
    arc_samples: int = 16,
) -> List[Tuple[float, float]]:
    """
    Vrátí uzavřený 2D obrys [(x, y), ...] pásku o šířce `width` podél `waypoints`
    s plynulými oblouky o poloměru `bend_radius`.
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
            raise ValueError(f"Roh {i} není ortogonální (cross={cross:.4f}).")

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

        # Vzorkování oblouku pro levou a pravou hranu
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
    Vrátí uzavřený 2D obrys [(x, y), ...] vodorovného 50 Ohm kmitočtového kmene z (x_port, y_T)
    k otočené svislé příčce T-článku na x_T s plynulými vnitřními kruhovými zaobleními (fillety).
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
            f"Délka 50 Ohm vedení (x_bar_left - x_port = {x_bar_left - x_left:.2f} mm) "
            f"nestačí pro zaoblení T-článku r={r_f:.2f} mm."
        )

    pts: List[Tuple[float, float]] = []
    # 1. Spodní hrana 50 Ohm přívodu
    pts.append((x_left, y_center - hw_50))
    pts.append((x_fillet_start, y_center - hw_50))

    # 2. Spodní zaoblení (střed: x_fillet_start, y_center - d_t, úhel: +pi/2 -> 0)
    c_bot = (x_fillet_start, y_center - d_t)
    for s in range(1, arc_samples + 1):
        ang = (math.pi / 2.0) * (1.0 - float(s) / float(arc_samples))
        pts.append((c_bot[0] + r_f * math.cos(ang), c_bot[1] + r_f * math.sin(ang)))

    # 3. Spodní a pravá hrana svislé příčky
    pts.append((x_bar_right, y_center - d_t))
    pts.append((x_bar_right, y_center + d_t))

    # 4. Horní hrana příčky
    pts.append((x_bar_left, y_center + d_t))

    # 5. Horní zaoblení (střed: x_fillet_start, y_center + d_t, úhel: 0 -> -pi/2)
    c_top = (x_fillet_start, y_center + d_t)
    for s in range(1, arc_samples + 1):
        ang = -(math.pi / 2.0) * (float(s) / float(arc_samples))
        pts.append((c_top[0] + r_f * math.cos(ang), c_top[1] + r_f * math.sin(ang)))

    # 6. Horní hrana 50 Ohm přívodu a uzavření na levé hraně
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
    Vrátí uzavřený 2D obrys [(x, y), ...] čtvercového vyzařovacího flíčku W x L
    s obdélníkovými výřezy (notches) pro zanořené transformátory na spodní a levé straně.
    """
    half_W = float(W) / 2.0
    half_L = float(L) / 2.0
    notch_b_w = float(w_T_b) + 2.0 * float(gap_b)
    notch_l_h = float(w_T_l) + 2.0 * float(gap_l)

    pts: List[Tuple[float, float]] = []
    # 1. Pravý horní roh
    pts.append((half_W, half_L))
    # 2. Levý horní roh
    pts.append((-half_W, half_L))

    # 3. Levá hrana s levým zářezem
    if inset_l > 1e-6:
        pts.append((-half_W, notch_l_h / 2.0))
        pts.append((-half_W + inset_l, notch_l_h / 2.0))
        pts.append((-half_W + inset_l, -notch_l_h / 2.0))
        pts.append((-half_W, -notch_l_h / 2.0))

    # 4. Levý dolní roh
    pts.append((-half_W, -half_L))

    # 5. Dolní hrana se spodním zářezem
    if inset_b > 1e-6:
        pts.append((-notch_b_w / 2.0, -half_L))
        pts.append((-notch_b_w / 2.0, -half_L + inset_b))
        pts.append((notch_b_w / 2.0, -half_L + inset_b))
        pts.append((notch_b_w / 2.0, -half_L))

    # 6. Pravý dolní roh
    pts.append((half_W, -half_L))

    return [(float(p[0]), float(p[1])) for p in pts]


# ==============================================================================
# 3. VÝPOČET ANALÝZY TRASOVÁNÍ A PARAMETRŮ MODELU 4
# ==============================================================================

def compute_model4_routing(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Vypočte veškeré RF a geometrické souřadnice Modelu 4 v čistém Pythonu,
    včetně přesných trasovacích bodů obou 100 Ohm větví a rozměrů substrátu.
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

    # 2. Parametry čtvrtvlnného transformátoru
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

    # 3. Mělký zářez a mezery
    inset_b = float(params.get('feed_inset_b', params.get('inset_b', params.get('y0b', params.get('y0', params.get('feed_inset', 2.5))))))
    inset_l = float(params.get('feed_inset_l', params.get('inset_l', params.get('y0l', params.get('y0', params.get('feed_inset', 2.5))))))
    if inset_b < 0.0 or inset_l < 0.0:
        raise ValueError(f"Hloubka zanoření (inset) musí být nezáporná: inset_b={inset_b}, inset_l={inset_l}")

    inset_gap_b = float(params.get('inset_gap_b', params.get('feed_inset_gap_b', params.get('gap_b', params.get('inset_gap', params.get('feed_inset_gap', 0.5))))))
    inset_gap_l = float(params.get('inset_gap_l', params.get('feed_inset_gap_l', params.get('gap_l', params.get('inset_gap', params.get('feed_inset_gap', 0.5))))))

    # 4. Fázovací prodloužení delta_L v 100 Ohm vedení
    raw_delta_l = params.get('feed_delta_l', params.get('delta_l', params.get('phase_delay_mm', params.get('feed_delta'))))
    feed_delta_l = float(raw_delta_l) if raw_delta_l is not None else lambda_g_4_feed

    # 5. Parametry oblouků a otočeného T-článku
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

    raw_mask_clearance = params.get('mask_clearance', params.get('feed_mask_clearance'))
    mask_clearance = float(raw_mask_clearance) if raw_mask_clearance is not None else MASK_CLEARANCE

    # 6. Pozice vstupů transformátorů a vnějších referenčních os
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
                f"Zadané feed_y_T={y_T:.2f} mm vyžaduje y_bot={y_bot:.2f} mm pro fázování ΔL={feed_delta_l:.2f} mm, "
                f"což zkracuje úsek před spodním transformátorem na {s_end_b_check:.2f} mm (< {end_straight:.2f} mm)."
            )

    s_end_b = y_junc_b - y_bot - bend_radius
    s_T_up = -y_T - d_t - bend_radius
    if s_T_up < 0.5 - 1e-6:
        raise ValueError(
            f"Horní rovný úsek za blokem T-článku s_T_up={s_T_up:.2f} mm (y_T={y_T:.2f} mm, d_t={d_t:.2f} mm, "
            f"R={bend_radius:.2f} mm) musí být >= 0.5 mm."
        )

    s_T_down = (y_T - y_bot) - d_t - bend_radius
    if s_T_down < 0.5 - 1e-6:
        raise ValueError(
            f"Dolní rovný úsek za blokem T-článku s_T_down={s_T_down:.2f} mm (y_T={y_T:.2f} mm, y_bot={y_bot:.2f} mm, "
            f"d_t={d_t:.2f} mm, R={bend_radius:.2f} mm) musí být >= 0.5 mm."
        )

    # 8. Trasovací body (waypoints) od osy T-článku (x_T, y_T) k transformátorům
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

    # Stavební waypoints pro napojení bez překryvu na blok T-článku (y_T ± d_t)
    arm_l_build_waypoints = [(x_T, y_T + d_t)] + arm_l_waypoints_full[1:]
    arm_b_build_waypoints = [(x_T, y_T - d_t)] + arm_b_waypoints_full[1:]

    # 9. Poloha levého 50 Ohm portu a symetrické rozměry substrátu
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
# 4. KICAD GEOMETRIE A TRANSFORMACE SOUŘADNIC
# ==============================================================================

def transform_cad_to_kicad(pt: Tuple[float, float], origin_x: float, origin_y: float) -> Tuple[float, float]:
    """
    Převede kartézský CAD bod (OpenCASCADE: +X vpravo, +Y nahoru)
    do souřadnic KiCadu (+X vpravo, +Y dolů).
    x_kicad = origin_x + x_cad
    y_kicad = origin_y - y_cad
    Zajišťuje striktní zachování LHCP polarizace (brání vertikálnímu převrácení).
    """
    return (float(origin_x + pt[0]), float(origin_y - pt[1]))


def transform_poly_to_kicad(
    poly: List[Tuple[float, float]],
    origin_x: float,
    origin_y: float,
) -> List[Tuple[float, float]]:
    """Transformuje celý 2D polygon z CAD do KiCad souřadnic."""
    return [transform_cad_to_kicad(p, origin_x, origin_y) for p in poly]


@dataclass
class KiCadGeometryData:
    """Kompletní reprezentace geometrie pro export do KiCad 8."""
    origin_x: float
    origin_y: float
    W_sub: float
    L_sub: float
    edge_cuts_rect: Tuple[float, float, float, float]  # (x_min, y_min, x_max, y_max)
    rf_polygons: List[List[Tuple[float, float]]]       # F.Cu Net 2 (RF_IN)
    gnd_polygons_top: List[List[Tuple[float, float]]]   # F.Cu Net 1 (GND)
    gnd_polygon_bottom: List[Tuple[float, float]]       # B.Cu Net 1 (GND)
    vias: List[Dict[str, Any]]                          # GND prokovy
    mask_openings: List[List[Tuple[float, float]]]      # F.Mask otvory
    mask_openings_bottom: List[List[Tuple[float, float]]] # B.Mask otvory
    sma_top_pad_center: Tuple[float, float]
    sma_bot_pad_center: Tuple[float, float]
    sma_pad_size: Tuple[float, float]                   # (dx, dy) = (3.5, 1.5)
    routing_info: Dict[str, Any]


def get_model4_kicad_geometry(
    params: Dict[str, Any],
    origin_x: Optional[float] = None,
    origin_y: Optional[float] = None,
    is_footprint: bool = False,
    overlap_delta: float = OVERLAP_DELTA,
    mask_clearance: Optional[float] = None,
) -> KiCadGeometryData:
    """
    Vytvoří kompletní sadu KiCad 8 geometrických prvků (F.Cu, B.Cu, F.Mask, B.Mask, Edge.Cuts, Vias)
    včetně 50 µm přesahů pro eliminaci DRC mikro-mezer, odsazení nepájivé masky a SMA G-S-G rozhraní.
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

    if mask_clearance is None:
        raw_mc = params.get('mask_clearance', info.get('mask_clearance', MASK_CLEARANCE))
        mask_clearance = float(raw_mc) if raw_mc is not None else MASK_CLEARANCE
    else:
        mask_clearance = float(mask_clearance)

    # Nastavení počátku souřadnic:
    # Pro footprint: (0, 0) je střed vyzařovacího flíčku
    # Pro PCB: posun o okraj 25 mm pro kladné souřadnice desky
    if is_footprint:
        ox = float(origin_x) if origin_x is not None else 0.0
        oy = float(origin_y) if origin_y is not None else 0.0
    else:
        ox = float(origin_x) if origin_x is not None else (W_sub / 2.0 + 25.0)
        oy = float(origin_y) if origin_y is not None else (L_sub / 2.0 + 25.0)

    # 1. Edge.Cuts obdélník
    edge_x_min = ox - W_sub / 2.0
    edge_x_max = ox + W_sub / 2.0
    edge_y_min = oy - L_sub / 2.0
    edge_y_max = oy + L_sub / 2.0
    edge_cuts_rect = (edge_x_min, edge_y_min, edge_x_max, edge_y_max)

    # 2. RF Segmenty (všechny se sítí Net 2 "RF_IN") s přesahem overlap_delta = 50 µm
    delta = float(overlap_delta)

    # A) Vyzařující flíček se zářezy
    patch_cad = compute_patch_with_insets_polygon(
        W, L, inset_b, inset_l, w_T_b, w_T_l, inset_gap_b, inset_gap_l
    )
    patch_kicad = transform_poly_to_kicad(patch_cad, ox, oy)

    # B) Spodní čtvrtvlnný transformátor
    # Rozsah Y v CAD: od (y_junc_b - delta) do (-L/2 + inset_b + delta)
    # Rozsah X v CAD: od -w_T_b/2 do +w_T_b/2
    y_trans_b_start = y_junc_b - delta
    y_trans_b_end = -L / 2.0 + inset_b + delta
    trans_b_cad = [
        (-w_T_b / 2.0, y_trans_b_start),
        (w_T_b / 2.0, y_trans_b_start),
        (w_T_b / 2.0, y_trans_b_end),
        (-w_T_b / 2.0, y_trans_b_end),
    ]
    trans_b_kicad = transform_poly_to_kicad(trans_b_cad, ox, oy)

    # C) Levý čtvrtvlnný transformátor
    # Rozsah X v CAD: od (x_junc_l - delta) do (-W/2 + inset_l + delta)
    # Rozsah Y v CAD: od -w_T_l/2 do +w_T_l/2
    x_trans_l_start = x_junc_l - delta
    x_trans_l_end = -W / 2.0 + inset_l + delta
    trans_l_cad = [
        (x_trans_l_start, -w_T_l / 2.0),
        (x_trans_l_end, -w_T_l / 2.0),
        (x_trans_l_end, w_T_l / 2.0),
        (x_trans_l_start, w_T_l / 2.0),
    ]
    trans_l_kicad = transform_poly_to_kicad(trans_l_cad, ox, oy)

    # D) Levá zakřivená 100 Ohm větev (arm_l) s přesahem
    arm_l_wps = [
        (x_T, y_T + d_t - delta),
        (x_T, 0.0),
        (x_junc_l + delta, 0.0),
    ]
    arm_l_cad = compute_curved_ribbon_outline(arm_l_wps, w_feed, bend_radius)
    arm_l_kicad = transform_poly_to_kicad(arm_l_cad, ox, oy)

    # E) Spodní zakřivená 100 Ohm větev (arm_b) s přesahem
    arm_b_wps = [
        (x_T, y_T - d_t + delta),
        (x_T, y_bot),
        (0.0, y_bot),
        (0.0, y_junc_b + delta),
    ]
    arm_b_cad = compute_curved_ribbon_outline(arm_b_wps, w_feed, bend_radius)
    arm_b_kicad = transform_poly_to_kicad(arm_b_cad, ox, oy)

    # F) T-článek a 50 Ohm přívodní kmen
    # Kmen začíná na x_port = -W_sub/2 (levá hrana desky / střed signálového padu SMA)
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

    # 3. SMA Rozhraní (Cinch Johnson 142-0701-801) - G-S-G
    # Signálový pad je integrován v 50 Ohm přívodu: šířka w_50 = 2.98 mm, délka 3.5 mm od x_port.
    # Horní a spodní zemní plošky: šířka 1.50 mm, délka 3.50 mm, mezera g = 0.70 mm.
    # Horní GND pad CAD: x in [x_port, x_port + 3.5], y in [y_T + 2.19, y_T + 3.69]
    # Spodní GND pad CAD: x in [x_port, x_port + 3.5], y in [y_T - 3.69, y_T - 2.19]
    sma_pad_len = 3.50
    sma_pad_w = 1.50

    gnd_top_cad = [
        (x_port, y_T + 2.19),
        (x_port + sma_pad_len, y_T + 2.19),
        (x_port + sma_pad_len, y_T + 3.69),
        (x_port, y_T + 3.69),
    ]
    gnd_bot_cad = [
        (x_port, y_T - 3.69),
        (x_port + sma_pad_len, y_T - 3.69),
        (x_port + sma_pad_len, y_T - 2.19),
        (x_port, y_T - 2.19),
    ]
    gnd_polygons_top = [
        transform_poly_to_kicad(gnd_top_cad, ox, oy),
        transform_poly_to_kicad(gnd_bot_cad, ox, oy),
    ]

    # Středy SMA GND plošek v KiCad souřadnicích (pro footprint pady)
    top_center_cad = (x_port + sma_pad_len / 2.0, y_T + 2.94)
    bot_center_cad = (x_port + sma_pad_len / 2.0, y_T - 2.94)
    sma_top_pad_center = transform_cad_to_kicad(top_center_cad, ox, oy)
    sma_bot_pad_center = transform_cad_to_kicad(bot_center_cad, ox, oy)
    sma_pad_size = (sma_pad_len, sma_pad_w)

    # 4. Spodní celistvá zem na B.Cu (Net 1 "GND")
    b_cu_gnd_cad = [
        (-W_sub / 2.0, -L_sub / 2.0),
        (W_sub / 2.0, -L_sub / 2.0),
        (W_sub / 2.0, L_sub / 2.0),
        (-W_sub / 2.0, L_sub / 2.0),
    ]
    gnd_polygon_bottom = transform_poly_to_kicad(b_cu_gnd_cad, ox, oy)

    # 5. Zemní prokovy (Via Stitching 2x3 prokovy)
    vias: List[Dict[str, Any]] = []
    via_x_offsets = [1.0, 2.0, 3.0]
    for x_off in via_x_offsets:
        # Horní prokov
        pt_top = transform_cad_to_kicad((x_port + x_off, y_T + 2.94), ox, oy)
        vias.append({
            'x': round(pt_top[0], 4),
            'y': round(pt_top[1], 4),
            'drill': 0.30,
            'size': 0.60,
            'net': 1,
            'net_name': "GND",
        })
        # Spodní prokov
        pt_bot = transform_cad_to_kicad((x_port + x_off, y_T - 2.94), ox, oy)
        vias.append({
            'x': round(pt_bot[0], 4),
            'y': round(pt_bot[1], 4),
            'drill': 0.30,
            'size': 0.60,
            'net': 1,
            'net_name': "GND",
        })

    # 6. Otevření nepájivé masky s definovaným přesahem (solder mask clearance)
    # A) Jednolité otevření masky nad horním SMA rozhraním: 4.0 mm x 8.0 mm
    sma_mask_cad = [
        (x_port, y_T - 4.0),
        (x_port + 4.0, y_T - 4.0),
        (x_port + 4.0, y_T + 4.0),
        (x_port, y_T + 4.0),
    ]
    sma_mask_kicad = transform_poly_to_kicad(sma_mask_cad, ox, oy)

    # B) Otevření masky nad vyzařovacím flíčkem pro ENIG zlacení s přesahem mask_clearance na každé straně
    patch_mask_cad = [
        (-W / 2.0 - mask_clearance, -L / 2.0 - mask_clearance),
        (W / 2.0 + mask_clearance, -L / 2.0 - mask_clearance),
        (W / 2.0 + mask_clearance, L / 2.0 + mask_clearance),
        (-W / 2.0 - mask_clearance, L / 2.0 + mask_clearance),
    ]
    patch_mask_kicad = transform_poly_to_kicad(patch_mask_cad, ox, oy)

    # C) Spodní čtvrtvlnný transformátor rozšířený o mask_clearance v šířce i délce
    trans_b_mask_cad = [
        (-w_T_b / 2.0 - mask_clearance, y_trans_b_start - mask_clearance),
        (w_T_b / 2.0 + mask_clearance, y_trans_b_start - mask_clearance),
        (w_T_b / 2.0 + mask_clearance, y_trans_b_end + mask_clearance),
        (-w_T_b / 2.0 - mask_clearance, y_trans_b_end + mask_clearance),
    ]
    trans_b_mask_kicad = transform_poly_to_kicad(trans_b_mask_cad, ox, oy)

    # D) Levý čtvrtvlnný transformátor rozšířený o mask_clearance v šířce i délce
    trans_l_mask_cad = [
        (x_trans_l_start - mask_clearance, -w_T_l / 2.0 - mask_clearance),
        (x_trans_l_end + mask_clearance, -w_T_l / 2.0 - mask_clearance),
        (x_trans_l_end + mask_clearance, w_T_l / 2.0 + mask_clearance),
        (x_trans_l_start - mask_clearance, w_T_l / 2.0 + mask_clearance),
    ]
    trans_l_mask_kicad = transform_poly_to_kicad(trans_l_mask_cad, ox, oy)

    # E) Levá zakřivená 100 Ohm větev (arm_l) s šířkou w_feed + 2 * mask_clearance
    arm_l_mask_cad = compute_curved_ribbon_outline(
        arm_l_wps, w_feed + 2.0 * mask_clearance, bend_radius
    )
    arm_l_mask_kicad = transform_poly_to_kicad(arm_l_mask_cad, ox, oy)

    # F) Spodní zakřivená 100 Ohm větev (arm_b) s šířkou w_feed + 2 * mask_clearance
    arm_b_mask_cad = compute_curved_ribbon_outline(
        arm_b_wps, w_feed + 2.0 * mask_clearance, bend_radius
    )
    arm_b_mask_kicad = transform_poly_to_kicad(arm_b_mask_cad, ox, oy)

    # G) T-článek s rozšířenými šířkami w_50 + 2 * mask_clearance a w_feed + 2 * mask_clearance
    t_junc_mask_cad = compute_t_junction_polygon(
        x_port,
        x_T,
        y_T,
        w_50 + 2.0 * mask_clearance,
        w_feed + 2.0 * mask_clearance,
        t_fillet_r,
    )
    t_junc_mask_kicad = transform_poly_to_kicad(t_junc_mask_cad, ox, oy)

    # Celá sada otvorů horní masky na F.Mask
    mask_openings = [
        sma_mask_kicad,
        patch_mask_kicad,
        trans_b_mask_kicad,
        trans_l_mask_kicad,
        arm_l_mask_kicad,
        arm_b_mask_kicad,
        t_junc_mask_kicad,
    ]

    # H) Otevření spodní nepájivé masky na B.Mask pro SMA konektor (4.0 mm x 8.0 mm)
    sma_mask_bot_cad = [
        (x_port, y_T - 4.0),
        (x_port + 4.0, y_T - 4.0),
        (x_port + 4.0, y_T + 4.0),
        (x_port, y_T + 4.0),
    ]
    mask_openings_bottom = [
        transform_poly_to_kicad(sma_mask_bot_cad, ox, oy),
    ]

    return KiCadGeometryData(
        origin_x=ox,
        origin_y=oy,
        W_sub=W_sub,
        L_sub=L_sub,
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
    )
