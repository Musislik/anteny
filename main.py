import os
import numpy as np
import skrf as rf
import matplotlib.pyplot as plt

from geometry import build_model
from mesh import assign_physical_groups_and_mesh
from palace_builder import build_palace_config
from runner import run_palace

def main():
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
        'freq_step': 0.05,
        'amr_threshold': 0.3
    }

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
    s11_file = os.path.join(output_dir, "port-S.s1p") # Lumped port S-parameters
    
    if os.path.exists(s11_file):
        ntwk = rf.Network(s11_file)
        plt.figure(figsize=(8, 6))
        ntwk.plot_s_db(m=0, n=0, label='S11')
        plt.title('Činitel odrazu (S11) - LHCP Flíčková anténa')
        plt.xlabel('Frekvence')
        plt.ylabel('S11 [dB]')
        plt.grid(True)
        plt.axhline(-10, color='r', linestyle='--')
        
        plot_path = "S11_graf.png"
        plt.savefig(plot_path)
        print(f"Graf byl úspěšně uložen do {plot_path}")
    else:
        print(f"Výstupní soubor {s11_file} nebyl nalezen. Simulace zřejmě selhala nebo byla zapsána jinam.")

if __name__ == "__main__":
    main()
