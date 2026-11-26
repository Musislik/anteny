"""
ParaView macro for real-time DYNAMIC phase animation with an INTERACTIVE FREQUENCY SLIDER.

Features:
1. Interactive on-screen slider for smooth frequency selection (2.320 - 2.345 GHz).
2. Continuous phase rotation (0 deg to 360 deg) by pressing PLAY on the top toolbar.
3. All calculations performed dynamically in GPU memory without writing any files to disk.

Run in ParaView:
    Tools -> Python Shell -> Run Script -> select this file
"""

import os
import vtk
from paraview.simple import *

try:
    import _env  # noqa: F401
    from postpro_utils import get_driven_boundary_pvd
except ImportError:
    def get_driven_boundary_pvd(caller_file=None):
        script_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
        local_pvd = os.path.join(script_dir, "driven_boundary", "driven_boundary.pvd")
        return os.path.abspath(local_pvd) if os.path.exists(local_pvd) else None

# Global reference to prevent Python from garbage-collecting the slider widget
_GLOBAL_FREQUENCY_SLIDER = None

def setup_dynamic_phase_scene():
    global _GLOBAL_FREQUENCY_SLIDER

    pvd_file = get_driven_boundary_pvd(caller_file=__file__ if "__file__" in globals() else None)
    if not pvd_file or not os.path.exists(pvd_file):
        print("[ERROR] File driven_boundary.pvd was not found.")
        print("Check DATA_DIR in .env or verify that the driven_boundary folder exists.")
        return

    print(f"--- 1. Loading frequency dataset: {pvd_file} ---")
    view = GetActiveViewOrCreate('RenderView')

    # Load dataset for all frequencies
    reader = PVDReader(registrationName='Palace_Frequency_Data', FileName=pvd_file)
    reader.UpdatePipelineInformation()
    reader.UpdatePipeline()

    raw_timesteps = getattr(reader, "TimestepValues", None)
    try:
        freqs = sorted({float(f) for f in raw_timesteps}) if raw_timesteps else []
    except TypeError:
        freqs = []

    if len(freqs) >= 2:
        default_freq = freqs[len(freqs) // 2]
        f_min = min(freqs)
        f_max = max(freqs)
    elif len(freqs) == 1:
        default_freq = freqs[0]
        f_min = default_freq - 0.005
        f_max = default_freq + 0.005
    else:
        default_freq = 2.330
        f_min = 2.320
        f_max = 2.345

    # Filter to select and lock a specific frequency
    print(f"--- 2. Creating frequency selector (ForceTime, default {default_freq:.3f} GHz) ---")
    ft = ForceTime(registrationName='Selected_Frequency_GHz', Input=reader)
    ft.ForcedTime = default_freq
    ft.UpdateVTKObjects()
    ft.UpdatePipeline()

    # Dynamic calculator for instantaneous field E(t)
    print("--- 3. Setting up dynamic phasor calculator ---")
    calc = Calculator(registrationName='E_Phase_Calculator', Input=ft)
    calc.ResultArrayName = 'E_phase'
    calc.Function = 'E_real'
    calc.UpdateVTKObjects()
    calc.UpdatePipeline()

    # Surface rendering with E_phase colormap
    disp_surf = Show(calc, view, 'GeometryRepresentation')
    disp_surf.Representation = 'Surface'
    ColorBy(disp_surf, ('POINTS', 'E_phase', 'Magnitude'))

    lut = GetColorTransferFunction('E_phase')
    lut.ApplyPreset('Turbo', True)
    # Scale up to 31,000 V/m covers the entire bandwidth without saturation
    lut.RescaleTransferFunction(0.0, 31000.0)

    sb = GetScalarBar(lut, view)
    sb.Title = '|E(t)| [V/m]'
    sb.ComponentTitle = 'Instantaneous Field (E_phase)'
    sb.Visibility = 1
    sb.WindowLocation = 'Lower Right Corner'

    # Vector arrows (Glyphs) indicating E_phase field direction
    print("--- 4. Creating field vector glyphs (Glyphs) ---")
    glyph = Glyph(registrationName='E_Field_Vectors', Input=calc)
    glyph.GlyphType = 'Arrow'
    glyph.OrientationArray = ['POINTS', 'E_phase']
    glyph.ScaleArray = ['POINTS', 'E_phase']
    glyph.ScaleFactor = 0.000008
    glyph.GlyphMode = 'Every Nth Point'
    glyph.Stride = 5
    glyph.UpdateVTKObjects()
    glyph.UpdatePipeline()

    disp_glyph = Show(glyph, view, 'GeometryRepresentation')
    ColorBy(disp_glyph, ('POINTS', 'E_phase', 'Magnitude'))
    disp_glyph.DiffuseColor = [1.0, 1.0, 1.0]

    # Text overlay displaying frequency and phase
    info_text = Text(registrationName='Info_Label')
    info_text.Text = f"Frequency: {default_freq:.3f} GHz  |  Phase phi: 000 deg"
    info_text.UpdateVTKObjects()
    info_text.UpdatePipeline()

    disp_text = Show(info_text, view)
    try:
        disp_text.Color = [1.0, 1.0, 0.2]
        disp_text.FontSize = 13
        disp_text.WindowLocation = 'Upper Left Corner'
    except Exception:
        pass

    # Camera setup (tilted top-down view)
    view.ResetCamera()
    view.CameraPosition = [0.0, -0.09, 0.11]
    view.CameraFocalPoint = [0.0, 0.0, 0.0015]
    view.CameraViewUp = [0.0, 0.9, 0.4]

    # 5. Animation loop for real-time phase rotation
    print("--- 5. Configuring phase animation loop (0 deg to 360 deg) ---")
    cue = PythonAnimationCue()
    cue.StartTime = 0.0
    cue.EndTime = 360.0
    cue.Script = """
def start_cue(cue):
    pass

def tick(cue):
    import numpy as np
    t = cue.GetAnimationTime()
    phi = t * 2.0 * np.pi
    deg = int(round(t * 360.0)) % 360
    cos_v = np.cos(phi)
    sin_v = np.sin(phi)

    from paraview.simple import FindSource
    c = FindSource('E_Phase_Calculator')
    if c:
        c.Function = f'E_real * ({cos_v:.6f}) - E_imag * ({sin_v:.6f})'
        c.UpdateVTKObjects()
        c.UpdatePipeline()

    g = FindSource('E_Field_Vectors')
    if g:
        g.UpdatePipeline()

    txt = FindSource('Info_Label')
    if txt:
        ft = FindSource('Selected_Frequency_GHz')
        f_val = float(ft.ForcedTime) if ft else 2.330
        txt.Text = f'Frequency: {f_val:.3f} GHz  |  Phase phi: {deg:03d} deg'
        txt.UpdateVTKObjects()
        txt.UpdatePipeline()

def end_cue(cue):
    pass
"""

    scene = GetAnimationScene()
    scene.StartTime = 0.0
    scene.EndTime = 360.0
    scene.PlayMode = 'Sequence'
    scene.NumberOfFrames = 36
    scene.Cues.append(cue)

    # 6. Interactive on-screen frequency slider (vtkSliderWidget)
    print("--- 6. Creating interactive on-screen frequency slider ---")
    render_window = view.SMProxy.GetRenderWindow()
    interactor = render_window.GetInteractor()

    slider_rep = vtk.vtkSliderRepresentation2D()
    slider_rep.SetMinimumValue(f_min)
    slider_rep.SetMaximumValue(f_max)
    slider_rep.SetValue(default_freq)
    slider_rep.SetTitleText("Frequency [GHz]")
    slider_rep.GetPoint1Coordinate().SetCoordinateSystemToNormalizedDisplay()
    slider_rep.GetPoint1Coordinate().SetValue(0.15, 0.07)
    slider_rep.GetPoint2Coordinate().SetCoordinateSystemToNormalizedDisplay()
    slider_rep.GetPoint2Coordinate().SetValue(0.65, 0.07)

    slider_widget = vtk.vtkSliderWidget()
    slider_widget.SetInteractor(interactor)
    slider_widget.SetRepresentation(slider_rep)
    slider_widget.SetAnimationModeToAnimate()
    slider_widget.EnabledOn()

    def on_freq_change(obj, event):
        raw_val = obj.GetRepresentation().GetValue()
        if freqs:
            snapped = min(freqs, key=lambda f: abs(f - raw_val))
        else:
            snapped = round(raw_val / 0.005) * 0.005
            snapped = max(f_min, min(f_max, snapped))
        obj.GetRepresentation().SetValue(snapped)

        # 1. Update ForceTime frequency
        ft.ForcedTime = snapped
        ft.UpdateVTKObjects()
        ft.UpdatePipeline()

        # 2. Force calculator update even when animation is paused
        calc.Modified()
        calc.UpdateVTKObjects()
        calc.UpdatePipeline()

        # 3. Force glyph vector update
        glyph.Modified()
        glyph.UpdateVTKObjects()
        glyph.UpdatePipeline()

        # 4. Update surface and vector representations in the view
        disp_surf.UpdatePipeline()
        disp_glyph.UpdatePipeline()

        # 5. Update on-screen label
        txt = FindSource('Info_Label')
        if txt:
            txt.Text = f'Frequency: {float(ft.ForcedTime):.3f} GHz'
            txt.UpdateVTKObjects()
            txt.UpdatePipeline()

        # 6. Re-render scene
        view.Update()
        Render()

    # React to both dragging and releasing the mouse button
    slider_widget.AddObserver(vtk.vtkCommand.InteractionEvent, on_freq_change)
    slider_widget.AddObserver(vtk.vtkCommand.EndInteractionEvent, on_freq_change)
    _GLOBAL_FREQUENCY_SLIDER = slider_widget

    # Immediate scene render
    view.Update()
    Render()

    print("==================================================")
    print("DYNAMIC SCENE READY AND UPDATED!")
    print("==================================================")

# Run scene setup
setup_dynamic_phase_scene()
