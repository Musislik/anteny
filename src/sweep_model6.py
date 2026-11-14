"""
sweep_model6.py - Parametrický sweep pro Model 6 (dvouportový model se zakřivenými 100 Ohm větvemi a interními porty).
Odvozeno z Modelu 4: zakončuje obě 100 Ohm větve přímo na interních lumped portech (Port 1 na y_T - d_t, Port 2 na y_T + d_t).

Podporované cíle sweepování (--sweep-target):
  1. 'patch_l': Sweepování délky vyzařujícího flíčku L pro ladění rezonanční frekvence.
  2. 'delta_l': Sweepování fázovacího rozdílu délek Delta L.
  3. 'trans_w' (nebo 'w_t'): Sweepování šířky čtvrtvlnného transformátoru w_T.
  4. 'trans_l' (nebo 'l_t'): Sweepování délky transformátoru l_T.
  5. 'inset' (nebo 'y0'): Sweepování mělkého zanoření flíčku (symetrické i asymetrické).
  6. 'bend_radius': Sweepování poloměru oblouků ohybů.
  7. 't_fillet_r': Sweepování poloměru zaoblení d_t = w_50/2 + t_fillet_r.
  8. 'driven_port': Výběr buzeného portu ('1', '2', 'all', 'both').
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
from tracker import print_summary_table_model6
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

DEFAULT_PATCH_LENGTHS_M6 = [28.40, 28.60, 28.80, 29.00, 29.20]
DEFAULT_TRANS_W_VALUES_M6 = [0.35, 0.38, 0.42, 0.45, 0.50]
DEFAULT_TRANS_L_VALUES_M6 = [18.0, 18.5, 19.0, 19.5, 20.0]
DEFAULT_INSET_VALUES_M6 = [1.5, 2.0, 2.5, 3.0, 3.5]
DEFAULT_DELTA_L_VALUES_M6 = [17.5, 18.0, 18.66, 19.0, 19.5]
DEFAULT_BEND_RADII_M6 = [2.0, 2.5, 3.0, 3.5, 4.0]
DEFAULT_T_FILLET_R_VALUES_M6 = [0.4, 0.6, 0.8, 1.0, 1.2]


def build_sweep_steps_m6(
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
    t_fillet_list=None,
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
    driven_port=None,
):
    """Sestaví kroky parametrického sweepu pro Model 6. Vrací (steps, desc)."""
    target = (sweep_target or os.getenv("SWEEP_TARGET") or "patch_l").lower().strip()
    if target in ("bend", "bend_r", "r_bend", "arc_radius"):
        target = "bend_radius"
    elif target in ("t_fillet", "fillet", "fillet_r", "t_fillet_r"):
        target = "t_fillet_r"
    elif target in ("driven", "port", "mode_port"):
        target = "driven_port"

    fixed_ib = _resolve_opt_float(inset_b, "FEED_INSET_B", default_val="2.5")
    fixed_il = _resolve_opt_float(inset_l, "FEED_INSET_L", default_val="2.5")
    fixed_tw = _resolve_opt_float(trans_w, "TRANS_W", default_val="0.42")
    fixed_tl = _resolve_opt_float(trans_l, "TRANS_L", default_val="19.00")
    fixed_dl = _resolve_opt_float(feed_delta_l, "FEED_DELTA_L", default_val="18.66")
    fixed_pl = _resolve_opt_float(patch_l, "SWEEP_PATCH_L", "PATCH_L", default_val="28.80")
    fixed_pw = _resolve_opt_float(patch_w, "SWEEP_PATCH_W", "PATCH_W", default_val=fixed_pl)

    fixed_br = _resolve_opt_float(bend_radius, "FEED_BEND_RADIUS", default_val="3.0")
    fixed_tf = _resolve_opt_float(t_fillet_r, "FEED_T_FILLET_R", default_val="0.8")
    fixed_l50 = _resolve_opt_float(feed_50_len, "FEED_50_LEN", default_val="9.0")
    fixed_ao = _resolve_opt_float(arm_offset, "FEED_ARM_OFFSET")
    fixed_es = _resolve_opt_float(end_straight, "FEED_END_STRAIGHT", default_val="4.6")
    fixed_dp = str(driven_port or os.getenv("DRIVEN_PORT", "all")).lower().strip()

    def _base_m6_fields():
        base = {
            'antenna_model': 6,
            'port_impedance': 100.0,
            'patch_L': fixed_pl,
            'patch_W': fixed_pw,
            'trans_w': fixed_tw,
            'trans_w_b': fixed_tw,
            'trans_w_l': fixed_tw,
            'trans_l': fixed_tl,
            'feed_inset_b': fixed_ib,
            'feed_inset_l': fixed_il,
            'inset_b': fixed_ib,
            'inset_l': fixed_il,
            'feed_delta_l': fixed_dl,
            'feed_bend_radius': fixed_br,
            'bend_radius': fixed_br,
            'feed_t_fillet_r': fixed_tf,
            't_fillet_r': fixed_tf,
            'feed_50_len': fixed_l50,
            'feed_end_straight': fixed_es,
            'driven_port': fixed_dp,
        }
        if fixed_ao is not None:
            base['feed_arm_offset'] = fixed_ao
        return base

    if target in ("bend_radius", "bend_r"):
        vals = bend_radii or _parse_float_list(os.getenv("SWEEP_BEND_RADII")) or DEFAULT_BEND_RADII_M6
        steps = []
        for r in vals:
            r_val = float(np.round(r, 2))
            step = _base_m6_fields()
            step['run_name'] = f"m6_bend_r{r_val:.2f}mm".replace('.', 'p')
            step['bend_radius'] = r_val
            step['feed_bend_radius'] = r_val
            steps.append(step)
        desc = f"Poloměr oblouků (sweep_target=bend_radius): {vals} mm (celkem {len(steps)} kroků)"
        return steps, desc

    if target in ("t_fillet_r", "t_fillet"):
        vals = t_fillet_list or _parse_float_list(os.getenv("SWEEP_T_FILLET_R")) or DEFAULT_T_FILLET_R_VALUES_M6
        steps = []
        for tf in vals:
            tf_val = float(np.round(tf, 2))
            step = _base_m6_fields()
            step['run_name'] = f"m6_fillet{tf_val:.2f}mm".replace('.', 'p')
            step['feed_t_fillet_r'] = tf_val
            step['t_fillet_r'] = tf_val
            steps.append(step)
        desc = f"Poloměr zaoblení T-uzlu (sweep_target=t_fillet_r): {vals} mm (celkem {len(steps)} kroků)"
        return steps, desc

    if target in ("driven_port", "port"):
        ports = ['all', '1', '2']
        steps = []
        for p in ports:
            step = _base_m6_fields()
            step['run_name'] = f"m6_port_{p}"
            step['driven_port'] = p
            steps.append(step)
        desc = f"Buzený port (sweep_target=driven_port): {ports} (celkem {len(steps)} kroků)"
        return steps, desc

    # Využijeme generátor z Modelu 3 pro patch_l, delta_l, trans_w, trans_l, inset
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

    steps = []
    for s in steps_m3:
        step = _base_m6_fields()
        step.update(s)
        old_rn = step.get('run_name', 'step')
        step['run_name'] = old_rn.replace('m3_', 'm6_') if old_rn.startswith('m3_') else f"m6_{old_rn}"
        steps.append(step)

    desc = desc.replace('Modelu 3', 'Modelu 6').replace('Model 3', 'Model 6')
    return steps, desc


def run_sweep_model6(
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
    t_fillet_list=None,
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
    driven_port=None,
    freq_min=None,
    freq_max=None,
    freq_step=None,
    amr_max_its=None,
    amr_threshold=None,
    linear_tol=None,
    linear_max_its=None,
    farfield_nsample=None,
    save_step=None,
    export_each=None,
    skip_simulation=False,
    **kwargs,
):
    """Spustí parametrický sweep pro Model 6."""
    steps, desc = build_sweep_steps_m6(
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
        t_fillet_list=t_fillet_list,
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
        driven_port=driven_port,
    )

    sim_settings = resolve_sweep_sim_settings(
        freq_min=freq_min,
        freq_max=freq_max,
        freq_step=freq_step,
        amr_max_its=amr_max_its,
        amr_threshold=amr_threshold,
        linear_tol=linear_tol,
        linear_max_its=linear_max_its,
        farfield_nsample=farfield_nsample,
        save_step=save_step,
    )

    do_export = _resolve_env_bool(export_each, "EXPORT_EACH", default=True)

    print("\n" + "=" * 90)
    print(f"SPUŠTĚNÍ PARAMETRICKÉHO SWEEPU PRO MODEL 6 (CELKEM {len(steps)} KROKŮ)")
    print(f"Cíl sweepování: {desc}")
    print(f"Frekvenční rozsah: {sim_settings.get('freq_min', 2.320):.3f} - {sim_settings.get('freq_max', 2.345):.3f} GHz (krok {sim_settings.get('freq_step', 0.005):.4f} GHz)")
    print(f"Nastavení AMR iterací: {sim_settings.get('amr_max_its', 2)}, lineární tolerance: {sim_settings.get('linear_tol', 1e-6)}")
    print(f"Automatický export po každém kroku: {'ANO' if do_export else 'NE'}")
    print("=" * 90 + "\n")

    t_start_total = time.time()
    for idx, step_params in enumerate(steps, 1):
        step_name = step_params.get('run_name', f"m6_step_{idx}")
        print(f"\n>>> [{idx}/{len(steps)}] Spouštím krok sweepu: {step_name} <<<")

        full_params = dict(step_params)
        full_params.update(sim_settings)
        full_params['antenna_model'] = 6
        full_params['port_impedance'] = 100.0

        t_step_start = time.time()
        try:
            main(custom_params=full_params, skip_simulation=skip_simulation)
            if do_export and not skip_simulation and export_paraview_package:
                try:
                    export_paraview_package(output_name=step_name, run_name=step_name, model_version=6)
                except Exception as exp_err:
                    print(f"Upozornění při exportu balíčku {step_name}: {exp_err}")
        except Exception as e:
            print(f"CHYBA: Krok sweepu {step_name} selhal: {e}")

        dt_step = time.time() - t_step_start
        print(f">>> [{idx}/{len(steps)}] Krok {step_name} dokončen za {dt_step:.1f} s <<<\n")

    total_time = time.time() - t_start_total
    print("\n" + "=" * 90)
    print(f"PARAMETRICKÝ SWEEP MODELU 6 DOKONČEN ZA {total_time:.1f} s ({total_time / 60.0:.2f} min)")
    print("=" * 90 + "\n")

    print_summary_table_model6()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parametrický sweep Modelu 6 (Dvouportový 100 Ohm model s interními porty)")
    parser.add_argument("--sweep-target", choices=["patch_l", "delta_l", "trans_w", "w_t", "trans_l", "l_t", "inset", "y0", "bend_radius", "t_fillet_r", "driven_port"], default=None)
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
    parser.add_argument("--t-fillet-list", type=float, nargs="+", default=None, dest="t_fillet_list")
    parser.add_argument("--trans-w", "--w-t", type=float, default=None, dest="trans_w")
    parser.add_argument("--trans-l", "--l-t", type=float, default=None, dest="trans_l")
    parser.add_argument("--inset-b", type=float, default=None, dest="inset_b")
    parser.add_argument("--inset-l", type=float, default=None, dest="inset_l")
    parser.add_argument("--feed-delta-l", type=float, default=None, dest="feed_delta_l")
    parser.add_argument("--patch-l", type=float, default=None, dest="patch_l")
    parser.add_argument("--patch-w", type=float, default=None, dest="patch_w")
    parser.add_argument("--bend-radius", type=float, default=None, dest="bend_radius")
    parser.add_argument("--t-fillet-r", type=float, default=None, dest="t_fillet_r")
    parser.add_argument("--feed-50-len", type=float, default=None, dest="feed_50_len")
    parser.add_argument("--arm-offset", type=float, default=None, dest="arm_offset")
    parser.add_argument("--end-straight", "--feed-end-straight", type=float, default=None, dest="end_straight")
    parser.add_argument("--driven-port", choices=["1", "2", "all", "both"], default=None, dest="driven_port")
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

    run_sweep_model6(**vars(args))
