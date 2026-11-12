"""
sweep_model5.py - Parametrický sweep pro Model 5 (dvouportový model se zakřivenými 100 Ohm větvemi).
Odstraňuje 50 Ohm T-článek a kmen, zakončuje obě 100 Ohm větve na samostatné 100 Ohm porty (Port 1 a Port 2).

Podporované cíle sweepování (--sweep-target):
  1. 'patch_l': Sweepování délky vyzařujícího flíčku L pro ladění rezonanční frekvence.
  2. 'delta_l': Sweepování fázovacího rozdílu délek Delta L (ladění fáze mezi rameny).
  3. 'trans_w' (nebo 'w_t'): Sweepování šířky čtvrtvlnného transformátoru w_T.
  4. 'trans_l' (nebo 'l_t'): Sweepování délky transformátoru l_T.
  5. 'inset' (nebo 'y0'): Sweepování mělkého zanoření flíčku (vstupní impedance flíčku).
  6. 'bend_radius': Sweepování poloměru oblouků ohybů.
  7. 'port_offset': Sweepování rozestupu portů na levé hraně substrátu.
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
from tracker import print_summary_table_model5
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

DEFAULT_PATCH_LENGTHS_M5 = [29.55, 29.75, 29.95, 30.15, 30.35]
DEFAULT_TRANS_W_VALUES_M5 = [0.25, 0.28, 0.30, 0.32, 0.35]
DEFAULT_TRANS_L_VALUES_M5 = [18.0, 18.5, 19.0, 19.5, 20.0]
DEFAULT_INSET_VALUES_M5 = [1.5, 2.0, 2.5, 3.0, 3.5]
DEFAULT_DELTA_L_VALUES_M5 = [17.5, 18.0, 18.66, 19.0, 19.5]
DEFAULT_BEND_RADII_M5 = [2.0, 2.5, 3.0, 3.5, 4.0]
DEFAULT_PORT_OFFSETS_M5 = [2.0, 2.5, 3.0, 3.2]


def build_sweep_steps_m5(
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
    port_offsets=None,
    trans_w=None,
    trans_l=None,
    inset_b=None,
    inset_l=None,
    feed_delta_l=None,
    patch_l=None,
    patch_w=None,
    bend_radius=None,
    port_offset=None,
    arm_offset=None,
    end_straight=None,
    driven_port=None,
):
    """Sestaví kroky parametrického sweepu pro Model 5. Vrací (steps, desc)."""
    target = (sweep_target or os.getenv("SWEEP_TARGET") or "patch_l").lower().strip()
    if target in ("bend", "bend_r", "r_bend", "arc_radius"):
        target = "bend_radius"
    elif target in ("port_offset", "offset_port", "d_port"):
        target = "port_offset"
    elif target in ("driven", "port", "mode_port"):
        target = "driven_port"

    fixed_ib = _resolve_opt_float(inset_b, "FEED_INSET_B", default_val="2.5")
    fixed_il = _resolve_opt_float(inset_l, "FEED_INSET_L", default_val="2.5")
    fixed_tw = _resolve_opt_float(trans_w, "TRANS_W", default_val="0.30")
    fixed_tl = _resolve_opt_float(trans_l, "TRANS_L", default_val="19.00")
    fixed_dl = _resolve_opt_float(feed_delta_l, "FEED_DELTA_L", default_val="18.66")
    fixed_pl = _resolve_opt_float(patch_l, "SWEEP_PATCH_L", "PATCH_L", default_val="29.95")
    fixed_pw = _resolve_opt_float(patch_w, "SWEEP_PATCH_W", "PATCH_W", default_val=fixed_pl)

    fixed_br = _resolve_opt_float(bend_radius, "FEED_BEND_RADIUS", default_val="3.0")
    fixed_po = _resolve_opt_float(port_offset, "FEED_PORT_OFFSET", default_val="3.0")
    fixed_ao = _resolve_opt_float(arm_offset, "FEED_ARM_OFFSET")
    fixed_es = _resolve_opt_float(end_straight, "FEED_END_STRAIGHT", default_val="4.6")
    fixed_dp = str(driven_port or os.getenv("DRIVEN_PORT", "all")).lower().strip()

    def _base_m5_fields():
        base = {
            'patch_L': fixed_pl,
            'patch_W': fixed_pw,
            'trans_w': fixed_tw,
            'trans_l': fixed_tl,
            'feed_inset_b': fixed_ib,
            'feed_inset_l': fixed_il,
            'feed_delta_l': fixed_dl,
            'bend_radius': fixed_br,
            'port_offset': fixed_po,
            'feed_end_straight': fixed_es,
            'driven_port': fixed_dp,
            'antenna_model': 5,
            'port_impedance': 100.0,
        }
        if fixed_ao is not None:
            base['feed_arm_offset'] = fixed_ao
        return base

    if target in ("bend_radius", "bend_r"):
        vals = bend_radii or _parse_float_list(os.getenv("SWEEP_BEND_RADII")) or DEFAULT_BEND_RADII_M5
        steps = []
        for r in vals:
            r_val = float(np.round(r, 2))
            step = _base_m5_fields()
            step['run_name'] = f"m5_bend_r{r_val:.2f}mm".replace('.', 'p')
            step['bend_radius'] = r_val
            step['feed_bend_radius'] = r_val
            steps.append(step)
        desc = f"Poloměr oblouků (sweep_target=bend_radius): {vals} mm (celkem {len(steps)} kroků)"
        return steps, desc

    if target in ("port_offset", "d_port"):
        vals = port_offsets or _parse_float_list(os.getenv("SWEEP_PORT_OFFSETS")) or DEFAULT_PORT_OFFSETS_M5
        steps = []
        for po in vals:
            po_val = float(np.round(po, 2))
            step = _base_m5_fields()
            step['run_name'] = f"m5_port_off{po_val:.2f}mm".replace('.', 'p')
            step['port_offset'] = po_val
            step['feed_port_offset'] = po_val
            steps.append(step)
        desc = f"Rozestup portů (sweep_target=port_offset): {vals} mm (celkem {len(steps)} kroků)"
        return steps, desc

    if target in ("driven_port", "port"):
        ports = ['all', '1', '2']
        steps = []
        for p in ports:
            step = _base_m5_fields()
            step['run_name'] = f"m5_port_{p}"
            step['driven_port'] = p
            steps.append(step)
        desc = f"Buzený port (sweep_target=driven_port): {ports} (celkem {len(steps)} kroků)"
        return steps, desc

    # Standardní cíle z Modelu 3 (patch_l, delta_l, trans_w, trans_l, inset)
    steps_m3, desc = build_sweep_steps_m3(
        sweep_target=target,
        mode=mode,
        insets=insets or (DEFAULT_INSET_VALUES_M5 if target in ('inset', 'y0') else None),
        insets_b=insets_b,
        insets_l=insets_l,
        fixed_name=fixed_name,
        fixed_val=fixed_val,
        manual_pairs=manual_pairs,
        trans_w_list=trans_w_list or (DEFAULT_TRANS_W_VALUES_M5 if target in ('trans_w', 'w_t') else None),
        trans_l_list=trans_l_list or (DEFAULT_TRANS_L_VALUES_M5 if target in ('trans_l', 'l_t') else None),
        delta_l=delta_l or (DEFAULT_DELTA_L_VALUES_M5 if target in ('delta_l', 'feed_delta_l') else None),
        patch_lengths=patch_lengths or (DEFAULT_PATCH_LENGTHS_M5 if target in ('patch_l', 'l') else None),
        trans_w=fixed_tw,
        trans_l=fixed_tl,
        inset_b=fixed_ib,
        inset_l=fixed_il,
        feed_delta_l=fixed_dl,
        patch_l=fixed_pl,
        patch_w=fixed_pw,
    )

    m5_steps = []
    for step in steps_m3:
        m5_step = _base_m5_fields()
        m5_step.update(step)
        m5_step['antenna_model'] = 5
        m5_step['port_impedance'] = 100.0
        rname = str(m5_step.get('run_name', 'run'))
        m5_step['run_name'] = "m5_" + rname[3:] if rname.startswith("m3_") else f"m5_{rname}"
        m5_steps.append(m5_step)

    desc_m5 = desc.replace('Model 3', 'Model 5')
    return m5_steps, desc_m5


def run_sweep_model5(
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
    port_offsets=None,
    trans_w=None,
    trans_l=None,
    inset_b=None,
    inset_l=None,
    feed_delta_l=None,
    patch_l=None,
    patch_w=None,
    bend_radius=None,
    port_offset=None,
    arm_offset=None,
    end_straight=None,
    driven_port=None,
    freq_min=None,
    freq_max=None,
    freq_step=None,
    amr_max_its=None,
    amr_threshold=None,
    farfield_nsample=None,
    linear_tol=None,
    linear_max_its=None,
    save_step=None,
    export_each=None,
    skip_simulation=False,
    **kwargs,
):
    """Spustí parametrický sweep pro Model 5."""
    steps, sweep_desc = build_sweep_steps_m5(
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
        port_offsets=port_offsets,
        trans_w=trans_w,
        trans_l=trans_l,
        inset_b=inset_b,
        inset_l=inset_l,
        feed_delta_l=feed_delta_l,
        patch_l=patch_l,
        patch_w=patch_w,
        bend_radius=bend_radius,
        port_offset=port_offset,
        arm_offset=arm_offset,
        end_straight=end_straight,
        driven_port=driven_port,
    )

    sim_overrides = resolve_sweep_sim_settings(
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

    export_each = _resolve_env_bool("SWEEP_EXPORT_EACH", True) if export_each is None else export_each
    total_steps = len(steps)

    print("\n" + "=" * 80)
    print("PARAMETRICKÝ SWEEP - MODEL 5 (DVOU PORTOVÝ 100 OHM MODEL S OBLOUKY)")
    print(f"Celkem simulačních kroků: {total_steps}")
    print(f"Cíl: {sweep_desc}")
    print("=" * 80 + "\n")

    start_time = time.time()
    successful_runs = 0

    for idx, step_params in enumerate(steps, 1):
        custom_cfg = step_params.copy()
        custom_cfg.update(sim_overrides)
        step_name = custom_cfg.get('run_name', f"m5_step_{idx}")

        print(f"\n>>> [{idx}/{total_steps}] Spouštím krok: {step_name}")
        step_start = time.time()

        try:
            main(custom_params=custom_cfg, skip_simulation=skip_simulation, clean=True)
            step_duration = time.time() - step_start
            print(f">>> [{idx}/{total_steps}] Dokončen krok: {step_name} (čas: {step_duration:.1f} s)")
            successful_runs += 1

            if export_each and export_paraview_package is not None and not skip_simulation:
                try:
                    export_paraview_package(run_name=step_name, model_version=5)
                except Exception as ex_err:
                    print(f"Upozornění: Export balíčku pro {step_name} selhal: {ex_err}")

        except Exception as err:
            print(f"CHYBA v kroku {step_name}: {err}")
            import traceback
            traceback.print_exc()

    total_duration = time.time() - start_time
    print("\n" + "=" * 80)
    print(f"SWEEP MODELU 5 DOKONČEN! Úspěšných: {successful_runs}/{total_steps} za {total_duration / 60.0:.2f} minut.")
    print("=" * 80 + "\n")

    print_summary_table_model5()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parametrický sweep Modelu 5 (Dvouportový 100 Ohm model s oblouky)")
    parser.add_argument("--sweep-target", choices=["patch_l", "delta_l", "trans_w", "w_t", "trans_l", "l_t", "inset", "y0", "bend_radius", "port_offset", "driven_port"], default=None)
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
    parser.add_argument("--port-offsets", type=float, nargs="+", default=None, dest="port_offsets")
    parser.add_argument("--trans-w", "--w-t", type=float, default=None, dest="trans_w")
    parser.add_argument("--trans-l", "--l-t", type=float, default=None, dest="trans_l")
    parser.add_argument("--inset-b", type=float, default=None, dest="inset_b")
    parser.add_argument("--inset-l", type=float, default=None, dest="inset_l")
    parser.add_argument("--feed-delta-l", type=float, default=None, dest="feed_delta_l")
    parser.add_argument("--patch-l", type=float, default=None, dest="patch_l")
    parser.add_argument("--patch-w", type=float, default=None, dest="patch_w")
    parser.add_argument("--bend-radius", type=float, default=None, dest="bend_radius")
    parser.add_argument("--port-offset", type=float, default=None, dest="port_offset")
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

    run_sweep_model5(
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
        port_offsets=args.port_offsets,
        trans_w=args.trans_w,
        trans_l=args.trans_l,
        inset_b=args.inset_b,
        inset_l=args.inset_l,
        feed_delta_l=args.feed_delta_l,
        patch_l=args.patch_l,
        patch_w=args.patch_w,
        bend_radius=args.bend_radius,
        port_offset=args.port_offset,
        arm_offset=args.arm_offset,
        end_straight=args.end_straight,
        driven_port=args.driven_port,
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
