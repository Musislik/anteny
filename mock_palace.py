import sys
import os
import json
import numpy as np

# Fyzikální a modelové konstanty
C_0_MM_GHZ = 299.792458  # Rychlost světla v mm * GHz
DEFAULT_Q = 50.0         # Typický činitel jakosti mikropáskového flíčku
S11_FLOOR_LINEAR = 0.05  # Minimální hodnota odrazu (-26 dB dno)

def generate_mock_touchstone(config_path):
    print(f"Mock Palace Solver: Načítám {config_path}")
    
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    freq_min = config['Solver']['Driven']['MinFreq']
    freq_max = config['Solver']['Driven']['MaxFreq']
    freq_step = config['Solver']['Driven']['FreqStep']
    
    output_dir = config['Problem'].get('Output', 'postpro')
    os.makedirs(output_dir, exist_ok=True)
    
    out_file = os.path.join(output_dir, "port-S.csv")
    
    freqs = np.arange(freq_min, freq_max + freq_step/2, freq_step)
    
    # Generování simulovaného S11
    Q = config.get("_Metadata", {}).get("Q", DEFAULT_Q)
    f_res = 2.3325  # Výchozí rezonanční frekvence (GHz)
    if "_Metadata" in config:
        patch_L = config["_Metadata"].get("patch_L", 30.0)
        patch_W = config["_Metadata"].get("patch_W", 30.0)
        h = config["_Metadata"].get("sub_h", 1.52)
        eps_r = config["Domains"]["Materials"][0]["Permittivity"]
        
        eps_eff = (eps_r + 1) / 2 + (eps_r - 1) / 2 / np.sqrt(1 + 12 * h / patch_W)
        delta_L = 0.412 * h * (eps_eff + 0.3) * (patch_W/h + 0.264) / ((eps_eff - 0.258) * (patch_W/h + 0.8))
        L_eff = patch_L + 2 * delta_L
        f_res = C_0_MM_GHZ / (2.0 * L_eff * np.sqrt(eps_eff))
    
    with open(out_file, 'w') as f:
        f.write("f (GHz), |S[1][1]| (dB), arg(S[1][1]) (deg)\n")
        
        for freq in freqs:
            # Model paralelního RLC rezonátoru zatíženého impedancí Z0:
            # Y = G + j * 2*Q*G*delta => Gamma = -j*Q*delta / (1 + j*Q*delta)
            delta = (freq - f_res) / f_res
            S11 = (-1j * Q * delta) / (1.0 + 1j * Q * delta)
            gamma_mag = np.abs(S11)
            gamma_ang = np.angle(S11, deg=True)
            
            gamma_mag = max(gamma_mag, S11_FLOOR_LINEAR)
            gamma_db = 20 * np.log10(gamma_mag)
            
            f.write(f"{freq:.6e}, {gamma_db:.6e}, {gamma_ang:.6e}\n")
            
    print(f"Mock Palace Solver: Uloženo {out_file}")
    
    # Generování prostorového ParaView VTU souboru
    pv_dir = os.path.join(output_dir, "paraview", "driven")
    os.makedirs(pv_dir, exist_ok=True)
    vtu_file = os.path.join(pv_dir, "driven_000000001.vtu")
    
    generate_mock_vtu(config, vtu_file)

def generate_mock_vtu(config, vtu_file):
    mesh_path = config.get("Model", {}).get("Mesh", "mesh.msh")
    if not os.path.exists(mesh_path) and os.path.exists(os.path.join(os.getcwd(), "mesh.msh")):
        mesh_path = os.path.join(os.getcwd(), "mesh.msh")

    meta = config.get("_Metadata", {})
    patch_L = meta.get("patch_L", 30.9)
    patch_W = meta.get("patch_W", 30.9)
    h = meta.get("sub_h", 1.52)
    L0 = config.get("Model", {}).get("L0", 1e-3)

    try:
        import meshio
        if os.path.exists(mesh_path):
            m = meshio.read(mesh_path)
            pts_mm = m.points
            x = pts_mm[:, 0]
            y = pts_mm[:, 1]
            z = pts_mm[:, 2]
            pts_m = pts_mm * L0

            t_cells = [c for c in m.cells if c.type == "tetra"]
            all_tetra = np.vstack([c.data for c in t_cells])

            # Analytický model EM pole flíčkové antény (LHCP v rezonanci)
            in_patch_xy = (np.abs(x) <= patch_W / 2.0) & (np.abs(y) <= patch_L / 2.0)
            in_sub = (z >= 0.0) & (z <= h)

            norm_x = np.clip(x / (patch_W / 2.0), -1.0, 1.0)
            norm_y = np.clip(y / (patch_L / 2.0), -1.0, 1.0)

            dx = np.maximum(0.0, np.abs(x) - patch_W / 2.0)
            dy = np.maximum(0.0, np.abs(y) - patch_L / 2.0)
            dist_patch_xy = np.sqrt(dx**2 + dy**2)
            dz = np.abs(z - h)
            dist_patch_3d = np.sqrt(dist_patch_xy**2 + dz**2)

            E0 = 2500.0  # Špičková intenzita E na vyzařujících hranách [V/m]

            # Dutinkový rezonanční mód (stojatá vlna pod patchem s uzlem uprostřed)
            ez_patch = -np.sin(np.pi * norm_x / 2.0) * in_patch_xy * in_sub * E0

            # Okrajové rozptylové pole (fringing field)
            fringing = E0 * np.exp(-dist_patch_3d / 4.0)

            # Napájecí mikropáskové vedení
            dist_feed_line = np.minimum(
                np.sqrt((x + 15.0)**2 + np.maximum(0.0, y + 15.0)**2),
                np.sqrt((y + 15.0)**2 + np.maximum(0.0, x + 15.0)**2)
            )
            ez_feed = 1200.0 * np.exp(-dist_feed_line / 3.0) * (z >= 0.0) * (z <= h * 1.5)

            # Složka Ez
            Ez_real = np.where(in_patch_xy & in_sub, ez_patch, 0.0)
            Ez_real += fringing * np.sign(x + 1e-6) * (z >= h)
            Ez_real += ez_feed * (z <= h * 1.2)

            # Horizontální složky Ex, Ey (vyzařování na hranách)
            Ex_real = fringing * np.sign(x + 1e-6) * (np.abs(x) > patch_W / 2.0 - 2.0) * 0.7
            Ey_real = fringing * np.sign(y + 1e-6) * (np.abs(y) > patch_L / 2.0 - 2.0) * 0.7

            # Vyzařování do horního poloprostoru
            r_upper = np.sqrt(x**2 + y**2 + np.maximum(0.0, z - h)**2)
            rad_factor = np.exp(-r_upper / 40.0) * np.maximum(0.0, z) / (r_upper + 1.0)
            Ez_real += 200.0 * rad_factor

            E_real = np.column_stack([Ex_real, Ey_real, Ez_real])
            E_imag = np.column_stack([Ey_real * 0.8, -Ex_real * 0.8, Ez_real * 0.5])

            out_mesh = meshio.Mesh(
                points=pts_m,
                cells=[("tetra", all_tetra)],
                point_data={
                    "E_real": E_real,
                    "E_imag": E_imag,
                    "E_mag": np.linalg.norm(E_real, axis=1)
                }
            )
            out_mesh.write(vtu_file)
            print(f"Mock Palace Solver: Vygenerováno pole {vtu_file} ({len(pts_m)} uzlů)")
            return
    except Exception as e:
        print(f"Mock Palace Solver: Nepodařilo se vygenerovat pole ze sítě ({e}), použiji základní šablonu.")

    # Fallback pokud síť nebo meshio není k dispozici
    mock_vtu_content = """<?xml version="1.0"?>
<VTKFile type="UnstructuredGrid" version="1.0" byte_order="LittleEndian" header_type="UInt64">
  <UnstructuredGrid>
    <Piece NumberOfPoints="4" NumberOfCells="1">
      <Points>
        <DataArray type="Float64" Name="Points" NumberOfComponents="3" format="ascii">
          0 0 0 1 0 0 0 1 0 0 0 1
        </DataArray>
      </Points>
      <Cells>
        <DataArray type="Int64" Name="connectivity" format="ascii">0 1 2 3</DataArray>
        <DataArray type="Int64" Name="offsets" format="ascii">4</DataArray>
        <DataArray type="UInt8" Name="types" format="ascii">10</DataArray>
      </Cells>
      <PointData>
        <DataArray type="Float64" Name="E_real" NumberOfComponents="3" format="ascii">
          0 0 1 0 0 1 0 0 1 0 0 1
        </DataArray>
      </PointData>
    </Piece>
  </UnstructuredGrid>
</VTKFile>
"""
    with open(vtu_file, "w") as f:
        f.write(mock_vtu_content)
    print(f"Mock Palace Solver: Uloženo {vtu_file}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        generate_mock_touchstone(sys.argv[1])
    else:
        generate_mock_touchstone("config.json")
