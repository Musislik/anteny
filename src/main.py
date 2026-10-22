import os
import sys
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
from postpro_utils import ensure_paraview_linked, load_env

from rf_calc import (
    synth_microstrip_w,
    synth_square_patch_size,
    C_0_MM_GHZ,
    DESIGN_FREQ_GHZ,
    PORT_Z0
)

def _resolve_param(key, env_key, default_val, custom_params=None, cast_type=float):
    """Vyhodnotí parametr s prioritou: custom_params > os.environ > default."""
    if custom_params:
        if key in custom_params and custom_params[key] is not None:
            return cast_type(custom_params[key])
        if key.lower() in custom_params and custom_params[key.lower()] is not None:
            return cast_type(custom_params[key.lower()])
        if key.upper() in custom_params and custom_params[key.upper()] is not None:
            return cast_type(custom_params[key.upper()])
    val = os.getenv(env_key)
    if val is not None:
        try:
            return cast_type(val)
        except (ValueError, TypeError):
            pass
    return default_val

def clean_previous_outputs(data_dir=None):
    print("--- 0. Čištění předchozích výstupů simulace ---")
    if data_dir is None:
        _, data_dir = load_env()
    dirs_to_clean = [os.path.join(data_dir, "postpro")]
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
    load_env()

    # 1. Parametrizace materiálů a frekvenčního pásma
    sub_h = _resolve_param('sub_h', 'SUB_H', 1.52, custom_params, float)
    eps_r = _resolve_param('eps_r', 'EPS_R', 4.3, custom_params, float)
    tan_delta = _resolve_param('tan_delta', 'TAN_DELTA', 0.02, custom_params, float)
    
    # Kmitočtové pásmo sweepu (GHz)
    freq_min = _resolve_param('freq_min', 'FREQ_MIN', 2.320, custom_params, float)
    freq_max = _resolve_param('freq_max', 'FREQ_MAX', 2.345, custom_params, float)
    freq_step = _resolve_param('freq_step', 'FREQ_STEP', 0.005, custom_params, float)
    
    # Parametry sítě a řešiče
    mesh_size_max = _resolve_param('mesh_size_max', 'MESH_SIZE_MAX', 8.0, custom_params, float)
    mesh_size_min = _resolve_param('mesh_size_min', 'MESH_SIZE_MIN', 0.5, custom_params, float)
    mesh_dist_min = _resolve_param('mesh_dist_min', 'MESH_DIST_MIN', 0.5, custom_params, float)
    mesh_dist_max = _resolve_param('mesh_dist_max', 'MESH_DIST_MAX', 6.0, custom_params, float)
    amr_max_its = _resolve_param('amr_max_its', 'AMR_MAX_ITS', 2, custom_params, int)
    amr_threshold = _resolve_param('amr_threshold', 'AMR_THRESHOLD', 0.2, custom_params, float)
    farfield_nsample = _resolve_param('farfield_nsample', 'FARFIELD_NSAMPLE', 16200, custom_params, int)
    save_step = _resolve_param('save_step', 'SAVE_STEP', 1, custom_params, int)
    port_impedance = _resolve_param('port_impedance', 'PORT_IMPEDANCE', PORT_Z0, custom_params, float)
    linear_tol = _resolve_param('linear_tol', 'LINEAR_TOL', 1e-6, custom_params, float)
    linear_max_its = _resolve_param('linear_max_its', 'LINEAR_MAX_ITS', 100, custom_params, int)

    print(f"--- Parametry simulace: Freq {freq_min:.3f}-{freq_max:.3f} GHz (krok {freq_step:.4f} GHz), Síť {mesh_size_min}-{mesh_size_max} mm, AMR {amr_max_its} it. (Tol {amr_threshold}), Solver Tol {linear_tol} (MaxIts {linear_max_its}) ---")

    # Geometrie flíčku (priority: custom_params > os.environ (PATCH_L/PATCH_W) > 30.3 mm)
    patch_size = float(np.round(synth_square_patch_size(DESIGN_FREQ_GHZ, sub_h, eps_r), 2))
    patch_l = _resolve_param('patch_L', 'PATCH_L', 30.3, custom_params, float)
    patch_w = _resolve_param('patch_W', 'PATCH_W', patch_l, custom_params, float)

    # Zanoření napaječe (inset feed)
    feed_inset = _resolve_param('feed_inset', 'FEED_INSET', 0.0, custom_params, float)
    if feed_inset == 0.0:
        feed_inset = _resolve_param('inset', 'INSET', 0.0, custom_params, float)

    feed_inset_gap = _resolve_param('feed_inset_gap', 'FEED_INSET_GAP', None, custom_params, float)
    if feed_inset_gap is None:
        feed_inset_gap = _resolve_param('inset_gap', 'INSET_GAP', None, custom_params, float)

    feed_inset_width = _resolve_param('feed_inset_width', 'FEED_INSET_WIDTH', None, custom_params, float)
    if feed_inset_width is None:
        feed_inset_width = _resolve_param('inset_width', 'INSET_WIDTH', None, custom_params, float)

    print(f"--- Geometrie flíčku: L = {patch_l:.2f} mm, W = {patch_w:.2f} mm, Zanoření napaječe: {feed_inset:.2f} mm ---")

    # Rozměry napájecí sítě a substrátu odvozené z analytického modelu bez magických čísel
    from rf_calc import calc_feed_network_dimensions
    feed_net = calc_feed_network_dimensions(patch_w, patch_l, sub_h, eps_r, freq_ghz=DESIGN_FREQ_GHZ, port_z0=port_impedance, inset=feed_inset)
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
        'mesh_dist_min': mesh_dist_min,
        'mesh_dist_max': mesh_dist_max,
        
        # Palace solver (frekvence v GHz)
        'freq_min': freq_min,
        'freq_max': freq_max,
        'freq_step': freq_step,
        'amr_max_its': amr_max_its,
        'amr_threshold': amr_threshold,
        'farfield_nsample': farfield_nsample,
        'save_step': save_step,
        'port_impedance': port_impedance,
        'linear_tol': linear_tol,
        'linear_max_its': linear_max_its,
        'design_freq_ghz': DESIGN_FREQ_GHZ
    }
    # Zahrnutí všech parametrů napájecí sítě (w1, w2, w3, délky l1-l8)
    params.update(feed_net)
    if feed_inset_gap is not None:
        params['inset_gap'] = feed_inset_gap
    if feed_inset_width is not None:
        params['inset_width'] = feed_inset_width
    
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

    # Propojení složky paraview na poslední iteraci, pokud Palace běžel v AMR režimu
    _, data_dir = load_env()
    ensure_paraview_linked(data_dir)

    print("--- 5. Zpracování výsledků ---")
    output_dir = os.path.join(data_dir, "postpro")
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
        
        plot_path = os.path.join(data_dir, "S11_graf.png")
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
                        help="Maximální velikost elementu sítě v mm (výchozí: 8.0 nebo z MESH_SIZE_MAX)")
    parser.add_argument("--mesh-min", type=float, default=None, dest="mesh_size_min",
                        help="Minimální velikost elementu sítě v mm (výchozí: 0.5 nebo z MESH_SIZE_MIN)")
    parser.add_argument("--amr-its", type=int, default=None, dest="amr_max_its",
                        help="Maximální počet adaptivních zjemnění AMR (výchozí: 2 nebo z AMR_MAX_ITS)")
    parser.add_argument("--amr-tol", "--amr-threshold", type=float, default=None, dest="amr_threshold",
                        help="Relativní tolerance pro zastavení AMR zjemnění (výchozí: 0.2 nebo z AMR_THRESHOLD)")
    parser.add_argument("--farfield-nsample", type=int, default=None, dest="farfield_nsample",
                        help="Počet bodů vzorkování dálkového pole (výchozí: 16200 nebo z FARFIELD_NSAMPLE)")
    parser.add_argument("--save-step", type=int, default=None, dest="save_step",
                        help="Krok ukládání 3D polí (výchozí: 1 nebo z SAVE_STEP)")
    parser.add_argument("--linear-tol", type=float, default=None, dest="linear_tol",
                        help="Relativní tolerance lineárního řešiče FGMRES (výchozí: 1e-6 nebo z LINEAR_TOL)")
    parser.add_argument("--linear-its", "--linear-max-its", type=int, default=None, dest="linear_max_its",
                        help="Maximální počet iterací lineárního řešiče FGMRES (výchozí: 100 nebo z LINEAR_MAX_ITS)")

    # Parametrizace geometrie patche a zanoření
    parser.add_argument("--patch-l", type=float, default=None, dest="patch_L",
                        help="Délka flíčku patche v mm (výchozí: 30.3 nebo z PATCH_L)")
    parser.add_argument("--patch-w", type=float, default=None, dest="patch_W",
                        help="Šířka flíčku patche v mm (výchozí: z PATCH_W nebo rovno patch-l)")
    parser.add_argument("--inset", "--feed-inset", type=float, default=None, dest="feed_inset",
                        help="Hloubka zanoření napaječe do flíčku v mm (výchozí: 0.0 nebo z FEED_INSET)")
    parser.add_argument("--inset-gap", type=float, default=None, dest="feed_inset_gap",
                        help="Šířka mezery zářezu po stranách napaječe v mm (výchozí: rovno šířce w3 cca 0.69 mm)")
    parser.add_argument("--inset-width", type=float, default=None, dest="feed_inset_width",
                        help="Celková šířka výřezu zářezu v mm (w3 + 2*gap)")

    args = parser.parse_args()

    cli_params = {}
    for param in ['freq_min', 'freq_max', 'freq_step', 'mesh_size_max', 'mesh_size_min', 'amr_max_its',
                  'amr_threshold', 'farfield_nsample', 'save_step', 'linear_tol', 'linear_max_its',
                  'patch_L', 'patch_W', 'feed_inset', 'feed_inset_gap', 'feed_inset_width']:
        val = getattr(args, param, None)
        if val is not None:
            cli_params[param] = val

    main(custom_params=cli_params if cli_params else None, skip_simulation=args.skip_simulation, clean=args.clean)

