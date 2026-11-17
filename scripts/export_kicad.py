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
from typing import Any, Dict, Tuple

# Automatické nastavení sys.path pro import z src/
try:
    import _env  # noqa: F401
except ImportError:
    try:
        import scripts._env  # noqa: F401
    except ImportError:
        pass

from postpro_utils import get_export_dir, get_profile_kicad_dir, load_env
from kicad_generator import generate_kicad_footprint, generate_kicad_pcb


def _env_float(env_keys: Tuple[str, ...], default: float) -> float:
    """Načte první platnou float hodnotu z posloupnosti proměnných prostředí."""
    for env_key in env_keys:
        val = os.getenv(env_key)
        if val is not None and val.strip() != "":
            try:
                return float(val)
            except ValueError:
                pass
    return default


def load_model4_params_from_env() -> Dict[str, Any]:
    """Načte výchozí konfiguraci Modelu 4 z proměnných prostředí / .env."""
    patch_l = _env_float(("PATCH_L",), 28.8)
    default_inset = _env_float(("FEED_INSET", "INSET"), 2.5)
    default_inset_gap = _env_float(("FEED_INSET_GAP", "INSET_GAP"), 0.5)

    params: Dict[str, Any] = {
        'patch_L': patch_l,
        'patch_W': _env_float(("PATCH_W",), patch_l),
        'sub_h': _env_float(("SUB_H",), 1.52),
        'eps_r': _env_float(("EPS_R",), 4.3),
        'design_freq_ghz': _env_float(("DESIGN_FREQ_GHZ",), 2.3325),
        'port_impedance': _env_float(("PORT_IMPEDANCE",), 50.0),
        'feed_inset_b': _env_float(("FEED_INSET_B", "INSET_B"), default_inset),
        'feed_inset_l': _env_float(("FEED_INSET_L", "INSET_L"), default_inset),
        'feed_inset_gap_b': _env_float(("FEED_INSET_GAP_B", "INSET_GAP_B"), default_inset_gap),
        'feed_inset_gap_l': _env_float(("FEED_INSET_GAP_L", "INSET_GAP_L"), default_inset_gap),
        'trans_w': _env_float(("TRANS_W",), 0.42),
        'feed_bend_radius': _env_float(("FEED_BEND_RADIUS",), 3.0),
        'feed_t_fillet_r': _env_float(("FEED_T_FILLET_R",), 0.8),
        'feed_50_len': _env_float(("FEED_50_LEN",), 9.0),
        'feed_end_straight': _env_float(("FEED_END_STRAIGHT",), 4.6),
        'sub_margin': _env_float(("SUB_MARGIN",), 8.0),
        'mask_clearance': _env_float(("MASK_CLEARANCE",), 0.30),
    }

    # Volitelné explicitní parametry
    opt_env_map = {
        'TRANS_W_B': 'trans_w_b',
        'TRANS_W_L': 'trans_w_l',
        'TRANS_L': 'trans_l',
        'TRANS_L_B': 'trans_l_b',
        'TRANS_L_L': 'trans_l_l',
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
        'SMA_GAP': 'sma_gap',
        'SMA_PAD_LEN': 'sma_pad_len',
        'SMA_PAD_W': 'sma_pad_w',
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

    profile_name = os.getenv("PROFILE_NAME")
    if profile_name is not None and profile_name.strip() != "":
        params['profile_name'] = profile_name.strip()

    silkscreen_subtitle = os.getenv("SILKSCREEN_SUBTITLE")
    if silkscreen_subtitle is not None and silkscreen_subtitle.strip() != "":
        params['silkscreen_subtitle'] = silkscreen_subtitle.strip()

    return params


def main() -> int:
    # 1. Argumenty příkazové řádky (parsujeme před load_env kvůli --profile)
    parser = argparse.ArgumentParser(
        description="Generátor výrobních a knihovních podkladů KiCad 10 pro Model 4 (LHCP SDARS anténa)."
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Název výrobního profilu varianty v results/<profile>/<profile>.env "
             "(přepíše kořenový .env; výchozí: ANTENNA_PROFILE nebo žádný)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Cílová složka pro uložení exportovaných souborů "
             "(výchozí: results/<profile>/kicad/ při aktivním profilu, jinak export/kicad/)",
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
    parser.add_argument("--trans-w-b", type=float, help="Šířka transformátoru spodní větve w_T_b [mm]")
    parser.add_argument("--trans-w-l", type=float, help="Šířka transformátoru levé větve w_T_l [mm]")
    parser.add_argument("--trans-l", type=float, help="Délka transformátoru l_T [mm]")
    parser.add_argument("--trans-l-b", type=float, help="Délka transformátoru spodní větve l_T_b [mm]")
    parser.add_argument("--trans-l-l", type=float, help="Délka transformátoru levé větve l_T_l [mm]")
    parser.add_argument("--inset", type=float, help="Hloubka zanoření zářezů na obou ramenech [mm]")
    parser.add_argument("--inset-b", type=float, help="Hloubka zanoření zářezu spodní větve [mm]")
    parser.add_argument("--inset-l", type=float, help="Hloubka zanoření zářezu levé větve [mm]")
    parser.add_argument("--inset-gap", type=float, help="Šířka mezery zářezu na obou ramenech [mm]")
    parser.add_argument("--inset-gap-b", type=float, help="Šířka mezery zářezu spodní větve [mm]")
    parser.add_argument("--inset-gap-l", type=float, help="Šířka mezery zářezu levé větve [mm]")
    parser.add_argument("--mask-clearance", type=float, help="Odsazení nepájivé masky (mask clearance) [mm]")
    parser.add_argument(
        "--sma-gap",
        type=float,
        help="Mezera G-S-G mezi 50 Ohm páskem a SMA GND ploškou [mm] (výchozí: 0.70)",
    )
    parser.add_argument(
        "--sma-pad-len",
        type=float,
        help="Délka SMA GND plošky [mm] (výchozí: 3.50)",
    )
    parser.add_argument(
        "--sma-pad-w",
        type=float,
        help="Šířka SMA GND plošky [mm] (výchozí: 1.50)",
    )

    args = parser.parse_args()

    # 2. Načtení kořenového .env a případného profilu varianty
    profile_arg = args.profile.strip() if args.profile else None
    root_dir, _ = load_env(profile=profile_arg)
    active_profile_env = os.getenv("ANTENNA_PROFILE", "").strip() or None
    if active_profile_env:
        if active_profile_env.endswith(".env"):
            profile_slug = os.path.splitext(os.path.basename(active_profile_env))[0]
        else:
            profile_slug = active_profile_env
    else:
        profile_slug = None

    # 3. Sestavení parametrů z .env (a profilu) s případným přepsáním z CLI
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
        params.pop('trans_w_b', None)
        params.pop('trans_w_l', None)
    if args.trans_w_b is not None:
        params['trans_w_b'] = args.trans_w_b
    if args.trans_w_l is not None:
        params['trans_w_l'] = args.trans_w_l
    if args.trans_l is not None:
        params['trans_l'] = args.trans_l
        params.pop('trans_l_b', None)
        params.pop('trans_l_l', None)
    if args.trans_l_b is not None:
        params['trans_l_b'] = args.trans_l_b
    if args.trans_l_l is not None:
        params['trans_l_l'] = args.trans_l_l
    if args.inset is not None:
        params['feed_inset_b'] = args.inset
        params['feed_inset_l'] = args.inset
    if args.inset_b is not None:
        params['feed_inset_b'] = args.inset_b
    if args.inset_l is not None:
        params['feed_inset_l'] = args.inset_l
    if args.inset_gap is not None:
        params['feed_inset_gap_b'] = args.inset_gap
        params['feed_inset_gap_l'] = args.inset_gap
    if args.inset_gap_b is not None:
        params['feed_inset_gap_b'] = args.inset_gap_b
    if args.inset_gap_l is not None:
        params['feed_inset_gap_l'] = args.inset_gap_l
    if args.mask_clearance is not None:
        params['mask_clearance'] = args.mask_clearance
    if args.sma_gap is not None:
        params['sma_gap'] = args.sma_gap
    if args.sma_pad_len is not None:
        params['sma_pad_len'] = args.sma_pad_len
    if args.sma_pad_w is not None:
        params['sma_pad_w'] = args.sma_pad_w

    if args.output_dir is not None:
        out_dir = os.path.abspath(args.output_dir)
    elif active_profile_env:
        out_dir = get_profile_kicad_dir(profile_arg or active_profile_env, root_dir=root_dir)
    else:
        out_dir = os.path.abspath(os.path.join(get_export_dir(root_dir), "kicad"))
    os.makedirs(out_dir, exist_ok=True)

    do_pcb = args.pcb or (not args.footprint)
    do_footprint = args.footprint or (not args.pcb)

    print("=" * 80)
    print(" UNIVERZÁLNÍ KICAD 10 EXPORT PRO MIKROPÁSKOVOU ANTÉNU (MODEL 4 LHCP)")
    print("=" * 80)
    if profile_slug:
        print(f"Aktivní profil: {profile_slug}")
    print(f"Cílový adresář: {out_dir}")
    print("-" * 80)

    res_pcb = None
    res_fp = None
    if profile_slug:
        pcb_file = os.path.join(out_dir, f"antenna_model4_{profile_slug}.kicad_pcb")
        fp_file = os.path.join(out_dir, f"Antenna_Model4_LHCP_{profile_slug}.kicad_mod")
    else:
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

    # Volitelná synchronizace do projektu kicad/antena1/ (pouze bez aktivního profilu)
    if not profile_slug:
        alt_kicad_dir = os.path.join(root_dir, "kicad", "antena1")
        if os.path.isdir(alt_kicad_dir) and os.path.abspath(out_dir) != os.path.abspath(alt_kicad_dir):
            import shutil
            if do_pcb and os.path.exists(pcb_file):
                shutil.copy2(pcb_file, os.path.join(alt_kicad_dir, "antenna_model4.kicad_pcb"))
                if res_pcb and res_pcb.get('dru_path') and os.path.exists(res_pcb['dru_path']):
                    shutil.copy2(res_pcb['dru_path'], os.path.join(alt_kicad_dir, "antenna_model4.kicad_dru"))
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
    if profile_slug:
        profile_label = params.get('profile_name') or profile_slug
        profile_summary = (
            f"{profile_slug} ({profile_label})" if profile_label != profile_slug else profile_slug
        )
        print(f"  Aktivní profil varianty:           {profile_summary}")
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
    is_asym_trans = (
        abs(info['w_T_b'] - info['w_T_l']) > 1e-6
        or abs(info['l_T_b'] - info['l_T_l']) > 1e-6
    )
    if is_asym_trans:
        print(
            f"  Transformátor spodní (w_T_b/l_T_b):{info['w_T_b']:.3f} mm / {info['l_T_b']:.3f} mm"
        )
        print(
            f"  Transformátor levý (w_T_l/l_T_l):  {info['w_T_l']:.3f} mm / {info['l_T_l']:.3f} mm"
        )
    else:
        print(
            f"  Čtvrtvlnný transformátor w_T / l_T:{info['w_T_b']:.3f} mm / {info['l_T_b']:.3f} mm"
        )
    is_asym_inset = (
        abs(info['inset_b'] - info['inset_l']) > 1e-6
        or abs(info['inset_gap_b'] - info['inset_gap_l']) > 1e-6
    )
    if is_asym_inset:
        print(
            f"  Zářez spodní (inset_b / gap_b):    {info['inset_b']:.2f} mm / {info['inset_gap_b']:.2f} mm"
        )
        print(
            f"  Zářez levý (inset_l / gap_l):      {info['inset_l']:.2f} mm / {info['inset_gap_l']:.2f} mm"
        )
    print(f"  Poloměr oblouků (feed_bend_radius):{info['bend_radius']:.2f} mm")
    print(f"  Zaoblení T-článku (t_fillet_r):    {info['t_fillet_r']:.2f} mm")
    print(f"  Délka levé větve (L_100_l):        {info['L_100_l']:.3f} mm")
    print(f"  Délka spodní větve (L_100_b):      {info['L_100_b']:.3f} mm")
    print(f"  Fázovací rozdíl drah (Delta L):    {info['L_100_b'] - info['L_100_l']:.3f} mm (požadavek: {info['feed_delta_l']:.3f} mm)")
    print(f"  Odsazení nepájivé masky (clearance):{info['mask_clearance']:.2f} mm (F.Mask RF + B.Mask SMA)")
    print(
        f"  SMA rozhraní:                      Cinch Johnson 142-0701-801 "
        f"(G-S-G gap={info['sma_gap']:.2f} mm, pad={info['sma_pad_len']:.2f}x{info['sma_pad_w']:.2f} mm, "
        f"maska={info['sma_mask_len']:.2f}x{2.0 * info['sma_mask_half_h']:.2f} mm, 6 prokovů D=0.3/0.6mm)"
    )
    print("=" * 80)
    print(" Export úspěšně dokončen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
