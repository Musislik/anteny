"""
sweep_model2.py - Samostatný parametrický sweep pro dvouportový Model 2 (LHCP).
Podporuje tři režimy sweepování:
  1. 'symmetric': Párový sweep se stejnou hloubkou zanoření na obou portech (inset_b = inset_l).
  2. 'single_fixed': Zafixování jednoho napaječe a sweepování druhého (např. fixní inset_l, sweep inset_b).
  3. 'grid': 2D kartézská mřížka (kombinace všech hodnot SWEEP_INSETS_B a SWEEP_INSETS_L).
"""

import os
import sys
import time
import argparse
import numpy as np

# Zajistíme dostupnost složek src a scripts
src_dir = os.path.dirname(os.path.abspath(__file__))
scripts_dir = os.path.abspath(os.path.join(src_dir, "..", "scripts"))
for d in (src_dir, scripts_dir):
    if d not in sys.path:
        sys.path.append(d)

from postpro_utils import load_env, get_export_dir
load_env()

from main import main
from tracker import print_summary_table

try:
    from export_package import export_paraview_package
except ImportError:
    export_paraview_package = None

DEFAULT_INSET_VALUES = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]


def _parse_float_list(val):
    if not val:
        return None
    tokens = str(val).replace(',', ' ').split()
    res = []
    for t in tokens:
        try:
            res.append(float(t))
        except ValueError:
            pass
    return res if res else None


def _resolve_env_float(sweep_key, base_key, default_val):
    val = os.getenv(sweep_key)
    if val is not None:
        try:
            return float(val)
        except ValueError:
            pass
    val = os.getenv(base_key)
    if val is not None:
        try:
            return float(val)
        except ValueError:
            pass
    return float(default_val)


def _resolve_env_int(sweep_key, base_key, default_val):
    val = os.getenv(sweep_key)
    if val is not None:
        try:
            return int(val)
        except ValueError:
            pass
    val = os.getenv(base_key)
    if val is not None:
        try:
            return int(val)
        except ValueError:
            pass
    return int(default_val)


def _resolve_env_bool(sweep_key, default_val=True):
    val = os.getenv(sweep_key)
    if val is None:
        return default_val
    return val.strip().lower() in ("true", "1", "yes", "y", "ano", "t")


def build_sweep_pairs(mode, insets=None, insets_b=None, insets_l=None, fixed_name=None, fixed_val=None):
    """
    Sestaví seznam dvojic (inset_b, inset_l) pro daný simulační režim.
    """
    mode = (mode or "symmetric").lower().strip()

    if mode == "grid":
        vals_b = insets_b or _parse_float_list(os.getenv("SWEEP_INSETS_B")) or [2.0, 3.0, 4.0]
        vals_l = insets_l or _parse_float_list(os.getenv("SWEEP_INSETS_L")) or [1.0, 2.0, 3.0, 4.0]
        pairs = [(float(b), float(l)) for b in vals_b for l in vals_l]
        return pairs, f"2D kartézská mřížka (Grid): {len(vals_b)} x {len(vals_l)} = {len(pairs)} bodů"

    elif mode == "single_fixed":
        fname = fixed_name or os.getenv("SWEEP_FIXED_INSET_NAME", "inset_l").lower().strip()
        fval = float(fixed_val if fixed_val is not None else os.getenv("SWEEP_FIXED_INSET_VAL", "2.5"))
        sweep_vals = insets or _parse_float_list(os.getenv("SWEEP_INSETS")) or DEFAULT_INSET_VALUES

        if "b" in fname:
            # Fixní je spodní (inset_b), sweepujeme levý (inset_l)
            pairs = [(fval, float(v)) for v in sweep_vals]
            desc = f"Fixní spodní inset_b = {fval:.2f} mm, sweepujeme levý inset_l: {sweep_vals} mm"
        else:
            # Fixní je levý (inset_l), sweepujeme spodní (inset_b)
            pairs = [(float(v), fval) for v in sweep_vals]
            desc = f"Fixní levý inset_l = {fval:.2f} mm, sweepujeme spodní inset_b: {sweep_vals} mm"

        return pairs, desc

    else:
        # Výchozí symetrický režim (symmetric)
        vals = insets or _parse_float_list(os.getenv("SWEEP_INSETS")) or DEFAULT_INSET_VALUES
        pairs = [(float(v), float(v)) for v in vals]
        return pairs, f"Symetrický párový sweep (inset_b = inset_l): {vals} mm"


def run_sweep_model2(
    mode=None,
    insets=None,
    insets_b=None,
    insets_l=None,
    fixed_name=None,
    fixed_val=None,
    patch_l=None,
    patch_w=None,
    freq_min=None,
    freq_max=None,
    freq_step=None,
    amr_max_its=None,
    amr_threshold=None,
    farfield_nsample=None,
    save_step=None,
    linear_tol=None,
    linear_max_its=None,
    export_each=None,
    skip_simulation=False,
):
    """
    Spustí dedikovaný parametrický sweep pro Model 2.
    """
    mode = mode or os.getenv("SWEEP_MODE", "symmetric")
    pairs, mode_desc = build_sweep_pairs(mode, insets, insets_b, insets_l, fixed_name, fixed_val)

    patch_l = patch_l if patch_l is not None else _resolve_env_float("SWEEP_PATCH_L", "PATCH_L", 30.3)
    patch_w = patch_w if patch_w is not None else _resolve_env_float("SWEEP_PATCH_W", "PATCH_W", patch_l)
    freq_min = freq_min if freq_min is not None else _resolve_env_float("SWEEP_FREQ_MIN", "FREQ_MIN", 2.280)
    freq_max = freq_max if freq_max is not None else _resolve_env_float("SWEEP_FREQ_MAX", "FREQ_MAX", 2.380)
    freq_step = freq_step if freq_step is not None else _resolve_env_float("SWEEP_FREQ_STEP", "FREQ_STEP", 0.005)
    amr_max_its = amr_max_its if amr_max_its is not None else _resolve_env_int("SWEEP_AMR_MAX_ITS", "AMR_MAX_ITS", 1)
    amr_threshold = amr_threshold if amr_threshold is not None else _resolve_env_float("SWEEP_AMR_THRESHOLD", "AMR_THRESHOLD", 0.3)
    farfield_nsample = farfield_nsample if farfield_nsample is not None else _resolve_env_int("SWEEP_FARFIELD_NSAMPLE", "FARFIELD_NSAMPLE", 16200)
    save_step = save_step if save_step is not None else _resolve_env_int("SWEEP_SAVE_STEP", "SAVE_STEP", 1)
    linear_tol = linear_tol if linear_tol is not None else _resolve_env_float("SWEEP_LINEAR_TOL", "LINEAR_TOL", 1e-5)
    linear_max_its = linear_max_its if linear_max_its is not None else _resolve_env_int("SWEEP_LINEAR_MAX_ITS", "LINEAR_MAX_ITS", 100)
    export_each = export_each if export_each is not None else _resolve_env_bool("SWEEP_EXPORT_EACH", True)

    total_steps = len(pairs)
    print("=" * 70)
    print("ZAHÁJENÍ PARAMETRICKÉHO SWEEPU MODELU 2 (DVOUPOVRTOVÝ MODEL LHCP)")
    print("=" * 70)
    print(f"  • Režim sweepování:          {mode_desc}")
    print(f"  • Celkový počet kroků:        {total_steps}")
    print(f"  • Frekvenční rozsah:          {freq_min:.3f} - {freq_max:.3f} GHz (krok {freq_step:.4f} GHz)")
    print(f"  • Rozměry flíčku:             L = {patch_l:.2f} mm, W = {patch_w:.2f} mm")
    print(f"  • AMR zjemnění / Solver Tol:  {amr_max_its} it. (Tol {amr_threshold}) / {linear_tol}")
    print(f"  • Ukládání 3D polí:           každých {save_step} kroků")
    print(f"  • Export ParaView balíčků:    {'ANO' if export_each else 'NE'}")
    print("  • Tabulka výsledků:           export/sweep_results_model2.csv")
    print("=" * 70)

    successful_runs = 0

    for i, (ib, il) in enumerate(pairs, start=1):
        ib_val = float(np.round(ib, 2))
        il_val = float(np.round(il, 2))
        export_name = f"m2_ib{ib_val:.2f}_il{il_val:.2f}mm"
        print(f"\n>>> [{i}/{total_steps}] Model 2 krok: inset_b = {ib_val:.2f} mm (Ey), inset_l = {il_val:.2f} mm (Ex) <<<")

        custom_params = {
            'antenna_model': 2,
            'run_name': export_name,
            'feed_inset_b': ib_val,
            'feed_inset_l': il_val,
            'inset_b': ib_val,
            'inset_l': il_val,
            'patch_L': patch_l,
            'patch_W': patch_w,
            'freq_min': freq_min,
            'freq_max': freq_max,
            'freq_step': freq_step,
            'amr_max_its': amr_max_its,
            'amr_threshold': amr_threshold,
            'farfield_nsample': farfield_nsample,
            'save_step': save_step,
            'linear_tol': linear_tol,
            'linear_max_its': linear_max_its,
        }

        try:
            main(custom_params=custom_params, skip_simulation=skip_simulation, clean=True)

            if export_each and not skip_simulation and export_paraview_package is not None:
                try:
                    export_paraview_package(output_name=export_name)
                except Exception as exp_err:
                    print(f"Varování: Export balíčku {export_name} selhal: {exp_err}")

            successful_runs += 1
            time.sleep(1)

        except Exception as e:
            print(f"[CHYBA] Krok s inset_b={ib_val}, inset_l={il_val} mm selhal: {e}")

    print("\n" + "=" * 70)
    print(f"SWEEP MODELU 2 DOKONČEN! Úspěšně proběhlo {successful_runs}/{total_steps} běhů.")
    print("=" * 70)

    print_summary_table(model_version=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parametrický sweep Modelu 2 (Dvouportový LHCP)")
    parser.add_argument("--mode", choices=["symmetric", "single_fixed", "grid"], default=None,
                        help="Režim sweepování: 'symmetric' (výchozí), 'single_fixed', 'grid'")
    parser.add_argument("--insets", type=float, nargs="+", default=None,
                        help="Hodnoty zanoření pro režimy symmetric a single_fixed")
    parser.add_argument("--insets-b", type=float, nargs="+", default=None,
                        help="Hodnoty spodního zanoření inset_b pro režim grid")
    parser.add_argument("--insets-l", type=float, nargs="+", default=None,
                        help="Hodnoty levého zanoření inset_l pro režim grid")
    parser.add_argument("--fixed-name", choices=["inset_b", "inset_l"], default=None,
                        help="Název fixovaného napaječe pro režim single_fixed")
    parser.add_argument("--fixed-val", type=float, default=None,
                        help="Hodnota fixovaného napaječe v mm pro režim single_fixed")
    parser.add_argument("--patch-l", type=float, default=None, dest="patch_l")
    parser.add_argument("--patch-w", type=float, default=None, dest="patch_w")
    parser.add_argument("--freq-min", type=float, default=None, dest="freq_min")
    parser.add_argument("--freq-max", type=float, default=None, dest="freq_max")
    parser.add_argument("--freq-step", type=float, default=None, dest="freq_step")
    parser.add_argument("--amr-its", type=int, default=None, dest="amr_max_its")
    parser.add_argument("--linear-tol", type=float, default=None, dest="linear_tol")
    parser.add_argument("--linear-its", type=int, default=None, dest="linear_max_its")
    parser.add_argument("--farfield-nsample", type=int, default=None, dest="farfield_nsample")
    parser.add_argument("--no-export", dest="export_each", action="store_false", default=None)
    parser.add_argument("--skip-simulation", "--no-docker", dest="skip_simulation", action="store_true", default=False)

    args = parser.parse_args()
    run_sweep_model2(
        mode=args.mode,
        insets=args.insets,
        insets_b=args.insets_b,
        insets_l=args.insets_l,
        fixed_name=args.fixed_name,
        fixed_val=args.fixed_val,
        patch_l=args.patch_l,
        patch_w=args.patch_w,
        freq_min=args.freq_min,
        freq_max=args.freq_max,
        freq_step=args.freq_step,
        amr_max_its=args.amr_max_its,
        farfield_nsample=args.farfield_nsample,
        linear_tol=args.linear_tol,
        linear_max_its=args.linear_max_its,
        export_each=args.export_each,
        skip_simulation=args.skip_simulation,
    )
