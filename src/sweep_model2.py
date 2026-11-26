"""
sweep_model2.py - Standalone parametric sweep for two-port Model 2 (LHCP).
Supports four sweep modes:
  1. 'symmetric': Paired sweep with equal inset depth on both ports (inset_b = inset_l).
  2. 'single_fixed': Fix one feed and sweep the other (e.g., fixed inset_l, sweep inset_b).
  3. 'grid': 2D Cartesian grid (combinations of all SWEEP_INSETS_B and SWEEP_INSETS_L values).
  4. 'manual': Explicitly defined pairs (inset_b, inset_l) or 1:1 zipped pairing of insets_b and insets_l.
"""

import os
import sys
import time
import argparse
import numpy as np

# Ensure src and scripts directories are available
src_dir = os.path.dirname(os.path.abspath(__file__))
scripts_dir = os.path.abspath(os.path.join(src_dir, "..", "scripts"))
for d in (src_dir, scripts_dir):
    if d not in sys.path:
        sys.path.append(d)

from postpro_utils import load_env
load_env()

from main import main
from tracker import print_summary_table

try:
    from export_package import export_paraview_package
except ImportError:
    export_paraview_package = None

DEFAULT_INSET_VALUES = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
DEFAULT_DELTA_L_VALUES = [16.0, 17.0, 18.0, 18.66, 19.0, 20.0]
DEFAULT_FEED_LENS_B = [35.0, 40.0, 43.51, 45.0, 50.0]
DEFAULT_FEED_LENS_L = [20.0, 22.0, 24.85, 26.0, 28.0]


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
    """
    Parse explicitly specified inset pairs (inset_b, inset_l).
    Supported formats:
      - '4.8:5.2, 5.0:5.2, 5.2:5.4'
      - '4.8,5.2; 5.0,5.2'
      - ['4.8:5.2', '5.0:5.2'] or ['4.8,5.2', '5.0,5.2']
      - [(4.8, 5.2), (5.0, 5.2)]
    """
    if not val:
        return None
    if isinstance(val, (list, tuple)):
        # If already a list of 2-element tuples/lists of numbers
        if val and isinstance(val[0], (list, tuple)) and len(val[0]) == 2:
            return [(float(b), float(l)) for b, l in val]
        # If a list of CLI strings (nargs="+")
        raw_items = []
        for x in val:
            raw_items.extend(str(x).replace(';', ' ').replace(',', ' ').split())
    else:
        # String separated by semicolons or commas/spaces
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

    # If standalone tokens remain, pair them sequentially
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


def _resolve_env_float(sweep_key, base_key, default_val):
    prof = os.getenv("SWEEP_PROFILE", "precise").lower().strip()
    prefix = "SWEEP_FAST_" if prof == "fast" else "SWEEP_PRECISE_"
    core_key = sweep_key.replace("SWEEP_", "")
    prof_key = f"{prefix}{core_key}"
    val = os.getenv(prof_key)
    if val is not None and val != "":
        try:
            return float(val)
        except ValueError:
            pass
    val = os.getenv(sweep_key)
    if val is not None and val != "":
        try:
            return float(val)
        except ValueError:
            pass
    val = os.getenv(base_key)
    if val is not None and val != "":
        try:
            return float(val)
        except ValueError:
            pass
    return float(default_val)


def _resolve_env_opt_float(sweep_key, base_key):
    prof = os.getenv("SWEEP_PROFILE", "precise").lower().strip()
    prefix = "SWEEP_FAST_" if prof == "fast" else "SWEEP_PRECISE_"
    core_key = sweep_key.replace("SWEEP_", "")
    prof_key = f"{prefix}{core_key}"
    val = os.getenv(prof_key)
    if val is not None and val != "":
        try:
            return float(val)
        except ValueError:
            pass
    val = os.getenv(sweep_key)
    if val is not None and val != "":
        try:
            return float(val)
        except ValueError:
            pass
    val = os.getenv(base_key)
    if val is not None and val != "":
        try:
            return float(val)
        except ValueError:
            pass
    return None


def _resolve_env_int(sweep_key, base_key, default_val):
    prof = os.getenv("SWEEP_PROFILE", "precise").lower().strip()
    prefix = "SWEEP_FAST_" if prof == "fast" else "SWEEP_PRECISE_"
    core_key = sweep_key.replace("SWEEP_", "")
    prof_key = f"{prefix}{core_key}"
    val = os.getenv(prof_key)
    if val is not None and val != "":
        try:
            return int(val)
        except ValueError:
            pass
    val = os.getenv(sweep_key)
    if val is not None and val != "":
        try:
            return int(val)
        except ValueError:
            pass
    val = os.getenv(base_key)
    if val is not None and val != "":
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


def build_sweep_pairs(mode, insets=None, insets_b=None, insets_l=None, fixed_name=None, fixed_val=None, manual_pairs=None):
    """
    Build the list of (inset_b, inset_l) pairs for the given simulation mode.
    """
    mode = (mode or "symmetric").lower().strip()

    if mode == "manual":
        # 1. Priority: Explicitly passed pairs in manual_pairs parameter
        pairs = _parse_manual_pairs(manual_pairs)

        # 2. Priority: Explicitly passed insets_b and insets_l lists from arguments
        if not pairs and (insets_b is not None or insets_l is not None):
            vals_b = insets_b or []
            vals_l = insets_l or []
            if len(vals_b) != len(vals_l):
                raise ValueError(
                    f"In 'manual' mode, insets_b and insets_l must have the same number of values. "
                    f"Given: insets_b={len(vals_b)} values, insets_l={len(vals_l)} values."
                )
            pairs = [(float(b), float(l)) for b, l in zip(vals_b, vals_l)]

        # 3. Priority: Environment variable SWEEP_MANUAL_PAIRS
        if not pairs:
            pairs = _parse_manual_pairs(os.getenv("SWEEP_MANUAL_PAIRS"))

        # 4. Priority: Environment variables SWEEP_INSETS_B and SWEEP_INSETS_L
        if not pairs:
            env_b = _parse_float_list(os.getenv("SWEEP_INSETS_B"))
            env_l = _parse_float_list(os.getenv("SWEEP_INSETS_L"))
            if env_b and env_l:
                if len(env_b) == len(env_l):
                    pairs = [(float(b), float(l)) for b, l in zip(env_b, env_l)]
                elif (os.getenv("SWEEP_MODE") or "").lower().strip() == "manual":
                    raise ValueError(
                        f"In 'manual' mode, insets_b and insets_l must have the same number of values. "
                        f"Given: insets_b={len(env_b)} values, insets_l={len(env_l)} values."
                    )

        # 5. Fallback: Default point if nothing was specified
        if not pairs:
            pairs = [(4.80, 5.20)]

        desc = f"Manual pairs: {len(pairs)} points -> {pairs}"
        return pairs, desc

    elif mode == "grid":
        vals_b = insets_b or _parse_float_list(os.getenv("SWEEP_INSETS_B")) or [2.0, 3.0, 4.0]
        vals_l = insets_l or _parse_float_list(os.getenv("SWEEP_INSETS_L")) or [1.0, 2.0, 3.0, 4.0]
        pairs = [(float(b), float(l)) for b in vals_b for l in vals_l]
        return pairs, f"2D Cartesian Grid: {len(vals_b)} x {len(vals_l)} = {len(pairs)} points"

    elif mode == "single_fixed":
        fname = fixed_name or os.getenv("SWEEP_FIXED_INSET_NAME", "inset_l").lower().strip()
        fval = float(fixed_val if fixed_val is not None else os.getenv("SWEEP_FIXED_INSET_VAL", "2.5"))
        sweep_vals = insets or _parse_float_list(os.getenv("SWEEP_INSETS")) or DEFAULT_INSET_VALUES

        if "b" in fname:
            # Bottom (inset_b) is fixed, sweep left (inset_l)
            pairs = [(fval, float(v)) for v in sweep_vals]
            desc = f"Fixed bottom inset_b = {fval:.2f} mm, sweeping left inset_l: {sweep_vals} mm"
        else:
            # Left (inset_l) is fixed, sweep bottom (inset_b)
            pairs = [(float(v), fval) for v in sweep_vals]
            desc = f"Fixed left inset_l = {fval:.2f} mm, sweeping bottom inset_b: {sweep_vals} mm"

        return pairs, desc

    else:
        # Default symmetric mode
        vals = insets or _parse_float_list(os.getenv("SWEEP_INSETS")) or DEFAULT_INSET_VALUES
        pairs = [(float(v), float(v)) for v in vals]
        return pairs, f"Symmetric paired sweep (inset_b = inset_l): {vals} mm"


def build_sweep_steps(
    sweep_target=None,
    mode=None,
    insets=None,
    insets_b=None,
    insets_l=None,
    fixed_name=None,
    fixed_val=None,
    manual_pairs=None,
    feed_lens_b=None,
    feed_lens_l=None,
    delta_l=None,
    feed_len_b=None,
    feed_len_l=None,
    feed_delta_l=None,
    inset_b=None,
    inset_l=None,
    patch_lengths=None,
    patch_l=None,
    patch_w=None,
):
    """
    Build the list of individual sweep steps for Model 2 based on sweep_target:
      - 'inset': sweep inset depth (default)
      - 'patch_l': sweep patch length (L / W)
      - 'delta_l': sweep phasing section Delta L
      - 'feed_len_b': sweep bottom feed length
      - 'feed_len_l': sweep left feed length
      - 'feed_lens': sweep combinations of both feed lengths
    """
    if sweep_target is not None:
        target = sweep_target
    elif patch_lengths is not None:
        target = "patch_l"
    elif delta_l is not None and (len(delta_l) > 1 or (insets is None and insets_b is None and insets_l is None and manual_pairs is None and feed_lens_b is None and feed_lens_l is None)):
        target = "delta_l"
    elif feed_lens_b is not None and feed_lens_l is not None:
        target = "feed_lens"
    elif feed_lens_b is not None:
        target = "feed_len_b"
    elif feed_lens_l is not None:
        target = "feed_len_l"
    elif insets is not None or insets_b is not None or insets_l is not None or manual_pairs is not None:
        target = "inset"
    elif os.getenv("SWEEP_TARGET"):
        target = os.getenv("SWEEP_TARGET")
    elif os.getenv("SWEEP_PATCH_LENGTHS"):
        target = "patch_l"
    elif os.getenv("SWEEP_DELTA_L"):
        target = "delta_l"
    elif os.getenv("SWEEP_FEED_LENS_B") and os.getenv("SWEEP_FEED_LENS_L"):
        target = "feed_lens"
    elif os.getenv("SWEEP_FEED_LENS_B"):
        target = "feed_len_b"
    elif os.getenv("SWEEP_FEED_LENS_L"):
        target = "feed_len_l"
    else:
        target = "inset"
    target = str(target).lower().strip()

    if target in ("patch_l", "patch", "patch_length", "patch_lengths"):
        target = "patch_l"
    elif target in ("delta_l", "feed_delta_l", "delta", "phase_delay"):
        target = "delta_l"
    elif target in ("feed_len_b", "feed_lens_b", "flb", "len_b"):
        target = "feed_len_b"
    elif target in ("feed_len_l", "feed_lens_l", "fll", "len_l"):
        target = "feed_len_l"
    elif target in ("feed_lens", "feed_lengths", "feeds"):
        target = "feed_lens"
    else:
        target = "inset"

    fixed_ib = float(inset_b if inset_b is not None else os.getenv("FEED_INSET_B", "0.0"))
    fixed_il = float(inset_l if inset_l is not None else os.getenv("FEED_INSET_L", "0.0"))

    fixed_flb = feed_len_b if feed_len_b is not None else _resolve_env_opt_float("SWEEP_FEED_LEN_B", "FEED_LEN_B")
    fixed_fll = feed_len_l if feed_len_l is not None else _resolve_env_opt_float("SWEEP_FEED_LEN_L", "FEED_LEN_L")
    fixed_dl = feed_delta_l if feed_delta_l is not None else _resolve_env_opt_float("SWEEP_FEED_DELTA_L", "FEED_DELTA_L")
    if fixed_dl is None and target != "delta_l" and delta_l is not None and len(delta_l) == 1:
        fixed_dl = float(delta_l[0])

    steps = []

    if target == "patch_l":
        vals = patch_lengths or _parse_float_list(os.getenv("SWEEP_PATCH_LENGTHS")) or [28.4, 28.6, 28.8, 29.0, 29.2]
        for pl in vals:
            pl_val = float(np.round(pl, 2))
            pw_val = float(patch_w) if patch_w is not None else pl_val
            step = {
                'run_name': f"m2_patchL_{pl_val:.2f}mm",
                'patch_L': pl_val,
                'patch_W': pw_val,
                'feed_inset_b': fixed_ib,
                'feed_inset_l': fixed_il,
                'inset_b': fixed_ib,
                'inset_l': fixed_il,
            }
            if fixed_flb is not None:
                step['feed_len_b'] = fixed_flb
            if fixed_fll is not None:
                step['feed_len_l'] = fixed_fll
            if fixed_dl is not None:
                step['feed_delta_l'] = fixed_dl
                step['delta_l'] = fixed_dl
            steps.append(step)
        desc = f"Patch length patch_L (sweep_target=patch_l): {vals} mm ({len(steps)} steps total)"
        return steps, desc

    elif target == "delta_l":
        vals = delta_l or _parse_float_list(os.getenv("SWEEP_DELTA_L")) or DEFAULT_DELTA_L_VALUES
        for dl in vals:
            dl_val = float(np.round(dl, 2))
            step = {
                'run_name': f"m2_dl{dl_val:.2f}mm",
                'feed_delta_l': dl_val,
                'delta_l': dl_val,
                'feed_inset_b': fixed_ib,
                'feed_inset_l': fixed_il,
                'inset_b': fixed_ib,
                'inset_l': fixed_il,
            }
            if fixed_fll is not None:
                step['feed_len_l'] = fixed_fll
            if fixed_flb is not None:
                step['feed_len_b'] = fixed_flb
            steps.append(step)
        desc = f"Phasing section Delta L (sweep_target=delta_l): {vals} mm ({len(steps)} steps total)"
        return steps, desc

    elif target == "feed_len_b":
        vals = feed_lens_b or _parse_float_list(os.getenv("SWEEP_FEED_LENS_B")) or DEFAULT_FEED_LENS_B
        for flb in vals:
            flb_val = float(np.round(flb, 2))
            step = {
                'run_name': f"m2_flb{flb_val:.2f}mm",
                'feed_len_b': flb_val,
                'feed_inset_b': fixed_ib,
                'feed_inset_l': fixed_il,
                'inset_b': fixed_ib,
                'inset_l': fixed_il,
            }
            if fixed_fll is not None:
                step['feed_len_l'] = fixed_fll
            if fixed_dl is not None:
                step['feed_delta_l'] = fixed_dl
            steps.append(step)
        desc = f"Bottom feed length (sweep_target=feed_len_b): {vals} mm ({len(steps)} steps total)"
        return steps, desc

    elif target == "feed_len_l":
        vals = feed_lens_l or _parse_float_list(os.getenv("SWEEP_FEED_LENS_L")) or DEFAULT_FEED_LENS_L
        for fll in vals:
            fll_val = float(np.round(fll, 2))
            step = {
                'run_name': f"m2_fll{fll_val:.2f}mm",
                'feed_len_l': fll_val,
                'feed_inset_b': fixed_ib,
                'feed_inset_l': fixed_il,
                'inset_b': fixed_ib,
                'inset_l': fixed_il,
            }
            if fixed_flb is not None:
                step['feed_len_b'] = fixed_flb
            if fixed_dl is not None:
                step['feed_delta_l'] = fixed_dl
            steps.append(step)
        desc = f"Left feed length (sweep_target=feed_len_l): {vals} mm ({len(steps)} steps total)"
        return steps, desc

    elif target == "feed_lens":
        vals_b = feed_lens_b or _parse_float_list(os.getenv("SWEEP_FEED_LENS_B")) or [38.0, 43.51, 48.0]
        vals_l = feed_lens_l or _parse_float_list(os.getenv("SWEEP_FEED_LENS_L")) or [20.0, 24.85, 28.0]
        m = (mode or os.getenv("SWEEP_MODE") or "grid").lower().strip()

        if m == "manual":
            pairs = _parse_manual_pairs(manual_pairs) or [(float(b), float(l)) for b, l in zip(vals_b, vals_l)]
        elif m == "symmetric":
            pairs = [(float(b), float(l)) for b, l in zip(vals_b, vals_l)] if len(vals_b) == len(vals_l) else [(float(b), float(b)) for b in vals_b]
        else: # grid
            pairs = [(float(b), float(l)) for b in vals_b for l in vals_l]

        for flb, fll in pairs:
            flb_val = float(np.round(flb, 2))
            fll_val = float(np.round(fll, 2))
            step = {
                'run_name': f"m2_flb{flb_val:.2f}_fll{fll_val:.2f}mm",
                'feed_len_b': flb_val,
                'feed_len_l': fll_val,
                'feed_inset_b': fixed_ib,
                'feed_inset_l': fixed_il,
                'inset_b': fixed_ib,
                'inset_l': fixed_il,
            }
            if fixed_dl is not None:
                step['feed_delta_l'] = fixed_dl
                step['delta_l'] = fixed_dl
            steps.append(step)
        desc = f"Both feed lengths feed_lens ({m}): {len(steps)} steps"
        return steps, desc

    else:
        # Default target 'inset'
        pairs, mode_desc = build_sweep_pairs(
            mode or os.getenv("SWEEP_MODE", "symmetric"),
            insets=insets,
            insets_b=insets_b,
            insets_l=insets_l,
            fixed_name=fixed_name,
            fixed_val=fixed_val,
            manual_pairs=manual_pairs,
        )
        for ib, il in pairs:
            ib_val = float(np.round(ib, 2))
            il_val = float(np.round(il, 2))
            step = {
                'run_name': f"m2_ib{ib_val:.2f}_il{il_val:.2f}mm",
                'feed_inset_b': ib_val,
                'feed_inset_l': il_val,
                'inset_b': ib_val,
                'inset_l': il_val,
            }
            if fixed_flb is not None:
                step['feed_len_b'] = fixed_flb
            if fixed_fll is not None:
                step['feed_len_l'] = fixed_fll
            if fixed_dl is not None:
                step['feed_delta_l'] = fixed_dl
            steps.append(step)
        return steps, mode_desc


def run_sweep_model2(
    mode=None,
    sweep_target=None,
    insets=None,
    insets_b=None,
    insets_l=None,
    fixed_name=None,
    fixed_val=None,
    manual_pairs=None,
    feed_lens_b=None,
    feed_lens_l=None,
    delta_l=None,
    feed_len_b=None,
    feed_len_l=None,
    feed_delta_l=None,
    inset_b=None,
    inset_l=None,
    patch_l=None,
    patch_w=None,
    patch_lengths=None,
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
    driven_port=None,
):
    """
    Run dedicated parametric sweep for Model 2.
    """
    steps, sweep_desc = build_sweep_steps(
        sweep_target=sweep_target,
        mode=mode,
        insets=insets,
        insets_b=insets_b,
        insets_l=insets_l,
        fixed_name=fixed_name,
        fixed_val=fixed_val,
        manual_pairs=manual_pairs,
        feed_lens_b=feed_lens_b,
        feed_lens_l=feed_lens_l,
        delta_l=delta_l,
        feed_len_b=feed_len_b,
        feed_len_l=feed_len_l,
        feed_delta_l=feed_delta_l,
        inset_b=inset_b,
        inset_l=inset_l,
        patch_lengths=patch_lengths,
        patch_l=patch_l,
        patch_w=patch_w,
    )

    driven_port = driven_port or os.getenv("SWEEP_DRIVEN_PORT") or os.getenv("DRIVEN_PORT", "all")
    prof = os.getenv("SWEEP_PROFILE", "precise").lower().strip()
    patch_l = patch_l if patch_l is not None else _resolve_env_float("SWEEP_PATCH_L", "PATCH_L", 30.3)
    patch_w = patch_w if patch_w is not None else _resolve_env_float("SWEEP_PATCH_W", "PATCH_W", patch_l)
    freq_min = freq_min if freq_min is not None else _resolve_env_float("SWEEP_FREQ_MIN", "FREQ_MIN", 2.280)
    freq_max = freq_max if freq_max is not None else _resolve_env_float("SWEEP_FREQ_MAX", "FREQ_MAX", 2.380)
    freq_step = freq_step if freq_step is not None else _resolve_env_float("SWEEP_FREQ_STEP", "FREQ_STEP", 0.005)
    amr_max_its = amr_max_its if amr_max_its is not None else _resolve_env_int("SWEEP_AMR_MAX_ITS", "AMR_MAX_ITS", 1)
    amr_threshold = amr_threshold if amr_threshold is not None else _resolve_env_float("SWEEP_AMR_THRESHOLD", "AMR_THRESHOLD", 0.3)
    mesh_size_min = _resolve_env_float("SWEEP_MESH_SIZE_MIN", "MESH_SIZE_MIN", 0.35 if prof == "fast" else 0.28)
    mesh_size_max = _resolve_env_float("SWEEP_MESH_SIZE_MAX", "MESH_SIZE_MAX", 8.0 if prof == "fast" else 6.0)
    mesh_dist_min = _resolve_env_float("SWEEP_MESH_DIST_MIN", "MESH_DIST_MIN", 0.5 if prof == "fast" else 0.4)
    mesh_dist_max = _resolve_env_float("SWEEP_MESH_DIST_MAX", "MESH_DIST_MAX", 5.0 if prof == "fast" else 4.5)
    farfield_nsample = farfield_nsample if farfield_nsample is not None else _resolve_env_int("SWEEP_FARFIELD_NSAMPLE", "FARFIELD_NSAMPLE", 16200)
    save_step = save_step if save_step is not None else _resolve_env_int("SWEEP_SAVE_STEP", "SAVE_STEP", 1)
    linear_tol = linear_tol if linear_tol is not None else _resolve_env_float("SWEEP_LINEAR_TOL", "LINEAR_TOL", 1e-5)
    linear_max_its = linear_max_its if linear_max_its is not None else _resolve_env_int("SWEEP_LINEAR_MAX_ITS", "LINEAR_MAX_ITS", 100)
    export_each = export_each if export_each is not None else _resolve_env_bool("SWEEP_EXPORT_EACH", True)

    total_steps = len(steps)
    print("=" * 70)
    print("STARTING MODEL 2 PARAMETRIC SWEEP (TWO-PORT LHCP MODEL)")
    print("=" * 70)
    print(f"  * Sweep target and mode:      {sweep_desc}")
    print(f"  * Total steps:                {total_steps}")
    print(f"  * Frequency range:            {freq_min:.3f} - {freq_max:.3f} GHz (step {freq_step:.4f} GHz)")
    if any('patch_L' in s for s in steps):
        p_lengths = [s['patch_L'] for s in steps]
        print(f"  * Patch dimensions (sweep L): {p_lengths} mm")
    else:
        print(f"  * Patch dimensions:           L = {patch_l:.2f} mm, W = {patch_w:.2f} mm")
    print(f"  * Gmsh mesh / AMR / Solver:   h_min={mesh_size_min} mm / {amr_max_its} it. (Tol {amr_threshold}) / {linear_tol}")
    print(f"  * 3D field saving:            every {save_step} steps")
    print(f"  * Export ParaView packages:   {'YES' if export_each else 'NO'}")
    print("  * Results table:              export/sweep_results_model2.csv")
    print("=" * 70)

    successful_runs = 0

    for i, step in enumerate(steps, start=1):
        export_name = step['run_name']
        print(f"\n>>> [{i}/{total_steps}] Model 2 step: {export_name} <<<")

        custom_params = {
            'antenna_model': 2,
            'patch_L': patch_l,
            'patch_W': patch_w,
            'driven_port': driven_port,
            'freq_min': freq_min,
            'freq_max': freq_max,
            'freq_step': freq_step,
            'mesh_size_min': mesh_size_min,
            'mesh_size_max': mesh_size_max,
            'mesh_dist_min': mesh_dist_min,
            'mesh_dist_max': mesh_dist_max,
            'amr_max_its': amr_max_its,
            'amr_threshold': amr_threshold,
            'farfield_nsample': farfield_nsample,
            'save_step': save_step,
            'linear_tol': linear_tol,
            'linear_max_its': linear_max_its,
        }
        custom_params.update(step)

        try:
            main(custom_params=custom_params, skip_simulation=skip_simulation, clean=True)

            if export_each and not skip_simulation and export_paraview_package is not None:
                try:
                    export_paraview_package(output_name=export_name)
                except Exception as exp_err:
                    print(f"Warning: Export of package {export_name} failed: {exp_err}")

            successful_runs += 1
            time.sleep(1)

        except Exception as e:
            print(f"[ERROR] Step {export_name} failed: {e}")

    print("\n" + "=" * 70)
    print(f"MODEL 2 SWEEP COMPLETED! {successful_runs}/{total_steps} runs succeeded.")
    print("=" * 70)

    print_summary_table(model_version=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Model 2 parametric sweep (Two-port LHCP)")
    parser.add_argument("--sweep-target", choices=["inset", "patch_l", "feed_len_b", "feed_len_l", "feed_delta_l", "delta_l", "feed_lens"], default=None,
                        help="Sweep target: 'inset' (default), 'patch_l', 'delta_l', 'feed_len_b', 'feed_len_l', 'feed_lens'")
    parser.add_argument("--mode", choices=["symmetric", "single_fixed", "grid", "manual"], default=None,
                        help="Sweep mode: 'symmetric' (default), 'single_fixed', 'grid', 'manual'")
    parser.add_argument("--pairs", "--manual-pairs", type=str, nargs="+", default=None, dest="manual_pairs",
                        help="Explicit pairs in 'val1:val2' format (e.g., --pairs 4.8:5.2 5.0:5.2)")
    parser.add_argument("--insets", type=float, nargs="+", default=None,
                        help="Inset values for symmetric and single_fixed modes")
    parser.add_argument("--insets-b", type=float, nargs="+", default=None,
                        help="Bottom inset_b values for grid and manual modes")
    parser.add_argument("--insets-l", type=float, nargs="+", default=None,
                        help="Left inset_l values for grid and manual modes")
    parser.add_argument("--fixed-name", choices=["inset_b", "inset_l"], default=None,
                        help="Name of the fixed feed for single_fixed mode")
    parser.add_argument("--fixed-val", type=float, default=None,
                        help="Value of the fixed feed in mm for single_fixed mode")

    # Arguments for patch length sweep
    parser.add_argument("--patch-lengths", type=float, nargs="+", default=None, dest="patch_lengths",
                        help="Patch length patch_L values in mm to sweep")

    # Arguments for sweeping and fixing feed lengths
    parser.add_argument("--delta-l", "--sweep-delta-l", type=float, nargs="+", default=None, dest="delta_l",
                        help="Phasing section Delta L values in mm to sweep")
    parser.add_argument("--feed-delta-l", type=float, default=None, dest="feed_delta_l",
                        help="Fixed feed length difference Delta L in mm")
    parser.add_argument("--feed-lens-b", type=float, nargs="+", default=None, dest="feed_lens_b",
                        help="Bottom feed length values to sweep")
    parser.add_argument("--feed-lens-l", type=float, nargs="+", default=None, dest="feed_lens_l",
                        help="Left feed length values to sweep")
    parser.add_argument("--feed-len-b", type=float, default=None, dest="feed_len_b",
                        help="Fixed bottom feed length in mm")
    parser.add_argument("--feed-len-l", type=float, default=None, dest="feed_len_l",
                        help="Fixed left feed length in mm")
    parser.add_argument("--inset-b", type=float, default=None, dest="inset_b",
                        help="Fixed bottom feed inset in mm")
    parser.add_argument("--inset-l", type=float, default=None, dest="inset_l",
                        help="Fixed left feed inset in mm")

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
    parser.add_argument("--driven-port", choices=["all", "1", "2"], default=None,
                        help="Driven port selection for Model 2: 'all' (both branches LHCP), '1' (bottom Ey only), '2' (left Ex only)")

    args = parser.parse_args()
    run_sweep_model2(
        mode=args.mode,
        sweep_target=args.sweep_target,
        insets=args.insets,
        insets_b=args.insets_b,
        insets_l=args.insets_l,
        fixed_name=args.fixed_name,
        fixed_val=args.fixed_val,
        manual_pairs=args.manual_pairs,
        feed_lens_b=args.feed_lens_b,
        feed_lens_l=args.feed_lens_l,
        delta_l=args.delta_l,
        feed_len_b=args.feed_len_b,
        feed_len_l=args.feed_len_l,
        feed_delta_l=args.feed_delta_l,
        inset_b=args.inset_b,
        inset_l=args.inset_l,
        patch_l=args.patch_l,
        patch_w=args.patch_w,
        patch_lengths=args.patch_lengths,
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
