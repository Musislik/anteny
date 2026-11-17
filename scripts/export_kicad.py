#!/usr/bin/env python3
"""
export_kicad.py - Uživatelský CLI nástroj pro export výrobních a knihovních podkladů KiCad 10.
Načítá konfiguraci z .env souboru (pomocí postpro_utils.load_env()) a umožňuje
jednoduché přepsání parametrů přes argumenty příkazové řádky.

Výchozí výstupní složka: export/kicad/
Generované soubory:
  - antenna_model4.kicad_pcb  (Kompletní výrobní DPS se stackupem, sítěmi RF_IN a GND, SMA rozhraním)
  - Antenna_Model4_LHCP.kicad_mod (Knihovní pouzdro s kotevním bodem uprostřed flíčku pro vložení do jiných projektů)
"""

import argparse
import os
import sys
from typing import Any, Dict

# Automatické nastavení sys.path pro import z src/
try:
    import _env  # noqa: F401
except ImportError:
    try:
        import scripts._env  # noqa: F401
    except ImportError:
        pass

from postpro_utils import get_export_dir, load_env
from kicad_generator import generate_kicad_footprint, generate_kicad_pcb


def load_model4_params_from_env() -> Dict[str, Any]:
    """Načte výchozí konfiguraci Modelu 4 z proměnných prostředí / .env."""
    params: Dict[str, Any] = {
        'patch_L': float(os.getenv("PATCH_L", 28.8)),
        'patch_W': float(os.getenv("PATCH_W", os.getenv("PATCH_L", 28.8))),
        'sub_h': float(os.getenv("SUB_H", 1.52)),
        'eps_r': float(os.getenv("EPS_R", 4.3)),
        'design_freq_ghz': float(os.getenv("DESIGN_FREQ_GHZ", 2.3325)),
        'port_impedance': float(os.getenv("PORT_IMPEDANCE", 50.0)),
        'feed_inset_b': float(os.getenv("FEED_INSET_B", 2.5)),
        'feed_inset_l': float(os.getenv("FEED_INSET_L", 2.5)),
        'feed_inset_gap_b': float(os.getenv("FEED_INSET_GAP_B", 0.5)),
        'feed_inset_gap_l': float(os.getenv("FEED_INSET_GAP_L", 0.5)),
        'trans_w': float(os.getenv("TRANS_W", 0.42)),
        'feed_bend_radius': float(os.getenv("FEED_BEND_RADIUS", 3.0)),
        'feed_t_fillet_r': float(os.getenv("FEED_T_FILLET_R", 0.8)),
        'feed_50_len': float(os.getenv("FEED_50_LEN", 9.0)),
        'feed_end_straight': float(os.getenv("FEED_END_STRAIGHT", 4.6)),
        'sub_margin': float(os.getenv("SUB_MARGIN", 8.0)),
        'mask_clearance': float(os.getenv("MASK_CLEARANCE", 0.30)),
    }

    # Volitelné explicitní parametry
    opt_env_map = {
        'TRANS_L': 'trans_l',
        'FEED_DELTA_L': 'feed_delta_l',
        'FEED_50_W': 'feed_50_w',
        'FEED_100_W': 'feed_100_w',
        'FEED_ARM_OFFSET': 'feed_arm_offset',
        'FEED_T_X': 'feed_x_T',
        'FEED_T_Y': 'feed_y_T',
        'SUB_W': 'sub_W',
        'SUB_L': 'sub_L',
        'FEED_MASK_CLEARANCE': 'mask_clearance',
        'MARGIN_RIGHT': 'margin_right',
        'MARGIN_TOP': 'margin_top',
        'MARGIN_BOTTOM': 'margin_bottom',
    }
    for env_var, param_key in opt_env_map.items():
        val = os.getenv(env_var)
        if val is not None and val.strip() != "":
            try:
                params[param_key] = float(val)
            except ValueError:
                pass

    raw_tight = os.getenv("TIGHT_PCB", os.getenv("CROP_PCB", "true"))
    params['tight_pcb'] = raw_tight.strip().lower() not in ('0', 'false', 'no', 'off')

    return params


def main() -> int:
    # 1. Načtení .env souboru
    root_dir, _ = load_env()
    default_export_dir = os.path.join(get_export_dir(root_dir), "kicad")

    # 2. Argumenty příkazové řádky
    parser = argparse.ArgumentParser(
        description="Generátor výrobních a knihovních podkladů KiCad 10 pro Model 4 (LHCP SDARS anténa)."
    )
    parser.add_argument(
        "--output-dir",
        default=default_export_dir,
        help=f"Cílová složka pro uložení exportovaných souborů (výchozí: {default_export_dir})",
    )
    group_mode = parser.add_mutually_exclusive_group()
    group_mode.add_argument(
        "--pcb",
        action="store_true",
        help="Vygenerovat pouze výrobní desku plošných spojů (.kicad_pcb)",
    )
    group_mode.add_argument(
        "--footprint",
        action="store_true",
        help="Vygenerovat pouze knihovní pouzdro součástky (.kicad_mod)",
    )
    group_mode.add_argument(
        "--all",
        action="store_true",
        default=True,
        help="Vygenerovat desku i footprint (výchozí chování)",
    )

    # Řízení ořezu desky (PCB crop)
    parser.add_argument(
        "--tight-pcb",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Exportovat kompaktní/oříznutý obrys DPS dle VF struktury (výchozí: zapnuto). "
             "Použijte --no-tight-pcb pro plný symetrický rozměr substrátu.",
    )
    parser.add_argument(
        "--crop-pcb",
        dest="crop_pcb_alias",
        action="store_true",
        default=None,
        help="Alias pro --tight-pcb.",
    )
    parser.add_argument(
        "--full-pcb",
        dest="full_pcb_alias",
        action="store_true",
        default=None,
        help="Alias pro --no-tight-pcb.",
    )
    parser.add_argument("--margin-right", type=float, help="Pravý okraj od flíčku [mm] (výchozí: 10.0)")
    parser.add_argument("--margin-top", type=float, help="Horní okraj od flíčku [mm] (výchozí: 10.0)")
    parser.add_argument("--margin-bottom", type=float, help="Spodní okraj pod spodním ramenem [mm] (výchozí: 5.0)")

    # Parametrické přepisy
    parser.add_argument("--patch-l", type=float, help="Délka vyzařujícího flíčku L [mm]")
    parser.add_argument("--patch-w", type=float, help="Šířka vyzařujícího flíčku W [mm]")
    parser.add_argument("--sub-h", type=float, help="Tloušťka substrátu h [mm]")
    parser.add_argument("--eps-r", type=float, help="Relativní permitivita substrátu eps_r [-]")
    parser.add_argument("--freq", type=float, help="Střední návrhová frekvence [GHz]")
    parser.add_argument("--port-z0", type=float, help="Jmenovitá impedance portu [Ohm]")
    parser.add_argument("--delta-l", type=float, help="Fázovací rozdíl drah Delta L [mm]")
    parser.add_argument("--bend-radius", type=float, help="Poloměr oblouků vedení [mm]")
    parser.add_argument("--t-fillet-r", type=float, help="Poloměr zaoblení T-článku [mm]")
    parser.add_argument("--trans-w", type=float, help="Šířka čtvrtvlnného transformátoru w_T [mm]")
    parser.add_argument("--trans-l", type=float, help="Délka transformátoru l_T [mm]")
    parser.add_argument("--inset", type=float, help="Hloubka zanoření zářezů na obou ramenech [mm]")
    parser.add_argument("--inset-gap", type=float, help="Šířka mezery zářezu [mm]")
    parser.add_argument("--mask-clearance", type=float, help="Odsazení nepájivé masky (mask clearance) [mm]")

    args = parser.parse_args()

    # 3. Sestavení parametrů z .env s případným přepsáním z CLI
    params = load_model4_params_from_env()

    if args.tight_pcb is not None:
        params['tight_pcb'] = args.tight_pcb
    elif args.full_pcb_alias:
        params['tight_pcb'] = False
    elif args.crop_pcb_alias:
        params['tight_pcb'] = True

    if args.margin_right is not None:
        params['tight_margin_right'] = args.margin_right
    if args.margin_top is not None:
        params['tight_margin_top'] = args.margin_top
    if args.margin_bottom is not None:
        params['tight_margin_bottom'] = args.margin_bottom

    if args.patch_l is not None:
        params['patch_L'] = args.patch_l
    if args.patch_w is not None:
        params['patch_W'] = args.patch_w
    if args.sub_h is not None:
        params['sub_h'] = args.sub_h
    if args.eps_r is not None:
        params['eps_r'] = args.eps_r
    if args.freq is not None:
        params['design_freq_ghz'] = args.freq
    if args.port_z0 is not None:
        params['port_impedance'] = args.port_z0
    if args.delta_l is not None:
        params['feed_delta_l'] = args.delta_l
    if args.bend_radius is not None:
        params['feed_bend_radius'] = args.bend_radius
    if args.t_fillet_r is not None:
        params['feed_t_fillet_r'] = args.t_fillet_r
    if args.trans_w is not None:
        params['trans_w'] = args.trans_w
    if args.trans_l is not None:
        params['trans_l'] = args.trans_l
    if args.inset is not None:
        params['feed_inset_b'] = args.inset
        params['feed_inset_l'] = args.inset
    if args.inset_gap is not None:
        params['feed_inset_gap_b'] = args.inset_gap
        params['feed_inset_gap_l'] = args.inset_gap
    if args.mask_clearance is not None:
        params['mask_clearance'] = args.mask_clearance

    out_dir = os.path.abspath(args.output_dir)
    os.makedirs(out_dir, exist_ok=True)

    do_pcb = args.pcb or (not args.footprint)
    do_footprint = args.footprint or (not args.pcb)

    print("=" * 80)
    print(" UNIVERZÁLNÍ KICAD 10 EXPORT PRO MIKROPÁSKOVOU ANTÉNU (MODEL 4 LHCP)")
    print("=" * 80)
    print(f"Cílový adresář: {out_dir}")
    print("-" * 80)

    res_pcb = None
    res_fp = None
    pcb_file = os.path.join(out_dir, "antenna_model4.kicad_pcb")
    fp_file = os.path.join(out_dir, "Antenna_Model4_LHCP.kicad_mod")

    if do_pcb:
        print(f"Generuji KiCad 10 desku (.kicad_pcb): {os.path.basename(pcb_file)} ...")
        res_pcb = generate_kicad_pcb(params, pcb_file)
        print(f"  -> Uloženo ({res_pcb['file_size_bytes']} B, {res_pcb['vias_count']} prokovů, "
              f"{res_pcb['rf_polygons_count']} RF polygonů, "
              f"{res_pcb['mask_openings_count']} F.Mask + {res_pcb['mask_openings_bottom_count']} B.Mask)")

    if do_footprint:
        print(f"Generuji KiCad 10 pouzdro (.kicad_mod): {os.path.basename(fp_file)} ...")
        res_fp = generate_kicad_footprint(params, fp_file)
        print(f"  -> Uloženo ({res_fp['file_size_bytes']} B, zákaznický pad 1 RF_IN + SMD pady 2,3 GND)")

    # Volitelná synchronizace do projektu kicad/antena1/
    alt_kicad_dir = os.path.join(root_dir, "kicad", "antena1")
    if os.path.isdir(alt_kicad_dir) and os.path.abspath(out_dir) != os.path.abspath(alt_kicad_dir):
        import shutil
        if do_pcb and os.path.exists(pcb_file):
            shutil.copy2(pcb_file, os.path.join(alt_kicad_dir, "antenna_model4.kicad_pcb"))
        if do_footprint and os.path.exists(fp_file):
            shutil.copy2(fp_file, os.path.join(alt_kicad_dir, "Antenna_Model4_LHCP.kicad_mod"))
        print(f"  -> Synchronizováno do projektu KiCad: {alt_kicad_dir}")

    # 4. Zobrazení souhrnné tabulky parametrů
    info = (res_pcb['routing_info'] if res_pcb else res_fp['routing_info'])
    w_pcb = res_pcb['W_sub'] if res_pcb else res_fp['W_sub']
    l_pcb = res_pcb['L_sub'] if res_pcb else res_fp['L_sub']
    tight_mode = bool(params.get('tight_pcb', True))
    mode_desc = "Kompaktní / oříznutý (tight_pcb=True)" if tight_mode else "Plný symetrický (tight_pcb=False)"
    print("-" * 80)
    print(" PŘEHLED VYGENEROVANÉ GEOMETRIE:")
    print("-" * 80)
    print(f"  Režim desky (PCB crop):            {mode_desc}")
    print(f"  Vyzařující flíček (L x W):         {info['L']:.2f} mm x {info['W']:.2f} mm")
    print(f"  Rozměry DPS (W_sub x L_sub x h):   {w_pcb:.2f} mm x {l_pcb:.2f} mm x {info['h']:.2f} mm (eps_r = {info['eps_r']:.2f})")
    if tight_mode:
        area_full = info['W_sub'] * info['L_sub']
        area_tight = w_pcb * l_pcb
        saving_pct = (1.0 - area_tight / area_full) * 100.0
        print(f"  Původní symetrický substrát:       {info['W_sub']:.2f} mm x {info['L_sub']:.2f} mm (úspora plochy: {saving_pct:.1f} %)")
    print(f"  Návrhová frekvence / Z0:           {info['f_design']:.4f} GHz / {info['port_z0']:.1f} Ohm")
    print(f"  50 Ohm přívodní pásek (w_50):      {info['w_50']:.3f} mm")
    print(f"  100 Ohm větve děliče (w_feed):     {info['w_feed']:.3f} mm (eps_eff = {info['eps_eff_feed']:.3f})")
    print(f"  Čtvrtvlnný transformátor w_T / l_T:{info['w_T_b']:.3f} mm / {info['l_T_b']:.3f} mm")
    print(f"  Poloměr oblouků (feed_bend_radius):{info['bend_radius']:.2f} mm")
    print(f"  Zaoblení T-článku (t_fillet_r):    {info['t_fillet_r']:.2f} mm")
    print(f"  Délka levé větve (L_100_l):        {info['L_100_l']:.3f} mm")
    print(f"  Délka spodní větve (L_100_b):      {info['L_100_b']:.3f} mm")
    print(f"  Fázovací rozdíl drah (Delta L):    {info['L_100_b'] - info['L_100_l']:.3f} mm (požadavek: {info['feed_delta_l']:.3f} mm)")
    print(f"  Odsazení nepájivé masky (clearance):{info['mask_clearance']:.2f} mm (F.Mask RF + B.Mask SMA)")
    print(f"  SMA rozhraní:                      Cinch Johnson 142-0701-801 (G-S-G, 6 prokovů D=0.3/0.6mm)")
    print("=" * 80)
    print(" Export úspěšně dokončen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
