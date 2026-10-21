import os
import shutil
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

def load_env_file(filepath=".env"):
    """Načte proměnné prostředí ze souboru .env, pokud existuje."""
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                            v = v[1:-1]
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception as e:
            print(f"Upozornění při čtení .env: {e}")

def _resolve_param(key, env_key, default_val, custom_params=None, cast_type=float):
    """Vyhodnotí parametr s prioritou: custom_params > os.environ > default."""
    if custom_params and key in custom_params and custom_params[key] is not None:
        return cast_type(custom_params[key])
    val = os.getenv(env_key)
    if val is not None:
        try:
            return cast_type(val)
        except (ValueError, TypeError):
            pass
    return default_val

def clean_previous_outputs():
    print("--- 0. Čištění předchozích výstupů simulace ---")
    dirs_to_clean = ["data/postpro"]
    for d in dirs_to_clean:
        if os.path.exists(d):
            for item in os.listdir(d):
                p = os.path.join(d, item)
                try:
                    if os.path.isdir(p):
                        shutil.rmtree(p)
                    elif os.path.isfile(p):
                        os.remove(p)
                except Exception as e:
                    print(f"Upozornění při mazání {p}: {e}")
    print("Složka data/postpro byla vyčištěna.")

def main(custom_params=None, skip_simulation=False, clean=False):
    if clean:
        clean_previous_outputs()

    # Načtení případného .env souboru
    load_env_file()

    # 1. Parametrizace materiálů a frekvenčního pásma
    sub_h = _resolve_param('sub_h', 'SUB_H', 1.52, custom_params, float)
    eps_r = _resolve_param('eps_r', 'EPS_R', 4.3, custom_params, float)
    tan_delta = _resolve_param('tan_delta', 'TAN_DELTA', 0.02, custom_params, float)
    
    # Kmitočtové pásmo sweepu (GHz)
    freq_min = _resolve_param('freq_min', 'FREQ_MIN', 2.320, custom_params, float)
    freq_max = _resolve_param('freq_max', 'FREQ_MAX', 2.345, custom_params, float)
    freq_step = _resolve_param('freq_step', 'FREQ_STEP', 0.005, custom_params, float)
    
    # Parametry sítě a řešiče
    mesh_size_max = _resolve_param('mesh_size_max', 'MESH_SIZE_MAX', 5.0, custom_params, float)
    mesh_size_min = _resolve_param('mesh_size_min', 'MESH_SIZE_MIN', 0.5, custom_params, float)
    amr_max_its = _resolve_param('amr_max_its', 'AMR_MAX_ITS', 2, custom_params, int)
    amr_threshold = _resolve_param('amr_threshold', 'AMR_THRESHOLD', 0.3, custom_params, float)
    port_impedance = _resolve_param('port_impedance', 'PORT_IMPEDANCE', PORT_Z0, custom_params, float)

    print(f"--- Parametry simulace: Freq {freq_min:.3f}-{freq_max:.3f} GHz (krok {freq_step:.4f} GHz), Síť {mesh_size_min}-{mesh_size_max} mm, AMR {amr_max_its} it. ---")

    # Geometrie flíčku syntetizovaná z analytické rezonance pro střed pásma SDARS
    patch_size = float(np.round(synth_square_patch_size(DESIGN_FREQ_GHZ, sub_h, eps_r), 2))
    patch_l = custom_params.get('patch_L', patch_size) if custom_params and 'patch_L' in custom_params else patch_size
    patch_w = custom_params.get('patch_W', patch_size) if custom_params and 'patch_W' in custom_params else patch_size
    
    # Rozměry napájecí sítě a substrátu odvozené z analytického modelu bez magických čísel
    from rf_calc import calc_feed_network_dimensions
    feed_net = calc_feed_network_dimensions(patch_w, patch_l, sub_h, eps_r, freq_ghz=DESIGN_FREQ_GHZ, port_z0=port_impedance)
    feed_w = feed_net['feed_w']
    sub_w = feed_net['sub_w']
    sub_l = feed_net['sub_l']
    feed_offset_x = feed_net['feed_offset_x']
    feed_offset_y = feed_net['feed_offset_y']
    
    # Rozměry vzduchového boxu: vzdálenost stěn >= lambda_0 / 4 při nejnižší frekvenci
    lambda_0_max = C_0_MM_GHZ / freq_min
    air_margin = float(np.round(lambda_0_max / 4.0, 1))

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
        'mesh_size_max': mesh_size_max,
        'mesh_size_min': mesh_size_min,
        
        # Palace solver (frekvence v GHz)
        'freq_min': freq_min,
        'freq_max': freq_max,
        'freq_step': freq_step,
        'amr_max_its': amr_max_its,
        'amr_threshold': amr_threshold,
        'port_impedance': port_impedance,
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
    
    if skip_simulation:
        print("--- Hotovo: Geometrie, STEP CAD model, náhled a síť byly vygenerovány lokálně bez simulace v Dockeru. ---")
        return

    print("--- 4. Spuštění fyzikální simulace (Palace) ---")
    try:
        run_palace()
    except Exception as e:
        print(f"Upozornění: Simulace Palace nebyla spuštěna: {e}")
        return
    
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
    import argparse
    parser = argparse.ArgumentParser(description="LHCP Patch Antenna Simulation & CAD Model Generation")
    parser.add_argument("--skip-simulation", "--no-docker", dest="skip_simulation", action="store_true",
                        help="Generovat pouze model, CAD STEP soubor a síť lokálně bez spouštění simulace v Dockeru")
    parser.add_argument("--clean", dest="clean", action="store_true",
                        help="Smazat předchozí výstupní data (postpro) před spuštěním nového výpočtu")
    
    # Parametrizace frekvenčního rozsahu a kroku
    parser.add_argument("--freq-min", type=float, default=None, dest="freq_min",
                        help="Minimální frekvence sweepu v GHz (výchozí: 2.320 nebo z FREQ_MIN)")
    parser.add_argument("--freq-max", type=float, default=None, dest="freq_max",
                        help="Maximální frekvence sweepu v GHz (výchozí: 2.345 nebo z FREQ_MAX)")
    parser.add_argument("--freq-step", type=float, default=None, dest="freq_step",
                        help="Frekvenční krok sweepu v GHz (výchozí: 0.005 nebo z FREQ_STEP)")

    # Parametrizace sítě a řešiče
    parser.add_argument("--mesh-max", type=float, default=None, dest="mesh_size_max",
                        help="Maximální velikost elementu sítě v mm (výchozí: 5.0 nebo z MESH_SIZE_MAX)")
    parser.add_argument("--mesh-min", type=float, default=None, dest="mesh_size_min",
                        help="Minimální velikost elementu sítě v mm (výchozí: 0.5 nebo z MESH_SIZE_MIN)")
    parser.add_argument("--amr-its", type=int, default=None, dest="amr_max_its",
                        help="Maximální počet adaptivních zjemnění AMR (výchozí: 2 nebo z AMR_MAX_ITS)")

    # Parametrizace geometrie patche
    parser.add_argument("--patch-l", type=float, default=None, dest="patch_L",
                        help="Délka flíčku patche v mm (výchozí: z analytického modelu)")
    parser.add_argument("--patch-w", type=float, default=None, dest="patch_W",
                        help="Šířka flíčku patche v mm (výchozí: z analytického modelu)")

    args = parser.parse_args()

    cli_params = {}
    for param in ['freq_min', 'freq_max', 'freq_step', 'mesh_size_max', 'mesh_size_min', 'amr_max_its', 'patch_L', 'patch_W']:
        val = getattr(args, param, None)
        if val is not None:
            cli_params[param] = val

    main(custom_params=cli_params if cli_params else None, skip_simulation=args.skip_simulation, clean=args.clean)

