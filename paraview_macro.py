from paraview.simple import *
import os

# Cesta k hlavnimu adresari projektu (lze upravit podle vaseho umisteni)
PROJECT_DIR = r"D:\code\anteny"

def setup_scene():
    # Zmena soucasneho pracovniho adresare do adresare projektu
    target_dir = PROJECT_DIR
    if not os.path.exists(target_dir):
        # Fallback pokud je skript spousten z korene projektu
        if os.path.exists(os.path.join(os.getcwd(), "postpro")):
            target_dir = os.getcwd()
        elif "__file__" in globals() and os.path.exists(os.path.join(os.path.dirname(__file__), "postpro")):
            target_dir = os.path.dirname(__file__)

    if os.path.exists(target_dir):
        os.chdir(target_dir)
        print(f"Pracovni adresar nastaven na: {target_dir}")
    else:
        print(f"[CHYBA] Adresar projektu nebyl nalezen: {PROJECT_DIR}")
        print("Zkontrolujte prosim nastaveni promenne PROJECT_DIR v makru.")
        return

    # Cesta k simulovanemu VTU souboru
    current_dir = os.getcwd()
    driven_dir = os.path.join(current_dir, "postpro", "paraview", "driven")
    vtu_file = os.path.join(driven_dir, "driven_000000001.vtu")
    if not os.path.exists(vtu_file) and os.path.isdir(driven_dir):
        vtu_candidates = [f for f in os.listdir(driven_dir) if f.endswith(".vtu")]
        if vtu_candidates:
            vtu_file = os.path.join(driven_dir, sorted(vtu_candidates)[-1])
    
    if not os.path.exists(vtu_file):
        print(f"[CHYBA] Soubor {vtu_file} nebyl nalezen.")
        print(f"Ujistete se, ze existuji vystupni data simulace ve slozce '{driven_dir}'.")
        return

    print(f"Nacitam data: {vtu_file}")
    
    # 1. Odstranime predchozi objekty pokud jiz ve scene existuji
    for src in list(GetSources().values()):
        try:
            Delete(src)
        except Exception:
            pass
            
    renderView1 = GetActiveViewOrCreate('RenderView')
    
    # 2. Nacteni pole z Palace
    driven_vtu = XMLUnstructuredGridReader(registrationName='Palace_Field', FileName=[vtu_file])
    
    # 3. Zobrazit obalku modelu s velkou pruhlednosti
    display_model = Show(driven_vtu, renderView1, 'UnstructuredGridRepresentation')
    display_model.Representation = 'Surface'
    display_model.Opacity = 0.1
    
    # 4. Vytvoreni rezu (Slice) na rozhrani substrat-vzduch (dynamicky podle config.json)
    sub_h_mm = 1.52  # Vychozi hodnota pro FR4
    config_file = os.path.join(current_dir, "config.json")
    if os.path.exists(config_file):
        try:
            import json
            with open(config_file, "r") as f:
                cfg = json.load(f)
                if "_Metadata" in cfg and "sub_h" in cfg["_Metadata"]:
                    sub_h_mm = float(cfg["_Metadata"]["sub_h"])
        except Exception as e:
            print(f"Nelze nacist sub_h z config.json: {e}")

    sub_h_m = sub_h_mm * 1e-3  # Prepocet mm na metry
    slice_patch = Slice(registrationName='Slice_Patch', Input=driven_vtu)
    slice_patch.SliceType = 'Plane'
    slice_patch.SliceOffsetValues = [0.0]
    
    # Normala kolmo nahoru, vyska na hranici FR4 v metrech
    slice_patch.SliceType.Origin = [0.0, 0.0, sub_h_m]
    slice_patch.SliceType.Normal = [0.0, 0.0, 1.0]
    
    display_slice = Show(slice_patch, renderView1, 'GeometryRepresentation')
    
    # 5. Obarveni podle pole (napr. E_real)
    ColorBy(display_slice, ('POINTS', 'E_real', 'Magnitude'))
    
    # 6. Nastaveni barevne skaly (Jet nebo Cool to Warm)
    e_realLUT = GetColorTransferFunction('E_real')
    e_realLUT.ApplyPreset('Cool to Warm', True)
    
    # Zapnout legendu (Color Bar)
    display_slice.SetScalarBarVisibility(renderView1, True)
    
    # 7. Vykresleni vektoru (Glyph) - elektricke pole
    glyph1 = Glyph(registrationName='E_Vectors', Input=slice_patch)
    glyph1.GlyphType = 'Arrow'
    glyph1.OrientationArray = ['POINTS', 'E_real']
    glyph1.ScaleArray = ['POINTS', 'E_real']
    glyph1.ScaleFactor = 1.0 # Bude nutne upravit podle realne velikosti E
    glyph1.GlyphMode = 'All Points'
    
    display_glyph = Show(glyph1, renderView1, 'GeometryRepresentation')
    ColorBy(display_glyph, ('POINTS', 'E_real', 'Magnitude'))
    
    # Skryjeme vektory ve vychozim stavu (uzivatel si je muze zapnout)
    Hide(glyph1, renderView1)
    
    # 8. Reset kamery a vykresleni
    renderView1.ResetCamera()
    renderView1.Update()
    
    print("==================================================")
    print("Scena byla uspesne pripravena!")
    print("- Byla nactena sit.")
    print(f"- Byl vytvoren rez (Slice) na z={sub_h_mm} mm (Substrat).")
    print("- Pole E_real bylo obarveno 'Cool to Warm'.")
    print("- Ve stromecku mate pripravene vektory (Glyph) ke skrytemu zobrazeni.")
    print("==================================================")

# Spusteni sceny automaticky pri zavolani skriptu
setup_scene()
