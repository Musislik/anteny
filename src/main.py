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

from rf_calc import (
    synth_microstrip_w,
    synth_square_patch_size,
    C_0_MM_GHZ,
    DESIGN_FREQ_GHZ,
    PORT_Z0
)

def main(custom_params=None):
    # 1. Analytická definice parametrů bez magických čísel
    sub_h = 1.52
    eps_r = 4.3
    tan_delta = 0.02
    
    # Kmitočtové pásmo sweepu (GHz)
    freq_min = 2.1
    freq_max = 2.6
    freq_step = 0.001
    
    # Geometrie flíčku syntetizovaná z analytické rezonance pro střed pásma SDARS
    patch_size = float(np.round(synth_square_patch_size(DESIGN_FREQ_GHZ, sub_h, eps_r), 2))
    patch_l = custom_params.get('patch_L', patch_size) if custom_params else patch_size
    patch_w = custom_params.get('patch_W', patch_size) if custom_params else patch_size
    
    # Rozměry napájecí sítě a substrátu odvozené z analytického modelu bez magických čísel
    from rf_calc import calc_feed_network_dimensions
    feed_net = calc_feed_network_dimensions(patch_w, patch_l, sub_h, eps_r, freq_ghz=DESIGN_FREQ_GHZ, port_z0=PORT_Z0)
    feed_w = feed_net['feed_w']
    sub_w = feed_net['sub_w']
    sub_l = feed_net['sub_l']
    feed_offset_x = feed_net['feed_offset_x']
    feed_offset_y = feed_net['feed_offset_y']
    
    # Rozměry vzduchového boxu: vzdálenost stěn >= lambda_0 / 4 při nejnižší frekvenci
    lambda_0_max = C_0_MM_GHZ / freq_min
    air_margin = float(np.round(lambda_0_max / 4.0, 1))  # cca 35.7 mm

    params = {
        # Geometrie
        'patch_L': patch_l,
        'patch_W': patch_w,
        'sub_h': sub_h,
        'sub_L': sub_l,
        'sub_W': sub_w,
        'feed_W': feed_w,
        'feed_offset_x': feed_offset_x,
        'feed_offset_y': feed_offset_y,
        'air_margin': air_margin,
        
        # Materiály
        'eps_r': eps_r,
        'tan_delta': tan_delta,
        
        # Síť
        'mesh_size_max': 5.0,
        'mesh_size_min': 0.5,
        
        # Palace solver (frekvence v GHz)
        'freq_min': freq_min,
        'freq_max': freq_max,
        'freq_step': freq_step,
        'amr_max_its': 2,
        'amr_threshold': 0.3,
        'port_impedance': PORT_Z0,
        'design_freq_ghz': DESIGN_FREQ_GHZ
    }
    # Zahrnutí všech parametrů napájecí sítě (w1, w2, w3, délky l1-l8)
    params.update(feed_net)
    
    run_name = None
    if custom_params:
        params.update(custom_params)
        run_name = "_".join([f"{k}={v}" for k, v in custom_params.items()])

    print("--- 1. Generování geometrie (OpenCASCADE) ---")
    build_model(params)
    
    # Export 3D modelu pro vizualizaci geometrie v CADu
    step_file = "data/antenna_model.step"
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
    output_dir = "data/postpro"
    s11_file = os.path.join(output_dir, "port-S.csv") # Palace outputs CSV
    
    if os.path.exists(s11_file):
        data_arr = np.loadtxt(s11_file, delimiter=',', skiprows=1)
        freqs = data_arr[:, 0]
        s11_db = data_arr[:, 1]
        
        plt.figure(figsize=(8, 6))
        plt.plot(freqs, s11_db, label='S11')
        plt.title('Činitel odrazu (S11) - LHCP Flíčková anténa')
        plt.xlabel('Frekvence [GHz]')
        plt.ylabel('S11 [dB]')
        plt.grid(True)
        plt.axhline(-10, color='r', linestyle='--')
        plt.legend()
        
        plot_path = "data/S11_graf.png"
        plt.savefig(plot_path)
        print(f"Graf byl úspěšně uložen do {plot_path}")
        
        # Logování do Aim Trackeru
        analyze_and_log_run(params, s11_file, run_name=run_name)
    else:
        print(f"Výstupní soubor {s11_file} nebyl nalezen. Simulace zřejmě selhala nebo byla zapsána jinam.")

if __name__ == "__main__":
    main()
