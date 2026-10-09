from paraview.simple import *
import os

def setup_scene():
    # Cesta k simulovanému VTU souboru
    # (Předpokládáme spuštění přímo z kořenové složky 'anteny', jinak upravte absolutní cestu)
    current_dir = os.getcwd()
    vtu_file = os.path.join(current_dir, "postpro", "paraview", "driven", "driven_000000001.vtu")
    
    if not os.path.exists(vtu_file):
        print(f"[CHYBA] Soubor {vtu_file} nebyl nalezen.")
        print("Ujistěte se, že spouštíte makro z hlavního adresáře 'anteny'.")
        return

    print(f"Načítám data: {vtu_file}")
    
    # 1. Odstraníme starou scénu
    Clear()
    renderView1 = GetActiveViewOrCreate('RenderView')
    
    # 2. Načtení pole z Palace
    driven_vtu = XMLUnstructuredGridReader(registrationName='Palace_Field', FileName=[vtu_file])
    
    # 3. Zobrazit obálku modelu s velkou průhledností
    display_model = Show(driven_vtu, renderView1, 'UnstructuredGridRepresentation')
    display_model.Representation = 'Surface'
    display_model.Opacity = 0.1
    
    # 4. Vytvoření řezu (Slice) na rozhraní substrát-vzduch (z = 1.52 mm)
    slice_patch = Slice(registrationName='Slice_Patch', Input=driven_vtu)
    slice_patch.SliceType = 'Plane'
    slice_patch.SliceOffsetValues = [0.0]
    
    # Normála kolmo nahoru, výška na hranici FR4 v metrech (1.52 mm = 0.00152 m)
    slice_patch.SliceType.Origin = [0.0, 0.0, 0.00152]
    slice_patch.SliceType.Normal = [0.0, 0.0, 1.0]
    
    display_slice = Show(slice_patch, renderView1, 'GeometryRepresentation')
    
    # 5. Obarvení podle pole (např. E_real)
    ColorBy(display_slice, ('POINTS', 'E_real', 'Magnitude'))
    
    # 6. Nastavení barevné škály (Jet nebo Cool to Warm)
    e_realLUT = GetColorTransferFunction('E_real')
    e_realLUT.ApplyPreset('Cool to Warm', True)
    
    # Zapnout legendu (Color Bar)
    display_slice.SetScalarBarVisibility(renderView1, True)
    
    # 7. Vykreslení vektorů (Glyph) - elektrické pole
    glyph1 = Glyph(registrationName='E_Vectors', Input=slice_patch)
    glyph1.GlyphType = 'Arrow'
    glyph1.OrientationArray = ['POINTS', 'E_real']
    glyph1.ScaleArray = ['POINTS', 'E_real']
    glyph1.ScaleFactor = 1.0 # Bude nutné upravit podle reálné velikosti E
    glyph1.GlyphMode = 'All Points'
    
    display_glyph = Show(glyph1, renderView1, 'GeometryRepresentation')
    ColorBy(display_glyph, ('POINTS', 'E_real', 'Magnitude'))
    
    # Skryjeme vektory ve výchozím stavu (uživatel si je může zapnout)
    Hide(glyph1, renderView1)
    
    # 8. Reset kamery a vykreslení
    renderView1.ResetCamera()
    renderView1.Update()
    
    print("==================================================")
    print("Scéna byla úspěšně připravena!")
    print("- Byla načtena síť.")
    print("- Byl vytvořen řez (Slice) na z=1.52 (Substrát).")
    print("- Pole E_real bylo obarveno 'Cool to Warm'.")
    print("- Ve stromečku máte připravené vektory (Glyph) ke skrytému zobrazení.")
    print("==================================================")

if __name__ == "__main__":
    setup_scene()
