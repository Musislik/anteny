import pyvista as pv
import os

def plot_e_field(vtu_file, output_image="efield.png"):
    print(f"Načítám soubor s polem: {vtu_file}")
    if not os.path.exists(vtu_file):
        print("Soubor nenalezen. Ujistěte se, že simulátor Palace úspěšně vygeneroval pole (VTU formát).")
        return
        
    try:
        # Povolit off-screen rendering pro headless běh
        pv.start_xvfb() # Může být potřeba na Linuxu, na Windows je ignorováno/nepotřebné
    except:
        pass
        
    mesh = pv.read(vtu_file)
    
    # Palace ukládá elektrické pole typicky jako 'E' nebo 'E_real', 'E_imag'
    # Pokud nemáme reálná data (mock), vykreslíme aspoň geometrii ze sítě
    
    plotter = pv.Plotter(off_screen=True)
    
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
    plotter.screenshot(output_image)
    print(f"Rozložení pole bylo exportováno do: {output_image}")

if __name__ == "__main__":
    import sys
    # Příklad použití: python plot_efield.py postpro/paraview/driven/driven_000000001.vtu
    target_vtu = sys.argv[1] if len(sys.argv) > 1 else "postpro/paraview/driven/driven_000000001.vtu"
    plot_e_field(target_vtu)
