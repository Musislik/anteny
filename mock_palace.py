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
    
    # Generování mock ParaView VTU souboru
    pv_dir = os.path.join(output_dir, "paraview", "driven")
    os.makedirs(pv_dir, exist_ok=True)
    vtu_file = os.path.join(pv_dir, "driven_000000001.vtu")
    
    # Simple valid VTU format structure
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
    with open(vtu_file, 'w') as f:
        f.write(mock_vtu_content)
    print(f"Mock Palace Solver: Uloženo {vtu_file}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        generate_mock_touchstone(sys.argv[1])
    else:
        generate_mock_touchstone("config.json")
