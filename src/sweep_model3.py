"""
sweep_model3.py - Samostatný parametrický sweep pro Model 3 (Hybridní dvoustupňové přizpůsobení).
Cesta B:
  - Mělký zářez y0 (výchozí 2.5 mm).
  - Vnitřní čtvrtvlnný transformátor (w_T ≈ 0.42 mm, l_T ≈ 18.9 mm).
  - Vnější 100 Ohm napaječ s fázovacím úsekem Delta L (≈ 18.66 mm).

Podporované cíle sweepování (--sweep-target):
  1. 'inset' (nebo 'y0'): Sweepování mělkého zanoření flíčku (reálná složka impedance flíčku).
  2. 'trans_w' (nebo 'w_t'): Sweepování šířky čtvrtvlnného transformátoru w_T.
  3. 'trans_l' (nebo 'l_t'): Sweepování délky transformátoru l_T.
  4. 'delta_l': Sweepování délky fázovacího úseku Delta L pro minimalizaci osového poměru (AR).
  5. 'patch_l': Sweepování délky vyzařujícího flíčku L pro přesné vycentrování rezonance.
"""

import os
import sys
import time
import argparse
import numpy as np

src_dir = os.path.dirname(os.path.abspath(__file__))
scripts_dir = os.path.abspath(os.path.join(src_dir, "..", "scripts"))
for d in (src_dir, scripts_dir):
    if d not in sys.path:
        sys.path.append(d)

from postpro_utils import load_env, get_export_dir
load_env()

from main import main
from tracker import print_summary_table_model3

try:
    from export_package import export_paraview_package
except ImportError:
    export_paraview_package = None

DEFAULT_INSET_VALUES_M3 = [1.5, 2.0, 2.5, 3.0, 3.5]
DEFAULT_TRANS_W_VALUES = [0.35, 0.38, 0.40, 0.42, 0.45, 0.50]
DEFAULT_TRANS_L_VALUES = [17.5, 18.0, 18.5, 18.88, 19.5, 20.0]
DEFAULT_DELTA_L_VALUES_M3 = [17.0, 17.5, 18.0, 18.66, 19.5, 20.0]
DEFAULT_PATCH_LENGTHS_M3 = [28.40, 28.60, 28.80, 29.00, 29.20]


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


def _parse_manual_pairs(val):
    if not val:
        return None
    if isinstance(val, (list, tuple)):
        if val and isinstance(val[0], (list, tuple)) and len(val[0]) == 2:
            return [(float(b), float(l)) for b, l in val]
        raw_items = []
        for x in val:
            raw_items.extend(str(x).replace(';', ' ').replace(',', ' ').split())
    else:
        raw_items = str(val).replace(';', ' ').replace(',', ' ').split()

    pairs = []
    tokens = []
    for item in raw_items:
        if ':' in item:
            parts = item.split(':')
            if len(parts) == 2:
                try:
                    pairs.append((float(parts[0]), float(parts[1])))
                    continue
                except ValueError:
                    pass
        tokens.append(item)

    i = 0
    while i < len(tokens) - 1:
        try:
            b = float(tokens[i])
            l = float(tokens[i + 1])
            pairs.append((b, l))
            i += 2
        except ValueError:
            i += 1

    return pairs if pairs else None


def _resolve_env_bool(sweep_key, default_val=True):
    val = os.getenv(sweep_key)
    if val is None:
        return default_val
    return val.strip().lower() in ("true", "1", "yes", "y", "ano", "t")


def build_sweep_steps_m3(
    sweep_target=None,
    mode=None,
    insets=None,
    insets_b=None,
    insets_l=None,
    fixed_name=None,
    fixed_val=None,
    manual_pairs=None,
    trans_w_list=None,
    trans_l_list=None,
    delta_l=None,
    patch_lengths=None,
    trans_w=None,
    trans_l=None,
    inset_b=None,
    inset_l=None,
    feed_delta_l=None,
    patch_l=None,
):
    """
    Sestaví seznam konfiguračních kroků (slovníků parametrů) pro parametrický sweep Modelu 3.
    """
    target = (sweep_target or os.getenv("SWEEP_TARGET") or "inset").lower().strip()
    if target in ("y0", "insets"):
        target = "inset"
    elif target in ("w_t", "w_trans", "transw", "transformer_w"):
        target = "trans_w"
    elif target in ("l_t", "l_trans", "transl", "transformer_l"):
        target = "trans_l"
    elif target in ("deltal", "phase_delay"):
        target = "delta_l"
    elif target in ("patch", "l_patch", "patch_length"):
        target = "patch_l"

    fixed_ib = float(inset_b if inset_b is not None else os.getenv("FEED_INSET_B", "2.5"))
    fixed_il = float(inset_l if inset_l is not None else os.getenv("FEED_INSET_L", "2.5"))
    fixed_tw = float(trans_w if trans_w is not None else os.getenv("TRANS_W", "0.42"))
    raw_tl = trans_l if trans_l is not None else os.getenv("TRANS_L")
    fixed_tl = float(raw_tl) if raw_tl is not None else None
    raw_dl = feed_delta_l if feed_delta_l is not None else os.getenv("FEED_DELTA_L")
    fixed_dl = float(raw_dl) if raw_dl is not None else None
    fixed_pl = float(patch_l if patch_l is not None else os.getenv("PATCH_L", "28.8"))

    steps = []

    if target == "trans_w":
        vals = trans_w_list or _parse_float_list(os.getenv("SWEEP_TRANS_W")) or DEFAULT_TRANS_W_VALUES
        for tw in vals:
            tw_val = float(np.round(tw, 3))
            step = {
                'run_name': f"m3_tw{tw_val:.2f}mm",
                'trans_w': tw_val,
                'trans_w_b': tw_val,
                'trans_w_l': tw_val,
                'feed_inset_b': fixed_ib,
                'feed_inset_l': fixed_il,
                'inset_b': fixed_ib,
                'inset_l': fixed_il,
                'patch_L': fixed_pl,
                'patch_W': fixed_pl,
            }
            if fixed_tl is not None:
                step['trans_l'] = fixed_tl
            if fixed_dl is not None:
                step['feed_delta_l'] = fixed_dl
            steps.append(step)
        desc = f"Šířka transformátoru w_T (sweep_target=trans_w): {vals} mm (celkem {len(steps)} kroků)"
        return steps, desc

    elif target == "trans_l":
        vals = trans_l_list or _parse_float_list(os.getenv("SWEEP_TRANS_L")) or DEFAULT_TRANS_L_VALUES
        for tl in vals:
            tl_val = float(np.round(tl, 2))
            step = {
                'run_name': f"m3_tl{tl_val:.2f}mm",
                'trans_l': tl_val,
                'trans_l_b': tl_val,
                'trans_l_l': tl_val,
                'trans_w': fixed_tw,
                'trans_w_b': fixed_tw,
                'trans_w_l': fixed_tw,
                'feed_inset_b': fixed_ib,
                'feed_inset_l': fixed_il,
                'inset_b': fixed_ib,
                'inset_l': fixed_il,
                'patch_L': fixed_pl,
                'patch_W': fixed_pl,
            }
            if fixed_dl is not None:
                step['feed_delta_l'] = fixed_dl
            steps.append(step)
        desc = f"Délka transformátoru l_T (sweep_target=trans_l): {vals} mm (celkem {len(steps)} kroků)"
        return steps, desc

    elif target == "delta_l":
        vals = delta_l or _parse_float_list(os.getenv("SWEEP_DELTA_L")) or DEFAULT_DELTA_L_VALUES_M3
        for dl in vals:
            dl_val = float(np.round(dl, 2))
            step = {
                'run_name': f"m3_dl{dl_val:.2f}mm",
                'feed_delta_l': dl_val,
                'trans_w': fixed_tw,
                'trans_w_b': fixed_tw,
                'trans_w_l': fixed_tw,
                'feed_inset_b': fixed_ib,
                'feed_inset_l': fixed_il,
                'inset_b': fixed_ib,
                'inset_l': fixed_il,
                'patch_L': fixed_pl,
                'patch_W': fixed_pl,
            }
            if fixed_tl is not None:
                step['trans_l'] = fixed_tl
            steps.append(step)
        desc = f"Fázovací úsek Delta L v 100 Ohm vedení (sweep_target=delta_l): {vals} mm (celkem {len(steps)} kroků)"
        return steps, desc

    elif target == "patch_l":
        vals = patch_lengths or _parse_float_list(os.getenv("SWEEP_PATCH_LENGTHS")) or DEFAULT_PATCH_LENGTHS_M3
        for pl in vals:
            pl_val = float(np.round(pl, 2))
            step = {
                'run_name': f"m3_patchL_{pl_val:.2f}mm",
                'patch_L': pl_val,
                'patch_W': pl_val,
                'trans_w': fixed_tw,
                'trans_w_b': fixed_tw,
                'trans_w_l': fixed_tw,
                'feed_inset_b': fixed_ib,
                'feed_inset_l': fixed_il,
                'inset_b': fixed_ib,
                'inset_l': fixed_il,
            }
            if fixed_tl is not None:
                step['trans_l'] = fixed_tl
            if fixed_dl is not None:
                step['feed_delta_l'] = fixed_dl
            steps.append(step)
        desc = f"Délka vyzařujícího flíčku L (sweep_target=patch_l): {vals} mm (celkem {len(steps)} kroků)"
        return steps, desc

    else:
        # Výchozí cíl: sweepování mělkého zářezu (target = 'inset')
        m = (mode or os.getenv("SWEEP_MODE") or "symmetric").lower().strip()
        if m == "manual":
            pairs = _parse_manual_pairs(manual_pairs) or _parse_manual_pairs(os.getenv("SWEEP_MANUAL_PAIRS"))
            if not pairs and (insets_b is not None or insets_l is not None):
                vb = insets_b or []
                vl = insets_l or []
                pairs = [(float(b), float(l)) for b, l in zip(vb, vl)]
            if not pairs:
                pairs = [(2.5, 2.5)]
            mode_desc = f"Manuálně zadané body: {len(pairs)} bodů -> {pairs}"
        elif m == "grid":
            vb = insets_b or _parse_float_list(os.getenv("SWEEP_INSETS_B")) or [2.0, 2.5, 3.0]
            vl = insets_l or _parse_float_list(os.getenv("SWEEP_INSETS_L")) or [2.0, 2.5, 3.0]
            pairs = [(float(b), float(l)) for b in vb for l in vl]
            mode_desc = f"2D kartézská mřížka: {len(vb)} x {len(vl)} = {len(pairs)} bodů"
        elif m == "single_fixed":
            fname = fixed_name or os.getenv("SWEEP_FIXED_INSET_NAME", "inset_l").lower().strip()
            fval = float(fixed_val if fixed_val is not None else os.getenv("SWEEP_FIXED_INSET_VAL", "2.5"))
            s_vals = insets or _parse_float_list(os.getenv("SWEEP_INSETS")) or DEFAULT_INSET_VALUES_M3
            if "b" in fname:
                pairs = [(fval, float(v)) for v in s_vals]
                mode_desc = f"Fixní spodní y0b = {fval:.2f} mm, sweep levý y0l: {s_vals} mm"
            else:
                pairs = [(float(v), fval) for v in s_vals]
                mode_desc = f"Fixní levý y0l = {fval:.2f} mm, sweep spodní y0b: {s_vals} mm"
        else:
            # symmetric
            s_vals = insets or _parse_float_list(os.getenv("SWEEP_INSETS")) or DEFAULT_INSET_VALUES_M3
            pairs = [(float(v), float(v)) for v in s_vals]
            mode_desc = f"Symetrický sweep mělkého zářezu (y0b = y0l): {s_vals} mm"

        for ib, il in pairs:
            ib_val = float(np.round(ib, 2))
            il_val = float(np.round(il, 2))
            step = {
                'run_name': f"m3_ib{ib_val:.2f}_il{il_val:.2f}mm",
                'feed_inset_b': ib_val,
                'feed_inset_l': il_val,
                'inset_b': ib_val,
                'inset_l': il_val,
                'trans_w': fixed_tw,
                'trans_w_b': fixed_tw,
                'trans_w_l': fixed_tw,
                'patch_L': fixed_pl,
                'patch_W': fixed_pl,
            }
            if fixed_tl is not None:
                step['trans_l'] = fixed_tl
            if fixed_dl is not None:
                step['feed_delta_l'] = fixed_dl
            steps.append(step)

        desc = f"Zanoření mělkého zářezu (sweep_target=inset) | {mode_desc} (celkem {len(steps)} kroků)"
        return steps, desc


def run_sweep_model3(
    mode=None,
    sweep_target=None,
    insets=None,
    insets_b=None,
    insets_l=None,
    fixed_name=None,
    fixed_val=None,
    manual_pairs=None,
    trans_w_list=None,
    trans_l_list=None,
    delta_l=None,
    patch_lengths=None,
    trans_w=None,
    trans_l=None,
    inset_b=None,
    inset_l=None,
    feed_delta_l=None,
    patch_l=None,
    patch_w=None,
    freq_min=None,
    freq_max=None,
    freq_step=None,
    amr_max_its=None,
    farfield_nsample=None,
    linear_tol=None,
    linear_max_its=None,
    export_each=None,
    skip_simulation=False,
    driven_port=None,
):
    """Hlavní prováděcí funkce pro parametrický sweep Modelu 3."""
    load_env()

    # Sestavení simulačních kroků
    steps, sweep_desc = build_sweep_steps_m3(
        sweep_target=sweep_target,
        mode=mode,
        insets=insets,
        insets_b=insets_b,
        insets_l=insets_l,
        fixed_name=fixed_name,
        fixed_val=fixed_val,
        manual_pairs=manual_pairs,
        trans_w_list=trans_w_list,
        trans_l_list=trans_l_list,
        delta_l=delta_l,
        patch_lengths=patch_lengths,
        trans_w=trans_w,
        trans_l=trans_l,
        inset_b=inset_b,
        inset_l=inset_l,
        feed_delta_l=feed_delta_l,
        patch_l=patch_l,
    )

    if export_each is None:
        export_each = _resolve_env_bool("SWEEP_EXPORT_EACH", default_val=True)

    # Globální parametry simulace
    s_fmin = float(freq_min if freq_min is not None else os.getenv("SWEEP_FREQ_MIN", os.getenv("FREQ_MIN", "2.320")))
    s_fmax = float(freq_max if freq_max is not None else os.getenv("SWEEP_FREQ_MAX", os.getenv("FREQ_MAX", "2.345")))
    s_fstep = float(freq_step if freq_step is not None else os.getenv("SWEEP_FREQ_STEP", os.getenv("FREQ_STEP", "0.001")))
    s_amr = int(amr_max_its if amr_max_its is not None else os.getenv("SWEEP_AMR_MAX_ITS", os.getenv("AMR_MAX_ITS", "0")))
    s_amr_tol = float(os.getenv("SWEEP_AMR_THRESHOLD", os.getenv("AMR_THRESHOLD", "0.15")))
    s_mesh_size_min = float(os.getenv("SWEEP_MESH_SIZE_MIN", os.getenv("MESH_SIZE_MIN", "0.28")))
    s_mesh_size_max = float(os.getenv("SWEEP_MESH_SIZE_MAX", os.getenv("MESH_SIZE_MAX", "6.0")))
    s_mesh_dist_min = float(os.getenv("SWEEP_MESH_DIST_MIN", os.getenv("MESH_DIST_MIN", "0.4")))
    s_mesh_dist_max = float(os.getenv("SWEEP_MESH_DIST_MAX", os.getenv("MESH_DIST_MAX", "4.5")))
    s_linear_tol = float(linear_tol if linear_tol is not None else os.getenv("SWEEP_LINEAR_TOL", os.getenv("LINEAR_TOL", "1e-5")))
    s_linear_max_its = int(linear_max_its if linear_max_its is not None else os.getenv("SWEEP_LINEAR_MAX_ITS", os.getenv("LINEAR_MAX_ITS", "150")))
    s_ff_nsample = int(farfield_nsample if farfield_nsample is not None else os.getenv("SWEEP_FARFIELD_NSAMPLE", os.getenv("FARFIELD_NSAMPLE", "4050")))
    s_save_step = int(os.getenv("SWEEP_SAVE_STEP", "0" if s_amr == 0 else "1"))
    s_driven_port = str(driven_port if driven_port is not None else os.getenv("SWEEP_DRIVEN_PORT", os.getenv("DRIVEN_PORT", "all"))).lower().strip()

    print("\n" + "=" * 105)
    print("SPUŠTĚNÍ PARAMETRICKÉHO SWEEPU MODELU 3 (HYBRIDNÍ PŘIZPŮSOBENÍ, CESTA B):")
    print(f"Cíl sweepování: {sweep_desc}")
    print(f"Frekvence: {s_fmin:.3f} až {s_fmax:.3f} GHz (krok {s_fstep:.4f} GHz)")
    print(f"Síť Gmsh: h_min = {s_mesh_size_min:.2f} mm, h_max = {s_mesh_size_max:.2f} mm | AMR zjemnění: {s_amr} iterací, Dálkové pole: {s_ff_nsample} bodů, Buzení portů: {s_driven_port}")
    print("=" * 105 + "\n")

    t_start = time.time()
    successful_runs = 0

    for i, step_params in enumerate(steps, start=1):
        step_name = step_params['run_name']
        print(f"\n>>> [Krok {i}/{len(steps)}] Spouštím: {step_name} <<<")

        custom_cfg = {
            'antenna_model': 3,
            'freq_min': s_fmin,
            'freq_max': s_fmax,
            'freq_step': s_fstep,
            'mesh_size_min': s_mesh_size_min,
            'mesh_size_max': s_mesh_size_max,
            'mesh_dist_min': s_mesh_dist_min,
            'mesh_dist_max': s_mesh_dist_max,
            'amr_max_its': s_amr,
            'amr_threshold': s_amr_tol,
            'farfield_nsample': s_ff_nsample,
            'save_step': s_save_step,
            'driven_port': s_driven_port,
            'linear_tol': s_linear_tol,
            'linear_max_its': s_linear_max_its,
        }
        if patch_w is not None:
            custom_cfg['patch_W'] = float(patch_w)

        custom_cfg.update(step_params)

        try:
            main(custom_params=custom_cfg, skip_simulation=skip_simulation, clean=True)
            successful_runs += 1

            # Export balíčku pro daný krok
            if export_each and not skip_simulation and export_paraview_package:
                try:
                    export_dir = get_export_dir()
                    zip_out = os.path.join(export_dir, f"{step_name}.zip")
                    export_paraview_package(output_name=step_name, output_zip=zip_out)
                except Exception as ex:
                    print(f"Upozornění při exportu balíčku pro {step_name}: {ex}")

        except Exception as e:
            print(f"CHYBA v kroku {i} ({step_name}): {e}")

    total_time = time.time() - t_start
    print("\n" + "=" * 105)
    print(f"PARAMETRICKÝ SWEEP MODELU 3 DOKONČEN! Úspěšných běhů: {successful_runs}/{len(steps)}. Celkový čas: {total_time:.1f} s")
    print("=" * 105 + "\n")

    print_summary_table_model3()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parametrický sweep Modelu 3 (Hybridní dvoustupňové přizpůsobení)")
    parser.add_argument("--sweep-target", choices=["inset", "y0", "trans_w", "w_t", "trans_l", "l_t", "delta_l", "patch_l"], default=None,
                        help="Cíl sweepování: 'inset' (y0, výchozí), 'trans_w' (w_T), 'trans_l' (l_T), 'delta_l', 'patch_l'")
    parser.add_argument("--mode", choices=["symmetric", "single_fixed", "grid", "manual"], default=None)
    parser.add_argument("--pairs", "--manual-pairs", type=str, nargs="+", default=None, dest="manual_pairs")
    parser.add_argument("--insets", type=float, nargs="+", default=None)
    parser.add_argument("--insets-b", type=float, nargs="+", default=None)
    parser.add_argument("--insets-l", type=float, nargs="+", default=None)
    parser.add_argument("--fixed-name", choices=["inset_b", "inset_l"], default=None)
    parser.add_argument("--fixed-val", type=float, default=None)
    parser.add_argument("--trans-w-list", "--w-t-list", type=float, nargs="+", default=None, dest="trans_w_list")
    parser.add_argument("--trans-l-list", "--l-t-list", type=float, nargs="+", default=None, dest="trans_l_list")
    parser.add_argument("--delta-l", "--sweep-delta-l", type=float, nargs="+", default=None, dest="delta_l")
    parser.add_argument("--patch-lengths", type=float, nargs="+", default=None, dest="patch_lengths")
    parser.add_argument("--trans-w", "--w-t", type=float, default=None, dest="trans_w")
    parser.add_argument("--trans-l", "--l-t", type=float, default=None, dest="trans_l")
    parser.add_argument("--inset-b", type=float, default=None, dest="inset_b")
    parser.add_argument("--inset-l", type=float, default=None, dest="inset_l")
    parser.add_argument("--feed-delta-l", type=float, default=None, dest="feed_delta_l")
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
    parser.add_argument("--driven-port", choices=["all", "1", "2"], default=None)

    args = parser.parse_args()

    run_sweep_model3(
        mode=args.mode,
        sweep_target=args.sweep_target,
        insets=args.insets,
        insets_b=args.insets_b,
        insets_l=args.insets_l,
        fixed_name=args.fixed_name,
        fixed_val=args.fixed_val,
        manual_pairs=args.manual_pairs,
        trans_w_list=args.trans_w_list,
        trans_l_list=args.trans_l_list,
        delta_l=args.delta_l,
        patch_lengths=args.patch_lengths,
        trans_w=args.trans_w,
        trans_l=args.trans_l,
        inset_b=args.inset_b,
        inset_l=args.inset_l,
        feed_delta_l=args.feed_delta_l,
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
        driven_port=args.driven_port,
    )
