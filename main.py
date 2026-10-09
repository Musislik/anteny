import os
import numpy as np
import skrf as rf
import matplotlib.pyplot as plt
import gmsh

from geometry import build_model
from mesh import assign_physical_groups_and_mesh
from palace_builder import build_palace_config
from runner import run_palace

from tracker import analyze_and_log_run

def main(custom_params=None):
    # 1. Definice parametrů
    params = {
        # Geometrie
        'patch_L': 30.8,
        'patch_W': 30.8,
        'sub_h': 1.52,
        'sub_L': 70.8,
        'sub_W': 70.8,
        'feed_W': 3.0,
        'air_margin': 35.0, # min lambda/4 ~ 32 mm
        
        # Materiály
        'eps_r': 4.3,
        'tan_delta': 0.02,
        
        # Síť
        'mesh_size_max': 5.0,
        'mesh_size_min': 0.5,
        
        # Palace solver (frekvence v GHz, Palace čte v GHz defaultně)
        # Očekávaná rezonance cca 2.33 GHz, nastavíme sweep 2.0 až 2.6 GHz
        'freq_min': 2.1,
        'freq_max': 2.6,
        'freq_step': 0.001,
        'amr_threshold': 0.3
    }
    
    if custom_params:
        params.update(custom_params)

    print("--- 1. Generování geometrie (OpenCASCADE) ---")
    build_model(params)
    
    # Export 3D modelu pro vizualizaci geometrie v CADu
    step_file = "antenna_model.step"
    gmsh.write(step_file)
    print(f"Geometrie byla exportována do {step_file} pro případné zobrazení v CAD softwaru.")
    
    # Isometrický náhled pomocí Matplotlib
    from visualization import plot_geometry
    plot_geometry(params)
    
    print("--- 2. Klasifikace domén a tvorba sítě (Gmsh) ---")
    assign_physical_groups_and_mesh(params)
    
    print("--- 3. Vytváření konfigurace pro Palace ---")
    build_palace_config(params)
    
    print("--- 4. Spuštění fyzikální simulace (Palace) ---")
    run_palace()
    
    print("--- 5. Zpracování výsledků ---")
    # Palace ukládá S-parametry jako Touchstone soubor do definovaného výstupního adresáře
    output_dir = "postpro"
    s11_file = os.path.join(output_dir, "port-S.csv") # Palace outputs CSV
    
    if os.path.exists(s11_file):
        data = np.loadtxt(s11_file, delimiter=',', skiprows=1)
        freqs = data[:, 0]
        s11_db = data[:, 1]
        
        plt.figure(figsize=(8, 6))
        plt.plot(freqs, s11_db, label='S11')
        plt.title('Činitel odrazu (S11) - LHCP Flíčková anténa')
        plt.xlabel('Frekvence [GHz]')
        plt.ylabel('S11 [dB]')
        plt.grid(True)
        plt.axhline(-10, color='r', linestyle='--')
        plt.legend()
        
        plot_path = "S11_graf.png"
        plt.savefig(plot_path)
        print(f"Graf byl úspěšně uložen do {plot_path}")
        
        # Logování do Aim Trackeru
        analyze_and_log_run(params, s11_file)
    else:
        print(f"Výstupní soubor {s11_file} nebyl nalezen. Simulace zřejmě selhala nebo byla zapsána jinam.")

if __name__ == "__main__":
    main()
