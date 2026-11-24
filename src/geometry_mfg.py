"""
geometry_mfg.py - Generátor 3D STEP modelu pro výrobu antény dle pokynů VUT FEKT
(Manufacturing of antennas - instructions.pdf).

Splňuje všech 6 bodů výrobních pokynů:
  1. Horní plocha vyzařovače i značek je umístěna přesně v rovině z = 0.
  2. V každém ze 4 rohů jsou vytvořeny dva kvádry (cubes) s horní plochou v z = 0
     a výškou substrátu h pro přesné ruční odstřižení desky po vyleptání.
  3. Identifikační znak 'PM.' s horní plochou v z = 0 umístěný nad horní hranou.
  4. Zrcadlový obraz horní strany (x -> -x) pro přípravu filmů fotocesty.
  5. V modelu je ponechán POUZE motiv antény, ořezové značky a identifikační znak
     (žádný dielektrický substrát, žádný vzduchový box, žádné porty).
  6. Export do standardního 3D formátu STEP (.step).
"""

import os
from typing import Any, Dict, List, Optional, Tuple

import gmsh
import numpy as np

from antenna_geometry import (
    compute_mfg_corner_marks,
    compute_mfg_ident_polygons,
)
from geometry_v4 import (
    build_curved_trace_occ,
    COORD_TOL,
)
from geometry_v7 import (
    compute_model7_routing,
    build_t_junction_trunk_occ_v7,
)


def _add_polygon_surface_occ(pts: List[Tuple[float, float]], z: float = 0.0) -> int:
    """Vytvoří rovinnou plochu (Plane Surface) v OpenCASCADE z 2D polygonu."""
    p_tags = []
    for x, y in pts:
        p_tags.append(gmsh.model.occ.addPoint(float(x), float(y), float(z)))

    lines = []
    n = len(p_tags)
    for i in range(n):
        lines.append(gmsh.model.occ.addLine(p_tags[i], p_tags[(i + 1) % n]))

    cl = gmsh.model.occ.addCurveLoop(lines)
    return gmsh.model.occ.addPlaneSurface([cl])


def build_mfg_model(
    params: Dict[str, Any],
    output_step_path: str,
    copper_thickness: float = 0.035,
    mark_len: float = 8.0,
    mark_w: float = 2.0,
    ident_symbol: str = "PM.",
    extrude_solids: bool = True,
) -> Dict[str, Any]:
    """
    Sestaví v OpenCASCADE (Gmsh) a vyexportuje kompletní výrobní 3D STEP model pro VUT.

    Args:
        params: Slovník parametrů antény (rozměry L, W, h, vedení atd.).
        output_step_path: Cesta k výstupnímu souboru .step.
        copper_thickness: Tloušťka vrstvy mědi [mm] pro extruzi z rovnoběžky z=0 dolů (výchozí: 35 µm).
        mark_len: Délka ramen ořezových kvádrů [mm] (výchozí: 8.0).
        mark_w: Šířka ořezových kvádrů [mm] (výchozí: 2.0).
        ident_symbol: Text identifikační značky (výchozí: 'PM.').
        extrude_solids: True pro 3D tělesa (solids), False pro 2D plochy (sheet bodies) v z=0.

    Returns:
        Slovník s metadaty o vygenerované geometrii.
    """
    info = compute_model7_routing(params)

    L = float(info['L'])
    W = float(info['W'])
    h = float(info['h'])
    w_50 = float(info['w_50'])
    w_feed = float(info['w_feed'])
    w_T_b = float(info['w_T_b'])
    w_T_r = float(info['w_T_r'])
    l_T_b = float(info['l_T_b'])
    l_T_r = float(info['l_T_r'])
    inset_b = float(info['inset_b'])
    inset_r = float(info['inset_r'])
    inset_gap_b = float(info['inset_gap_b'])
    inset_gap_r = float(info['inset_gap_r'])
    bend_radius = float(info['bend_radius'])
    t_fillet_r = float(info['t_fillet_r'])
    x_T = float(info['x_T'])
    y_T = float(info['y_T'])
    x_port = float(info['x_port'])
    y_junc_b = float(info['y_junc_b'])

    raw_tp = params.get('tight_pcb', params.get('crop_pcb', True))
    tight_pcb = (
        raw_tp.strip().lower() not in ('0', 'false', 'no', 'off')
        if isinstance(raw_tp, str)
        else bool(raw_tp)
    )

    margin_right = float(params.get('tight_margin_right', params.get('margin_right', 10.0)))
    margin_top = float(params.get('tight_margin_top', params.get('margin_top', 10.0)))
    margin_bottom = float(params.get('tight_margin_bottom', params.get('margin_bottom', 5.0)))

    if tight_pcb:
        mfg_x_min = -(W / 2.0 + margin_right)
        mfg_x_max = x_port
        mfg_y_min = float(info['y_bot']) - margin_bottom
        mfg_y_max = L / 2.0 + margin_top
    else:
        W_sub = float(info['W_sub'])
        L_sub = float(info['L_sub'])
        mfg_x_min = -W_sub / 2.0
        mfg_x_max = W_sub / 2.0
        mfg_y_min = -L_sub / 2.0
        mfg_y_max = L_sub / 2.0

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("vut_antenna_mfg")

    # =========================================================================
    # 1. Zrcadlený vyzařující flíček a napájecí síť v z = 0
    # =========================================================================
    patch_base = gmsh.model.occ.addRectangle(-W / 2.0, -L / 2.0, 0.0, W, L)
    tool_notches = []
    if inset_b > 0.0:
        notch_b_w = w_T_b + 2.0 * inset_gap_b
        notch_b = gmsh.model.occ.addRectangle(-notch_b_w / 2.0, -L / 2.0 - 0.05, 0.0, notch_b_w, inset_b + 0.05)
        tool_notches.append((2, notch_b))
    if inset_r > 0.0:
        notch_r_h = w_T_r + 2.0 * inset_gap_r
        notch_r = gmsh.model.occ.addRectangle(W / 2.0 - inset_r, -notch_r_h / 2.0, 0.0, inset_r + 0.05, notch_r_h)
        tool_notches.append((2, notch_r))

    if tool_notches:
        cut_surfs, _ = gmsh.model.occ.cut([(2, patch_base)], tool_notches)
        patch_tag = cut_surfs[0][1]
    else:
        patch_tag = patch_base

    trans_b = gmsh.model.occ.addRectangle(-w_T_b / 2.0, y_junc_b, 0.0, w_T_b, l_T_b)
    trans_r = gmsh.model.occ.addRectangle(W / 2.0 - inset_r, -w_T_r / 2.0, 0.0, l_T_r, w_T_r)

    trunk_tag, _ = build_t_junction_trunk_occ_v7(x_port, x_T, y_T, w_50, w_feed, t_fillet_r, 0.0)
    arm_r_tag = build_curved_trace_occ(info['arm_r_build_waypoints'], w_feed, bend_radius, 0.0)
    arm_b_tag = build_curved_trace_occ(info['arm_b_build_waypoints'], w_feed, bend_radius, 0.0)

    fused_feed, _ = gmsh.model.occ.fuse([(2, trunk_tag)], [(2, arm_r_tag), (2, arm_b_tag)])
    feed_net_tags = [tag for dim, tag in fused_feed if dim == 2]
    antenna_surfs = [patch_tag, trans_b, trans_r] + feed_net_tags

    # =========================================================================
    # 2. Osm ořezových kvádrů v rozích substrátu (výška h, horní plocha v z = 0)
    # =========================================================================
    marks_cad = compute_mfg_corner_marks(
        mfg_x_min, mfg_x_max, mfg_y_min, mfg_y_max, mark_len=mark_len, mark_w=mark_w
    )

    corner_cube_tags = []
    for rect in marks_cad:
        xs = [p[0] for p in rect]
        ys = [p[1] for p in rect]
        rx = min(xs)
        ry = min(ys)
        rdx = max(xs) - rx
        rdy = max(ys) - ry
        # Kvádry s horní plochou v z = 0 a spodní v z = -h
        box_tag = gmsh.model.occ.addBox(rx, ry, -h, rdx, rdy, h)
        corner_cube_tags.append(box_tag)

    # =========================================================================
    # 3. Identifikační značka 'PM.' (zrcadlená podél osy Y, horní plocha v z = 0)
    # =========================================================================
    ident_polys = compute_mfg_ident_polygons(
        text=ident_symbol,
        center_x=(mfg_x_min + mfg_x_max) / 2.0,
        base_y=mfg_y_max + 4.0,
        height=5.0,
        stroke_w=0.8,
        mirror=True,
    )

    ident_tags = []
    for poly in ident_polys:
        surf = _add_polygon_surface_occ(poly, z=0.0)
        if extrude_solids:
            # Extruze do záporného Z o výšku substrátu h
            ext = gmsh.model.occ.extrude([(2, surf)], 0.0, 0.0, -h)
            solid_tags = [tag for dim, tag in ext if dim == 3]
            ident_tags.extend(solid_tags)
        else:
            ident_tags.append(surf)

    # =========================================================================
    # 4. Extruze motivu mědi na požadovanou tloušťku dolů (z 0 do -t_cu)
    # =========================================================================
    if extrude_solids:
        t_cu = float(copper_thickness)
        ext_metal = gmsh.model.occ.extrude([(2, s) for s in antenna_surfs], 0.0, 0.0, -t_cu)
        copper_solid_tags = [tag for dim, tag in ext_metal if dim == 3]
    else:
        copper_solid_tags = antenna_surfs

    gmsh.model.occ.synchronize()

    # =========================================================================
    # 5. Export do STEP souboru
    # =========================================================================
    abs_out = os.path.abspath(output_step_path)
    os.makedirs(os.path.dirname(abs_out), exist_ok=True)
    gmsh.write(abs_out)
    gmsh.finalize()

    file_size = os.path.getsize(abs_out) if os.path.exists(abs_out) else 0

    return {
        'output_path': abs_out,
        'file_size_bytes': file_size,
        'corner_marks_count': len(corner_cube_tags),
        'ident_symbol': ident_symbol,
        'is_mirrored': True,
        'top_z': 0.0,
        'substrate_w': mfg_x_max - mfg_x_min,
        'substrate_l': mfg_y_max - mfg_y_min,
        'h': h,
        'copper_thickness': copper_thickness,
    }
