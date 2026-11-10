import glob
import pyvista as pv
import os
import sys

import _env
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

    print(f"Načítám soubor s polem: {vtu_file}")
    if not os.path.exists(vtu_file):
        print(f"Soubor {vtu_file} nenalezen. Ujistěte se, že simulátor Palace úspěšně vygeneroval pole.")
        return
        
    try:
        # Povolit off-screen rendering pro headless běh
        pv.start_xvfb() # Může být potřeba na Linuxu, na Windows je ignorováno/nepotřebné
    except Exception:
        pass
        
    mesh = pv.read(vtu_file)
    
    # Palace ukládá elektrické pole typicky jako 'E' nebo 'E_real', 'E_imag'
    # Pokud nemáme reálná data (mock), vykreslíme aspoň geometrii ze sítě
    
    plotter = pv.Plotter(off_screen=True)
    try:
        # Zkusíme najít vektorová data E
        e_field_key = None
        for key in mesh.point_data.keys():
            if 'E' in key or 'e' in key.lower():
                e_field_key = key
                break
                
        if e_field_key:
            plotter.add_mesh(mesh, scalars=e_field_key, cmap='jet', show_scalar_bar=True)
        else:
            # Pokud pole neexistuje, vykreslíme jen povrch a obarvíme podle osy Z
            plotter.add_mesh(mesh, scalars=mesh.points[:, 2], cmap='viridis', show_scalar_bar=False)
            print("Vektorové E-pole nenalezeno v datech, vykresluji pouze síť.")

        plotter.view_isometric()
        plotter.add_axes()
        os.makedirs(os.path.dirname(os.path.abspath(output_image)) or ".", exist_ok=True)
        plotter.screenshot(output_image)
        print(f"Rozložení pole bylo exportováno do: {output_image}")
    finally:
        plotter.close()

if __name__ == "__main__":
    target_vtu = sys.argv[1] if len(sys.argv) > 1 else None
    target_out = sys.argv[2] if len(sys.argv) > 2 else None
    plot_e_field(target_vtu, target_out)
