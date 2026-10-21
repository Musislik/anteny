"""
Export animovaného GIFu rozložení točivého elektrického pole (LHCP).

Možnosti spuštění:
1. Pomocí Dockeru:
    docker compose run --rm pipeline python scripts/export_lhcp_gif.py
2. Pomocí pvpython (ParaView):
    & "D:\\Programy\\ParaView\\bin\\pvpython.exe" scripts/export_lhcp_gif.py
3. Přímo v Pythonu (pokud máte pyvista nebo vtk s matplotlib):
    python scripts/export_lhcp_gif.py
"""

import os
import sys
import glob
import shutil
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
from matplotlib.animation import FuncAnimation, PillowWriter


def find_default_dataset():
    """Najde nejvhodnější výstupní soubor simulace (přednostně rezonance v driven_boundary)."""
    candidates = [
        "data/postpro/paraview/driven_boundary/Cycle000003/data.pvtu",
        "data/postpro/paraview/driven_boundary/Cycle000002/data.pvtu",
        "data/postpro/paraview/driven_boundary/Cycle000001/data.pvtu",
        "postpro/paraview/driven_boundary/Cycle000003/data.pvtu",
        "data/postpro/paraview/driven/Cycle000003/data.pvtu",
        "data/postpro/paraview/driven/driven_000000001.vtu",
        "postpro/paraview/driven/driven_000000001.vtu"
    ]
    # Také zkusíme glob pro libovolný Cycle v driven_boundary
    cycles = sorted(glob.glob("data/postpro/paraview/driven_boundary/Cycle*/data.pvtu"))
    if cycles:
        # Pokud máme více cyklů (např. 6), vezmeme prostřední (typicky rezonanční kmitočet)
        mid_idx = len(cycles) // 2
        candidates.insert(0, cycles[mid_idx])

    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def read_mesh_fields(vtu_path):
    """Univerzální načtení bodů a komplexních polí (pyvista, vtk nebo meshio)."""
    print(f"--- Načítám data pole z: {vtu_path} ---")
    points = None
    e_real = None
    e_imag = None

    # 1. Zkusíme PyVista (standard v Docker kontejneru pipeline)
    try:
        import pyvista as pv
        mesh = pv.read(vtu_path)
        points = np.array(mesh.points)
        if "E_real" in mesh.point_data and "E_imag" in mesh.point_data:
            e_real = np.array(mesh.point_data["E_real"])
            e_imag = np.array(mesh.point_data["E_imag"])
        print(f"Načteno přes PyVista ({len(points)} bodů).")
    except Exception:
        pass

    # 2. Zkusíme VTK (standard v pvpython)
    if points is None:
        try:
            import vtk
            from vtk.util import numpy_support
            if vtu_path.endswith(".pvtu"):
                reader = vtk.vtkXMLPUnstructuredGridReader()
            else:
                reader = vtk.vtkXMLUnstructuredGridReader()
            reader.SetFileName(vtu_path)
            reader.Update()
            data = reader.GetOutput()
            points = numpy_support.vtk_to_numpy(data.GetPoints().GetData())
            pd = data.GetPointData()
            if pd.GetArray("E_real") and pd.GetArray("E_imag"):
                e_real = numpy_support.vtk_to_numpy(pd.GetArray("E_real"))
                e_imag = numpy_support.vtk_to_numpy(pd.GetArray("E_imag"))
            print(f"Načteno přes VTK ({len(points)} bodů).")
        except Exception:
            pass

    # 3. Zkusíme meshio jako zálohu
    if points is None:
        try:
            import meshio
            mesh = meshio.read(vtu_path)
            points = mesh.points
            if "E_real" in mesh.point_data and "E_imag" in mesh.point_data:
                e_real = mesh.point_data["E_real"]
                e_imag = mesh.point_data["E_imag"]
            print(f"Načteno přes Meshio ({len(points)} bodů).")
        except Exception:
            pass

    if points is None or e_real is None or e_imag is None:
        raise RuntimeError(
            f"Chyba: Nepodařilo se načíst body nebo pole E_real/E_imag ze souboru {vtu_path}.\n"
            "Ujistěte se, že spouštíte skript v Dockeru (pipeline) nebo přes pvpython."
        )

    return points, e_real, e_imag


def export_lhcp_gif(vtu_path=None,
                    output_gif="postpro/lhcp_rotation.gif",
                    n_frames=36,
                    sub_h_mm=1.52,
                    domain_extent_mm=32.0):
    if vtu_path is None:
        vtu_path = find_default_dataset()
        if vtu_path is None:
            print("CHYBA: Nebyl nalezen žádný výstupní soubor simulace (.pvtu/.vtu)!")
            print("Nejprve spusťte simulaci (např. python src/main.py).")
            return

    points, e_real, e_imag = read_mesh_fields(vtu_path)

    # Detekce měřítka jednotek (metry vs milimetry)
    max_coord = np.max(np.abs(points[:, 0]))
    if max_coord < 1.0:
        print("Detekovány souřadnice v metrech -> převádím na mm.")
        x_mm = points[:, 0] * 1e3
        y_mm = points[:, 1] * 1e3
        z_mm = points[:, 2] * 1e3
    else:
        print("Detekovány souřadnice v milimetrech.")
        x_mm = points[:, 0]
        y_mm = points[:, 1]
        z_mm = points[:, 2]

    # Filtrace bodů v rovině patche (z cca sub_h_mm = 1.52 mm)
    z_tol = 0.1
    mask_plane = np.abs(z_mm - sub_h_mm) <= z_tol
    if np.sum(mask_plane) < 10:
        z_tol = 0.5
        mask_plane = np.abs(z_mm - sub_h_mm) <= z_tol

    # Omezení na doménu patche a napájecího vedení
    domain_mask = mask_plane & (np.abs(x_mm) <= domain_extent_mm) & (np.abs(y_mm) <= domain_extent_mm)
    xp = x_mm[domain_mask]
    yp = y_mm[domain_mask]
    er_p = e_real[domain_mask]
    ei_p = e_imag[domain_mask]

    print(f"Vybráno {len(xp)} bodů sítě v rovině patche (z = {sub_h_mm:.2f} mm, oblast +/-{domain_extent_mm} mm).")
    if len(xp) < 10:
        print("CHYBA: Nalezen nedostatečný počet bodů v rovině patche pro vykreslení!")
        return

    # Vytvoření regulární 2D mřížky pro čisté zobrazení
    grid_res = 80
    xi = np.linspace(-domain_extent_mm, domain_extent_mm, grid_res)
    yi = np.linspace(-domain_extent_mm, domain_extent_mm, grid_res)
    Xi, Yi = np.meshgrid(xi, yi)

    # Triangulace bodů pro interpolaci na mřížku
    print("Provádím triangulaci sítě pro interpolaci...")
    triang = mtri.Triangulation(xp, yp)
    
    interp_er_x = mtri.LinearTriInterpolator(triang, er_p[:, 0])
    interp_er_y = mtri.LinearTriInterpolator(triang, er_p[:, 1])
    interp_er_z = mtri.LinearTriInterpolator(triang, er_p[:, 2])

    interp_ei_x = mtri.LinearTriInterpolator(triang, ei_p[:, 0])
    interp_ei_y = mtri.LinearTriInterpolator(triang, ei_p[:, 1])
    interp_ei_z = mtri.LinearTriInterpolator(triang, ei_p[:, 2])

    Ex_r = interp_er_x(Xi, Yi)
    Ey_r = interp_er_y(Xi, Yi)
    Ez_r = interp_er_z(Xi, Yi)

    Ex_i = interp_ei_x(Xi, Yi)
    Ey_i = interp_ei_y(Xi, Yi)
    Ez_i = interp_ei_z(Xi, Yi)

    # Nahrazení NaN mimo doménu nulami
    for arr in [Ex_r, Ey_r, Ez_r, Ex_i, Ey_i, Ez_i]:
        arr[np.isnan(arr)] = 0.0

    phases = np.linspace(0, 2 * np.pi, n_frames, endpoint=False)

    # Stanovení stálé horní meze škály (98. percentil)
    max_mag = 0.0
    for phi in phases[::4]:
        Ex = Ex_r * np.cos(phi) - Ex_i * np.sin(phi)
        Ey = Ey_r * np.cos(phi) - Ey_i * np.sin(phi)
        Ez = Ez_r * np.cos(phi) - Ez_i * np.sin(phi)
        mag = np.sqrt(Ex**2 + Ey**2 + Ez**2)
        finite_vals = mag[np.isfinite(mag)]
        if len(finite_vals) > 0:
            max_mag = max(max_mag, float(np.percentile(finite_vals, 98)))

    if max_mag <= 0:
        max_mag = 1.0

    # Příprava grafického okna
    fig, ax = plt.subplots(figsize=(7.5, 6.5), dpi=110)
    plt.subplots_adjust(left=0.1, right=0.86, top=0.9, bottom=0.1)
    cax = fig.add_axes([0.88, 0.15, 0.03, 0.7])

    patch_w = 30.9
    step = 4  # krok pro vektorové šipky quiveru

    def update(frame):
        ax.clear()
        phi = phases[frame]
        deg = int(round(np.degrees(phi)))

        # Vypočet okamžitého harmonického pole: E(t) = E_re * cos(wt) - E_im * sin(wt)
        Ex = Ex_r * np.cos(phi) - Ex_i * np.sin(phi)
        Ey = Ey_r * np.cos(phi) - Ey_i * np.sin(phi)
        Ez = Ez_r * np.cos(phi) - Ez_i * np.sin(phi)
        mag = np.sqrt(Ex**2 + Ey**2 + Ez**2)

        im = ax.pcolormesh(Xi, Yi, mag, cmap='turbo', shading='auto', vmin=0, vmax=max_mag)

        # Šipky vektoru elektrického pole v rovině (Ex, Ey)
        ax.quiver(
            Xi[::step, ::step], Yi[::step, ::step],
            Ex[::step, ::step], Ey[::step, ::step],
            color='white', scale=max_mag * 1.8, scale_units='xy',
            alpha=0.9, width=0.005
        )

        # Obrys flíčku antény (30.9 x 30.9 mm)
        rect = plt.Rectangle(
            (-patch_w / 2, -patch_w / 2), patch_w, patch_w,
            fill=False, edgecolor='cyan', linestyle='--', linewidth=1.5, label='Patch'
        )
        ax.add_patch(rect)

        ax.set_title(
            f"Rotace pole LHCP — Fáze $\\omega t = {deg:03d}^\\circ$\n"
            r"$\vec{E}(\omega t) = \vec{E}_{re}\cos(\omega t) - \vec{E}_{im}\sin(\omega t)$",
            fontsize=11, fontweight='bold'
        )
        ax.set_xlabel("X [mm]")
        ax.set_ylabel("Y [mm]")
        ax.set_xlim(-domain_extent_mm, domain_extent_mm)
        ax.set_ylim(-domain_extent_mm, domain_extent_mm)
        ax.set_aspect('equal')
        ax.grid(True, linestyle=':', alpha=0.4)

        if frame == 0:
            cbar = fig.colorbar(im, cax=cax)
            cbar.set_label("|E| [V/m]", fontweight='bold')

        return ax,

    print(f"Generuji {n_frames} snímků animace rotace pole...")
    anim = FuncAnimation(fig, update, frames=n_frames, blit=False)

    os.makedirs(os.path.dirname(output_gif) or ".", exist_ok=True)
    writer = PillowWriter(fps=10)
    anim.save(output_gif, writer=writer)
    plt.close()

    # Také zkopírujeme do data/postpro pokud byl specifikován jiný adresář
    alt_output = "data/postpro/lhcp_rotation.gif" if output_gif.startswith("postpro") else "postpro/lhcp_rotation.gif"
    try:
        os.makedirs(os.path.dirname(alt_output), exist_ok=True)
        shutil.copyfile(output_gif, alt_output)
    except Exception:
        pass

    print("==================================================")
    print(f"Animovaný GIF byl úspěšně vygenerován do: {output_gif}")
    if os.path.exists(alt_output):
        print(f"Zároveň uložen do: {alt_output}")
    print("==================================================")


if __name__ == "__main__":
    vtu = sys.argv[1] if len(sys.argv) > 1 else None
    out = sys.argv[2] if len(sys.argv) > 2 else "data/postpro/lhcp_rotation.gif"
    export_lhcp_gif(vtu, out)
