import os
import time
import numpy as np
from main import main
from rf_calc import synth_square_patch_size, DESIGN_FREQ_GHZ

# Výchozí parametry substrátu pro analytický odhad rezonance
DEFAULT_SUB_H = 1.52
DEFAULT_EPS_R = 4.3

def generate_sweep_patch_lengths(center_freq=DESIGN_FREQ_GHZ, h=DEFAULT_SUB_H, eps_r=DEFAULT_EPS_R, span_mm=1.6, num_points=5):
    """
    Dynamicky generuje pole rozměrů flíčku symetricky kolem rezonance L0 +/- delta_L.
    """
    env_l = os.getenv('PATCH_L')
    if env_l is not None:
        try:
            l0 = float(env_l)
        except ValueError:
            l0 = synth_square_patch_size(center_freq, h, eps_r)
    else:
        l0 = synth_square_patch_size(center_freq, h, eps_r)
    half_span = span_mm / 2.0
    lengths = np.linspace(l0 - half_span, l0 + half_span, num_points)
    return [float(np.round(l, 2)) for l in lengths]

def run_sweep(patch_lengths=None):
    # Dynamicky generované hodnoty délky patche kolem analytické rezonance L0
    if patch_lengths is None:
        patch_lengths = generate_sweep_patch_lengths()
    
    print("==================================================")
    print("Zahajuji parametrický sweep pro patch_L")
    print(f"Hodnoty k testování: {patch_lengths}")
    print("==================================================")
    
    for i, length in enumerate(patch_lengths):
        print(f"\n[{i+1}/{len(patch_lengths)}] Spouštím simulaci pro patch_L = {length} mm")
        
        custom_params = {
            'patch_L': length,
            # Během sweepu můžeme měnit i další parametry, pokud chceme (např. 'patch_W': length, pro zachování čtverce)
            'patch_W': length 
        }
        
        try:
            # Zavolá hlavní simulační pipeline s vlastními parametry
            main(custom_params=custom_params)
            
            # Pauza pro přehlednost (volitelné)
            time.sleep(2)
        except Exception as e:
            print(f"Při běhu s patch_L={length} došlo k chybě: {e}")

    print("\n==================================================")
    print("Sweep dokončen! Výsledky jsou uloženy a zalogovány v MLflow.")
    print("Pro zobrazení dashboardu spusťte v terminálu příkaz: mlflow ui")
    print("==================================================")

if __name__ == "__main__":
    run_sweep()
