import glob
import pyvista as pv
import os
import sys

import _env  # noqa: F401
from postpro_utils import load_env, ensure_paraview_linked

def plot_e_field(vtu_file=None, output_image=None):
    root_dir, data_dir = load_env()
    ensure_paraview_linked(data_dir)

    if vtu_file is None:
        cycles = sorted(glob.glob(os.path.join(data_dir, "postpro", "paraview", "driven_boundary", "Cycle*", "data.pvtu")))
        if cycles:
            vtu_file = cycles[len(cycles) // 2]
        else:
            vtu_file = os.path.join(data_dir, "postpro", "paraview", "driven_boundary", "Cycle000003", "data.pvtu")
    if output_image is None:
        output_image = os.path.join(data_dir, "postpro", "efield.png")

    print(f"Loading field file: {vtu_file}")
    if not os.path.exists(vtu_file):
        print(f"File {vtu_file} not found. Make sure Palace simulation generated the field output.")
        return
        
    try:
        # Enable off-screen rendering for headless execution
        pv.start_xvfb() # May be needed on Linux; ignored/unnecessary on Windows
    except Exception:
        pass
        
    mesh = pv.read(vtu_file)
    
    # Palace typically saves the electric field as 'E' or 'E_real', 'E_imag'
    # If real field data is unavailable (mock), render the mesh geometry
    
    plotter = pv.Plotter(off_screen=True)
    try:
        # Try to find electric field vector data
        e_field_key = None
        for key in mesh.point_data.keys():
            if 'E' in key or 'e' in key.lower():
                e_field_key = key
                break
                
        if e_field_key:
            plotter.add_mesh(mesh, scalars=e_field_key, cmap='jet', show_scalar_bar=True)
        else:
            # If the field array does not exist, plot the surface colored by the Z-axis
            plotter.add_mesh(mesh, scalars=mesh.points[:, 2], cmap='viridis', show_scalar_bar=False)
            print("Vector E-field not found in data, rendering mesh only.")

        plotter.view_isometric()
        plotter.add_axes()
        os.makedirs(os.path.dirname(os.path.abspath(output_image)) or ".", exist_ok=True)
        plotter.screenshot(output_image)
        print(f"Field distribution exported to: {output_image}")
    finally:
        plotter.close()

if __name__ == "__main__":
    target_vtu = sys.argv[1] if len(sys.argv) > 1 else None
    target_out = sys.argv[2] if len(sys.argv) > 2 else None
    plot_e_field(target_vtu, target_out)
