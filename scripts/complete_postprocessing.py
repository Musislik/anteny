#!/usr/bin/env python3
"""
complete_postprocessing.py - Complete post-processing and plot generation after a Palace simulation.
Resumes right after the AMR simulation finishes in src/main.py.
"""

import os
import sys
import json
import shutil
import numpy as np

# Add src and scripts to sys.path
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_CURRENT_DIR, ".."))
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
_SCRIPTS_DIR = os.path.join(_ROOT_DIR, "scripts")

for p in (_SCRIPTS_DIR, _SRC_DIR, _ROOT_DIR):
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

from postpro_utils import (
    load_env,
    ensure_paraview_linked,
    get_latest_iteration_dir,
    get_export_dir,
)
from main import (
    _process_results_model1,
    _process_results_model2,
    _generate_advanced_plots,
)

def run_postprocessing(profile=None, run_name=None):
    root_dir, data_dir = load_env(profile=profile)
    output_dir = os.path.join(data_dir, "postpro")
    
    print(f"Project root: {root_dir}")
    print(f"Data directory: {data_dir}")
    print(f"Output directory: {output_dir}")

    # 1. Load params.json from data_dir
    params_file = os.path.join(data_dir, "params.json")
    params = {}
    if os.path.exists(params_file):
        with open(params_file, "r", encoding="utf-8") as pf:
            params = json.load(pf)
        print(f"Loaded parameters from {params_file} (Model {params.get('antenna_model')})")
    else:
        print(f"Warning: {params_file} not found, using default parameters.")
        params = {"antenna_model": 4}

    antenna_model = int(params.get("antenna_model", 4))

    # 2. Link paraview directory to the latest iteration (AMR)
    print("\n--- Ensuring paraview link in postpro ---")
    pv_link = ensure_paraview_linked(data_dir)
    print(f"ParaView link: {pv_link}")

    # Ensure relative symlink for paraview inside postpro (works both in Docker and on host)
    latest_iter = get_latest_iteration_dir(data_dir)
    if latest_iter:
        rel_iter = os.path.basename(latest_iter)
        iter_pv = os.path.join(latest_iter, "paraview")
        target_pv = os.path.join(output_dir, "paraview")
        if os.path.exists(iter_pv):
            try:
                if os.path.islink(target_pv) or os.path.exists(target_pv):
                    os.unlink(target_pv)
                os.symlink(os.path.join(rel_iter, "paraview"), target_pv)
                print(f"Created relative symlink: {target_pv} -> {os.path.join(rel_iter, 'paraview')}")
            except Exception as e:
                print(f"Note on paraview symlink: {e}")

    # 3. Process results according to the antenna model (matching main.py)
    print(f"\n--- 5. Processing results for Model {antenna_model} ---")
    if antenna_model in (2, 3, 5, 6):
        _process_results_model2(params, output_dir, data_dir, run_name)
    else:
        _process_results_model1(params, output_dir, data_dir, run_name)

    # 4. Optional package export (if requested in params)
    if params.get("export", False) or params.get("export_name"):
        try:
            from export_package import export_paraview_package
            exp_name = params.get("export_name") or run_name
            print(f"\n--- 6. Exporting results package: {exp_name or 'antenna_export'} ---")
            export_paraview_package(output_name=exp_name, run_name=run_name, model_version=antenna_model)
        except Exception as e:
            print(f"Warning during package export: {e}")

    print("\n=== Post-processing and plot generation completed successfully! ===")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Complete plot generation after a Palace simulation")
    parser.add_argument("--profile", type=str, default=None, help="Manufacturing variant profile")
    parser.add_argument("--run-name", type=str, default=None, help="Run name for logging")
    args = parser.parse_args()

    run_postprocessing(profile=args.profile, run_name=args.run_name)
