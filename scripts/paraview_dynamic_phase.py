"""
ParaView Makro pro DYNAMICKOU animaci fáze v reálném čase s INTERAKTIVNÍM POSUVNÍKEM FREKVENCE.

Funkce:
1. Interaktivní grafický posuvník přímo na obrazovce pro plynulou změnu frekvence (2.320 - 2.345 GHz).
2. Plynulá rotace fáze (0° až 360°) stisknutím tlačítka PLAY na horní liště.
3. Vše počítáno dynamicky v paměti GPU bez ukládání jakýchkoliv souborů na disk.

Spuštění v ParaView:
    Tools -> Python Shell -> Run Script -> vyberte tento soubor
"""

import os
import sys
import vtk
from paraview.simple import *

try:
    import _env
    from postpro_utils import get_driven_boundary_pvd
except ImportError:
    def get_driven_boundary_pvd(caller_file=None):
        script_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
        local_pvd = os.path.join(script_dir, "driven_boundary", "driven_boundary.pvd")
        return os.path.abspath(local_pvd) if os.path.exists(local_pvd) else None

# Globální reference, aby Python nesmazal posuvník z paměti
_GLOBAL_FREQUENCY_SLIDER = None

def setup_dynamic_phase_scene():
    global _GLOBAL_FREQUENCY_SLIDER

    pvd_file = get_driven_boundary_pvd(caller_file=__file__ if "__file__" in globals() else None)
    if not pvd_file or not os.path.exists(pvd_file):
        print(f"[CHYBA] Soubor driven_boundary.pvd nebyl nalezen.")
        print("Zkontrolujte parametr DATA_DIR v souboru .env nebo existenci složky driven_boundary.")
        return

    print(f"--- 1. Načítám frekvenční data: {pvd_file} ---")
    view = GetActiveViewOrCreate('RenderView')

    # Načtení databáze všech frekvencí
    reader = PVDReader(registrationName='Palace_Frekvencni_Data', FileName=pvd_file)
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

    # Filtr pro výběr a uzamčení konkrétní frekvence
    print(f"--- 2. Vytvářím volič frekvence (ForceTime, výchozí {default_freq:.3f} GHz) ---")
    ft = ForceTime(registrationName='Zvolena_Frekvence_GHz', Input=reader)
    ft.ForcedTime = default_freq
    ft.UpdateVTKObjects()
    ft.UpdatePipeline()

    # Dynamický kalkulátor okamžitého pole E(t)
    print("--- 3. Nastavuji dynamický fázorový kalkulátor ---")
    calc = Calculator(registrationName='E_Phase_Kalkulator', Input=ft)
    calc.ResultArrayName = 'E_phase'
    calc.Function = 'E_real'
    calc.UpdateVTKObjects()
    calc.UpdatePipeline()

    # Zobrazení povrchu s barevnou mapou pole E_phase
    disp_surf = Show(calc, view, 'GeometryRepresentation')
    disp_surf.Representation = 'Surface'
    ColorBy(disp_surf, ('POINTS', 'E_phase', 'Magnitude'))

    lut = GetColorTransferFunction('E_phase')
    lut.ApplyPreset('Turbo', True)
    # Rozsah škály do 31 000 V/m pokrývá celou šířku pásma bez saturace
    lut.RescaleTransferFunction(0.0, 31000.0)

    sb = GetScalarBar(lut, view)
    sb.Title = '|E(t)| [V/m]'
    sb.ComponentTitle = 'Okamžité pole (E_phase)'
    sb.Visibility = 1
    sb.WindowLocation = 'Lower Right Corner'

    # Vektorové šipky pole (Glyphs) ukazující směr pole E_phase
    print("--- 4. Vytvářím vektorové šipky pole (Glyphs) ---")
    glyph = Glyph(registrationName='Vektory_E_Pole', Input=calc)
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

    # Textový popisek s frekvencí a fází
    info_text = Text(registrationName='Popisek_Info')
    info_text.Text = f"Frekvence: {default_freq:.3f} GHz  |  Fáze φ: 000°"
    info_text.UpdateVTKObjects()
    info_text.UpdatePipeline()

    disp_text = Show(info_text, view)
    try:
        disp_text.Color = [1.0, 1.0, 0.2]
        disp_text.FontSize = 13
        disp_text.WindowLocation = 'Upper Left Corner'
    except Exception:
        pass

    # Nastavení kamery (nadhled s mírným náklonem)
    view.ResetCamera()
    view.CameraPosition = [0.0, -0.09, 0.11]
    view.CameraFocalPoint = [0.0, 0.0, 0.0015]
    view.CameraViewUp = [0.0, 0.9, 0.4]

    # 5. Animační smyčka pro rotaci fáze v reálném čase
    print("--- 5. Konfiguruji animační fázovou smyčku (0° až 360°) ---")
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
    c = FindSource('E_Phase_Kalkulator')
    if c:
        c.Function = f'E_real * ({cos_v:.6f}) - E_imag * ({sin_v:.6f})'
        c.UpdateVTKObjects()
        c.UpdatePipeline()

    g = FindSource('Vektory_E_Pole')
    if g:
        g.UpdatePipeline()

    txt = FindSource('Popisek_Info')
    if txt:
        ft = FindSource('Zvolena_Frekvence_GHz')
        f_val = float(ft.ForcedTime) if ft else 2.330
        txt.Text = f'Frekvence: {f_val:.3f} GHz  |  Fáze φ: {deg:03d}°'
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

    # 6. Interaktivní grafický posuvník frekvence na obrazovce (vtkSliderWidget)
    print("--- 6. Vytvářím interaktivní posuvník frekvence na obrazovce ---")
    render_window = view.SMProxy.GetRenderWindow()
    interactor = render_window.GetInteractor()

    slider_rep = vtk.vtkSliderRepresentation2D()
    slider_rep.SetMinimumValue(f_min)
    slider_rep.SetMaximumValue(f_max)
    slider_rep.SetValue(default_freq)
    slider_rep.SetTitleText("Frekvence [GHz]")
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

        # 1. Změna frekvence na ForceTime
        ft.ForcedTime = snapped
        ft.UpdateVTKObjects()
        ft.UpdatePipeline()

        # 2. Vynucení přepočtu kalkulátoru i při pauznuté animaci
        calc.Modified()
        calc.UpdateVTKObjects()
        calc.UpdatePipeline()

        # 3. Vynucení přepočtu vektorových šipek
        glyph.Modified()
        glyph.UpdateVTKObjects()
        glyph.UpdatePipeline()

        # 4. Aktualizace zobrazení povrchu i šipek v okně
        disp_surf.UpdatePipeline()
        disp_glyph.UpdatePipeline()

        # 5. Aktualizace textu na obrazovce
        txt = FindSource('Popisek_Info')
        if txt:
            txt.Text = f'Frekvence: {float(ft.ForcedTime):.3f} GHz'
            txt.UpdateVTKObjects()
            txt.UpdatePipeline()

        # 6. Překreslení scény
        view.Update()
        Render()

    # Reagovat jak na tažení, tak na puštění myši
    slider_widget.AddObserver(vtk.vtkCommand.InteractionEvent, on_freq_change)
    slider_widget.AddObserver(vtk.vtkCommand.EndInteractionEvent, on_freq_change)
    _GLOBAL_FREQUENCY_SLIDER = slider_widget

    # Okamžité překreslení scény
    view.Update()
    Render()

    print("==================================================")
    print("DYNAMICKÁ SCÉNA PŘIPRAVENA A AKTUALIZOVÁNA!")
    print("==================================================")

# Spustit nastavení scény
setup_dynamic_phase_scene()
