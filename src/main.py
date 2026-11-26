import os
import sys
import shutil
import subprocess
import json
import numpy as np
import matplotlib.pyplot as plt
import gmsh

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.abspath(os.path.join(_CURRENT_DIR, "..", "scripts"))
if os.path.exists(_SCRIPTS_DIR) and _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from geometry import build_model
from mesh import assign_physical_groups_and_mesh
from palace_builder import build_palace_config
from runner import run_palace

from tracker import analyze_and_log_run
from postpro_utils import (
    ensure_paraview_linked,
    load_env,
    copy_postpro_directory,
    merge_two_port_simulations,
)

from rf_calc import (
    C_0_MM_GHZ,
    DESIGN_FREQ_GHZ,
    PORT_Z0
)

def _resolve_param(key, env_key, default_val, custom_params=None, cast_type=float):
    """Resolve parameter with priority: custom_params > os.environ > default."""
    if custom_params:
        if key in custom_params and custom_params[key] is not None:
            return cast_type(custom_params[key])
        if key.lower() in custom_params and custom_params[key.lower()] is not None:
            return cast_type(custom_params[key.lower()])
        if key.upper() in custom_params and custom_params[key.upper()] is not None:
            return cast_type(custom_params[key.upper()])
    val = os.getenv(env_key)
    if val is not None and str(val).strip() != "":
        try:
            return cast_type(val)
        except (ValueError, TypeError):
            pass
    return default_val


def _resolve_param_aliases(keys, env_keys, default_val, custom_params=None, cast_type=float):
    """Resolve parameter across an alias list with priority: custom_params > os.environ > default."""
    if custom_params:
        for key in keys:
            for variant in (key, key.lower(), key.upper()):
                if variant in custom_params and custom_params[variant] is not None:
                    return cast_type(custom_params[variant])
    for env_key in env_keys:
        val = os.getenv(env_key)
        if val is not None and val != "":
            try:
                return cast_type(val)
            except (ValueError, TypeError):
                pass
    return default_val


def _resolve_hybrid_stage_params(params, custom_params=None):
    """Shared configuration for shallow inset notches, transformers, and phasing (Model 3 and Model 4)."""
    trans_w = _resolve_param_aliases(('trans_w', 'w_T', 'w_trans'), ('TRANS_W',), 0.42, custom_params, float)
    trans_w_b = _resolve_param_aliases(('trans_w_b', 'w_T_b', 'w_trans_b'), ('TRANS_W_B',), trans_w, custom_params, float)
    trans_w_l = _resolve_param_aliases(('trans_w_l', 'w_T_l', 'w_trans_l'), ('TRANS_W_L',), trans_w, custom_params, float)
    params['trans_w'] = trans_w
    params['trans_w_b'] = trans_w_b
    params['trans_w_l'] = trans_w_l
    params['w_T'] = trans_w

    trans_l = _resolve_param_aliases(('trans_l', 'l_T', 'l_trans'), ('TRANS_L',), None, custom_params, float)
    trans_l_b = _resolve_param_aliases(('trans_l_b', 'l_T_b', 'l_trans_b'), ('TRANS_L_B',), trans_l, custom_params, float)
    trans_l_l = _resolve_param_aliases(('trans_l_l', 'l_T_l', 'l_trans_l'), ('TRANS_L_L',), trans_l, custom_params, float)
    if trans_l is not None:
        params['trans_l'] = trans_l
        params['l_T'] = trans_l
    if trans_l_b is not None:
        params['trans_l_b'] = trans_l_b
    if trans_l_l is not None:
        params['trans_l_l'] = trans_l_l

    default_inset = _resolve_param_aliases(('feed_inset', 'inset', 'y0'), ('FEED_INSET', 'INSET'), 2.5, custom_params, float)
    feed_inset_b = _resolve_param_aliases(('feed_inset_b', 'inset_b', 'y0b'), ('FEED_INSET_B', 'INSET_B'), default_inset, custom_params, float)
    feed_inset_l = _resolve_param_aliases(('feed_inset_l', 'inset_l', 'y0l'), ('FEED_INSET_L', 'INSET_L'), default_inset, custom_params, float)

    default_gap = _resolve_param_aliases(('feed_inset_gap', 'inset_gap'), ('FEED_INSET_GAP', 'INSET_GAP'), 0.5, custom_params, float)
    feed_gap_b = _resolve_param_aliases(('feed_inset_gap_b', 'inset_gap_b', 'gap_b'), ('FEED_INSET_GAP_B', 'INSET_GAP_B'), default_gap, custom_params, float)
    feed_gap_l = _resolve_param_aliases(('feed_inset_gap_l', 'inset_gap_l', 'gap_l'), ('FEED_INSET_GAP_L', 'INSET_GAP_L'), default_gap, custom_params, float)

    params['feed_inset_b'] = feed_inset_b
    params['feed_inset_l'] = feed_inset_l
    params['inset_b'] = feed_inset_b
    params['inset_l'] = feed_inset_l
    params['inset_gap_b'] = feed_gap_b
    params['inset_gap_l'] = feed_gap_l

    feed_delta_l = _resolve_param_aliases(
        ('feed_delta_l', 'delta_l', 'phase_delay_mm', 'feed_delta'),
        ('FEED_DELTA_L', 'DELTA_L'),
        None,
        custom_params,
        float,
    )
    if feed_delta_l is not None:
        params['feed_delta_l'] = feed_delta_l

    return trans_w, feed_inset_b, feed_inset_l, feed_delta_l

def _is_link_or_junction(path):
    """Return True if path is a symlink or a Windows directory junction."""
    if os.path.islink(path):
        return True
    if hasattr(os.path, "isjunction") and os.path.isjunction(path):
        return True
    if sys.platform == "win32":
        try:
            st = os.lstat(path)
            if getattr(st, "st_file_attributes", 0) & 0x0400:  # FILE_ATTRIBUTE_REPARSE_POINT
                return True
        except OSError:
            pass
    return False


def _unlink_reparse_point(path):
    """Safely unlink a symlink or Windows junction without deleting target contents."""
    if os.path.islink(path):
        try:
            os.unlink(path)
            return
        except OSError:
            pass
    try:
        os.rmdir(path)
        return
    except OSError:
        pass
    if sys.platform == "win32":
        subprocess.run(
            ["cmd", "/c", "rmdir", path],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        os.remove(path)


def _clean_dir(path):
    """Safely clean directory contents including symlinks and Windows junctions."""
    if not os.path.exists(path) and not os.path.lexists(path):
        return
    if _is_link_or_junction(path):
        _unlink_reparse_point(path)
        return
    if not os.path.isdir(path):
        return
    for item in os.listdir(path):
        p = os.path.join(path, item)
        try:
            if _is_link_or_junction(p):
                _unlink_reparse_point(p)
            elif os.path.isdir(p):
                _clean_dir(p)
                os.rmdir(p)
            else:
                os.remove(p)
        except Exception as e:
            print(f"Warning while deleting {p}: {e}")


def clean_previous_outputs(data_dir=None):
    print("--- 0. Cleaning previous simulation outputs ---")
    if data_dir is None:
        _, data_dir = load_env()
    dirs_to_clean = [
        os.path.join(data_dir, "postpro"),
        os.path.join(data_dir, "postpro_p1"),
        os.path.join(data_dir, "postpro_p2"),
    ]
    for d in dirs_to_clean:
        _clean_dir(d)
    print(f"Simulation output directories ({os.path.join(data_dir, 'postpro*')}) have been cleaned.")

def main(custom_params=None, skip_simulation=False, clean=False, profile=None):
    # Load .env file (and optional variant profile) and ensure target data directory exists
    root_dir, data_dir = load_env(profile=profile)
    os.makedirs(data_dir, exist_ok=True)

    if clean:
        clean_previous_outputs(data_dir=data_dir)

    # Antenna model (1 = original 50 Ohm T-splitter, 2 = dual-port 100 Ohm, 3 = hybrid 2-port, 4 = final 50 Ohm T-junction with bends, 5 = dual-port curved 100 Ohm, 6 = dual-port curved internal, 7 = mirrored Model 4 RHCP)
    antenna_model = _resolve_param('antenna_model', 'ANTENNA_MODEL', 1, custom_params, int)

    # 1. Material and frequency band parameterization
    sub_h = _resolve_param('sub_h', 'SUB_H', 1.52, custom_params, float)
    eps_r = _resolve_param('eps_r', 'EPS_R', 4.3, custom_params, float)
    tan_delta = _resolve_param('tan_delta', 'TAN_DELTA', 0.02, custom_params, float)
    design_freq_ghz = _resolve_param('design_freq_ghz', 'DESIGN_FREQ_GHZ', DESIGN_FREQ_GHZ, custom_params, float)
    
    # Frequency sweep band (GHz)
    freq_min = _resolve_param('freq_min', 'FREQ_MIN', 2.320, custom_params, float)
    freq_max = _resolve_param('freq_max', 'FREQ_MAX', 2.345, custom_params, float)
    freq_step = _resolve_param('freq_step', 'FREQ_STEP', 0.005, custom_params, float)
    
    # Mesh and solver parameters
    mesh_size_max = _resolve_param('mesh_size_max', 'MESH_SIZE_MAX', 8.0, custom_params, float)
    mesh_size_min = _resolve_param('mesh_size_min', 'MESH_SIZE_MIN', 0.5, custom_params, float)
    mesh_dist_min = _resolve_param('mesh_dist_min', 'MESH_DIST_MIN', 0.5, custom_params, float)
    mesh_dist_max = _resolve_param('mesh_dist_max', 'MESH_DIST_MAX', 6.0, custom_params, float)
    amr_max_its = _resolve_param('amr_max_its', 'AMR_MAX_ITS', 2, custom_params, int)
    amr_threshold = _resolve_param('amr_threshold', 'AMR_THRESHOLD', 0.2, custom_params, float)
    farfield_nsample = _resolve_param('farfield_nsample', 'FARFIELD_NSAMPLE', 16200, custom_params, int)
    save_step = _resolve_param('save_step', 'SAVE_STEP', 1, custom_params, int)
    
    default_port_z0 = 100.0 if antenna_model in (2, 3, 5, 6) else PORT_Z0
    port_impedance = _resolve_param('port_impedance', 'PORT_IMPEDANCE', default_port_z0, custom_params, float)
    linear_tol = _resolve_param('linear_tol', 'LINEAR_TOL', 1e-6, custom_params, float)
    linear_max_its = _resolve_param('linear_max_its', 'LINEAR_MAX_ITS', 100, custom_params, int)
    linear_max_size = _resolve_param('linear_max_size', 'LINEAR_MAX_SIZE', None, custom_params, int)

    print(f"--- Model {antenna_model} | Freq {freq_min:.3f}-{freq_max:.3f} GHz (step {freq_step:.4f} GHz), Mesh {mesh_size_min}-{mesh_size_max} mm, Port Z0 {port_impedance:.1f} Ohm ---")

    # Patch geometry (default 29.95 mm for Models 5 & 6; 28.8 mm for Models 2, 3, 4 & 7; 30.3 mm for Model 1)
    default_patch_l = 29.95 if antenna_model in (5, 6) else (28.8 if antenna_model in (2, 3, 4, 7) else 30.3)
    patch_l = _resolve_param('patch_L', 'PATCH_L', default_patch_l, custom_params, float)
    patch_w = _resolve_param('patch_W', 'PATCH_W', patch_l, custom_params, float)

    # Air box dimensions: wall distance >= lambda_0 / 4 at lowest frequency
    lambda_0_max = C_0_MM_GHZ / freq_min
    air_margin = float(np.round(lambda_0_max / 4.0, 1))

    params = {
        'antenna_model': antenna_model,
        'patch_L': patch_l,
        'patch_W': patch_w,
        'sub_h': sub_h,
        'air_margin': air_margin,
        'eps_r': eps_r,
        'tan_delta': tan_delta,
        'mesh_size_max': mesh_size_max,
        'mesh_size_min': mesh_size_min,
        'mesh_dist_min': mesh_dist_min,
        'mesh_dist_max': mesh_dist_max,
        'freq_min': freq_min,
        'freq_max': freq_max,
        'freq_step': freq_step,
        'amr_max_its': amr_max_its,
        'amr_threshold': amr_threshold,
        'farfield_nsample': farfield_nsample,
        'save_step': save_step,
        'port_impedance': port_impedance,
        'linear_tol': linear_tol,
        'linear_max_its': linear_max_its,
        'linear_max_size': linear_max_size,
        'design_freq_ghz': design_freq_ghz,
    }

    if antenna_model == 6:
        # MODEL 6: Dual-port model with curved 100 Ohm branches and internal ports (derived from Model 4)
        trans_w, feed_inset_b, feed_inset_l, feed_delta_l = _resolve_hybrid_stage_params(params, custom_params)

        bend_radius = _resolve_param_aliases(('feed_bend_radius', 'bend_radius'), ('FEED_BEND_RADIUS',), 3.0, custom_params, float)
        t_fillet_r = _resolve_param_aliases(('feed_t_fillet_r', 't_fillet_r'), ('FEED_T_FILLET_R',), 0.8, custom_params, float)
        feed_50_len = _resolve_param_aliases(('feed_50_len', 'l1'), ('FEED_50_LEN',), 9.0, custom_params, float)
        arm_offset = _resolve_param_aliases(('feed_arm_offset', 'arm_offset'), ('FEED_ARM_OFFSET',), None, custom_params, float)
        end_straight = _resolve_param_aliases(('feed_end_straight', 'end_straight'), ('FEED_END_STRAIGHT',), 4.6, custom_params, float)

        driven_port = _resolve_param('driven_port', 'DRIVEN_PORT', 'all', custom_params, str)
        params['driven_port'] = driven_port

        params['feed_bend_radius'] = bend_radius
        params['feed_t_fillet_r'] = t_fillet_r
        params['feed_50_len'] = feed_50_len
        params['feed_end_straight'] = end_straight
        if arm_offset is not None:
            params['feed_arm_offset'] = arm_offset

        optional_m6_specs = [
            (('feed_50_w', 'w_50', 'w1'), ('FEED_50_W',), 'feed_50_w'),
            (('feed_100_w', 'w_feed', 'w_100', 'w2'), ('FEED_100_W',), 'feed_100_w'),
            (('sub_margin',), ('SUB_MARGIN',), 'sub_margin'),
            (('feed_x_T', 'x_T'), ('FEED_T_X',), 'feed_x_T'),
            (('feed_y_T', 'y_T'), ('FEED_T_Y',), 'feed_y_T'),
            (('feed_y_bot', 'y_bot'), ('FEED_Y_BOT',), 'feed_y_bot'),
            (('sub_W', 'sub_w'), ('SUB_W',), 'sub_W'),
            (('sub_L', 'sub_l'), ('SUB_L',), 'sub_L'),
        ]
        for aliases, env_keys, target_key in optional_m6_specs:
            val = _resolve_param_aliases(aliases, env_keys, None, custom_params, float)
            if val is not None:
                params[target_key] = val

        dl_str = f", delta_l={feed_delta_l:.2f}mm" if feed_delta_l is not None else ""
        print(
            f"--- Model 6 (Dual-port curved model with internal 100 Ω ports): w_T={trans_w:.2f} mm, "
            f"y0b={feed_inset_b:.2f} mm, y0l={feed_inset_l:.2f} mm, R_bend={bend_radius:.2f} mm, "
            f"Driven = {driven_port}{dl_str} ---"
        )

    elif antenna_model == 5:
        # MODEL 5: Dual-port model with curved 100 Ohm branches (without 50 Ohm T-junction)
        trans_w, feed_inset_b, feed_inset_l, feed_delta_l = _resolve_hybrid_stage_params(params, custom_params)

        bend_radius = _resolve_param_aliases(('feed_bend_radius', 'bend_radius'), ('FEED_BEND_RADIUS',), 3.0, custom_params, float)
        arm_offset = _resolve_param_aliases(('feed_arm_offset', 'arm_offset'), ('FEED_ARM_OFFSET',), None, custom_params, float)
        end_straight = _resolve_param_aliases(('feed_end_straight', 'end_straight'), ('FEED_END_STRAIGHT',), 4.6, custom_params, float)
        port_offset = _resolve_param_aliases(('feed_port_offset', 'port_offset'), ('FEED_PORT_OFFSET', 'PORT_OFFSET'), 3.0, custom_params, float)

        driven_port = _resolve_param('driven_port', 'DRIVEN_PORT', 'all', custom_params, str)
        params['driven_port'] = driven_port

        params['feed_bend_radius'] = bend_radius
        params['feed_end_straight'] = end_straight
        params['feed_port_offset'] = port_offset
        if arm_offset is not None:
            params['feed_arm_offset'] = arm_offset

        optional_m5_specs = [
            (('feed_100_w', 'w_feed', 'w_100', 'w2'), ('FEED_100_W',), 'feed_100_w'),
            (('sub_margin',), ('SUB_MARGIN',), 'sub_margin'),
            (('feed_x_T', 'x_T'), ('FEED_T_X',), 'feed_x_T'),
            (('feed_y_T', 'y_T'), ('FEED_T_Y',), 'feed_y_T'),
            (('feed_y_bot', 'y_bot'), ('FEED_Y_BOT',), 'feed_y_bot'),
            (('sub_W', 'sub_w'), ('SUB_W',), 'sub_W'),
            (('sub_L', 'sub_l'), ('SUB_L',), 'sub_L'),
        ]
        for aliases, env_keys, target_key in optional_m5_specs:
            val = _resolve_param_aliases(aliases, env_keys, None, custom_params, float)
            if val is not None:
                params[target_key] = val

        dl_str = f", delta_l={feed_delta_l:.2f}mm" if feed_delta_l is not None else ""
        print(
            f"--- Model 5 (Dual-port curved 100 Ω): w_T={trans_w:.2f} mm, "
            f"y0b={feed_inset_b:.2f} mm, y0l={feed_inset_l:.2f} mm, R_bend={bend_radius:.2f} mm, "
            f"Driven = {driven_port}, Port offset={port_offset:.2f} mm{dl_str} ---"
        )

    elif antenna_model == 7:
        # MODEL 7: Mirrored Model 4 along Y-axis for opposite polarization RHCP (right-side 50 Ohm T-junction with bends)
        trans_w, feed_inset_b, feed_inset_l, feed_delta_l = _resolve_hybrid_stage_params(params, custom_params)

        bend_radius = _resolve_param_aliases(('feed_bend_radius', 'bend_radius'), ('FEED_BEND_RADIUS',), 3.0, custom_params, float)
        t_fillet_r = _resolve_param_aliases(('feed_t_fillet_r', 't_fillet_r'), ('FEED_T_FILLET_R',), 0.8, custom_params, float)
        feed_50_len = _resolve_param_aliases(('feed_50_len', 'l1'), ('FEED_50_LEN',), 9.0, custom_params, float)
        arm_offset = _resolve_param_aliases(('feed_arm_offset', 'arm_offset'), ('FEED_ARM_OFFSET',), None, custom_params, float)
        end_straight = _resolve_param_aliases(('feed_end_straight', 'end_straight'), ('FEED_END_STRAIGHT',), 4.6, custom_params, float)

        params['feed_bend_radius'] = bend_radius
        params['feed_t_fillet_r'] = t_fillet_r
        params['feed_50_len'] = feed_50_len
        params['feed_end_straight'] = end_straight
        if arm_offset is not None:
            params['feed_arm_offset'] = arm_offset

        optional_m7_specs = [
            (('feed_50_w', 'w_50', 'w1'), ('FEED_50_W',), 'feed_50_w'),
            (('feed_100_w', 'w_feed', 'w_100', 'w2'), ('FEED_100_W',), 'feed_100_w'),
            (('sub_margin',), ('SUB_MARGIN',), 'sub_margin'),
            (('feed_x_T', 'x_T'), ('FEED_T_X',), 'feed_x_T'),
            (('feed_y_T', 'y_T'), ('FEED_T_Y',), 'feed_y_T'),
            (('sub_W', 'sub_w'), ('SUB_W',), 'sub_W'),
            (('sub_L', 'sub_l'), ('SUB_L',), 'sub_L'),
        ]
        for aliases, env_keys, target_key in optional_m7_specs:
            val = _resolve_param_aliases(aliases, env_keys, None, custom_params, float)
            if val is not None:
                params[target_key] = val

        dl_str = f", delta_l={feed_delta_l:.2f}mm" if feed_delta_l is not None else ""
        print(
            f"--- Model 7 (Mirrored 50 Ω T-junction for RHCP + bends): w_T={trans_w:.2f} mm, "
            f"y0b={feed_inset_b:.2f} mm, y0r={feed_inset_l:.2f} mm, R_bend={bend_radius:.2f} mm, "
            f"L50={feed_50_len:.2f} mm{dl_str} ---"
        )

    elif antenna_model == 4:
        # MODEL 4: Final model completing Model 3 (rotated left 50 Ohm T-junction without meander)
        trans_w, feed_inset_b, feed_inset_l, feed_delta_l = _resolve_hybrid_stage_params(params, custom_params)

        bend_radius = _resolve_param_aliases(('feed_bend_radius', 'bend_radius'), ('FEED_BEND_RADIUS',), 3.0, custom_params, float)
        t_fillet_r = _resolve_param_aliases(('feed_t_fillet_r', 't_fillet_r'), ('FEED_T_FILLET_R',), 0.8, custom_params, float)
        feed_50_len = _resolve_param_aliases(('feed_50_len', 'l1'), ('FEED_50_LEN',), 9.0, custom_params, float)
        arm_offset = _resolve_param_aliases(('feed_arm_offset', 'arm_offset'), ('FEED_ARM_OFFSET',), None, custom_params, float)
        end_straight = _resolve_param_aliases(('feed_end_straight', 'end_straight'), ('FEED_END_STRAIGHT',), 4.6, custom_params, float)

        params['feed_bend_radius'] = bend_radius
        params['feed_t_fillet_r'] = t_fillet_r
        params['feed_50_len'] = feed_50_len
        params['feed_end_straight'] = end_straight
        if arm_offset is not None:
            params['feed_arm_offset'] = arm_offset

        optional_m4_specs = [
            (('feed_50_w', 'w_50', 'w1'), ('FEED_50_W',), 'feed_50_w'),
            (('feed_100_w', 'w_feed', 'w_100', 'w2'), ('FEED_100_W',), 'feed_100_w'),
            (('sub_margin',), ('SUB_MARGIN',), 'sub_margin'),
            (('feed_x_T', 'x_T'), ('FEED_T_X',), 'feed_x_T'),
            (('feed_y_T', 'y_T'), ('FEED_T_Y',), 'feed_y_T'),
            (('sub_W', 'sub_w'), ('SUB_W',), 'sub_W'),
            (('sub_L', 'sub_l'), ('SUB_L',), 'sub_L'),
        ]
        for aliases, env_keys, target_key in optional_m4_specs:
            val = _resolve_param_aliases(aliases, env_keys, None, custom_params, float)
            if val is not None:
                params[target_key] = val

        dl_str = f", delta_l={feed_delta_l:.2f}mm" if feed_delta_l is not None else ""
        print(
            f"--- Model 4 (Final 50 Ω T-junction + bends): w_T={trans_w:.2f} mm, "
            f"y0b={feed_inset_b:.2f} mm, y0l={feed_inset_l:.2f} mm, R_bend={bend_radius:.2f} mm, "
            f"L50={feed_50_len:.2f} mm{dl_str} ---"
        )

    elif antenna_model == 3:
        # MODEL 3: Hybrid two-stage matching (Path B)
        trans_w, feed_inset_b, feed_inset_l, feed_delta_l = _resolve_hybrid_stage_params(params, custom_params)

        driven_port = _resolve_param('driven_port', 'DRIVEN_PORT', 'all', custom_params, str)
        params['driven_port'] = driven_port

        feed_len_b = _resolve_param('feed_len_b', 'FEED_LEN_B', None, custom_params, float)
        feed_len_l = _resolve_param('feed_len_l', 'FEED_LEN_L', None, custom_params, float)
        if feed_len_b is not None:
            params['feed_len_b'] = feed_len_b
        if feed_len_l is not None:
            params['feed_len_l'] = feed_len_l

        len_info = []
        if feed_len_b is not None:
            len_info.append(f"feed_len_b={feed_len_b:.2f}mm")
        if feed_len_l is not None:
            len_info.append(f"feed_len_l={feed_len_l:.2f}mm")
        if feed_delta_l is not None:
            len_info.append(f"delta_l={feed_delta_l:.2f}mm")
        len_str = f", {', '.join(len_info)}" if len_info else ""

        print(f"--- Model 3 (Hybrid Matching): w_T={trans_w:.2f} mm, y0b={feed_inset_b:.2f} mm, y0l={feed_inset_l:.2f} mm, Driven = {driven_port}{len_str} ---")

    elif antenna_model == 2:
        # MODEL 2: Independent inset depths inset_b and inset_l
        feed_inset_b = _resolve_param('feed_inset_b', 'FEED_INSET_B', None, custom_params, float)
        if feed_inset_b is None:
            feed_inset_b = _resolve_param('inset_b', 'INSET_B', None, custom_params, float)
        if feed_inset_b is None:
            feed_inset_b = _resolve_param('feed_inset', 'FEED_INSET', 0.0, custom_params, float)

        feed_inset_l = _resolve_param('feed_inset_l', 'FEED_INSET_L', None, custom_params, float)
        if feed_inset_l is None:
            feed_inset_l = _resolve_param('inset_l', 'INSET_L', None, custom_params, float)
        if feed_inset_l is None:
            feed_inset_l = _resolve_param('feed_inset', 'FEED_INSET', 0.0, custom_params, float)

        feed_gap_b = _resolve_param('feed_inset_gap_b', 'FEED_INSET_GAP_B', None, custom_params, float)
        if feed_gap_b is None:
            feed_gap_b = _resolve_param('inset_gap_b', 'INSET_GAP_B', None, custom_params, float)
        if feed_gap_b is None:
            feed_gap_b = _resolve_param('feed_inset_gap', 'FEED_INSET_GAP', None, custom_params, float)

        feed_gap_l = _resolve_param('feed_inset_gap_l', 'FEED_INSET_GAP_L', None, custom_params, float)
        if feed_gap_l is None:
            feed_gap_l = _resolve_param('inset_gap_l', 'INSET_GAP_L', None, custom_params, float)
        if feed_gap_l is None:
            feed_gap_l = _resolve_param('feed_inset_gap', 'FEED_INSET_GAP', None, custom_params, float)

        params['feed_inset_b'] = feed_inset_b
        params['feed_inset_l'] = feed_inset_l
        params['inset_b'] = feed_inset_b
        params['inset_l'] = feed_inset_l
        if feed_gap_b is not None:
            params['inset_gap_b'] = feed_gap_b
        if feed_gap_l is not None:
            params['inset_gap_l'] = feed_gap_l

        driven_port = _resolve_param('driven_port', 'DRIVEN_PORT', 'all', custom_params, str)
        params['driven_port'] = driven_port

        # Explicit feedline lengths (feed_len_b, feed_len_l, feed_delta_l)
        feed_len_b = _resolve_param('feed_len_b', 'FEED_LEN_B', None, custom_params, float)
        if feed_len_b is None:
            feed_len_b = _resolve_param('feed_length_b', 'FEED_LENGTH_B', None, custom_params, float)
        if feed_len_b is None:
            feed_len_b = _resolve_param('L_feed_b', 'L_FEED_B', None, custom_params, float)

        feed_len_l = _resolve_param('feed_len_l', 'FEED_LEN_L', None, custom_params, float)
        if feed_len_l is None:
            feed_len_l = _resolve_param('feed_length_l', 'FEED_LENGTH_L', None, custom_params, float)
        if feed_len_l is None:
            feed_len_l = _resolve_param('L_feed_l', 'L_FEED_L', None, custom_params, float)

        feed_delta_l = _resolve_param('feed_delta_l', 'FEED_DELTA_L', None, custom_params, float)
        if feed_delta_l is None:
            feed_delta_l = _resolve_param('delta_l', 'DELTA_L', None, custom_params, float)
        if feed_delta_l is None:
            feed_delta_l = _resolve_param('phase_delay_mm', 'PHASE_DELAY_MM', None, custom_params, float)

        if feed_len_b is not None:
            params['feed_len_b'] = feed_len_b
        if feed_len_l is not None:
            params['feed_len_l'] = feed_len_l
        if feed_delta_l is not None:
            params['feed_delta_l'] = feed_delta_l

        len_info = []
        if feed_len_b is not None:
            len_info.append(f"feed_len_b={feed_len_b:.2f}mm")
        if feed_len_l is not None:
            len_info.append(f"feed_len_l={feed_len_l:.2f}mm")
        if feed_delta_l is not None:
            len_info.append(f"delta_l={feed_delta_l:.2f}mm")
        len_str = f", {', '.join(len_info)}" if len_info else ""

        print(f"--- Model 2: Bottom inset (Ey) = {feed_inset_b:.2f} mm, Left inset (Ex) = {feed_inset_l:.2f} mm, Driven = {driven_port}{len_str} ---")

    else:
        # MODEL 1: Original T-splitter and analytical feed network
        feed_inset = _resolve_param('feed_inset', 'FEED_INSET', 0.0, custom_params, float)
        if feed_inset == 0.0:
            feed_inset = _resolve_param('inset', 'INSET', 0.0, custom_params, float)

        feed_inset_gap = _resolve_param('feed_inset_gap', 'FEED_INSET_GAP', None, custom_params, float)
        if feed_inset_gap is None:
            feed_inset_gap = _resolve_param('inset_gap', 'INSET_GAP', None, custom_params, float)

        feed_inset_width = _resolve_param('feed_inset_width', 'FEED_INSET_WIDTH', None, custom_params, float)
        if feed_inset_width is None:
            feed_inset_width = _resolve_param('inset_width', 'INSET_WIDTH', None, custom_params, float)

        from rf_calc import calc_feed_network_dimensions
        feed_net = calc_feed_network_dimensions(
            patch_w, patch_l, sub_h, eps_r,
            freq_ghz=DESIGN_FREQ_GHZ, port_z0=port_impedance, inset=feed_inset
        )
        params.update(feed_net)
        params['feed_inset'] = feed_inset
        params['inset'] = feed_inset
        if feed_inset_gap is not None:
            params['inset_gap'] = feed_inset_gap
        if feed_inset_width is not None:
            params['inset_width'] = feed_inset_width

        print(f"--- Model 1: L = {patch_l:.2f} mm, W = {patch_w:.2f} mm, Inset: {feed_inset:.2f} mm ---")

    run_name = None
    if custom_params:
        params.update(custom_params)
        run_name = custom_params.get('run_name') or "_".join([f"{k}={v}" for k, v in custom_params.items()])

    print("--- 1. Generating geometry (OpenCASCADE) ---")
    build_model(params)
    
    # Export 3D model for CAD
    step_file = os.path.join(data_dir, "antenna_model.step")
    gmsh.write(step_file)
    print(f"Geometry exported to {step_file} for CAD inspection.")
    
    # 2D top view of geometry via Matplotlib
    from visualization import plot_geometry
    plot_geometry(params, filename=os.path.join(data_dir, "geometry_iso.png"))
    
    print("--- 2. Domain classification and mesh generation (Gmsh) ---")
    assign_physical_groups_and_mesh(params, data_dir=data_dir)
    
    print("--- 3. Generating Palace configuration ---")
    build_palace_config(params, data_dir=data_dir)

    # Save current model parameters to data_dir/params.json
    pfile = os.path.join(data_dir, "params.json")
    try:
        def _to_json_val(val):
            if isinstance(val, (np.integer,)):
                return int(val)
            if isinstance(val, (np.floating,)):
                return float(val)
            if isinstance(val, np.ndarray):
                return val.tolist()
            if isinstance(val, dict):
                return {k: _to_json_val(v) for k, v in val.items()}
            if isinstance(val, (list, tuple)):
                return [_to_json_val(v) for v in val]
            return val

        serializable_params = {k: _to_json_val(v) for k, v in params.items() if not str(k).startswith('_')}
        os.makedirs(data_dir, exist_ok=True)
        with open(pfile, "w", encoding="utf-8") as pf:
            json.dump(serializable_params, pf, indent=4)
        print(f"Model parameters saved to {pfile}")
    except Exception as e:
        print(f"Warning while saving {pfile}: {e}")

    if skip_simulation:
        print("--- Done: Geometry, STEP CAD model, preview, and mesh generated locally without running Docker simulation. ---")
        return

    print("--- 4. Running physical simulation (Palace) ---")
    output_dir = os.path.join(data_dir, "postpro")

    driven_mode = str(params.get('driven_port', os.getenv('DRIVEN_PORT', 'all'))).lower().strip()
    is_model_matrix = (
        antenna_model in (2, 3, 5, 6)
        and driven_mode in ('all', 'both', 'matrix', 'full', 's_matrix')
    )

    if is_model_matrix:
        print("--- Running two-step simulation for full 2-port S-matrix (Port 1 and Port 2) ---")

        # Clean any leftovers from previous runs in postpro before step 1
        _clean_dir(output_dir)

        # STEP 1: Port 1 (bottom, Ey)
        print("\n>>> Step 1/2: Simulating Port 1 excitation (Bottom feedline Ey, Port 2 = 100 Ω load) <<<")
        params_p1 = dict(params)
        params_p1['driven_port'] = '1'
        build_palace_config(params_p1, data_dir=data_dir)

        try:
            run_palace()
        except Exception as e:
            print(f"Warning: Simulation Step 1 (Port 1) failed: {e}")
            return

        p1_dir = os.path.join(data_dir, "postpro_p1")
        _clean_dir(p1_dir)
        copy_postpro_directory(output_dir, p1_dir)
        _clean_dir(output_dir)

        # STEP 2: Port 2 (left, Ex)
        print("\n>>> Step 2/2: Simulating Port 2 excitation (Left feedline Ex, Port 1 = 100 Ω load) <<<")
        params_p2 = dict(params)
        params_p2['driven_port'] = '2'
        build_palace_config(params_p2, data_dir=data_dir)

        try:
            run_palace()
        except Exception as e:
            print(f"Warning: Simulation Step 2 (Port 2) failed: {e}")
            return

        p2_dir = os.path.join(data_dir, "postpro_p2")
        _clean_dir(p2_dir)
        copy_postpro_directory(output_dir, p2_dir)
        _clean_dir(output_dir)

        # STEP 3: Merge outputs from both runs into full 2-port matrix in data/postpro
        print("\n--- Merging outputs from both runs into full 2-port S-matrix ---")
        merge_two_port_simulations(p1_dir, p2_dir, output_dir)

        # Restore default config.json
        build_palace_config(params, data_dir=data_dir)

    else:
        # Standard single-step run (Model 1, or single explicitly selected port for Models 2 and 3)
        build_palace_config(params, data_dir=data_dir)
        try:
            run_palace()
        except Exception as e:
            print(f"Warning: Palace simulation could not be started: {e}")
            return

    # Link paraview folder to the latest iteration if Palace ran in AMR mode
    ensure_paraview_linked(data_dir)

    print("--- 5. Post-processing results ---")
    
    # Process results according to the antenna model
    if antenna_model in (2, 3, 5, 6):
        _process_results_model2(params, output_dir, data_dir, run_name)
    else:
        _process_results_model1(params, output_dir, data_dir, run_name)

    # 6. Automatic export package if requested
    if params.get('export', False) or params.get('export_name'):
        try:
            from export_package import export_paraview_package
            exp_name = params.get('export_name') or run_name
            print(f"\n--- 6. Exporting results package: {exp_name or 'antenna_export'} ---")
            export_paraview_package(output_name=exp_name, run_name=run_name, model_version=antenna_model)
        except Exception as e:
            print(f"Warning during package export: {e}")

def _generate_advanced_plots(output_dir, data_dir):
    """Automatically generate S-parameters/impedance plot and 2D/3D radiation patterns after each simulation step."""
    params_for_deembed = None
    params_path = os.path.join(data_dir, "params.json")
    if os.path.exists(params_path):
        try:
            with open(params_path, "r", encoding="utf-8") as f:
                params_for_deembed = json.load(f)
        except Exception:
            pass

    # 1. S-parameters and impedance plot
    try:
        from plot_s_parameters import plot_s_parameters
        s_png_data = os.path.join(data_dir, "plot_s_parameters.png")
        s_png_post = os.path.join(output_dir, "plot_s_parameters.png")
        plot_s_parameters(output_dir, output_png=s_png_data, params=params_for_deembed)
        if os.path.abspath(s_png_data) != os.path.abspath(s_png_post) and os.path.exists(s_png_data):
            shutil.copy2(s_png_data, s_png_post)
    except Exception as e:
        print(f"Warning during automatic S-parameters plot generation: {e}")

    # 2. 2D and 3D radiation patterns (if farfield-rE.csv exists)
    try:
        from plot_radiation_pattern import plot_radiation_pattern_2d, plot_radiation_pattern_3d
        ff_file = os.path.join(output_dir, "farfield-rE.csv")
        if os.path.exists(ff_file) and os.path.getsize(ff_file) > 0:
            rd_2d_data = os.path.join(data_dir, "radiation_pattern_2d.png")
            rd_2d_post = os.path.join(output_dir, "radiation_pattern_2d.png")
            rd_3d_data = os.path.join(data_dir, "radiation_pattern_3d.png")
            rd_3d_post = os.path.join(output_dir, "radiation_pattern_3d.png")
            
            plot_radiation_pattern_2d(output_dir, output_png=rd_2d_data)
            plot_radiation_pattern_3d(output_dir, output_png=rd_3d_data)
            
            if os.path.abspath(rd_2d_data) != os.path.abspath(rd_2d_post) and os.path.exists(rd_2d_data):
                shutil.copy2(rd_2d_data, rd_2d_post)
            if os.path.abspath(rd_3d_data) != os.path.abspath(rd_3d_post) and os.path.exists(rd_3d_data):
                shutil.copy2(rd_3d_data, rd_3d_post)
    except Exception as e:
        print(f"Warning during automatic radiation pattern generation: {e}")

    # 3. Impedance de-embedding plot (plot_deembedding.png)
    try:
        from plot_deembedding import plot_impedance_deembedding
        deemb_png_data = os.path.join(data_dir, "plot_deembedding.png")
        deemb_png_post = os.path.join(output_dir, "plot_deembedding.png")

        plot_impedance_deembedding(output_dir, params=params_for_deembed, output_png=deemb_png_data)
        if os.path.abspath(deemb_png_data) != os.path.abspath(deemb_png_post) and os.path.exists(deemb_png_data):
            shutil.copy2(deemb_png_data, deemb_png_post)
    except Exception as e:
        print(f"Warning during automatic impedance de-embedding plot generation: {e}")

    # 4. Boresight gain and axial ratio vs. frequency plot (plot_gain_frequency.png)
    try:
        from plot_gain_frequency import plot_gain_frequency
        ff_file = os.path.join(output_dir, "farfield-rE.csv")
        if os.path.exists(ff_file) and os.path.getsize(ff_file) > 0:
            gain_png_data = os.path.join(data_dir, "plot_gain_frequency.png")
            gain_png_post = os.path.join(output_dir, "plot_gain_frequency.png")

            plot_gain_frequency(output_dir, output_png=gain_png_data, params=params_for_deembed)
            if os.path.abspath(gain_png_data) != os.path.abspath(gain_png_post) and os.path.exists(gain_png_data):
                shutil.copy2(gain_png_data, gain_png_post)
    except Exception as e:
        print(f"Warning during automatic boresight gain plot generation: {e}")

    # Synchronize plots/ and images/ subfolders between data_dir and output_dir
    if os.path.abspath(data_dir) != os.path.abspath(output_dir):
        for subf in ["plots", "images"]:
            src_f = os.path.join(data_dir, subf)
            dst_f = os.path.join(output_dir, subf)
            if os.path.exists(src_f) and os.path.isdir(src_f):
                os.makedirs(dst_f, exist_ok=True)
                for item in os.listdir(src_f):
                    s_item = os.path.join(src_f, item)
                    d_item = os.path.join(dst_f, item)
                    if os.path.isfile(s_item):
                        try:
                            shutil.copy2(s_item, d_item)
                        except Exception:
                            pass

def _process_results_model1(params, output_dir, data_dir, run_name):
    s11_file = os.path.join(output_dir, "port-S.csv")
    if os.path.exists(s11_file) and os.path.getsize(s11_file) > 0:
        try:
            data_arr = np.loadtxt(s11_file, delimiter=',', skiprows=1)
            if data_arr.ndim == 1:
                data_arr = data_arr.reshape(1, -1)
            freqs = data_arr[:, 0]
            s11_db = data_arr[:, 1]
            
            model_num = int(params.get("antenna_model", 1))
            title_s11 = (
                "Reflection Coefficient (S11) - Model 7 (Opposite Polarization RHCP, 50 Ω T-junction with Bends)"
                if model_num == 7
                else (
                    "Reflection Coefficient (S11) - Model 4 (Final 50 Ω T-junction with Bends)"
                    if model_num == 4
                    else "Reflection Coefficient (S11) - Model 1 (LHCP Patch Antenna with T-splitter)"
                )
            )
            plt.figure(figsize=(8, 6))
            plt.plot(freqs, s11_db, label='S11', color='navy', lw=2)
            plt.title(title_s11)
            plt.xlabel('Frequency [GHz]')
            plt.ylabel('S11 [dB]')
            plt.grid(True)
            plt.axhline(-10, color='r', linestyle='--', label='-10 dB threshold')
            plt.legend()
            
            plot_path = os.path.join(data_dir, "plot_s11.png")
            plt.savefig(plot_path)
            if model_num in (4, 7):
                plots_dir = os.path.join(data_dir, "plots")
                os.makedirs(plots_dir, exist_ok=True)
                plt.savefig(os.path.join(plots_dir, "plot_s11.png"))
            plt.close()
            print(f"Plot saved successfully to {plot_path}")
        except Exception as e:
            print(f"Warning while plotting S11: {e}")
            
        analyze_and_log_run(params, s11_file, run_name=run_name)
    else:
        print(f"Output file {s11_file} was not found. The simulation likely failed or wrote elsewhere.")

    _generate_advanced_plots(output_dir, data_dir)

def _process_results_model2(params, output_dir, data_dir, run_name):
    from tracker import extract_s_parameters_model2
    s_params = extract_s_parameters_model2(output_dir, z0=float(params.get('port_impedance', 100.0)))
    
    if s_params and 'freqs' in s_params:
        try:
            freqs = s_params['freqs']
            s11_db = s_params.get('s11_db')
            s22_db = s_params.get('s22_db')
            s21_db = s_params.get('s21_db')
            s12_db = s_params.get('s12_db')

            plt.figure(figsize=(8, 6))
            if s11_db is not None:
                plt.plot(freqs, s11_db, label='S11 (Bottom port, Ey)', color='blue', lw=2)
            if s22_db is not None:
                plt.plot(freqs, s22_db, label='S22 (Left port, Ex)', color='crimson', lw=2, linestyle='--')
            if s21_db is not None and s12_db is not None and not np.allclose(s21_db, s12_db, atol=1e-3):
                plt.plot(freqs, s21_db, label='S21 (Coupling 1->2)', color='darkgreen', lw=1.5, linestyle=':')
                plt.plot(freqs, s12_db, label='S12 (Coupling 2->1)', color='teal', lw=1.5, linestyle='-.')
            elif s21_db is not None:
                plt.plot(freqs, s21_db, label='S21 (Coupling 1->2)', color='darkgreen', lw=1.5, linestyle=':')
            elif s12_db is not None:
                plt.plot(freqs, s12_db, label='S12 (Coupling 2->1)', color='darkgreen', lw=1.5, linestyle=':')
            plt.title(f'Reflection Coefficients S11 and S22 - Model {params.get("antenna_model", 2)} (100 Ω LHCP)')
            plt.xlabel('Frequency [GHz]')
            plt.ylabel('S-parameters [dB]')
            plt.grid(True)
            plt.axhline(-10, color='red', linestyle='--', lw=1.5, label='-10 dB threshold')
            plt.legend()

            plot_path = os.path.join(data_dir, "plot_s11_s22.png")
            plt.savefig(plot_path)
            # Backward-compatibility copy
            plt.savefig(os.path.join(data_dir, "plot_s11.png"))

            # Save into plots/
            plots_dir = os.path.join(data_dir, "plots")
            os.makedirs(plots_dir, exist_ok=True)
            plt.savefig(os.path.join(plots_dir, "plot_s11_s22.png"))
            plt.close()
            print(f"S11 and S22 plot saved successfully to {plot_path}")
        except Exception as e:
            print(f"Warning while plotting S-parameters: {e}")

    # Log to model table
    dummy_csv = os.path.join(output_dir, "port-S.csv")
    analyze_and_log_run(params, dummy_csv, run_name=run_name)

    _generate_advanced_plots(output_dir, data_dir)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="LHCP Patch Antenna Simulation & CAD Model Generation")
    parser.add_argument("--profile", type=str, default=None, dest="profile",
                        help="Manufacturing profile name in results/<profile>/<profile>.env (overrides root .env; default: ANTENNA_PROFILE)")
    parser.add_argument("--model", type=int, choices=[1, 2, 3, 4, 5, 6, 7], default=None, dest="antenna_model",
                        help="Antenna model version: 1 (50 Ohm T-splitter), 2 (dual-port 100 Ohm), 3 (hybrid 2-port), 4 (final 50 Ohm T-junction with bends), 5 (dual-port curved 100 Ohm), 6 (dual-port curved with internal 100 Ohm ports), 7 (mirrored Model 4 for RHCP). Default: 1 or from ANTENNA_MODEL")
    parser.add_argument("--skip-simulation", "--no-docker", dest="skip_simulation", action="store_true",
                        help="Generate only the model, CAD STEP file, and mesh locally without starting the Docker simulation")
    parser.add_argument("--clean", dest="clean", action="store_true",
                        help="Delete previous output data (postpro) before running a new simulation")
    
    # Frequency range and step parameterization
    parser.add_argument("--freq-min", type=float, default=None, dest="freq_min",
                        help="Minimum sweep frequency in GHz (default: 2.320 or from FREQ_MIN)")
    parser.add_argument("--freq-max", type=float, default=None, dest="freq_max",
                        help="Maximum sweep frequency in GHz (default: 2.345 or from FREQ_MAX)")
    parser.add_argument("--freq-step", type=float, default=None, dest="freq_step",
                        help="Sweep frequency step in GHz (default: 0.005 or from FREQ_STEP)")

    # Mesh and solver parameterization
    parser.add_argument("--mesh-max", type=float, default=None, dest="mesh_size_max",
                        help="Maximum mesh element size in mm (default: 8.0 or from MESH_SIZE_MAX)")
    parser.add_argument("--mesh-min", type=float, default=None, dest="mesh_size_min",
                        help="Minimum mesh element size in mm (default: 0.5 or from MESH_SIZE_MIN)")
    parser.add_argument("--amr-its", type=int, default=None, dest="amr_max_its",
                        help="Maximum number of AMR adaptive refinements (default: 2 or from AMR_MAX_ITS)")
    parser.add_argument("--amr-tol", "--amr-threshold", type=float, default=None, dest="amr_threshold",
                        help="Relative tolerance to stop AMR refinement (default: 0.2 or from AMR_THRESHOLD)")
    parser.add_argument("--farfield-nsample", type=int, default=None, dest="farfield_nsample",
                        help="Number of far-field sampling points (default: 16200 or from FARFIELD_NSAMPLE)")
    parser.add_argument("--save-step", type=int, default=None, dest="save_step",
                        help="Save step for 3D fields (default: 1 or from SAVE_STEP)")
    parser.add_argument("--linear-tol", type=float, default=None, dest="linear_tol",
                        help="Relative tolerance of FGMRES linear solver (default: 1e-6 or from LINEAR_TOL)")
    parser.add_argument("--linear-its", "--linear-max-its", type=int, default=None, dest="linear_max_its",
                        help="Maximum iterations of FGMRES linear solver (default: 100 or from LINEAR_MAX_ITS)")
    parser.add_argument("--linear-max-size", type=int, default=None, dest="linear_max_size",
                        help="Maximum Krylov subspace size for FGMRES / restart (default: None = no restart, or from LINEAR_MAX_SIZE)")
    parser.add_argument("--port-impedance", type=float, default=None, dest="port_impedance",
                        help="Port impedance in Ohms (default: 50.0 for Models 1 and 4, 100.0 for Models 2, 3, 5, and 6, or from PORT_IMPEDANCE)")

    # Patch geometry and inset parameterization
    parser.add_argument("--patch-l", type=float, default=None, dest="patch_L",
                        help="Patch length in mm (default: 30.3 for M1, 28.8 for M2/M3/M4, 29.95 for M5/M6, or from PATCH_L)")
    parser.add_argument("--patch-w", type=float, default=None, dest="patch_W",
                        help="Patch width in mm (default: from PATCH_W or equal to patch-l)")
    parser.add_argument("--inset", "--feed-inset", type=float, default=None, dest="feed_inset",
                        help="Feedline inset depth into patch in mm (default: 0.0 or from FEED_INSET)")
    parser.add_argument("--inset-b", type=float, default=None, dest="feed_inset_b",
                        help="Bottom feedline inset depth for Models 2, 3, 4, 5, and 6 (default: FEED_INSET_B or FEED_INSET)")
    parser.add_argument("--inset-l", type=float, default=None, dest="feed_inset_l",
                        help="Left feedline inset depth for Models 2, 3, 4, 5, and 6 (default: FEED_INSET_L or FEED_INSET)")
    parser.add_argument("--inset-gap-b", type=float, default=None, dest="feed_inset_gap_b",
                        help="Notch gap width for bottom feedline (default: FEED_INSET_GAP_B)")
    parser.add_argument("--inset-gap-l", type=float, default=None, dest="feed_inset_gap_l",
                        help="Notch gap width for left feedline (default: FEED_INSET_GAP_L)")
    parser.add_argument("--feed-len-b", "--feed-length-b", type=float, default=None, dest="feed_len_b",
                        help="Bottom feedline length for Models 2 and 3 in mm (default: from W_sub + lambda_g/4 or FEED_LEN_B)")
    parser.add_argument("--feed-len-l", "--feed-length-l", type=float, default=None, dest="feed_len_l",
                        help="Left feedline length for Models 2 and 3 in mm (default: L_ref or FEED_LEN_L)")
    parser.add_argument("--feed-delta-l", "--delta-l", type=float, default=None, dest="feed_delta_l",
                        help="Feedline length difference Delta L = L_feed_b - L_feed_l for Models 2, 3, 4, 5, and 6 in mm (default: lambda_g/4 or FEED_DELTA_L)")
    parser.add_argument("--trans-w", "--w-t", "--w-trans", type=float, default=None, dest="trans_w",
                        help="Quarter-wave transformer width for Models 3, 4, 5, and 6 in mm (default: 0.42 for M3/M4/M6, 0.30 for M5, or TRANS_W)")
    parser.add_argument("--trans-l", "--l-t", "--l-trans", type=float, default=None, dest="trans_l",
                        help="Quarter-wave transformer length for Models 3, 4, 5, and 6 in mm (default: auto lambda_g/4, 19.0 for M5, or TRANS_L)")
    parser.add_argument("--trans-l-b", "--l-t-b", type=float, default=None, dest="trans_l_b",
                        help="Bottom-arm transformer length in mm (default: trans_l)")
    parser.add_argument("--trans-l-l", "--l-t-l", type=float, default=None, dest="trans_l_l",
                        help="Left-arm transformer length in mm (default: trans_l)")
    parser.add_argument("--driven-port", type=str, default=None, dest="driven_port",
                        help="Driven port selection for Models 2, 3, 5, and 6: '1' (bottom), '2' (left), 'all' (both simultaneously for LHCP). Default: all")

    # Model 4, 5, and 6 parameterization (bends and branch geometry)
    parser.add_argument("--bend-radius", "--feed-bend-radius", type=float, default=None, dest="feed_bend_radius",
                        help="Centerline radius of circular bends for Models 4, 5, and 6 in mm (default: 3.0 or FEED_BEND_RADIUS)")
    parser.add_argument("--t-fillet", "--t-fillet-r", type=float, default=None, dest="feed_t_fillet_r",
                        help="Inner corner fillet radius of T-junction for Models 4 and 6 in mm (default: 0.8 or FEED_T_FILLET_R)")
    parser.add_argument("--feed-50-len", type=float, default=None, dest="feed_50_len",
                        help="Length of 50 Ohm input line to T-junction for Models 4 and 6 in mm (default: 9.0 or FEED_50_LEN)")
    parser.add_argument("--end-straight", "--feed-end-straight", type=float, default=None, dest="feed_end_straight",
                        help="Straight input section of 100 Ohm branches before transformers for Models 4, 5, and 6 in mm (default: 4.6 or FEED_END_STRAIGHT)")
    parser.add_argument("--arm-offset", type=float, default=None, dest="feed_arm_offset",
                        help="Lateral offset of vertical 100 Ohm arm for Models 4, 5, and 6 in mm (default: auto end_straight + bend_radius = 7.6 or FEED_ARM_OFFSET)")
    parser.add_argument("--port-offset", "--feed-port-offset", type=float, default=None, dest="feed_port_offset",
                        help="Port offset from virtual center y_T for Model 5 in mm (default: 3.0 or FEED_PORT_OFFSET)")
    parser.add_argument("--design-freq", type=float, default=None, dest="design_freq_ghz",
                        help="Design center frequency for lambda_g/4 synthesis in GHz (default: 2.3325 or DESIGN_FREQ_GHZ)")
    parser.add_argument("--export", dest="export", action="store_true", default=False,
                        help="Automatically create export package (ZIP) in export/ after simulation completes")
    parser.add_argument("--export-name", type=str, default=None, dest="export_name",
                        help="Custom export package or folder name (default: run_name or auto-numbering)")

    args = parser.parse_args()

    cli_params = {}
    for param in ['antenna_model', 'freq_min', 'freq_max', 'freq_step', 'mesh_size_max', 'mesh_size_min', 'amr_max_its',
                  'amr_threshold', 'farfield_nsample', 'save_step', 'linear_tol', 'linear_max_its', 'linear_max_size', 'port_impedance',
                  'patch_L', 'patch_W', 'feed_inset', 'feed_inset_b', 'feed_inset_l', 'feed_inset_gap_b', 'feed_inset_gap_l',
                  'feed_len_b', 'feed_len_l', 'feed_delta_l', 'trans_w', 'trans_l', 'trans_l_b', 'trans_l_l', 'driven_port',
                  'feed_bend_radius', 'feed_t_fillet_r', 'feed_50_len', 'feed_end_straight', 'feed_arm_offset',
                  'feed_port_offset', 'design_freq_ghz', 'export', 'export_name']:
        val = getattr(args, param, None)
        if val is not None:
            cli_params[param] = val

    main(
        custom_params=cli_params if cli_params else None,
        skip_simulation=args.skip_simulation,
        clean=args.clean,
        profile=args.profile,
    )
