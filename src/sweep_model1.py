"""
sweep_model1.py - Parametrický sweep pro Model 1 (1 port, T-dělič výkonu).
"""

import os
import sys
import time
import argparse
import numpy as np

# Zajistíme dostupnost src a scripts složek pro importy
src_dir = os.path.dirname(os.path.abspath(__file__))
scripts_dir = os.path.abspath(os.path.join(src_dir, "..", "scripts"))
for d in (src_dir, scripts_dir):
    if d not in sys.path:
        sys.path.append(d)

from postpro_utils import load_env
load_env()

from main import main
from rf_calc import synth_square_patch_size, DESIGN_FREQ_GHZ
from tracker import print_summary_table

# Import exportní utility pro uložení balíčků po každém kroku
try:
    from export_package import export_paraview_package
except ImportError:
    export_paraview_package = None

DEFAULT_SUB_H = 1.52
DEFAULT_EPS_R = 4.3
DEFAULT_INSET_VALUES = [0.0, 3.0, 4.5, 4.8, 5.0, 5.2]


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


def generate_sweep_patch_lengths(center_freq=DESIGN_FREQ_GHZ, h=DEFAULT_SUB_H, eps_r=DEFAULT_EPS_R, span_mm=1.6, num_points=5):
    env_l = os.getenv('PATCH_L')
    if env_l is not None:
        try:
            l0 = float(env_l)
        except ValueError:
            l0 = synth_square_patch_size(center_freq, h, eps_r)
    else:
        l0 = synth_square_patch_size(center_freq, h, eps_r)
    half_span = span_mm / 2.0
    lengths = np.linspace(l0 - half_span, l0 + half_span, num_points)
    return [float(np.round(l, 2)) for l in lengths]


def _resolve_model1_sim_params(
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
):
    """Vyhodnotí společné simulační parametry pro sweepy Modelu 1."""
    sim_params = {
        'freq_min': freq_min if freq_min is not None else _resolve_env_float("SWEEP_FREQ_MIN", "FREQ_MIN", 2.280),
        'freq_max': freq_max if freq_max is not None else _resolve_env_float("SWEEP_FREQ_MAX", "FREQ_MAX", 2.380),
        'freq_step': freq_step if freq_step is not None else _resolve_env_float("SWEEP_FREQ_STEP", "FREQ_STEP", 0.005),
        'amr_max_its': amr_max_its if amr_max_its is not None else _resolve_env_int("SWEEP_AMR_MAX_ITS", "AMR_MAX_ITS", 1),
        'amr_threshold': amr_threshold if amr_threshold is not None else _resolve_env_float("SWEEP_AMR_THRESHOLD", "AMR_THRESHOLD", 0.3),
        'farfield_nsample': farfield_nsample if farfield_nsample is not None else _resolve_env_int("SWEEP_FARFIELD_NSAMPLE", "FARFIELD_NSAMPLE", 16200),
        'save_step': save_step if save_step is not None else _resolve_env_int("SWEEP_SAVE_STEP", "SAVE_STEP", 1),
        'linear_tol': linear_tol if linear_tol is not None else _resolve_env_float("SWEEP_LINEAR_TOL", "LINEAR_TOL", 1e-5),
        'linear_max_its': linear_max_its if linear_max_its is not None else _resolve_env_int("SWEEP_LINEAR_MAX_ITS", "LINEAR_MAX_ITS", 100),
    }
    resolved_export_each = export_each if export_each is not None else _resolve_env_bool("SWEEP_EXPORT_EACH", True)
    return sim_params, resolved_export_each


def _execute_model1_step(custom_params, export_name, export_each, skip_simulation, step_label):
    """Spustí jeden simulační krok Modelu 1 a volitelně exportuje ParaView balíček."""
    try:
        main(custom_params=custom_params, skip_simulation=skip_simulation, clean=True)

        if export_each and not skip_simulation and export_paraview_package is not None:
            try:
                export_paraview_package(output_name=export_name)
            except Exception as exp_err:
                print(f"Varování: Export balíčku {export_name} selhal: {exp_err}")

        time.sleep(1)
        return True
    except Exception as e:
        print(f"[CHYBA] Krok {step_label} selhal: {e}")
        return False


def run_inset_sweep(
    insets=None,
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
    if insets is None:
        insets = _parse_float_list(os.getenv("SWEEP_INSETS")) or DEFAULT_INSET_VALUES

    patch_l = patch_l if patch_l is not None else _resolve_env_float("SWEEP_PATCH_L", "PATCH_L", 30.3)
    patch_w = patch_w if patch_w is not None else _resolve_env_float("SWEEP_PATCH_W", "PATCH_W", patch_l)
    sim_params, export_each = _resolve_model1_sim_params(
        freq_min=freq_min,
        freq_max=freq_max,
        freq_step=freq_step,
        amr_max_its=amr_max_its,
        amr_threshold=amr_threshold,
        farfield_nsample=farfield_nsample,
        save_step=save_step,
        linear_tol=linear_tol,
        linear_max_its=linear_max_its,
        export_each=export_each,
    )

    total_steps = len(insets)
    print("=" * 65)
    print("ZAHÁJENÍ PARAMETRICKÉHO SWEEPU MODELU 1 (T-DĚLIČ)")
    print(f"  • Testované hodnoty zanoření: {insets} mm")
    print(f"  • Frekvenční rozsah:          {sim_params['freq_min']:.3f} - {sim_params['freq_max']:.3f} GHz (krok {sim_params['freq_step']:.4f} GHz)")
    print(f"  • Rozměry flíčku:             L = {patch_l:.2f} mm, W = {patch_w:.2f} mm")
    print("=" * 65)

    successful_runs = 0

    for i, inset in enumerate(insets, start=1):
        inset_val = float(np.round(inset, 3))
        export_name = f"m1_inset_{inset_val:.2f}mm"
        print(f"\n>>> [{i}/{total_steps}] Model 1 krok: feed_inset = {inset_val:.3f} mm <<<")

        custom_params = {
            'antenna_model': 1,
            'run_name': export_name,
            'feed_inset': inset_val,
            'patch_L': patch_l,
            'patch_W': patch_w,
            **sim_params,
        }

        if _execute_model1_step(custom_params, export_name, export_each, skip_simulation, f"s feed_inset={inset_val} mm"):
            successful_runs += 1

    print("\n" + "=" * 65)
    print(f"SWEEP MODELU 1 DOKONČEN! Úspěšně proběhlo {successful_runs}/{total_steps} běhů.")
    print("=" * 65)

    print_summary_table(model_version=1)


def run_patch_length_sweep(
    patch_lengths=None,
    export_each=None,
    skip_simulation=False,
    farfield_nsample=None,
    freq_min=None,
    freq_max=None,
    freq_step=None,
    amr_max_its=None,
    amr_threshold=None,
    save_step=None,
    linear_tol=None,
    linear_max_its=None,
):
    if patch_lengths is None:
        patch_lengths = _parse_float_list(os.getenv("SWEEP_PATCH_LENGTHS")) or generate_sweep_patch_lengths()

    sim_params, export_each = _resolve_model1_sim_params(
        freq_min=freq_min,
        freq_max=freq_max,
        freq_step=freq_step,
        amr_max_its=amr_max_its,
        amr_threshold=amr_threshold,
        farfield_nsample=farfield_nsample,
        save_step=save_step,
        linear_tol=linear_tol,
        linear_max_its=linear_max_its,
        export_each=export_each,
    )

    print("=" * 65)
    print("ZAHÁJENÍ PARAMETRICKÉHO SWEEPU PRO PATCH_L (MODEL 1)")
    print(f"Hodnoty k testování: {patch_lengths} mm")
    print("=" * 65)

    for i, length in enumerate(patch_lengths, start=1):
        length_val = float(length)
        export_name = f"m1_patchL_{length_val:.2f}mm"
        print(f"\n[{i}/{len(patch_lengths)}] Model 1: patch_L = {length_val} mm")
        custom_params = {
            'antenna_model': 1,
            'run_name': export_name,
            'patch_L': length_val,
            'patch_W': length_val,
            **sim_params,
        }

        _execute_model1_step(custom_params, export_name, export_each, skip_simulation, f"s patch_L={length_val} mm")

    print("\n" + "=" * 65)
    print("Sweep patch_L dokončen!")
    print("=" * 65)

    print_summary_table(model_version=1)


def run_sweep_model1(**kwargs):
    param = kwargs.get('param', 'inset')
    common_sim_kwargs = {
        'freq_min': kwargs.get('freq_min'),
        'freq_max': kwargs.get('freq_max'),
        'freq_step': kwargs.get('freq_step'),
        'amr_max_its': kwargs.get('amr_max_its'),
        'amr_threshold': kwargs.get('amr_threshold'),
        'farfield_nsample': kwargs.get('farfield_nsample'),
        'save_step': kwargs.get('save_step'),
        'linear_tol': kwargs.get('linear_tol'),
        'linear_max_its': kwargs.get('linear_max_its'),
        'export_each': kwargs.get('export_each'),
        'skip_simulation': kwargs.get('skip_simulation', False),
    }
    if param == "patch_l":
        return run_patch_length_sweep(
            patch_lengths=kwargs.get('patch_lengths'),
            **common_sim_kwargs,
        )
    else:
        return run_inset_sweep(
            insets=kwargs.get('insets'),
            patch_l=kwargs.get('patch_l'),
            patch_w=kwargs.get('patch_w'),
            **common_sim_kwargs,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parametrický sweep Modelu 1 (T-dělič)")
    parser.add_argument("--param", choices=["inset", "patch_l"], default="inset")
    parser.add_argument("--insets", type=float, nargs="+", default=None)
    parser.add_argument("--patch-lengths", type=float, nargs="+", default=None, dest="patch_lengths")
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
    run_sweep_model1(
        param=args.param,
        insets=args.insets,
        patch_lengths=args.patch_lengths,
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
