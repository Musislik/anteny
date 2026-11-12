"""
sweep_model4.py - Parametrický sweep pro finální Model 4 (50 Ohm T-článek s oblouky).
Přebírá výchozí hodnoty z Modelu 3 a přidává ladění parametrů T-článku a oblouků.

Podporované cíle sweepování (--sweep-target):
  1. 'patch_l': Sweepování délky vyzařujícího flíčku L.
  2. 'delta_l': Sweepování fázovacího rozdílu délek Delta L (ladění AR finálního modelu).
  3. 'trans_w' (nebo 'w_t'): Sweepování šířky čtvrtvlnného transformátoru w_T.
  4. 'trans_l' (nebo 'l_t'): Sweepování délky transformátoru l_T.
  5. 'inset' (nebo 'y0'): Sweepování mělkého zanoření flíčku.
  6. 'bend_radius': Sweepování poloměru oblouků ohybů.
  7. 'feed_50_len': Sweepování délky 50 Ohm vstupního přívodu k T-článku.
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
from tracker import print_summary_table_model4
from sweep_model3 import (
    _parse_float_list,
    _resolve_env_bool,
    _resolve_opt_float,
    build_sweep_steps_m3,
    resolve_sweep_sim_settings,
)

try:
    from export_package import export_paraview_package
except ImportError:
    export_paraview_package = None

DEFAULT_BEND_RADII_M4 = [2.0, 2.5, 3.0, 3.5, 4.0]
DEFAULT_FEED_50_LENS_M4 = [6.0, 8.0, 9.0, 10.0, 12.0]


def build_sweep_steps_m4(
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
    bend_radii=None,
    feed_50_lens=None,
    trans_w=None,
    trans_l=None,
    inset_b=None,
    inset_l=None,
    feed_delta_l=None,
    patch_l=None,
    patch_w=None,
    bend_radius=None,
    t_fillet_r=None,
    feed_50_len=None,
    arm_offset=None,
    end_straight=None,
):
    """Sestaví kroky parametrického sweepu pro Model 4 se zděděnými výchozími hodnotami Modelu 3."""
    target = (sweep_target or os.getenv("SWEEP_TARGET") or "patch_l").lower().strip()
    if target in ("bend", "bend_r", "r_bend", "arc_radius"):
        target = "bend_radius"
    elif target in ("l50", "feed50", "feed_50"):
        target = "feed_50_len"

    fixed_ib = _resolve_opt_float(inset_b, "FEED_INSET_B", default_val="2.5")
    fixed_il = _resolve_opt_float(inset_l, "FEED_INSET_L", default_val="2.5")
    fixed_tw = _resolve_opt_float(trans_w, "TRANS_W", default_val="0.42")
    fixed_tl = _resolve_opt_float(trans_l, "TRANS_L")
    fixed_dl = _resolve_opt_float(feed_delta_l, "FEED_DELTA_L")
    fixed_pl = _resolve_opt_float(patch_l, "SWEEP_PATCH_L", "PATCH_L", default_val="28.8")
    fixed_pw = _resolve_opt_float(patch_w, "SWEEP_PATCH_W", "PATCH_W", default_val=fixed_pl)

    fixed_br = _resolve_opt_float(bend_radius, "FEED_BEND_RADIUS", default_val="3.0")
    fixed_tf = _resolve_opt_float(t_fillet_r, "FEED_T_FILLET_R", default_val="0.8")
    fixed_l50 = _resolve_opt_float(feed_50_len, "FEED_50_LEN", default_val="9.0")
    fixed_ao = _resolve_opt_float(arm_offset, "FEED_ARM_OFFSET")
    fixed_es = _resolve_opt_float(end_straight, "FEED_END_STRAIGHT", default_val="4.6")

    def _base_m4_fields():
        base = {
            'patch_L': fixed_pl,
            'patch_W': fixed_pw,
            'trans_w': fixed_tw,
            'trans_w_b': fixed_tw,
            'trans_w_l': fixed_tw,
            'feed_inset_b': fixed_ib,
            'feed_inset_l': fixed_il,
            'inset_b': fixed_ib,
            'inset_l': fixed_il,
            'feed_bend_radius': fixed_br,
            'feed_t_fillet_r': fixed_tf,
            'feed_50_len': fixed_l50,
            'feed_end_straight': fixed_es,
        }
        if fixed_ao is not None:
            base['feed_arm_offset'] = fixed_ao
        if fixed_tl is not None:
            base['trans_l'] = fixed_tl
        if fixed_dl is not None:
            base['feed_delta_l'] = fixed_dl
        return base

    if target == "bend_radius":
        vals = bend_radii or _parse_float_list(os.getenv("SWEEP_BEND_RADII")) or DEFAULT_BEND_RADII_M4
        steps = []
        for br in vals:
            br_val = float(np.round(br, 3))
            step = _base_m4_fields()
            step['run_name'] = f"m4_rbend{br_val:.2f}mm"
            step['feed_bend_radius'] = br_val
            steps.append(step)
        desc = f"Poloměr oblouků (sweep_target=bend_radius): {vals} mm (celkem {len(steps)} kroků)"
        return steps, desc

    if target == "feed_50_len":
        vals = feed_50_lens or _parse_float_list(os.getenv("SWEEP_FEED_50_LEN")) or DEFAULT_FEED_50_LENS_M4
        steps = []
        for l50 in vals:
            l50_val = float(np.round(l50, 2))
            step = _base_m4_fields()
            step['run_name'] = f"m4_l50_{l50_val:.2f}mm"
            step['feed_50_len'] = l50_val
            steps.append(step)
        desc = f"Délka 50 Ohm přívodu (sweep_target=feed_50_len): {vals} mm (celkem {len(steps)} kroků)"
        return steps, desc

    steps_m3, desc = build_sweep_steps_m3(
        sweep_target=target,
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
        patch_w=patch_w,
    )

    m4_steps = []
    for step in steps_m3:
        m4_step = _base_m4_fields()
        m4_step.update(step)
        rname = str(m4_step.get('run_name', 'run'))
        m4_step['run_name'] = "m4_" + rname[3:] if rname.startswith("m3_") else f"m4_{rname}"
        m4_steps.append(m4_step)

    return m4_steps, desc


def run_sweep_model4(
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
    bend_radii=None,
    feed_50_lens=None,
    trans_w=None,
    trans_l=None,
    inset_b=None,
    inset_l=None,
    feed_delta_l=None,
    patch_l=None,
    patch_w=None,
    bend_radius=None,
    t_fillet_r=None,
    feed_50_len=None,
    arm_offset=None,
    freq_min=None,
    freq_max=None,
    freq_step=None,
    amr_max_its=None,
    farfield_nsample=None,
    linear_tol=None,
    linear_max_its=None,
    export_each=None,
    skip_simulation=False,
    amr_threshold=None,
    save_step=None,
    end_straight=None,
):
    """Hlavní prováděcí funkce pro parametrický sweep Modelu 4."""
    load_env()

    steps, sweep_desc = build_sweep_steps_m4(
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
        bend_radii=bend_radii,
        feed_50_lens=feed_50_lens,
        trans_w=trans_w,
        trans_l=trans_l,
        inset_b=inset_b,
        inset_l=inset_l,
        feed_delta_l=feed_delta_l,
        patch_l=patch_l,
        patch_w=patch_w,
        bend_radius=bend_radius,
        t_fillet_r=t_fillet_r,
        feed_50_len=feed_50_len,
        arm_offset=arm_offset,
        end_straight=end_straight,
    )

    if export_each is None:
        export_each = _resolve_env_bool("SWEEP_EXPORT_EACH", default_val=True)

    sim_cfg = resolve_sweep_sim_settings(
        freq_min=freq_min,
        freq_max=freq_max,
        freq_step=freq_step,
        amr_max_its=amr_max_its,
        amr_threshold=amr_threshold,
        farfield_nsample=farfield_nsample,
        linear_tol=linear_tol,
        linear_max_its=linear_max_its,
        save_step=save_step,
    )
    sweep_profile = sim_cfg['sweep_profile']

    print("\n" + "=" * 105)
    print(f"SPUŠTĚNÍ PARAMETRICKÉHO SWEEPU MODELU 4 (PROFIL: {sweep_profile.upper()}):")
    print(f"Cíl sweepování: {sweep_desc}")
    print(f"Frekvence: {sim_cfg['freq_min']:.3f} až {sim_cfg['freq_max']:.3f} GHz (krok {sim_cfg['freq_step']:.4f} GHz)")
    print(
        f"Síť Gmsh: h_min = {sim_cfg['mesh_size_min']:.2f} mm, h_max = {sim_cfg['mesh_size_max']:.2f} mm | "
        f"AMR: max {sim_cfg['amr_max_its']} it. (Tol {sim_cfg['amr_threshold']}) | Lineární řešič Tol: {sim_cfg['linear_tol']}"
    )
    print("=" * 105 + "\n")

    t_start = time.time()
    successful_runs = 0

    for i, step_params in enumerate(steps, start=1):
        step_name = step_params['run_name']
        print(f"\n>>> [Krok {i}/{len(steps)}] Spouštím: {step_name} <<<")

        custom_cfg = {
            'antenna_model': 4,
            'freq_min': sim_cfg['freq_min'],
            'freq_max': sim_cfg['freq_max'],
            'freq_step': sim_cfg['freq_step'],
            'mesh_size_min': sim_cfg['mesh_size_min'],
            'mesh_size_max': sim_cfg['mesh_size_max'],
            'mesh_dist_min': sim_cfg['mesh_dist_min'],
            'mesh_dist_max': sim_cfg['mesh_dist_max'],
            'amr_max_its': sim_cfg['amr_max_its'],
            'amr_threshold': sim_cfg['amr_threshold'],
            'farfield_nsample': sim_cfg['farfield_nsample'],
            'save_step': sim_cfg['save_step'],
            'linear_tol': sim_cfg['linear_tol'],
            'linear_max_its': sim_cfg['linear_max_its'],
        }
        custom_cfg.update(step_params)

        try:
            main(custom_params=custom_cfg, skip_simulation=skip_simulation, clean=True)
            successful_runs += 1

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
    print(f"PARAMETRICKÝ SWEEP MODELU 4 DOKONČEN! Úspěšných běhů: {successful_runs}/{len(steps)}. Celkový čas: {total_time:.1f} s")
    print("=" * 105 + "\n")

    print_summary_table_model4()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parametrický sweep Modelu 4 (Finální 50 Ohm T-článek s oblouky)")
    parser.add_argument(
        "--sweep-target",
        choices=["patch_l", "delta_l", "trans_w", "w_t", "trans_l", "l_t", "inset", "y0", "bend_radius", "feed_50_len"],
        default=None,
        help="Cíl sweepování pro Model 4",
    )
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
    parser.add_argument("--bend-radii", type=float, nargs="+", default=None, dest="bend_radii")
    parser.add_argument("--feed-50-lens", type=float, nargs="+", default=None, dest="feed_50_lens")
    parser.add_argument("--trans-w", "--w-t", type=float, default=None, dest="trans_w")
    parser.add_argument("--trans-l", "--l-t", type=float, default=None, dest="trans_l")
    parser.add_argument("--inset-b", type=float, default=None, dest="inset_b")
    parser.add_argument("--inset-l", type=float, default=None, dest="inset_l")
    parser.add_argument("--feed-delta-l", type=float, default=None, dest="feed_delta_l")
    parser.add_argument("--patch-l", type=float, default=None, dest="patch_l")
    parser.add_argument("--patch-w", type=float, default=None, dest="patch_w")
    parser.add_argument("--bend-radius", type=float, default=None, dest="bend_radius")
    parser.add_argument("--t-fillet", type=float, default=None, dest="t_fillet_r")
    parser.add_argument("--feed-50-len", type=float, default=None, dest="feed_50_len")
    parser.add_argument("--arm-offset", type=float, default=None, dest="arm_offset")
    parser.add_argument("--end-straight", "--feed-end-straight", type=float, default=None, dest="end_straight")
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

    run_sweep_model4(
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
        bend_radii=args.bend_radii,
        feed_50_lens=args.feed_50_lens,
        trans_w=args.trans_w,
        trans_l=args.trans_l,
        inset_b=args.inset_b,
        inset_l=args.inset_l,
        feed_delta_l=args.feed_delta_l,
        patch_l=args.patch_l,
        patch_w=args.patch_w,
        bend_radius=args.bend_radius,
        t_fillet_r=args.t_fillet_r,
        feed_50_len=args.feed_50_len,
        arm_offset=args.arm_offset,
        end_straight=args.end_straight,
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
