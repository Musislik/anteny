"""
Script to generate a phasor-rotation time series (LHCP field phase animation).
Computes harmonic evolution over one period T (phase 0 deg to 350 deg in 10 deg steps):
    E(phi) = E_real * cos(phi) - E_imag * sin(phi)
    J_s(phi) = J_s_real * cos(phi) - J_s_imag * sin(phi)
The output is saved as a ParaView PVD collection that can be played directly in ParaView.
"""

import os
import glob
import numpy as np
from paraview.simple import *

import _env  # noqa: F401
from postpro_utils import load_env, ensure_paraview_linked

def generate_phase_series(
    input_pvtu=None,
    out_dir=None,
    n_frames=36,
    freq_label="2.330 GHz"
):
    root_dir, data_dir = load_env()
    os.chdir(root_dir)
    ensure_paraview_linked(data_dir)

    if out_dir is None:
        out_dir = os.path.join(data_dir, "postpro", "paraview", "phase_animation")

    if input_pvtu is None:
        cycles = sorted(glob.glob(os.path.join(data_dir, "postpro", "paraview", "driven_boundary", "Cycle*", "data.pvtu")))
        if cycles:
            mid_idx = len(cycles) // 2
            input_pvtu = os.path.abspath(cycles[mid_idx])
        else:
            default_cycle = os.path.join(data_dir, "postpro", "paraview", "driven_boundary", "Cycle000003", "data.pvtu")
            if os.path.exists(default_cycle):
                input_pvtu = os.path.abspath(default_cycle)

    if not input_pvtu or not os.path.exists(input_pvtu):
        print(f"[ERROR] Input file not found: {input_pvtu}")
        print(f"Check DATA_DIR ({data_dir}) in .env or run the simulation first.")
        return False

    print(f"--- 1. Loading field data from resonant step ({freq_label}): {input_pvtu} ---")
    ResetSession()
    reader = XMLPartitionedUnstructuredGridReader(FileName=[input_pvtu])
    reader.UpdatePipeline()

    os.makedirs(out_dir, exist_ok=True)
    phases_deg = np.linspace(0, 360, n_frames, endpoint=False)
    phases_rad = np.radians(phases_deg)

    pvd_entries = []
    print(f"--- 2. Generating {n_frames} phase frames (0 deg to 350 deg) ---")

    for idx, (deg, rad) in enumerate(zip(phases_deg, phases_rad)):
        cos_val = np.cos(rad)
        sin_val = np.sin(rad)

        calc = Calculator(registrationName=f'Calc_{idx}', Input=reader)
        calc.ResultArrayName = 'E_phase'
        calc.Function = f'E_real * ({cos_val:.8f}) - E_imag * ({sin_val:.8f})'
        calc.UpdatePipeline()

        # Also add surface current if available
        calc2 = Calculator(registrationName=f'Calc_J_{idx}', Input=calc)
        calc2.ResultArrayName = 'J_phase'
        calc2.Function = f'J_s_real * ({cos_val:.8f}) - J_s_imag * ({sin_val:.8f})'
        calc2.UpdatePipeline()

        vtu_filename = f"frame_{idx:03d}.vtu"
        vtu_path = os.path.join(out_dir, vtu_filename)
        
        writer = XMLUnstructuredGridWriter(Input=calc2, FileName=vtu_path)
        writer.UpdatePipeline()
        Delete(writer)
        Delete(calc2)
        Delete(calc)

        pvd_entries.append(f'    <DataSet timestep="{deg:.1f}" group="" part="0" file="{vtu_filename}"/>')
        if (idx + 1) % 6 == 0 or idx == n_frames - 1:
            print(f"  -> Done: {idx + 1}/{n_frames} frames ({deg:.0f} deg)")

    # Write PVD collection file
    pvd_path = os.path.join(out_dir, "phase_animation.pvd")
    with open(pvd_path, "w") as f:
        f.write('<?xml version="1.0"?>\n')
        f.write('<VTKFile type="Collection" version="0.1" byte_order="LittleEndian">\n')
        f.write('  <Collection>\n')
        f.write('\n'.join(pvd_entries))
        f.write('\n  </Collection>\n')
        f.write('</VTKFile>\n')

    print("==================================================")
    print("PVD phase animation successfully generated at:")
    print(f"  {pvd_path}")
    print("==================================================")
    return True

if __name__ == "__main__":
    generate_phase_series()
