"""
Simple script to package an interactive ParaView presentation into a single ZIP archive.

Usage:
    python scripts/export_package.py
    (automatically creates an incremented export: export/antenna_export_1.zip, export/antenna_export_2.zip, ...)

Or with a custom name:
    python scripts/export_package.py my_antenna
    python scripts/export_package.py --name my_antenna.zip
    (if the file already exists, automatically increments to my_antenna_2.zip, my_antenna_3.zip, ...)
"""

import os
import shutil
import zipfile
import re
import argparse

try:
    import _env  # noqa: F401
except ImportError:
    try:
        import scripts._env  # noqa: F401
    except ImportError:
        pass
from postpro_utils import load_env, ensure_paraview_linked, get_export_dir


def get_next_default_export_path(export_dir, base_name="antenna_export"):
    """
    Find the next available filename with an incremented index, e.g., antenna_export_1.zip.
    """
    os.makedirs(export_dir, exist_ok=True)
    pattern = re.compile(rf"^{re.escape(base_name)}_(\d+)\.zip$", re.IGNORECASE)

    existing_nums = []
    for fname in os.listdir(export_dir):
        m = pattern.match(fname)
        if m:
            existing_nums.append(int(m.group(1)))

    next_num = max(existing_nums, default=0) + 1
    while os.path.exists(os.path.join(export_dir, f"{base_name}_{next_num}.zip")):
        next_num += 1

    return os.path.join(export_dir, f"{base_name}_{next_num}.zip")


def resolve_export_path(root_dir, output_name=None, default_base="antenna_export", export_dir=None):
    """
    Determine the target ZIP file path according to EXPORT_DIR in .env.
    - If output_name is omitted: returns <export_dir>/antenna_export_<N>.zip (starting at 1).
    - If output_name is given:
        - if <name>.zip does not exist, uses <name>.zip
        - if <name>.zip already exists, creates <name>_2.zip, <name>_3.zip, etc.
    """
    if export_dir is None:
        export_dir = get_export_dir(root_dir)
    os.makedirs(export_dir, exist_ok=True)

    if not output_name:
        return get_next_default_export_path(export_dir, default_base)

    if not os.path.isabs(output_name):
        dirname, basename = os.path.split(output_name)
        if dirname:
            target_dir = os.path.abspath(os.path.join(root_dir, dirname))
        else:
            target_dir = export_dir
    else:
        target_dir, basename = os.path.split(output_name)

    os.makedirs(target_dir, exist_ok=True)

    stem = basename[:-4] if basename.lower().endswith(".zip") else basename
    base_zip = os.path.join(target_dir, f"{stem}.zip")

    if not os.path.exists(base_zip):
        return base_zip

    # File already exists -> search for index 2 and higher
    pattern = re.compile(rf"^{re.escape(stem)}_(\d+)\.zip$", re.IGNORECASE)
    existing_nums = []
    for fname in os.listdir(target_dir):
        m = pattern.match(fname)
        if m:
            existing_nums.append(int(m.group(1)))

    next_num = max(existing_nums, default=1) + 1
    while os.path.exists(os.path.join(target_dir, f"{stem}_{next_num}.zip")):
        next_num += 1

    return os.path.join(target_dir, f"{stem}_{next_num}.zip")


def export_paraview_package(output_name=None, output_zip=None, run_name=None, **kwargs):
    orig_cwd = os.getcwd()
    temp_pack_dir = None
    try:
        root_dir, data_dir = load_env()
        os.chdir(root_dir)

        # Ensure link to the latest AMR iteration
        ensure_paraview_linked(data_dir)

        target_name = output_name if output_name is not None else (output_zip if output_zip is not None else run_name)
        output_zip = resolve_export_path(root_dir, target_name)

        # 1. Check available data in DATA_DIR
        postpro_dir = os.path.abspath(os.path.join(data_dir, "postpro"))
        boundary_dir = os.path.abspath(os.path.join(postpro_dir, "paraview", "driven_boundary"))
        has_boundary = os.path.exists(boundary_dir) and os.path.isdir(boundary_dir)

        s11_file = os.path.join(postpro_dir, "port-S.csv")
        step_file = os.path.join(data_dir, "antenna_model.step")
        config_file = os.path.join(data_dir, "config.json")

        has_any_data = (
            has_boundary
            or (os.path.exists(s11_file) and os.path.getsize(s11_file) > 0)
            or (os.path.exists(step_file) and os.path.getsize(step_file) > 0)
            or (os.path.exists(config_file) and os.path.getsize(config_file) > 0)
        )

        if not has_any_data:
            print(f"[ERROR] No simulation output data or CAD model found in {data_dir}.")
            print("Check DATA_DIR in .env or run the simulation first.")
            return False

        script_path = os.path.join(root_dir, "scripts", "paraview_dynamic_phase.py")

        # Prepare output directory
        out_dir = os.path.dirname(output_zip)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        # Temporary staging folder for assembling the package
        zip_stem = os.path.splitext(os.path.basename(output_zip))[0]
        temp_pack_dir = os.path.join(out_dir, f"{zip_stem}_temp")
        if os.path.exists(temp_pack_dir):
            shutil.rmtree(temp_pack_dir, ignore_errors=True)
        os.makedirs(temp_pack_dir, exist_ok=True)

        print(f"--- 1. Copying files into package from {data_dir} ---")

        # A) ParaView, analysis, and utility scripts
        if has_boundary and os.path.exists(script_path):
            shutil.copy2(script_path, os.path.join(temp_pack_dir, "paraview_dynamic_phase.py"))
            print("  + paraview_dynamic_phase.py")

        for s_script in ["plot_s_parameters.py", "plot_radiation_pattern.py", "plot_deembedding.py", "plot_gain_frequency.py"]:
            s_path = os.path.join(root_dir, "scripts", s_script)
            if os.path.exists(s_path):
                shutil.copy2(s_path, os.path.join(temp_pack_dir, s_script))
                print(f"  + {s_script}")

        for src_mod in ["postpro_utils.py", "rf_calc.py"]:
            mod_path = os.path.join(root_dir, "src", src_mod)
            if os.path.exists(mod_path):
                shutil.copy2(mod_path, os.path.join(temp_pack_dir, src_mod))
                print(f"  + {src_mod}")

        # B) Surface simulation data (driven_boundary)
        if has_boundary:
            dest_boundary = os.path.join(temp_pack_dir, "driven_boundary")
            shutil.copytree(boundary_dir, dest_boundary)
            print("  + driven_boundary/ (complete 3D field data across all frequencies)")
        else:
            print("  i driven_boundary/ is unavailable (simulation ran with SAVE_STEP=0; 3D fields were not saved)")

        # C) Supplementary results and key simulation data
        gif_src = os.path.join(postpro_dir, "lhcp_rotation.gif")
        if os.path.exists(gif_src):
            shutil.copy2(gif_src, os.path.join(temp_pack_dir, "lhcp_rotation.gif"))
            print("  + lhcp_rotation.gif (preview animation)")

        # Automatically generate S-parameter, gain, and radiation pattern plots before packaging
        try:
            from plot_s_parameters import plot_s_parameters
            from plot_radiation_pattern import plot_radiation_pattern_2d, plot_radiation_pattern_3d
            from plot_gain_frequency import plot_gain_frequency

            s_param_png = os.path.join(data_dir, "plot_s_parameters.png")
            if not os.path.exists(s_param_png) or os.path.getsize(s_param_png) == 0:
                src_plot_dir = postpro_dir if os.path.exists(os.path.join(postpro_dir, "port-V.csv")) or os.path.exists(os.path.join(postpro_dir, "port-S.csv")) else data_dir
                plot_s_parameters(src_plot_dir, output_png=s_param_png)

            ff_file = os.path.join(postpro_dir, "farfield-rE.csv")
            if os.path.exists(ff_file) and os.path.getsize(ff_file) > 0:
                rd_2d_png = os.path.join(data_dir, "radiation_pattern_2d.png")
                rd_3d_png = os.path.join(data_dir, "radiation_pattern_3d.png")
                gain_freq_png = os.path.join(data_dir, "plot_gain_frequency.png")

                if not os.path.exists(rd_2d_png) or os.path.getsize(rd_2d_png) == 0:
                    plot_radiation_pattern_2d(postpro_dir, output_png=rd_2d_png)
                if not os.path.exists(rd_3d_png) or os.path.getsize(rd_3d_png) == 0:
                    plot_radiation_pattern_3d(postpro_dir, output_png=rd_3d_png)
                if not os.path.exists(gain_freq_png) or os.path.getsize(gain_freq_png) == 0:
                    plot_gain_frequency(postpro_dir, output_png=gain_freq_png)
        except Exception as plot_err:
            print(f"Warning while preparing plots for export: {plot_err}")

        # Important CSV and configuration outputs from postpro
        important_postpro = [
            ("port-S.csv", "S-parameters / reflection coefficient S11"),
            ("farfield-rE.csv", "far-field data (gain, LHCP/RHCP, axial ratio AR)"),
            ("port-V.csv", "excitation port voltage"),
            ("port-I.csv", "excitation port current"),
            ("domain-E.csv", "domain field energy and dielectric losses"),
            ("error-indicators.csv", "adaptive mesh refinement (AMR) error indicators"),
            ("config_resolved.json", "resolved solver configuration"),
            ("palace.json", "Palace FEM solver configuration"),
        ]
        for fname, desc in important_postpro:
            fsrc = os.path.join(postpro_dir, fname)
            if os.path.exists(fsrc) and os.path.getsize(fsrc) > 0:
                shutil.copy2(fsrc, os.path.join(temp_pack_dir, fname))
                print(f"  + {fname} ({desc})")

        # CAD STEP model, 2D plots, radiation patterns, and configuration (from data root or postpro)
        extra_models = [
            ("antenna_model.step", "3D CAD model of the antenna"),
            ("geometry_iso.png", "2D preview of antenna geometry"),
            ("plot_s11.png", "2D S11 reflection coefficient plot"),
            ("plot_s_parameters.png", "S-parameters and port impedance plot"),
            ("plot_deembedding.png", "analytical feed-network de-embedding diagnostics"),
            ("plot_gain_frequency.png", "boresight gain and polarization purity (AR/XPD) vs. frequency"),
            ("radiation_pattern_2d.png", "2D polar cuts in X-Z and Y-Z planes"),
            ("radiation_pattern_3d.png", "3D radiation pattern lobe"),
            ("config.json", "input configuration for the Palace FEM solver"),
            ("params.json", "geometry and model parameters"),
        ]
        for fname, desc in extra_models:
            fsrc = os.path.join(data_dir, fname)
            if not os.path.exists(fsrc):
                fsrc = os.path.join(postpro_dir, fname)
            if os.path.exists(fsrc) and os.path.getsize(fsrc) > 0:
                shutil.copy2(fsrc, os.path.join(temp_pack_dir, fname))
                print(f"  + {fname} ({desc})")

        # Subfolders plots/ and images/ containing individual sub-plots and geometry schematics
        for subfolder in ["plots", "images"]:
            src_sub = os.path.join(data_dir, subfolder)
            if not os.path.exists(src_sub):
                src_sub = os.path.join(postpro_dir, subfolder)
            if os.path.exists(src_sub) and os.path.isdir(src_sub):
                dst_sub = os.path.join(temp_pack_dir, subfolder)
                shutil.copytree(src_sub, dst_sub, dirs_exist_ok=True)
                print(f"  + {subfolder}/ (individual sub-plots and geometry schematics)")

        # D) Detailed usage instructions and file manifest (README.txt)
        if has_boundary:
            readme_content = """======================================================================
LHCP PATCH ANTENNA — COMPLETE RESULTS EXPORT PACKAGE
======================================================================

PACKAGE CONTENTS:
1. 3D Model and Field Animations:
   - paraview_dynamic_phase.py  ... ParaView control macro
   - driven_boundary/           ... Full FEM mesh and 3D fields for all frequencies
   - lhcp_rotation.gif          ... Quick field-rotation preview
   - antenna_model.step         ... 3D CAD geometry model (for CAD / PCB fabrication)
   - geometry_iso.png           ... 2D preview of antenna geometry

2. RF Parameters and Radiation:
   - port-S.csv                 ... S11 sweep across band (magnitude in dB and phase)
   - farfield-rE.csv            ... Vector far-field data (gain, LHCP/RHCP, axial ratio AR)
   - port-V.csv, port-I.csv     ... Complex port voltage and current (Zin = V / I)
   - domain-E.csv               ... Field energy and dielectric / air losses
   - plot_s11.png               ... S11 plot with -10 dB matching threshold

3. Configuration and Generated Plots:
   - config.json                ... Solver input configuration for reproducibility
   - config_resolved.json       ... Resolved solver configuration (if present)
   - plot_s_parameters.png      ... S11, S22, and port input impedance Zin plot
   - plot_gain_frequency.png    ... Boresight gain (+Z) and polarization purity (AR, XPD) vs. frequency
   - radiation_pattern_2d.png   ... 2D polar cuts X-Z and Y-Z (LHCP) + AR
   - radiation_pattern_3d.png   ... 3D radiation pattern in dBi
   - plot_deembedding.png       ... Feed-network de-embedding summary plot
   - plots/                     ... Folder with individual sub-plots:
                                  plot_s11_s22.png, plot_s21_isolation.png, plot_gain_frequency.png,
                                  radiation_pattern_cut_xz.png, radiation_pattern_cut_yz.png,
                                  plot_axial_ratio.png, plot_impedance_rp1.png,
                                  plot_impedance_rp2.png, plot_impedance_rp3.png
   - images/                    ... Folder with geometry schematics:
                                  geometry_top_view.png, geometry_transformer_detail.png

HOW TO VIEW THE INTERACTIVE MODEL IN PARAVIEW:
1. Open ParaView.
2. From the top menu choose: Tools -> Python Shell -> Run Script
3. Select the file: paraview_dynamic_phase.py (directly from this folder)
4. Use the slider to switch frequencies and press PLAY to start phase rotation.

HOW TO REGENERATE PLOTS (using scripts from scripts/):
1. S-parameters and impedance:
   python scripts/plot_s_parameters.py export/<export_dir>
2. Boresight gain and polarization purity vs. frequency:
   python scripts/plot_gain_frequency.py export/<export_dir>
3. 2D and 3D radiation patterns:
   python scripts/plot_radiation_pattern.py export/<export_dir> --freq 2.333
======================================================================
"""
        else:
            readme_content = """======================================================================
LHCP PATCH ANTENNA — RESULTS EXPORT PACKAGE (WITHOUT 3D FIELDS)
======================================================================

NOTE:
This package was generated from a run with SAVE_STEP=0 (fast S-parameter and
far-field evaluation without saving 3D spatial fields for ParaView).

PACKAGE CONTENTS:
1. RF Parameters and Radiation:
   - port-S.csv                 ... S11 sweep across band (magnitude in dB and phase)
   - farfield-rE.csv            ... Vector far-field data (gain, LHCP/RHCP, axial ratio AR)
   - port-V.csv, port-I.csv     ... Complex port voltage and current (Zin = V / I)
   - domain-E.csv               ... Field energy and dielectric / air losses
   - plot_s11.png               ... S11 plot with -10 dB matching threshold

2. Geometry and Models:
   - antenna_model.step         ... 3D CAD geometry model (for CAD / PCB fabrication)
   - geometry_iso.png           ... 2D preview of antenna geometry
   - config.json                ... Solver input configuration for reproducibility
   - config_resolved.json       ... Resolved solver configuration (if present)

3. Generated Plots:
   - plot_s_parameters.png      ... S11, S22, and port input impedance Zin plot
   - plot_gain_frequency.png    ... Boresight gain (+Z) and polarization purity (AR, XPD) vs. frequency
   - radiation_pattern_2d.png   ... 2D polar cuts X-Z and Y-Z (LHCP) + AR
   - radiation_pattern_3d.png   ... 3D radiation pattern in dBi
   - plot_deembedding.png       ... Feed-network de-embedding summary plot
   - plots/                     ... Folder with individual sub-plots:
                                  plot_s11_s22.png, plot_s21_isolation.png, plot_gain_frequency.png,
                                  radiation_pattern_cut_xz.png, radiation_pattern_cut_yz.png,
                                  plot_axial_ratio.png, plot_impedance_rp1.png,
                                  plot_impedance_rp2.png, plot_impedance_rp3.png
   - images/                    ... Folder with geometry schematics:
                                  geometry_top_view.png, geometry_transformer_detail.png

HOW TO REGENERATE PLOTS:
1. S-parameters and impedance:
   python scripts/plot_s_parameters.py export/<export_dir>
2. Boresight gain and polarization purity vs. frequency:
   python scripts/plot_gain_frequency.py export/<export_dir>
3. 2D and 3D radiation patterns:
   python scripts/plot_radiation_pattern.py export/<export_dir> --freq 2.333
======================================================================
"""
        with open(os.path.join(temp_pack_dir, "README.txt"), "w", encoding="utf-8") as f:
            f.write(readme_content)
        print("  + README.txt (usage instructions and file manifest)")

        # 2. Create ZIP archive
        print(f"--- 2. Compressing into ZIP archive: {output_zip} ---")
        if os.path.exists(output_zip):
            os.remove(output_zip)

        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(temp_pack_dir):
                for file in files:
                    abs_path = os.path.join(root, file)
                    rel_path = os.path.relpath(abs_path, temp_pack_dir)
                    zf.write(abs_path, rel_path)

        zip_size_mb = os.path.getsize(output_zip) / (1024 * 1024)

        print("======================================================================")
        print("PACKAGE CREATED SUCCESSFULLY!")
        print("ZIP archive ready for sharing/archiving:")
        print(f"   -> {os.path.abspath(output_zip)} ({zip_size_mb:.1f} MB)")
        print("Temporary unpacked directory has been removed.")
        print("======================================================================")
        return True
    finally:
        # 3. Clean up temporary unpacked folder and restore original working directory
        if temp_pack_dir and os.path.exists(temp_pack_dir):
            shutil.rmtree(temp_pack_dir, ignore_errors=True)
            print(f"--- 3. Removed unpacked directory {os.path.basename(temp_pack_dir)} ---")
        if os.path.exists(orig_cwd):
            os.chdir(orig_cwd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Package interactive ParaView presentation into a ZIP archive."
    )
    parser.add_argument(
        "filename",
        nargs="?",
        default=None,
        help="Optional output zip filename (e.g., my_antenna or my_antenna.zip).",
    )
    parser.add_argument(
        "-n",
        "--name",
        dest="name",
        default=None,
        help="Specify the output zip filename.",
    )
    args = parser.parse_args()
    target_name = args.name or args.filename
    export_paraview_package(output_name=target_name)
