import os
import sys
import shutil
import json
import numpy as np
import matplotlib.pyplot as plt
import gmsh

from geometry import build_model
from mesh import assign_physical_groups_and_mesh
from palace_builder import build_palace_config
from runner import run_palace

from tracker import analyze_and_log_run
from postpro_utils import (
    ensure_paraview_linked,
    load_env,
    copy_postpro_directory,
    merge_two_port_simulations,
)

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
    dirs_to_clean = [
        os.path.join(data_dir, "postpro"),
        os.path.join(data_dir, "postpro_p1"),
        os.path.join(data_dir, "postpro_p2"),
    ]
    for d in dirs_to_clean:
        if os.path.exists(d):
            for item in os.listdir(d):
                p = os.path.join(d, item)
                try:
                    if os.path.islink(p):
                        try:
                            os.unlink(p)
                        except Exception:
                            os.remove(p)
                    elif os.path.isdir(p):
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        try:
                            os.remove(p)
                        except Exception:
                            pass
                except Exception as e:
                    print(f"Upozornění při mazání {p}: {e}")
    print("Výstupní složky simulace (data/postpro*) byly vyčištěny.")

def main(custom_params=None, skip_simulation=False, clean=False):
    if clean:
        clean_previous_outputs()

    # Načtení případného .env souboru
    load_env()

    # Model antény (1 = původní T-dělič 50 Ohm, 2 = dvouportový model 100 Ohm LHCP, 3 = hybridní dvoustupňové přizpůsobení)
    antenna_model = _resolve_param('antenna_model', 'ANTENNA_MODEL', 1, custom_params, int)

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
    
    default_port_z0 = 100.0 if antenna_model in (2, 3) else PORT_Z0
    port_impedance = _resolve_param('port_impedance', 'PORT_IMPEDANCE', default_port_z0, custom_params, float)
    linear_tol = _resolve_param('linear_tol', 'LINEAR_TOL', 1e-6, custom_params, float)
    linear_max_its = _resolve_param('linear_max_its', 'LINEAR_MAX_ITS', 100, custom_params, int)

    print(f"--- Model {antenna_model} | Freq {freq_min:.3f}-{freq_max:.3f} GHz (krok {freq_step:.4f} GHz), Síť {mesh_size_min}-{mesh_size_max} mm, Port Z0 {port_impedance:.1f} Ohm ---")

    # Geometrie flíčku (výchozí 28.8 mm pro Model 2 a 3, 30.3 mm pro Model 1)
    default_patch_l = 28.8 if antenna_model in (2, 3) else 30.3
    patch_l = _resolve_param('patch_L', 'PATCH_L', default_patch_l, custom_params, float)
    patch_w = _resolve_param('patch_W', 'PATCH_W', patch_l, custom_params, float)

    # Rozměry vzduchového boxu: vzdálenost stěn >= lambda_0 / 4 při nejnižší frekvenci
    lambda_0_max = C_0_MM_GHZ / freq_min
    air_margin = float(np.round(lambda_0_max / 4.0, 1))

    params = {
        'antenna_model': antenna_model,
        'patch_L': patch_l,
        'patch_W': patch_w,
        'sub_h': sub_h,
        'air_margin': air_margin,
        'eps_r': eps_r,
        'tan_delta': tan_delta,
        'mesh_size_max': mesh_size_max,
        'mesh_size_min': mesh_size_min,
        'mesh_dist_min': mesh_dist_min,
        'mesh_dist_max': mesh_dist_max,
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
        'design_freq_ghz': DESIGN_FREQ_GHZ,
    }

    if antenna_model == 3:
        # MODEL 3: Hybridní dvoustupňové přizpůsobení (Cesta B)
        # Šířka a délka čtvrtvlnného transformátoru
        trans_w = _resolve_param('trans_w', 'TRANS_W', 0.42, custom_params, float)
        trans_w_b = _resolve_param('trans_w_b', 'TRANS_W_B', trans_w, custom_params, float)
        trans_w_l = _resolve_param('trans_w_l', 'TRANS_W_L', trans_w, custom_params, float)
        params['trans_w'] = trans_w
        params['trans_w_b'] = trans_w_b
        params['trans_w_l'] = trans_w_l
        params['w_T'] = trans_w

        trans_l = _resolve_param('trans_l', 'TRANS_L', None, custom_params, float)
        trans_l_b = _resolve_param('trans_l_b', 'TRANS_L_B', trans_l, custom_params, float)
        trans_l_l = _resolve_param('trans_l_l', 'TRANS_L_L', trans_l, custom_params, float)
        if trans_l is not None:
            params['trans_l'] = trans_l
            params['l_T'] = trans_l
        if trans_l_b is not None:
            params['trans_l_b'] = trans_l_b
        if trans_l_l is not None:
            params['trans_l_l'] = trans_l_l

        # Mělký zářez
        feed_inset_b = _resolve_param('feed_inset_b', 'FEED_INSET_B', None, custom_params, float)
        if feed_inset_b is None:
            feed_inset_b = _resolve_param('inset_b', 'INSET_B', None, custom_params, float)
        if feed_inset_b is None:
            feed_inset_b = _resolve_param('feed_inset', 'FEED_INSET', 2.5, custom_params, float)

        feed_inset_l = _resolve_param('feed_inset_l', 'FEED_INSET_L', None, custom_params, float)
        if feed_inset_l is None:
            feed_inset_l = _resolve_param('inset_l', 'INSET_L', None, custom_params, float)
        if feed_inset_l is None:
            feed_inset_l = _resolve_param('feed_inset', 'FEED_INSET', 2.5, custom_params, float)

        feed_gap_b = _resolve_param('feed_inset_gap_b', 'FEED_INSET_GAP_B', None, custom_params, float)
        if feed_gap_b is None:
            feed_gap_b = _resolve_param('inset_gap_b', 'INSET_GAP_B', None, custom_params, float)
        if feed_gap_b is None:
            feed_gap_b = _resolve_param('feed_inset_gap', 'FEED_INSET_GAP', 0.5, custom_params, float)

        feed_gap_l = _resolve_param('feed_inset_gap_l', 'FEED_INSET_GAP_L', None, custom_params, float)
        if feed_gap_l is None:
            feed_gap_l = _resolve_param('inset_gap_l', 'INSET_GAP_L', None, custom_params, float)
        if feed_gap_l is None:
            feed_gap_l = _resolve_param('feed_inset_gap', 'FEED_INSET_GAP', 0.5, custom_params, float)

        params['feed_inset_b'] = feed_inset_b
        params['feed_inset_l'] = feed_inset_l
        params['inset_b'] = feed_inset_b
        params['inset_l'] = feed_inset_l
        params['inset_gap_b'] = feed_gap_b
        params['inset_gap_l'] = feed_gap_l

        driven_port = _resolve_param('driven_port', 'DRIVEN_PORT', 'all', custom_params, str)
        params['driven_port'] = driven_port

        # Explicitní délky přívodů a fázovacího úseku
        feed_len_b = _resolve_param('feed_len_b', 'FEED_LEN_B', None, custom_params, float)
        feed_len_l = _resolve_param('feed_len_l', 'FEED_LEN_L', None, custom_params, float)
        feed_delta_l = _resolve_param('feed_delta_l', 'FEED_DELTA_L', None, custom_params, float)
        if feed_delta_l is None:
            feed_delta_l = _resolve_param('delta_l', 'DELTA_L', None, custom_params, float)

        if feed_len_b is not None:
            params['feed_len_b'] = feed_len_b
        if feed_len_l is not None:
            params['feed_len_l'] = feed_len_l
        if feed_delta_l is not None:
            params['feed_delta_l'] = feed_delta_l

        len_info = []
        if feed_len_b is not None:
            len_info.append(f"feed_len_b={feed_len_b:.2f}mm")
        if feed_len_l is not None:
            len_info.append(f"feed_len_l={feed_len_l:.2f}mm")
        if feed_delta_l is not None:
            len_info.append(f"delta_l={feed_delta_l:.2f}mm")
        len_str = f", {', '.join(len_info)}" if len_info else ""

        print(f"--- Model 3 (Hybrid Matching): w_T={trans_w:.2f} mm, y0b={feed_inset_b:.2f} mm, y0l={feed_inset_l:.2f} mm, Buzení = {driven_port}{len_str} ---")

    elif antenna_model == 2:
        # MODEL 2: Nezávislá zanoření inset_b a inset_l
        feed_inset_b = _resolve_param('feed_inset_b', 'FEED_INSET_B', None, custom_params, float)
        if feed_inset_b is None:
            feed_inset_b = _resolve_param('inset_b', 'INSET_B', None, custom_params, float)
        if feed_inset_b is None:
            feed_inset_b = _resolve_param('feed_inset', 'FEED_INSET', 0.0, custom_params, float)

        feed_inset_l = _resolve_param('feed_inset_l', 'FEED_INSET_L', None, custom_params, float)
        if feed_inset_l is None:
            feed_inset_l = _resolve_param('inset_l', 'INSET_L', None, custom_params, float)
        if feed_inset_l is None:
            feed_inset_l = _resolve_param('feed_inset', 'FEED_INSET', 0.0, custom_params, float)

        feed_gap_b = _resolve_param('feed_inset_gap_b', 'FEED_INSET_GAP_B', None, custom_params, float)
        if feed_gap_b is None:
            feed_gap_b = _resolve_param('inset_gap_b', 'INSET_GAP_B', None, custom_params, float)
        if feed_gap_b is None:
            feed_gap_b = _resolve_param('feed_inset_gap', 'FEED_INSET_GAP', None, custom_params, float)

        feed_gap_l = _resolve_param('feed_inset_gap_l', 'FEED_INSET_GAP_L', None, custom_params, float)
        if feed_gap_l is None:
            feed_gap_l = _resolve_param('inset_gap_l', 'INSET_GAP_L', None, custom_params, float)
        if feed_gap_l is None:
            feed_gap_l = _resolve_param('feed_inset_gap', 'FEED_INSET_GAP', None, custom_params, float)

        params['feed_inset_b'] = feed_inset_b
        params['feed_inset_l'] = feed_inset_l
        params['inset_b'] = feed_inset_b
        params['inset_l'] = feed_inset_l
        if feed_gap_b is not None:
            params['inset_gap_b'] = feed_gap_b
        if feed_gap_l is not None:
            params['inset_gap_l'] = feed_gap_l

        driven_port = _resolve_param('driven_port', 'DRIVEN_PORT', 'all', custom_params, str)
        params['driven_port'] = driven_port

        # Explicitní délky přívodů (feed_len_b, feed_len_l, feed_delta_l)
        feed_len_b = _resolve_param('feed_len_b', 'FEED_LEN_B', None, custom_params, float)
        if feed_len_b is None:
            feed_len_b = _resolve_param('feed_length_b', 'FEED_LENGTH_B', None, custom_params, float)
        if feed_len_b is None:
            feed_len_b = _resolve_param('L_feed_b', 'L_FEED_B', None, custom_params, float)

        feed_len_l = _resolve_param('feed_len_l', 'FEED_LEN_L', None, custom_params, float)
        if feed_len_l is None:
            feed_len_l = _resolve_param('feed_length_l', 'FEED_LENGTH_L', None, custom_params, float)
        if feed_len_l is None:
            feed_len_l = _resolve_param('L_feed_l', 'L_FEED_L', None, custom_params, float)

        feed_delta_l = _resolve_param('feed_delta_l', 'FEED_DELTA_L', None, custom_params, float)
        if feed_delta_l is None:
            feed_delta_l = _resolve_param('delta_l', 'DELTA_L', None, custom_params, float)
        if feed_delta_l is None:
            feed_delta_l = _resolve_param('phase_delay_mm', 'PHASE_DELAY_MM', None, custom_params, float)

        if feed_len_b is not None:
            params['feed_len_b'] = feed_len_b
        if feed_len_l is not None:
            params['feed_len_l'] = feed_len_l
        if feed_delta_l is not None:
            params['feed_delta_l'] = feed_delta_l

        len_info = []
        if feed_len_b is not None:
            len_info.append(f"feed_len_b={feed_len_b:.2f}mm")
        if feed_len_l is not None:
            len_info.append(f"feed_len_l={feed_len_l:.2f}mm")
        if feed_delta_l is not None:
            len_info.append(f"delta_l={feed_delta_l:.2f}mm")
        len_str = f", {', '.join(len_info)}" if len_info else ""

        print(f"--- Model 2: Inset spodní (Ey) = {feed_inset_b:.2f} mm, Inset levý (Ex) = {feed_inset_l:.2f} mm, Buzení = {driven_port}{len_str} ---")

    else:
        # MODEL 1: Původní T-dělič a analytická napájecí síť
        feed_inset = _resolve_param('feed_inset', 'FEED_INSET', 0.0, custom_params, float)
        if feed_inset == 0.0:
            feed_inset = _resolve_param('inset', 'INSET', 0.0, custom_params, float)

        feed_inset_gap = _resolve_param('feed_inset_gap', 'FEED_INSET_GAP', None, custom_params, float)
        if feed_inset_gap is None:
            feed_inset_gap = _resolve_param('inset_gap', 'INSET_GAP', None, custom_params, float)

        feed_inset_width = _resolve_param('feed_inset_width', 'FEED_INSET_WIDTH', None, custom_params, float)
        if feed_inset_width is None:
            feed_inset_width = _resolve_param('inset_width', 'INSET_WIDTH', None, custom_params, float)

        from rf_calc import calc_feed_network_dimensions
        feed_net = calc_feed_network_dimensions(
            patch_w, patch_l, sub_h, eps_r,
            freq_ghz=DESIGN_FREQ_GHZ, port_z0=port_impedance, inset=feed_inset
        )
        params.update(feed_net)
        params['feed_inset'] = feed_inset
        params['inset'] = feed_inset
        if feed_inset_gap is not None:
            params['inset_gap'] = feed_inset_gap
        if feed_inset_width is not None:
            params['inset_width'] = feed_inset_width

        print(f"--- Model 1: L = {patch_l:.2f} mm, W = {patch_w:.2f} mm, Zanoření: {feed_inset:.2f} mm ---")

    run_name = None
    if custom_params:
        params.update(custom_params)
        run_name = custom_params.get('run_name') or "_".join([f"{k}={v}" for k, v in custom_params.items()])

    print("--- 1. Generování geometrie (OpenCASCADE) ---")
    build_model(params)
    
    # Export 3D modelu pro CAD
    step_file = "data/antenna_model.step"
    gmsh.write(step_file)
    print(f"Geometrie byla exportována do {step_file} pro případné zobrazení v CAD softwaru.")
    
    # 2D pohled shora na geometrii pomocí Matplotlib
    from visualization import plot_geometry
    plot_geometry(params, filename="data/geometry_iso.png")
    root_dir_pre, current_data_dir_pre = load_env()
    if os.path.abspath(current_data_dir_pre) != os.path.abspath(os.path.join(root_dir_pre, "data")):
        target_iso = os.path.join(current_data_dir_pre, "geometry_iso.png")
        if os.path.abspath(target_iso) != os.path.abspath("data/geometry_iso.png"):
            try:
                plot_geometry(params, filename=target_iso)
            except Exception:
                pass
    
    print("--- 2. Klasifikace domén a tvorba sítě (Gmsh) ---")
    assign_physical_groups_and_mesh(params)
    
    print("--- 3. Vytváření konfigurace pro Palace ---")
    build_palace_config(params)

    # Uložení aktuálních parametrů modelu do data/params.json
    root_dir, current_data_dir = load_env()
    target_param_files = [os.path.join(root_dir, "data", "params.json")]
    if os.path.abspath(current_data_dir) != os.path.abspath(os.path.join(root_dir, "data")):
        target_param_files.append(os.path.join(current_data_dir, "params.json"))

    try:
        def _to_json_val(val):
            if isinstance(val, (np.integer,)):
                return int(val)
            if isinstance(val, (np.floating,)):
                return float(val)
            if isinstance(val, np.ndarray):
                return val.tolist()
            if isinstance(val, dict):
                return {k: _to_json_val(v) for k, v in val.items()}
            if isinstance(val, (list, tuple)):
                return [_to_json_val(v) for v in val]
            return val

        serializable_params = {k: _to_json_val(v) for k, v in params.items() if not str(k).startswith('_')}
        for pfile in target_param_files:
            try:
                os.makedirs(os.path.dirname(pfile), exist_ok=True)
                with open(pfile, "w", encoding="utf-8") as pf:
                    json.dump(serializable_params, pf, indent=4)
                print(f"Parametry modelu byly uloženy do {pfile}")
            except Exception as e_pfile:
                print(f"Upozornění při ukládání {pfile}: {e_pfile}")
    except Exception as e:
        print(f"Upozornění při přípravě parametrů pro uložení: {e}")

    if skip_simulation:
        print("--- Hotovo: Geometrie, STEP CAD model, náhled a síť byly vygenerovány lokálně bez simulace v Dockeru. ---")
        return

    print("--- 4. Spuštění fyzikální simulace (Palace) ---")
    _, data_dir = load_env()
    output_dir = os.path.join(data_dir, "postpro")

    driven_mode = str(params.get('driven_port', os.getenv('DRIVEN_PORT', 'all'))).lower().strip()
    is_model_matrix = (
        antenna_model in (2, 3)
        and driven_mode in ('all', 'both', 'matrix', 'full', 's_matrix')
    )

    if is_model_matrix:
        print("--- Spouštím dvoukrokovou simulaci pro kompletní 2-portovou S-matici (Port 1 a Port 2) ---")

        # 1. KROK: Port 1 (spodní, Ey)
        print("\n>>> Krok 1/2: Simulace buzení Portu 1 (Spodní napaječ Ey, Port 2 = 100 Ω zátěž) <<<")
        params_p1 = dict(params)
        params_p1['driven_port'] = '1'
        build_palace_config(params_p1)

        try:
            run_palace()
        except Exception as e:
            print(f"Upozornění: Simulace Krok 1 (Port 1) selhala: {e}")
            return

        p1_dir = os.path.join(data_dir, "postpro_p1")
        if os.path.exists(p1_dir):
            shutil.rmtree(p1_dir, ignore_errors=True)
        copy_postpro_directory(output_dir, p1_dir)

        # 2. KROK: Port 2 (levý, Ex)
        print("\n>>> Krok 2/2: Simulace buzení Portu 2 (Levý napaječ Ex, Port 1 = 100 Ω zátěž) <<<")
        params_p2 = dict(params)
        params_p2['driven_port'] = '2'
        build_palace_config(params_p2)

        try:
            run_palace()
        except Exception as e:
            print(f"Upozornění: Simulace Krok 2 (Port 2) selhala: {e}")
            return

        p2_dir = os.path.join(data_dir, "postpro_p2")
        if os.path.exists(p2_dir):
            shutil.rmtree(p2_dir, ignore_errors=True)
        copy_postpro_directory(output_dir, p2_dir)

        # 3. KROK: Sloučení výstupů z obou kroků do kompletní 2-portové matice v data/postpro
        print("\n--- Sloučení výstupů z obou běhů do kompletní 2-portové S-matice ---")
        merge_two_port_simulations(p1_dir, p2_dir, output_dir)

        # Obnovení výchozí konfigurace config.json
        build_palace_config(params)

    else:
        # Běžný jednorázový běh (Model 1, nebo explicitně zadaný jeden port u Modelu 2 a 3)
        build_palace_config(params)
        try:
            run_palace()
        except Exception as e:
            print(f"Upozornění: Simulace Palace nebyla spuštěna: {e}")
            return

    # Propojení složky paraview na poslední iteraci, pokud Palace běžel v AMR režimu
    ensure_paraview_linked(data_dir)

    print("--- 5. Zpracování výsledků ---")
    
    # Zpracování výsledků podle modelu antény
    if antenna_model in (2, 3):
        _process_results_model2(params, output_dir, data_dir, run_name)
    else:
        _process_results_model1(params, output_dir, data_dir, run_name)

def _generate_advanced_plots(output_dir, data_dir):
    """Automatické generování grafu S-parametrů/impedance a 2D/3D vyzařovacích diagramů po každém kroku simulace."""
    params_for_deembed = None
    params_path = os.path.join(data_dir, "params.json")
    if os.path.exists(params_path):
        try:
            with open(params_path, "r", encoding="utf-8") as f:
                params_for_deembed = json.load(f)
        except Exception:
            pass

    # 1. Graf S-parametrů a impedance
    try:
        from plot_s_parameters import plot_s_parameters
        s_png_data = os.path.join(data_dir, "graf_S_parametry.png")
        s_png_post = os.path.join(output_dir, "graf_S_parametry.png")
        plot_s_parameters(output_dir, output_png=s_png_data, params=params_for_deembed)
        if os.path.abspath(s_png_data) != os.path.abspath(s_png_post) and os.path.exists(s_png_data):
            shutil.copy2(s_png_data, s_png_post)
    except Exception as e:
        print(f"Upozornění při automatickém generování grafu S-parametrů: {e}")

    # 2. 2D a 3D vyzařovací diagram (pokud existuje farfield-rE.csv)
    try:
        from plot_radiation_pattern import plot_radiation_pattern_2d, plot_radiation_pattern_3d
        ff_file = os.path.join(output_dir, "farfield-rE.csv")
        if os.path.exists(ff_file) and os.path.getsize(ff_file) > 0:
            rd_2d_data = os.path.join(data_dir, "vyzarovaci_diagram_2d.png")
            rd_2d_post = os.path.join(output_dir, "vyzarovaci_diagram_2d.png")
            rd_3d_data = os.path.join(data_dir, "vyzarovaci_diagram_3d.png")
            rd_3d_post = os.path.join(output_dir, "vyzarovaci_diagram_3d.png")
            
            plot_radiation_pattern_2d(output_dir, output_png=rd_2d_data)
            plot_radiation_pattern_3d(output_dir, output_png=rd_3d_data)
            
            if os.path.abspath(rd_2d_data) != os.path.abspath(rd_2d_post) and os.path.exists(rd_2d_data):
                shutil.copy2(rd_2d_data, rd_2d_post)
            if os.path.abspath(rd_3d_data) != os.path.abspath(rd_3d_post) and os.path.exists(rd_3d_data):
                shutil.copy2(rd_3d_data, rd_3d_post)
    except Exception as e:
        print(f"Upozornění při automatickém generování vyzařovacích diagramů: {e}")

    # 3. Graf de-embeddingu impedančních skoků (graf_impedance_skoky.png)
    try:
        from plot_deembedding import plot_impedance_deembedding
        deemb_png_data = os.path.join(data_dir, "graf_impedance_skoky.png")
        deemb_png_post = os.path.join(output_dir, "graf_impedance_skoky.png")

        plot_impedance_deembedding(output_dir, params=params_for_deembed, output_png=deemb_png_data)
        if os.path.abspath(deemb_png_data) != os.path.abspath(deemb_png_post) and os.path.exists(deemb_png_data):
            shutil.copy2(deemb_png_data, deemb_png_post)
    except Exception as e:
        print(f"Upozornění při automatickém generování grafu de-embeddingu impedance: {e}")

    # Synchronizace podsložek grafy/ a obrazky/ mezi data_dir a output_dir
    if os.path.abspath(data_dir) != os.path.abspath(output_dir):
        for subf in ["grafy", "obrazky"]:
            src_f = os.path.join(data_dir, subf)
            dst_f = os.path.join(output_dir, subf)
            if os.path.exists(src_f) and os.path.isdir(src_f):
                os.makedirs(dst_f, exist_ok=True)
                for item in os.listdir(src_f):
                    s_item = os.path.join(src_f, item)
                    d_item = os.path.join(dst_f, item)
                    if os.path.isfile(s_item):
                        try:
                            shutil.copy2(s_item, d_item)
                        except Exception:
                            pass

def _process_results_model1(params, output_dir, data_dir, run_name):
    s11_file = os.path.join(output_dir, "port-S.csv")
    if os.path.exists(s11_file) and os.path.getsize(s11_file) > 0:
        try:
            data_arr = np.loadtxt(s11_file, delimiter=',', skiprows=1)
            if data_arr.ndim == 1:
                data_arr = data_arr.reshape(1, -1)
            freqs = data_arr[:, 0]
            s11_db = data_arr[:, 1]
            
            plt.figure(figsize=(8, 6))
            plt.plot(freqs, s11_db, label='S11', color='navy', lw=2)
            plt.title('Činitel odrazu (S11) - Model 1 (LHCP Flíčková anténa s T-děličem)')
            plt.xlabel('Frekvence [GHz]')
            plt.ylabel('S11 [dB]')
            plt.grid(True)
            plt.axhline(-10, color='r', linestyle='--', label='Mez -10 dB')
            plt.legend()
            
            plot_path = os.path.join(data_dir, "S11_graf.png")
            plt.savefig(plot_path)
            plt.close()
            print(f"Graf byl úspěšně uložen do {plot_path}")
        except Exception as e:
            print(f"Upozornění při vykreslování S11 grafu: {e}")
            
        analyze_and_log_run(params, s11_file, run_name=run_name)
    else:
        print(f"Výstupní soubor {s11_file} nebyl nalezen. Simulace zřejmě selhala nebo byla zapsána jinam.")

    _generate_advanced_plots(output_dir, data_dir)

def _process_results_model2(params, output_dir, data_dir, run_name):
    from tracker import extract_s_parameters_model2
    s_params = extract_s_parameters_model2(output_dir, z0=100.0)
    
    if s_params and 'freqs' in s_params:
        try:
            freqs = s_params['freqs']
            s11_db = s_params.get('s11_db')
            s22_db = s_params.get('s22_db')
            s21_db = s_params.get('s21_db')
            s12_db = s_params.get('s12_db')

            plt.figure(figsize=(8, 6))
            if s11_db is not None:
                plt.plot(freqs, s11_db, label='S11 (Spodní port, Ey)', color='blue', lw=2)
            if s22_db is not None:
                plt.plot(freqs, s22_db, label='S22 (Levý port, Ex)', color='crimson', lw=2, linestyle='--')
            if s21_db is not None:
                plt.plot(freqs, s21_db, label='S21 (Vazba 1->2)', color='darkgreen', lw=1.5, linestyle=':')
            elif s12_db is not None:
                plt.plot(freqs, s12_db, label='S12 (Vazba 2->1)', color='darkgreen', lw=1.5, linestyle=':')
            plt.title(f'Činitele odrazu S11 a S22 - Model {params.get("antenna_model", 2)} (100 Ω LHCP)')
            plt.xlabel('Frekvence [GHz]')
            plt.ylabel('S-parametry [dB]')
            plt.grid(True)
            plt.axhline(-10, color='red', linestyle='--', lw=1.5, label='Mez -10 dB')
            plt.legend()

            plot_path = os.path.join(data_dir, "S_params_graf.png")
            plt.savefig(plot_path)
            # Kopie pro zpětnou kompatibilitu
            plt.savefig(os.path.join(data_dir, "S11_graf.png"))

            # Uložení do grafy/
            grafy_dir = os.path.join(data_dir, "grafy")
            os.makedirs(grafy_dir, exist_ok=True)
            plt.savefig(os.path.join(grafy_dir, "graf_S11_S22.png"))
            plt.close()
            print(f"Graf S11 a S22 byl úspěšně uložen do {plot_path}")
        except Exception as e:
            print(f"Upozornění při vykreslování S-parametrů grafu: {e}")

    # Záznam do tabulky Modelu
    dummy_csv = os.path.join(output_dir, "port-S.csv")
    analyze_and_log_run(params, dummy_csv, run_name=run_name)

    _generate_advanced_plots(output_dir, data_dir)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="LHCP Patch Antenna Simulation & CAD Model Generation")
    parser.add_argument("--model", type=int, choices=[1, 2, 3], default=None, dest="antenna_model",
                        help="Verze modelu antény: 1 (T-dělič 50 Ohm), 2 (dvouportový 100 Ohm LHCP), 3 (hybridní dvoustupňový). Výchozí: 1 nebo z ANTENNA_MODEL")
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
                        help="Délka flíčku patche v mm (výchozí: 30.3 pro M1, 28.8 pro M2/M3 nebo z PATCH_L)")
    parser.add_argument("--patch-w", type=float, default=None, dest="patch_W",
                        help="Šířka flíčku patche v mm (výchozí: z PATCH_W nebo rovno patch-l)")
    parser.add_argument("--inset", "--feed-inset", type=float, default=None, dest="feed_inset",
                        help="Hloubka zanoření napaječe do flíčku v mm (výchozí: 0.0 nebo z FEED_INSET)")
    parser.add_argument("--inset-b", type=float, default=None, dest="feed_inset_b",
                        help="Hloubka zanoření spodního napaječe pro Model 2 a 3 (výchozí: FEED_INSET_B nebo FEED_INSET)")
    parser.add_argument("--inset-l", type=float, default=None, dest="feed_inset_l",
                        help="Hloubka zanoření levého napaječe pro Model 2 a 3 (výchozí: FEED_INSET_L nebo FEED_INSET)")
    parser.add_argument("--inset-gap-b", type=float, default=None, dest="feed_inset_gap_b",
                        help="Šířka mezery zářezu spodního napaječe (výchozí: FEED_INSET_GAP_B)")
    parser.add_argument("--inset-gap-l", type=float, default=None, dest="feed_inset_gap_l",
                        help="Šířka mezery zářezu levého napaječe (výchozí: FEED_INSET_GAP_L)")
    parser.add_argument("--feed-len-b", "--feed-length-b", type=float, default=None, dest="feed_len_b",
                        help="Délka spodního přívodu pro Model 2 a 3 v mm (výchozí: z W_sub + lambda_g/4 nebo FEED_LEN_B)")
    parser.add_argument("--feed-len-l", "--feed-length-l", type=float, default=None, dest="feed_len_l",
                        help="Délka levého přívodu pro Model 2 a 3 v mm (výchozí: L_ref nebo FEED_LEN_L)")
    parser.add_argument("--feed-delta-l", "--delta-l", type=float, default=None, dest="feed_delta_l",
                        help="Rozdíl délek přívodů Delta L = L_feed_b - L_feed_l pro Model 2 a 3 v mm (výchozí: lambda_g/4 nebo FEED_DELTA_L)")
    parser.add_argument("--trans-w", "--w-t", "--w-trans", type=float, default=None, dest="trans_w",
                        help="Šířka čtvrtvlnného transformátoru pro Model 3 v mm (výchozí: 0.42 nebo TRANS_W)")
    parser.add_argument("--trans-l", "--l-t", "--l-trans", type=float, default=None, dest="trans_l",
                        help="Délka čtvrtvlnného transformátoru pro Model 3 v mm (výchozí: auto lambda_g/4 nebo TRANS_L)")
    parser.add_argument("--driven-port", type=str, default=None, dest="driven_port",
                        help="Volba buzeného portu pro Model 2 a 3: '1' (spodní), '2' (levý), 'all' (oba současně pro LHCP). Výchozí: all")

    args = parser.parse_args()

    cli_params = {}
    for param in ['antenna_model', 'freq_min', 'freq_max', 'freq_step', 'mesh_size_max', 'mesh_size_min', 'amr_max_its',
                  'amr_threshold', 'farfield_nsample', 'save_step', 'linear_tol', 'linear_max_its',
                  'patch_L', 'patch_W', 'feed_inset', 'feed_inset_b', 'feed_inset_l', 'feed_inset_gap_b', 'feed_inset_gap_l',
                  'feed_len_b', 'feed_len_l', 'feed_delta_l', 'trans_w', 'trans_l', 'driven_port']:
        val = getattr(args, param, None)
        if val is not None:
            cli_params[param] = val

    main(custom_params=cli_params if cli_params else None, skip_simulation=args.skip_simulation, clean=args.clean)
