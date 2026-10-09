import skrf as rf
import numpy as np
import os
import matplotlib.pyplot as plt

try:
    import mlflow
except ImportError:
    mlflow = None

# Konstanty pro vyhodnocení parametrů
S11_BW_THRESHOLD_DB = -10.0
GHZ_TO_MHZ = 1000.0
SDARS_FREQ_MIN_GHZ = 2.320
SDARS_FREQ_MAX_GHZ = 2.345

def analyze_and_log_run(params, csv_filepath, run_name=None):
    if mlflow is None:
        print("MLflow Tracker: Balíček 'mlflow' není nainstalován. Logování přeskočeno.")
        return

    if not os.path.exists(csv_filepath):
        print(f"MLflow Tracker: Soubor {csv_filepath} nenalezen, nelze zalogovat.")
        return

    # Načtení dat z CSV (Palace formát) nebo Touchstone souboru
    if csv_filepath.endswith('.s1p'):
        nw = rf.Network(csv_filepath)
        freqs = nw.f / 1e9
        s11_db = nw.s_db[:, 0, 0]
    else:
        data = np.loadtxt(csv_filepath, delimiter=',', skiprows=1)
        freqs = data[:, 0]
        s11_db = data[:, 1]

    # Výpočet metrik
    min_idx = np.argmin(s11_db)
    f0 = freqs[min_idx]
    s11_min = s11_db[min_idx]

    # Hledání šířky pásma pod -10 dB s interpolací a kontrolou mezí
    bw_mhz = 0.0
    covers_band = False
    
    if s11_min <= S11_BW_THRESHOLD_DB:
        f_low = None
        f_high = None
        
        for i in range(min_idx, 0, -1):
            if s11_db[i] <= S11_BW_THRESHOLD_DB and s11_db[i-1] > S11_BW_THRESHOLD_DB:
                f_low = freqs[i-1] + (S11_BW_THRESHOLD_DB - s11_db[i-1]) * (freqs[i] - freqs[i-1]) / (s11_db[i] - s11_db[i-1])
                break
                
        for i in range(min_idx, len(freqs)-1):
            if s11_db[i] <= S11_BW_THRESHOLD_DB and s11_db[i+1] > S11_BW_THRESHOLD_DB:
                f_high = freqs[i] + (S11_BW_THRESHOLD_DB - s11_db[i]) * (freqs[i+1] - freqs[i]) / (s11_db[i+1] - s11_db[i])
                break
                
        # Pokud oba průchody existují uvnitř simulačního okna, spočteme šířku pásma
        if f_low is not None and f_high is not None:
            bw_mhz = (f_high - f_low) * GHZ_TO_MHZ
            # Kritérium: pásmo SDARS 2.320 GHz až 2.345 GHz musí být celé pokryto pod -10 dB
            covers_band = bool(f_low <= SDARS_FREQ_MIN_GHZ and f_high >= SDARS_FREQ_MAX_GHZ)
        else:
            # Rezonance dosahuje na okraj sweepu bez plného uzavření pod -10 dB
            bw_mhz = 0.0
            covers_band = False

    # Logování do MLflow
    print(f"MLflow Tracker: Loguji běh do databáze...")
    mlflow.set_experiment("Antenna_Patch_Sweep")
    
    with mlflow.start_run(run_name=run_name):
        # Zalogování parametrů
        mlflow.log_params(params)
        
        # Zalogování metrik
        mlflow.log_metric("f_resonance_GHz", float(f0))
        mlflow.log_metric("S11_min_dB", float(s11_min))
        mlflow.log_metric("Bandwidth_MHz", float(bw_mhz))
        mlflow.log_metric("Covers_S_Band", int(covers_band))
        
        # Zalogování celé křivky S11 do historie metrik a uložení výstupu jako artefaktu
        for f_val, s_val in zip(freqs, s11_db):
            # MLflow uses steps, we will use MHz for granularity
            mlflow.log_metric("S11_Curve_dB", float(s_val), step=int(round(f_val * GHZ_TO_MHZ)))
            
        mlflow.log_artifact(csv_filepath, "S-Parameters")
        
        # Záchyt obrázku (pokud existuje graf)
        plot_path = "data/S11_graf.png"
        if os.path.exists(plot_path):
            mlflow.log_artifact(plot_path, "Plots")

    print(f"MLflow Tracker: Běh uložen (f0={f0:.3f} GHz, minS11={s11_min:.1f} dB).")
