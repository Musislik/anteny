from paraview.simple import *
import os
import sys
import json

import _env
from postpro_utils import load_env, ensure_paraview_linked

def setup_scene():
    root_dir, data_dir = load_env()
    os.chdir(root_dir)
    ensure_paraview_linked(data_dir)

    # Cesta k simulovanému PVD souboru přímo z DATA_DIR
    boundary_pvd = os.path.join(data_dir, "postpro", "paraview", "driven_boundary", "driven_boundary.pvd")
    domain_pvd = os.path.join(data_dir, "postpro", "paraview", "driven", "driven.pvd")

    pvd_file = None
    if os.path.exists(boundary_pvd):
        pvd_file = boundary_pvd
    elif os.path.exists(domain_pvd):
        pvd_file = domain_pvd

    if not pvd_file:
        print(f"[CHYBA] Soubor driven_boundary.pvd nebyl nalezen v {data_dir}/postpro/paraview.")
        print("Ujistěte se, že existují výstupní data simulace a že je správně nastaven DATA_DIR v .env.")
        return

    # 1. Kompletni reset ParaView session (vymaze pamet, starou pipeline a uvolni cache pro nacteni novych dat)
    ResetSession()
    renderView1 = GetActiveViewOrCreate('RenderView')
    
    # 2. Nacteni pole z Palace / simulace
    print(f"Nacitam PVD casovou radu: {pvd_file}")
    driven_vtu = PVDReader(registrationName='Palace_Field', FileName=pvd_file)

    # 3. Zobrazit obrysovou krabici (Domain Bounding Box) pro 3D orientaci
    domain_box = Outline(registrationName='Domain_Box', Input=driven_vtu)
    disp_box = Show(domain_box, renderView1, 'GeometryRepresentation')
    disp_box.DiffuseColor = [0.45, 0.45, 0.45]
    
    # 4. Vytvoreni horizontalniho rezu v rovine patche (z = sub_h)
    sub_h_mm = 1.52  # Vychozi hodnota pro FR4
    config_file = os.path.join(data_dir, "config.json")
    if not os.path.exists(config_file):
        config_file = os.path.join(root_dir, "config.json")
    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                cfg = json.load(f)
                if "_Metadata" in cfg and "sub_h" in cfg["_Metadata"]:
                    sub_h_mm = float(cfg["_Metadata"]["sub_h"])
        except Exception as e:
            print(f"Nelze nacist sub_h z config.json: {e}")

    sub_h_m = sub_h_mm * 1e-3  # Prepocet mm na metry
    slice_patch = Slice(registrationName='Slice_Patch_XY', Input=driven_vtu)
    slice_patch.SliceType = 'Plane'
    slice_patch.SliceOffsetValues = [0.0]
    slice_patch.SliceType.Origin = [0.0, 0.0, sub_h_m]
    slice_patch.SliceType.Normal = [0.0, 0.0, 1.0]
    
    disp_slice = Show(slice_patch, renderView1, 'GeometryRepresentation')
    disp_slice.Representation = 'Surface'
    
    # 5. Obarveni podle intenzity pole (|E_real|)
    ColorBy(disp_slice, ('POINTS', 'E_real', 'Magnitude'))
    e_realLUT = GetColorTransferFunction('E_real')
    e_realLUT.ApplyPreset('Cool to Warm', True)
    
    # Nastaveni legendy (Color Bar)
    sb = GetScalarBar(e_realLUT, renderView1)
    sb.Title = '|E| [V/m]'
    sb.ComponentTitle = 'Intenzita pole'
    sb.Visibility = 1
    sb.WindowLocation = 'Lower Right Corner'
    
    # 6. Vertikalni rez (Slice_Cut_XZ) pro zobrazeni vyzarovani do vzduchu (vychozi skryty)
    slice_xz = Slice(registrationName='Slice_Cut_XZ', Input=driven_vtu)
    slice_xz.SliceType = 'Plane'
    slice_xz.SliceType.Origin = [0.0, 0.0, 0.0]
    slice_xz.SliceType.Normal = [0.0, 1.0, 0.0]
    disp_xz = Show(slice_xz, renderView1, 'GeometryRepresentation')
    disp_xz.Representation = 'Surface'
    ColorBy(disp_xz, ('POINTS', 'E_real', 'Magnitude'))
    Hide(slice_xz, renderView1)
    
    # 7. Vektorove sipky (E_Vectors) - pripraveny s korektnim meritkem (skryte ve vychozim stavu)
    glyph1 = Glyph(registrationName='E_Vectors', Input=slice_patch)
    glyph1.GlyphType = 'Arrow'
    glyph1.OrientationArray = ['POINTS', 'E_real']
    glyph1.ScaleArray = ['POINTS', 'E_real']
    glyph1.ScaleFactor = 0.000006  # Rozumne meritko v metrech odpovidajici poli ~3000 V/m
    glyph1.GlyphMode = 'Every Nth Point'
    glyph1.Stride = 4
    
    disp_glyph = Show(glyph1, renderView1, 'GeometryRepresentation')
    ColorBy(disp_glyph, ('POINTS', 'E_real', 'Magnitude'))
    Hide(glyph1, renderView1)
    
    # 8. Aktivnim objektem ucinime rez s intenzitou (Slice_Patch_XY)
    Show(slice_patch, renderView1)
    SetActiveSource(slice_patch)
    
    # 9. Nastaveni izometrickeho uhlu kamery
    renderView1.ResetCamera()
    renderView1.CameraPosition = [0.08, -0.15, 0.12]
    renderView1.CameraFocalPoint = [0.0, 0.0, sub_h_m]
    renderView1.CameraViewUp = [-0.3, 0.5, 0.8]
    renderView1.Update()
    
    print("==================================================")
    print("Scena byla uspesne pripravena pro zobrazeni intenzity E-pole!")
    print(f"- [Aktivni] Slice_Patch_XY: Rez v rovine patche (z={sub_h_mm} mm) - intenzita pole")
    print("- [Skryto]  Slice_Cut_XZ:   Vertikalni rez vyzarovani do vzduchu (kliknete na oko)")
    print("- [Skryto]  E_Vectors:      Vektorove sipky s korektnim meritkem (kliknete na oko)")
    print("- [Skryto]  Domain_Box:     3D obrys vypocetni oblasti")
    print("==================================================")

# Spusteni sceny automaticky pri zavolani skriptu
setup_scene()
