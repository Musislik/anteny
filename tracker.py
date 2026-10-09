import skrf as rf
import numpy as np
import os
import matplotlib.pyplot as plt

try:
    import mlflow
except ImportError:
    mlflow = None

def analyze_and_log_run(params, s1p_filepath):
    if mlflow is None:
        print("MLflow Tracker: Balíček 'mlflow' není nainstalován. Logování přeskočeno.")
        return

    if not os.path.exists(s1p_filepath):
        print(f"MLflow Tracker: Soubor {s1p_filepath} nenalezen, nelze zalogovat.")
        return

    # Načtení dat z CSV (Palace formát)
    data = np.loadtxt(s1p_filepath, delimiter=',', skiprows=1)
    freqs = data[:, 0]
    s11_db = data[:, 1]

    # Výpočet metrik
    min_idx = np.argmin(s11_db)
    f0 = freqs[min_idx]
    s11_min = s11_db[min_idx]

    # Hledání šířky pásma pod -10 dB s interpolací a spojitostí
    bw_mhz = 0.0
    covers_band = False
    
    if s11_min <= -10:
        f_low = freqs[0]
        f_high = freqs[-1]
        
        for i in range(min_idx, 0, -1):
            if s11_db[i] <= -10 and s11_db[i-1] > -10:
                f_low = freqs[i-1] + (-10 - s11_db[i-1]) * (freqs[i] - freqs[i-1]) / (s11_db[i] - s11_db[i-1])
                break
                
        for i in range(min_idx, len(freqs)-1):
            if s11_db[i] <= -10 and s11_db[i+1] > -10:
                f_high = freqs[i] + (-10 - s11_db[i]) * (freqs[i+1] - freqs[i]) / (s11_db[i+1] - s11_db[i])
                break
                
        bw_mhz = (f_high - f_low) * 1000
        # Check if resonance is near 2.33 and inside the band
        covers_band = bool(f_low <= 2.330 and f_high >= 2.330)

    # Logování do MLflow
    print(f"MLflow Tracker: Loguji běh do databáze...")
    mlflow.set_experiment("Antenna_Patch_Sweep")
    
    with mlflow.start_run():
        # Zalogování parametrů
        mlflow.log_params(params)
        
        # Zalogování metrik
        mlflow.log_metric("f_resonance_GHz", float(f0))
        mlflow.log_metric("S11_min_dB", float(s11_min))
        mlflow.log_metric("Bandwidth_MHz", float(bw_mhz))
        mlflow.log_metric("Covers_S_Band", int(covers_band))
        
        # Zalogování celé křivky S11 do historie metrik a uložení s1p jako artefaktu
        for f_val, s_val in zip(freqs, s11_db):
            # MLflow uses steps, we will use MHz for granularity
            mlflow.log_metric("S11_Curve_dB", float(s_val), step=int(round(f_val * 1000)))
            
        mlflow.log_artifact(s1p_filepath, "S-Parameters")
        
        # Záchyt obrázku (pokud existuje graf)
        if os.path.exists("S11_graf.png"):
            mlflow.log_artifact("S11_graf.png", "Plots")

    print(f"MLflow Tracker: Běh uložen (f0={f0:.3f} GHz, minS11={s11_min:.1f} dB).")
