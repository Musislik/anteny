#!/usr/bin/env python3
"""
export_mfg_step.py - User CLI tool for exporting the 3D STEP manufacturing model per VUT instructions.
(Manufacturing of antennas - instructions.pdf)

Generates a .step file satisfying all 6 manufacturing requirements:
  1. Top surface of the radiating patch and marks is located at z = 0.
  2. 8 corner alignment blocks (2 per substrate corner) with top face at z = 0 and height h.
  3. Identification symbol 'PM.' with top face at z = 0 placed above the upper edge.
  4. Mirrored image of the top side (x -> -x).
  5. Only the antenna pattern, alignment marks, and identification symbol are kept in the model.
  6. Saved in standard STEP format for manufacturing.
"""

import argparse
import os
import sys
from typing import Any, Dict

# Automatic sys.path setup for imports from src/
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
        description="3D STEP manufacturing model generator for VUT (Manufacturing of antennas - instructions.pdf)."
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Manufacturing variant profile name in results/<profile>/<profile>.env (default: ANTENNA_PROFILE)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output path for the .step file (default: export/vut_mfg/antenna_model4_mfg_PM.step)",
    )
    parser.add_argument(
        "--ident-symbol",
        type=str,
        default="PM.",
        help="Identification mark on the copper layer (default: 'PM.')",
    )
    parser.add_argument(
        "--copper-thickness",
        type=float,
        default=0.035,
        help="Copper thickness for 3D solids [mm] (default: 0.035 mm = 35 um)",
    )
    parser.add_argument(
        "--mark-len",
        type=float,
        default=8.0,
        help="Arm length of corner alignment blocks [mm] (default: 8.0)",
    )
    parser.add_argument(
        "--mark-w",
        type=float,
        default=2.0,
        help="Width of corner alignment blocks [mm] (default: 2.0)",
    )
    parser.add_argument(
        "--sheet",
        action="store_true",
        help="Export as 2D sheet surfaces at z=0 instead of 3D solids",
    )

    args = parser.parse_args()

    # 1. Load .env
    profile_arg = args.profile.strip() if args.profile else None
    root_dir, _ = load_env(profile=profile_arg)
    active_profile_env = os.getenv("ANTENNA_PROFILE", "").strip() or None
    if active_profile_env:
        profile_slug = os.path.splitext(os.path.basename(active_profile_env))[0]
    else:
        profile_slug = None

    params = load_model4_params_from_env()

    # 2. Target output path
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
    print(" MANUFACTURING 3D STEP EXPORT PER VUT INSTRUCTIONS (Manufacturing of antennas)")
    print("=" * 80)
    if profile_slug:
        print(f"Active profile:        {profile_slug}")
    print(f"Identification symbol: {args.ident_symbol}")
    print(f"Orientation:           Mirrored (x -> -x, top side at z = 0)")
    print(f"Output file:           {out_path}")
    print("-" * 80)

    try:
        from geometry_mfg import build_mfg_model
    except ImportError as e:
        print(f"Error importing geometry_mfg: {e}", file=sys.stderr)
        print("Make sure you run the script in an environment with Gmsh installed (e.g., via the Docker pipeline):", file=sys.stderr)
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

    print("Export completed:")
    print(f"  File:                {res['output_path']}")
    print(f"  Size:                {res['file_size_bytes']} B")
    print(f"  Alignment marks:     {res['corner_marks_count']} blocks (8 along substrate perimeter)")
    print(f"  Substrate size:      {res['substrate_w']:.2f} mm x {res['substrate_l']:.2f} mm (thickness h = {res['h']:.2f} mm)")
    print(f"  Z-coordinate:        Top surface of radiator and marks at z = {res['top_z']:.1f}")
    print(f"  Geometry type:       {'3D Solids' if not args.sheet else '2D Sheet Surfaces'}")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
