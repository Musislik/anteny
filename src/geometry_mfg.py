"""
geometry_mfg.py - 3D STEP model generator for antenna manufacturing per BUT FEKT guidelines
(Manufacturing of antennas - instructions.pdf).

Satisfies all 6 points of the manufacturing guidelines:
  1. Top surface of the radiator and marks lies strictly on the z = 0 plane.
  2. Two blocks (cubes) are created at each of the 4 corners with top surface at z = 0
     and height equal to substrate thickness h for accurate manual board trimming after etching.
  3. Identification mark 'PM.' with top surface at z = 0 placed above the top edge.
  4. Mirror image of the top side (x -> -x) for photolithography film preparation.
  5. ONLY the antenna pattern, corner cut marks, and identification mark are kept in the model
     (no dielectric substrate, no air box, no ports).
  6. Export to standard 3D STEP (.step) format.
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
    """Create a planar surface (Plane Surface) in OpenCASCADE from a 2D polygon."""
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
    Build in OpenCASCADE (Gmsh) and export the complete manufacturing 3D STEP model for BUT.

    Args:
        params: Antenna parameter dictionary (dimensions L, W, h, feed lines, etc.).
        output_step_path: Path to the output .step file.
        copper_thickness: Copper layer thickness [mm] for extrusion downward from z=0 (default: 35 µm).
        mark_len: Corner cut-mark leg length [mm] (default: 8.0).
        mark_w: Corner cut-mark width [mm] (default: 2.0).
        ident_symbol: Identification mark text (default: 'PM.').
        extrude_solids: True for 3D solids, False for 2D sheet bodies at z=0.

    Returns:
        Dictionary with metadata about the generated geometry.
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
    # 1. Mirrored radiating patch and feed network at z = 0
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
    # 2. Eight corner cut-mark blocks at substrate corners (height h, top face at z = 0)
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
        # Blocks with top face at z = 0 and bottom face at z = -h
        box_tag = gmsh.model.occ.addBox(rx, ry, -h, rdx, rdy, h)
        corner_cube_tags.append(box_tag)

    # =========================================================================
    # 3. Identification mark 'PM.' (mirrored across Y-axis, top face at z = 0)
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
            # Extrude along negative Z by substrate height h
            ext = gmsh.model.occ.extrude([(2, surf)], 0.0, 0.0, -h)
            solid_tags = [tag for dim, tag in ext if dim == 3]
            ident_tags.extend(solid_tags)
        else:
            ident_tags.append(surf)

    # =========================================================================
    # 4. Extrude copper pattern downward to target thickness (from 0 to -t_cu)
    # =========================================================================
    if extrude_solids:
        t_cu = float(copper_thickness)
        ext_metal = gmsh.model.occ.extrude([(2, s) for s in antenna_surfs], 0.0, 0.0, -t_cu)
        copper_solid_tags = [tag for dim, tag in ext_metal if dim == 3]
    else:
        copper_solid_tags = antenna_surfs

    gmsh.model.occ.synchronize()

    # =========================================================================
    # 5. Export to STEP file
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
