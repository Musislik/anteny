"""
kicad_generator.py - Pure-Python generátor KiCad 10 výrobních a knihovních podkladů pro Model 4.
Formát souborů: KiCad 10 S-výrazy (verze formátu 20260206).
Nevyžaduje žádné externí binárky ani knihovny (běží v čistém Pythonu se standardní knihovnou).
"""

import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from antenna_geometry import (
    KiCadGeometryData,
    get_model4_kicad_geometry,
)


def _gen_uuid() -> str:
    """Vygeneruje unikátní RFC 4122 UUID pro KiCad prvek."""
    return str(uuid.uuid4())


def _escape_kicad_str(text: str) -> str:
    """Escapuje zpětná lomítka a uvozovky pro S-výrazy KiCad."""
    return str(text).replace("\\", "\\\\").replace('"', '\\"')


def _format_pts(points: List[Tuple[float, float]], indent: int = 8) -> str:
    """Naformátuje seznam bodů (x, y) do bloku (pts (xy x y)...)."""
    sp = " " * indent
    lines = [f"{sp}(pts"]
    for x, y in points:
        lines.append(f"{sp}  (xy {x:.4f} {y:.4f})")
    lines.append(f"{sp})")
    return "\n".join(lines)


def _format_zone(
    net_name: str,
    layer: str,
    polygon_pts: List[Tuple[float, float]],
    priority: int = 1,
    connect_pads_clearance: float = 0.2,
    min_thickness: float = 0.05,
    thermal_gap: float = 0.5,
    thermal_bridge: float = 0.5,
    indent: int = 2,
) -> str:
    """Sestaví S-výraz pro plně naplněnou zónu (zone) v KiCad 10."""
    sp = " " * indent
    pts_str = _format_pts(polygon_pts, indent=indent + 4)
    u = _gen_uuid()

    return f"""{sp}(zone
{sp}  (net "{net_name}")
{sp}  (layer "{layer}")
{sp}  (uuid "{u}")
{sp}  (hatch edge 0.5)
{sp}  (priority {priority})
{sp}  (connect_pads (clearance {connect_pads_clearance:.2f}))
{sp}  (min_thickness {min_thickness:.4f})
{sp}  (fill yes (thermal_gap {thermal_gap:.2f}) (thermal_bridge_width {thermal_bridge:.2f}))
{sp}  (polygon
{pts_str}
{sp}  )
{sp}  (filled_polygon
{sp}    (layer "{layer}")
{pts_str}
{sp}  )
{sp})"""


def generate_kicad_pcb(
    params: Dict[str, Any],
    output_path: str,
    origin_x: Optional[float] = None,
    origin_y: Optional[float] = None,
    tight_pcb: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Vygeneruje kompletní desku plošných spojů (.kicad_pcb) pro KiCad 10.

    Zahrnuje:
      - Explicitní vrstvy KiCad 10: F.Cu, B.Cu, F.Mask, B.Mask, Edge.Cuts, F.SilkS atd.
      - Pojmenované sítě přímo na prvcích: "GND" a "RF_IN".
      - Horní RF strukturu na F.Cu (flíček, transformátory, oblouky, T-článek) se sítí "RF_IN".
      - Spodní souvislou zem na B.Cu se sítí "GND".
      - SMA rozhraní na F.Cu se zemními ploškami a 6 prokovy se sítí "GND".
      - Obrys desky W_sub x L_sub na Edge.Cuts (volitelně kompaktní tight_pcb).
      - Otevření nepájivé masky na F.Mask s clearance (SMA rozhraní + vyzařovač + RF vedení).
      - Otevření nepájivé masky na B.Mask pro SMA rozhraní (pájení spodních zemních pinů).
    """
    geom: KiCadGeometryData = get_model4_kicad_geometry(
        params, origin_x=origin_x, origin_y=origin_y, is_footprint=False, tight_pcb=tight_pcb
    )

    info = geom.routing_info
    sub_h = float(info['h'])
    x_min, y_min, x_max, y_max = geom.edge_cuts_rect

    lines: List[str] = []

    # Hlavička KiCad 10 PCB
    lines.append('(kicad_pcb')
    lines.append('  (version 20260206)')
    lines.append('  (generator "antena_kicad_generator")')
    lines.append('  (generator_version "10.0")')
    lines.append('  (general')
    lines.append(f'    (thickness {sub_h:.3f})')
    lines.append('    (legacy_teardrops no)')
    lines.append('  )')
    lines.append('  (paper "A4")')

    # Deklarace vrstev (kanonické číslování KiCad 10)
    lines.append('  (layers')
    lines.append('    (0 "F.Cu" signal)')
    lines.append('    (2 "B.Cu" power)')
    lines.append('    (9 "F.Adhes" user "F.Adhesive")')
    lines.append('    (11 "B.Adhes" user "B.Adhesive")')
    lines.append('    (13 "F.Paste" user)')
    lines.append('    (15 "B.Paste" user)')
    lines.append('    (5 "F.SilkS" user "F.Silkscreen")')
    lines.append('    (7 "B.SilkS" user "B.Silkscreen")')
    lines.append('    (1 "F.Mask" user)')
    lines.append('    (3 "B.Mask" user)')
    lines.append('    (17 "Dwgs.User" user "User.Drawings")')
    lines.append('    (19 "Cmts.User" user "User.Comments")')
    lines.append('    (21 "Eco1.User" user "User.Eco1")')
    lines.append('    (23 "Eco2.User" user "User.Eco2")')
    lines.append('    (25 "Edge.Cuts" user)')
    lines.append('    (27 "Margin" user)')
    lines.append('    (31 "F.CrtYd" user "F.Courtyard")')
    lines.append('    (29 "B.CrtYd" user "B.Courtyard")')
    lines.append('    (35 "F.Fab" user)')
    lines.append('    (33 "B.Fab" user)')
    lines.append('  )')

    # DRC a Plot nastavení
    lines.append('  (setup')
    lines.append('    (pad_to_mask_clearance 0)')
    lines.append('    (allow_soldermask_bridges_in_footprints no)')
    lines.append('    (pcbplotparams')
    lines.append('      (layerselection 0x00000000_00000000_55555555_5755f5ff)')
    lines.append('      (plot_on_all_layers_selection 0x00000000_00000000_00000000_00000000)')
    lines.append('      (disableapertmacros no)')
    lines.append('      (usegerberextensions no)')
    lines.append('      (usegerberattributes yes)')
    lines.append('      (usegerberadvancedattributes yes)')
    lines.append('      (creategerberjobfile yes)')
    lines.append('      (outputformat 1)')
    lines.append('    )')
    lines.append('  )')

    # Obrys desky na Edge.Cuts (4 obvodové čáry)
    edges = [
        ((x_min, y_min), (x_max, y_min)),
        ((x_max, y_min), (x_max, y_max)),
        ((x_max, y_max), (x_min, y_max)),
        ((x_min, y_max), (x_min, y_min)),
    ]
    for p1, p2 in edges:
        u = _gen_uuid()
        lines.append(
            f'  (gr_line (start {p1[0]:.4f} {p1[1]:.4f}) (end {p2[0]:.4f} {p2[1]:.4f}) '
            f'(stroke (width 0.1) (type solid)) (layer "Edge.Cuts") (uuid "{u}"))'
        )

    # Popisy na vrstvě F.SilkS
    raw_subtitle = params.get('silkscreen_subtitle')
    raw_profile = params.get('profile_name')
    subtitle_text: Optional[str] = None
    if raw_subtitle is not None and str(raw_subtitle).strip() != "":
        subtitle_text = str(raw_subtitle).strip()
    elif raw_profile is not None and str(raw_profile).strip() != "":
        subtitle_text = f"{str(raw_profile).strip()} | h={sub_h:.2f} mm, er={float(info['eps_r']):.2f}"

    u_title = _gen_uuid()
    title_y = y_min - 4.0 if subtitle_text is not None else y_min - 3.0
    lines.append(
        f'  (gr_text "Model 4 LHCP SDARS Patch Antenna (2.3325 GHz)" '
        f'(at {(x_min + x_max) / 2.0:.4f} {title_y:.4f}) (layer "F.SilkS") (uuid "{u_title}") '
        f'(effects (font (size 1.2 1.2) (thickness 0.15))))'
    )
    if subtitle_text is not None:
        u_subtitle = _gen_uuid()
        lines.append(
            f'  (gr_text "{_escape_kicad_str(subtitle_text)}" '
            f'(at {(x_min + x_max) / 2.0:.4f} {y_min - 1.8:.4f}) (layer "F.SilkS") (uuid "{u_subtitle}") '
            f'(effects (font (size 0.9 0.9) (thickness 0.12))))'
        )
    u_rf = _gen_uuid()
    y_rf_label = geom.origin_y - float(info['y_T'])
    lines.append(
        f'  (gr_text "50 Ohm RF IN" (at {x_min - 3.0:.4f} {y_rf_label:.4f} 90) '
        f'(layer "F.SilkS") (uuid "{u_rf}") (effects (font (size 0.9 0.9) (thickness 0.12))))'
    )

    # Spodní celistvá zemní plocha B.Cu ("GND")
    lines.append(
        _format_zone(
            net_name="GND",
            layer="B.Cu",
            polygon_pts=geom.gnd_polygon_bottom,
            priority=1,
        )
    )

    # Horní SMA zemní plošky F.Cu ("GND")
    for gnd_poly in geom.gnd_polygons_top:
        lines.append(
            _format_zone(
                net_name="GND",
                layer="F.Cu",
                polygon_pts=gnd_poly,
                priority=2,
            )
        )

    # Zemní prokovy (Via Stitching, "GND")
    for v in geom.vias:
        u_via = _gen_uuid()
        lines.append(
            f'  (via (at {v["x"]:.4f} {v["y"]:.4f}) (size {v["size"]:.4f}) (drill {v["drill"]:.4f}) '
            f'(layers "F.Cu" "B.Cu") (net "GND") (uuid "{u_via}"))'
        )

    # Horní RF struktura F.Cu ("RF_IN")
    for rf_poly in geom.rf_polygons:
        lines.append(
            _format_zone(
                net_name="RF_IN",
                layer="F.Cu",
                polygon_pts=rf_poly,
                priority=1,
            )
        )

    # Otevření nepájivé masky na F.Mask
    for mask_poly in geom.mask_openings:
        u_mask = _gen_uuid()
        pts_str = _format_pts(mask_poly, indent=6)
        lines.append('  (gr_poly')
        lines.append(pts_str)
        lines.append(f'    (stroke (width 0) (type solid)) (fill yes) (layer "F.Mask") (uuid "{u_mask}")')
        lines.append('  )')

    # Otevření nepájivé masky na B.Mask (SMA konektor)
    for mask_poly in geom.mask_openings_bottom:
        u_mask = _gen_uuid()
        pts_str = _format_pts(mask_poly, indent=6)
        lines.append('  (gr_poly')
        lines.append(pts_str)
        lines.append(f'    (stroke (width 0) (type solid)) (fill yes) (layer "B.Mask") (uuid "{u_mask}")')
        lines.append('  )')

    # Ukončení PCB souboru
    lines.append('  (embedded_fonts no)')
    lines.append(')')
    content = "\n".join(lines) + "\n"

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    return {
        'output_path': os.path.abspath(output_path),
        'file_size_bytes': len(content.encode('utf-8')),
        'W_sub': geom.W_sub,
        'L_sub': geom.L_sub,
        'tight_pcb': geom.tight_pcb,
        'vias_count': len(geom.vias),
        'rf_polygons_count': len(geom.rf_polygons),
        'mask_openings_count': len(geom.mask_openings),
        'mask_openings_bottom_count': len(geom.mask_openings_bottom),
        'routing_info': info,
    }


def generate_kicad_footprint(
    params: Dict[str, Any],
    output_path: str,
    tight_pcb: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Vygeneruje knihovní pouzdro součástky (.kicad_mod) pro KiCad 10.

    Kotevní bod (0, 0) leží v geometrickém středu vyzařujícího flíčku.
    Struktura:
      - Vlastní SMD pad "1" ("RF_IN") obsahující kompletní geometrii antény na F.Cu a F.Mask.
      - SMD pady "2" a "3" ("GND") pro nožičky SMA konektoru.
      - Otevření masky F.Mask pro SMA konektor.
      - Obrys substrátu a ohraničení na vrstvách F.Fab a F.CrtYd.
    """
    geom: KiCadGeometryData = get_model4_kicad_geometry(
        params, origin_x=0.0, origin_y=0.0, is_footprint=True, tight_pcb=tight_pcb
    )
    info = geom.routing_info

    x_min, y_min, x_max, y_max = geom.edge_cuts_rect
    pad_len, pad_w = geom.sma_pad_size
    top_x, top_y = geom.sma_top_pad_center
    bot_x, bot_y = geom.sma_bot_pad_center

    lines: List[str] = []

    raw_fp_name = params.get('footprint_name')
    raw_profile = params.get('profile_name')
    if raw_fp_name is not None and str(raw_fp_name).strip() != "":
        fp_name = str(raw_fp_name).strip()
    elif raw_profile is not None and str(raw_profile).strip() != "":
        fp_name = f"Antenna_Model4_LHCP_{str(raw_profile).strip()}"
    else:
        fp_name = "Antenna_Model4_LHCP"
    fp_name_esc = _escape_kicad_str(fp_name)

    # Hlavička Footprintu KiCad 10
    lines.append(f'(footprint "{fp_name_esc}"')
    lines.append('  (version 20260206)')
    lines.append('  (generator "antena_kicad_generator")')
    lines.append('  (generator_version "10.0")')
    lines.append('  (layer "F.Cu")')
    lines.append('  (descr "Model 4 LHCP Patch Antenna (SDARS 2.3325 GHz) with Cinch Johnson 142-0701-801 SMA interface")')
    lines.append('  (tags "antenna patch lhcp rf sdars 50ohm sma")')

    # Standardní vlastnosti pouzdra
    lines.append(f'  (property "Reference" "ANT**" (at 0.0000 {y_min - 4.0:.4f} 0) (layer "F.SilkS") (uuid "{_gen_uuid()}")')
    lines.append('    (effects (font (size 1 1) (thickness 0.15)))')
    lines.append('  )')
    lines.append(f'  (property "Value" "{fp_name_esc}" (at 0.0000 {y_max + 4.0:.4f} 0) (layer "F.Fab") (uuid "{_gen_uuid()}")')
    lines.append('    (effects (font (size 1 1) (thickness 0.15)))')
    lines.append('  )')
    lines.append(f'  (property "Datasheet" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{_gen_uuid()}")')
    lines.append('    (effects (font (size 1.27 1.27)))')
    lines.append('  )')
    lines.append(f'  (property "Description" "Model 4 LHCP Patch Antenna" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{_gen_uuid()}")')
    lines.append('    (effects (font (size 1.27 1.27)))')
    lines.append('  )')
    lines.append('  (duplicate_pad_numbers_are_jumpers no)')

    # Zákaznický pad 1 ("RF_IN") s celou RF geometrií
    mask_clearance = float(params.get('mask_clearance', info.get('mask_clearance', 0.30)))
    lines.append('  (pad "1" smd custom (at 0 0) (size 1 1) (layers "F.Cu" "F.Mask")')
    lines.append(f'    (solder_mask_margin {mask_clearance:.4f})')
    lines.append('    (zone_connect 2)')
    lines.append('    (options (clearance outline) (anchor rect))')
    lines.append('    (primitives')
    for rf_poly in geom.rf_polygons:
        pts_str = _format_pts(rf_poly, indent=8)
        lines.append('      (gr_poly')
        lines.append(pts_str)
        lines.append('        (width 0) (fill yes)')
        lines.append('      )')
    lines.append('    )')
    lines.append(f'    (uuid "{_gen_uuid()}")')
    lines.append('  )')

    # SMD plošky pro SMA zemní nožičky
    lines.append(
        f'  (pad "2" smd rect (at {top_x:.4f} {top_y:.4f}) (size {pad_len:.4f} {pad_w:.4f}) '
        f'(layers "F.Cu" "F.Mask") (uuid "{_gen_uuid()}"))'
    )
    lines.append(
        f'  (pad "3" smd rect (at {bot_x:.4f} {bot_y:.4f}) (size {pad_len:.4f} {pad_w:.4f}) '
        f'(layers "F.Cu" "F.Mask") (uuid "{_gen_uuid()}"))'
    )

    # Obrys desky a clearance na F.Fab a F.CrtYd
    lines.append(
        f'  (fp_rect (start {x_min:.4f} {y_min:.4f}) (end {x_max:.4f} {y_max:.4f}) '
        f'(stroke (width 0.1) (type default)) (fill no) (layer "F.Fab") (uuid "{_gen_uuid()}"))'
    )
    lines.append(
        f'  (fp_rect (start {x_min - 0.5:.4f} {y_min - 0.5:.4f}) (end {x_max + 0.5:.4f} {y_max + 0.5:.4f}) '
        f'(stroke (width 0.05) (type default)) (fill no) (layer "F.CrtYd") (uuid "{_gen_uuid()}"))'
    )

    # Jednolité obdélníkové otevření masky SMA rozhraní na F.Mask a B.Mask (dynamicky dle šířky G-S-G)
    x_port = float(info['x_port'])
    y_T = float(info['y_T'])
    sma_mask_len = float(info['sma_mask_len'])
    sma_mask_half_h = float(info['sma_mask_half_h'])
    # CAD: x in [x_port, x_port + sma_mask_len], y in [y_T - sma_mask_half_h, y_T + sma_mask_half_h]
    # KiCad (origin=0): x_k = x, y_k = -y
    m_x1 = x_port
    m_x2 = x_port + sma_mask_len
    m_y1 = -y_T - sma_mask_half_h
    m_y2 = -y_T + sma_mask_half_h
    lines.append(
        f'  (fp_rect (start {min(m_x1, m_x2):.4f} {min(m_y1, m_y2):.4f}) '
        f'(end {max(m_x1, m_x2):.4f} {max(m_y1, m_y2):.4f}) '
        f'(stroke (width 0) (type solid)) (fill yes) (layer "F.Mask") (uuid "{_gen_uuid()}"))'
    )
    lines.append(
        f'  (fp_rect (start {min(m_x1, m_x2):.4f} {min(m_y1, m_y2):.4f}) '
        f'(end {max(m_x1, m_x2):.4f} {max(m_y1, m_y2):.4f}) '
        f'(stroke (width 0) (type solid)) (fill yes) (layer "B.Mask") (uuid "{_gen_uuid()}"))'
    )

    # Popis portu
    lines.append(
        f'  (fp_text user "50 OHM RF IN" (at {x_min + 7.0:.4f} {-y_T:.4f} 0) (layer "F.SilkS") '
        f'(uuid "{_gen_uuid()}") (effects (font (size 0.8 0.8) (thickness 0.12))))'
    )

    # Ukončení footprintu
    lines.append('  (embedded_fonts no)')
    lines.append(')')
    content = "\n".join(lines) + "\n"

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    return {
        'output_path': os.path.abspath(output_path),
        'file_size_bytes': len(content.encode('utf-8')),
        'W_sub': geom.W_sub,
        'L_sub': geom.L_sub,
        'tight_pcb': geom.tight_pcb,
        'routing_info': info,
    }
