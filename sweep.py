import time
from main import main

def run_sweep():
    # Zvolené hodnoty délky patche pro parametrický sweep
    patch_lengths = [30.0, 30.4, 30.8, 31.2, 31.6]
    
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
