from paraview.simple import *
import os
import json

import _env  # noqa: F401
from postpro_utils import load_env, ensure_paraview_linked

def setup_scene():
    root_dir, data_dir = load_env()
    os.chdir(root_dir)
    ensure_paraview_linked(data_dir)

    # Path to simulated PVD file directly from DATA_DIR
    boundary_pvd = os.path.join(data_dir, "postpro", "paraview", "driven_boundary", "driven_boundary.pvd")
    domain_pvd = os.path.join(data_dir, "postpro", "paraview", "driven", "driven.pvd")

    pvd_file = None
    if os.path.exists(boundary_pvd):
        pvd_file = boundary_pvd
    elif os.path.exists(domain_pvd):
        pvd_file = domain_pvd

    if not pvd_file:
        print(f"[ERROR] File driven_boundary.pvd was not found in {data_dir}/postpro/paraview.")
        print("Verify that simulation output data exists and DATA_DIR is properly set in .env.")
        return

    # 1. Full ParaView session reset (clears memory, old pipeline, and cache to load fresh data)
    ResetSession()
    renderView1 = GetActiveViewOrCreate('RenderView')
    
    # 2. Load field data from Palace / simulation
    print(f"Loading PVD time series: {pvd_file}")
    driven_vtu = PVDReader(registrationName='Palace_Field', FileName=pvd_file)

    # 3. Display Domain Bounding Box for 3D orientation
    domain_box = Outline(registrationName='Domain_Box', Input=driven_vtu)
    disp_box = Show(domain_box, renderView1, 'GeometryRepresentation')
    disp_box.DiffuseColor = [0.45, 0.45, 0.45]
    
    # 4. Create horizontal slice in the patch plane (z = sub_h)
    sub_h_mm = 1.52  # Default value for FR4
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
            print(f"Unable to load sub_h from config.json: {e}")

    sub_h_m = sub_h_mm * 1e-3  # Convert mm to meters
    slice_patch = Slice(registrationName='Slice_Patch_XY', Input=driven_vtu)
    slice_patch.SliceType = 'Plane'
    slice_patch.SliceOffsetValues = [0.0]
    slice_patch.SliceType.Origin = [0.0, 0.0, sub_h_m]
    slice_patch.SliceType.Normal = [0.0, 0.0, 1.0]
    
    disp_slice = Show(slice_patch, renderView1, 'GeometryRepresentation')
    disp_slice.Representation = 'Surface'
    
    # 5. Color by field intensity (|E_real|)
    ColorBy(disp_slice, ('POINTS', 'E_real', 'Magnitude'))
    e_realLUT = GetColorTransferFunction('E_real')
    e_realLUT.ApplyPreset('Cool to Warm', True)
    
    # Configure Color Bar legend
    sb = GetScalarBar(e_realLUT, renderView1)
    sb.Title = '|E| [V/m]'
    sb.ComponentTitle = 'Field Intensity'
    sb.Visibility = 1
    sb.WindowLocation = 'Lower Right Corner'
    
    # 6. Vertical slice (Slice_Cut_XZ) to visualize air radiation (hidden by default)
    slice_xz = Slice(registrationName='Slice_Cut_XZ', Input=driven_vtu)
    slice_xz.SliceType = 'Plane'
    slice_xz.SliceType.Origin = [0.0, 0.0, 0.0]
    slice_xz.SliceType.Normal = [0.0, 1.0, 0.0]
    disp_xz = Show(slice_xz, renderView1, 'GeometryRepresentation')
    disp_xz.Representation = 'Surface'
    ColorBy(disp_xz, ('POINTS', 'E_real', 'Magnitude'))
    Hide(slice_xz, renderView1)
    
    # 7. Vector arrows (E_Vectors) - configured with proper scale (hidden by default)
    glyph1 = Glyph(registrationName='E_Vectors', Input=slice_patch)
    glyph1.GlyphType = 'Arrow'
    glyph1.OrientationArray = ['POINTS', 'E_real']
    glyph1.ScaleArray = ['POINTS', 'E_real']
    glyph1.ScaleFactor = 0.000006  # Reasonable scale in meters for ~3000 V/m field
    glyph1.GlyphMode = 'Every Nth Point'
    glyph1.Stride = 4
    
    disp_glyph = Show(glyph1, renderView1, 'GeometryRepresentation')
    ColorBy(disp_glyph, ('POINTS', 'E_real', 'Magnitude'))
    Hide(glyph1, renderView1)
    
    # 8. Set intensity slice (Slice_Patch_XY) as active object
    Show(slice_patch, renderView1)
    SetActiveSource(slice_patch)
    
    # 9. Set isometric camera angle
    renderView1.ResetCamera()
    renderView1.CameraPosition = [0.08, -0.15, 0.12]
    renderView1.CameraFocalPoint = [0.0, 0.0, sub_h_m]
    renderView1.CameraViewUp = [-0.3, 0.5, 0.8]
    renderView1.Update()
    
    print("==================================================")
    print("Scene successfully prepared for E-field intensity visualization!")
    print(f"- [Active] Slice_Patch_XY: Patch-plane slice (z={sub_h_mm} mm) - field intensity")
    print("- [Hidden] Slice_Cut_XZ:   Vertical radiation slice in air (click eye icon)")
    print("- [Hidden] E_Vectors:      Vector arrows with proper scaling (click eye icon)")
    print("- [Hidden] Domain_Box:     3D computational domain outline")
    print("==================================================")

# Run scene setup automatically when script is invoked
setup_scene()
