#!/usr/bin/env python3
"""
export_mfg_step.py - Uživatelský CLI nástroj pro export 3D STEP výrobního modelu dle pokynů VUT.
(Manufacturing of antennas - instructions.pdf)

Vygeneruje soubor .step, který splňuje všech 6 bodů výrobních pokynů:
  1. Horní plocha vyzařovače i značek je umístěna v z = 0.
  2. 8 ořezových kvádrů (2 pro každý roh substrátu) s horní plochou v z = 0 a výškou h.
  3. Identifikační znak 'PM.' s horní plochou v z = 0 umístěný nad horní hranou.
  4. Zrcadlový obraz horní strany (x -> -x).
  5. V modelu je ponechán POUZE motiv antény, ořezové značky a identifikační znak.
  6. Uloženo do standardního formátu STEP pro výrobu.
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
from export_kicad import load_model4_params_from_env


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generátor výrobního 3D STEP modelu pro VUT (Manufacturing of antennas - instructions.pdf)."
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Název výrobního profilu varianty v results/<profile>/<profile>.env (výchozí: ANTENNA_PROFILE)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Cílová cesta pro uložení .step souboru (výchozí: export/vut_mfg/antenna_model4_mfg_PM.step)",
    )
    parser.add_argument(
        "--ident-symbol",
        type=str,
        default="PM.",
        help="Identifikační značka na vrstvě mědi (výchozí: 'PM.')",
    )
    parser.add_argument(
        "--copper-thickness",
        type=float,
        default=0.035,
        help="Tloušťka mědi pro 3D tělesa [mm] (výchozí: 0.035 mm = 35 µm)",
    )
    parser.add_argument(
        "--mark-len",
        type=float,
        default=8.0,
        help="Délka ramen ořezových kvádrů [mm] (výchozí: 8.0)",
    )
    parser.add_argument(
        "--mark-w",
        type=float,
        default=2.0,
        help="Šířka ořezových kvádrů [mm] (výchozí: 2.0)",
    )
    parser.add_argument(
        "--sheet",
        action="store_true",
        help="Exportovat jako 2D plochy v z=0 místo 3D těles (solids)",
    )

    args = parser.parse_args()

    # 1. Načtení .env
    profile_arg = args.profile.strip() if args.profile else None
    root_dir, _ = load_env(profile=profile_arg)
    active_profile_env = os.getenv("ANTENNA_PROFILE", "").strip() or None
    if active_profile_env:
        profile_slug = os.path.splitext(os.path.basename(active_profile_env))[0]
    else:
        profile_slug = None

    params = load_model4_params_from_env()

    # 2. Cílová cesta
    if args.output:
        out_path = os.path.abspath(args.output)
    else:
        export_base = get_export_dir(root_dir)
        mfg_dir = os.path.join(export_base, "vut_mfg")
        if profile_slug:
            out_path = os.path.join(mfg_dir, f"antenna_model4_{profile_slug}_mfg_{args.ident_symbol.rstrip('.')}.step")
        else:
            out_path = os.path.join(mfg_dir, f"antenna_model4_mfg_{args.ident_symbol.rstrip('.')}.step")

    print("=" * 80)
    print(" VÝROBNÍ 3D STEP EXPORT DLE POKYNŮ VUT (Manufacturing of antennas)")
    print("=" * 80)
    if profile_slug:
        print(f"Aktivní profil:       {profile_slug}")
    print(f"Identifikační symbol: {args.ident_symbol}")
    print(f"Orientace:            Zrcadlená (x -> -x, horní strana v z = 0)")
    print(f"Cílový soubor:        {out_path}")
    print("-" * 80)

    try:
        from geometry_mfg import build_mfg_model
    except ImportError as e:
        print(f"Chyba importu geometry_mfg: {e}", file=sys.stderr)
        print("Ujistěte se, že spouštíte skript v prostředí s nainstalovaným Gmsh (např. přes Docker pipeline):", file=sys.stderr)
        print("  docker compose run --rm pipeline python scripts/export_mfg_step.py", file=sys.stderr)
        return 1

    res = build_mfg_model(
        params=params,
        output_step_path=out_path,
        copper_thickness=args.copper_thickness,
        mark_len=args.mark_len,
        mark_w=args.mark_w,
        ident_symbol=args.ident_symbol,
        extrude_solids=not args.sheet,
    )

    print(f"Export dokončen:")
    print(f"  Soubor:             {res['output_path']}")
    print(f"  Velikost:           {res['file_size_bytes']} B")
    print(f"  Počet ořezů:        {res['corner_marks_count']} kvádrů (8 po obvodu substrátu)")
    print(f"  Rozměr substrátu:   {res['substrate_w']:.2f} mm x {res['substrate_l']:.2f} mm (tloušťka h = {res['h']:.2f} mm)")
    print(f"  Z-souřadnice:       Horní plocha vyzařovače i značek na z = {res['top_z']:.1f}")
    print(f"  Tělesa:             {'3D Solids (objemová tělesa)' if not args.sheet else '2D Sheet Surfaces'}")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
