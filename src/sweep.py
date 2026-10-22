import os
import sys
import time
import argparse
import numpy as np

# Zajistíme dostupnost src a scripts složek pro importy
src_dir = os.path.dirname(os.path.abspath(__file__))
scripts_dir = os.path.abspath(os.path.join(src_dir, "..", "scripts"))
for d in (src_dir, scripts_dir):
    if d not in sys.path:
        sys.path.append(d)

from main import main
from rf_calc import synth_square_patch_size, DESIGN_FREQ_GHZ

# Import exportní utility pro uložení balíčků po každém kroku
try:
    from export_package import export_paraview_package
except ImportError:
    export_paraview_package = None

# Výchozí parametry substrátu pro analytický odhad rezonance
DEFAULT_SUB_H = 1.52
DEFAULT_EPS_R = 4.3

# Cílená výchozí sada hodnot zanoření (v mm):
# 0.0 mm (reference bez zanoření) -> 3.0 mm (přechodový bod) -> 4.5, 4.8, 5.0, 5.2 mm (hledání optima kolem 220-230 Ohm)
DEFAULT_INSET_VALUES = [0.0, 3.0, 4.5, 4.8, 5.0, 5.2]


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


def run_inset_sweep(insets=None, patch_l=30.3, patch_w=None, export_each=True, skip_simulation=False):
    """
    Parametrický sweep délky zanoření napáječe (feed_inset).

    :param insets: Seznam hodnot zanoření v mm (např. [0.0, 3.0, 4.8, 5.0])
    :param patch_l: Délka flíčku v mm (výchozí: 30.3 mm)
    :param patch_w: Šířka flíčku v mm (výchozí: rovno patch_l)
    :param export_each: Pokud je True, po každém úspěšném kroku vytvoří pojmenovaný ZIP balíček v export/
    :param skip_simulation: Pokud je True, generuje pouze geometrii a síť bez spouštění Palace v Dockeru
    """
    if insets is None:
        insets = DEFAULT_INSET_VALUES

    if patch_w is None:
        patch_w = patch_l

    total_steps = len(insets)
    print("=" * 65)
    print("ZAHÁJENÍ PARAMETRICKÉHO SWEEPU ZANOŘENÍ NAPÁJEČE (FEED_INSET)")
    print(f"Testované hodnoty zanoření: {insets} mm")
    print(f"Rozměry flíčku: L = {patch_l:.2f} mm, W = {patch_w:.2f} mm")
    print(f"Automatický export balíčku: {'ANO' if export_each else 'NE'}")
    print("Čištění data/postpro před každým krokem: VŽDY AKTIVNÍ")
    print("=" * 65)

    successful_runs = 0

    for i, inset in enumerate(insets, start=1):
        inset_val = float(np.round(inset, 3))
        export_name = f"antena_inset_{inset_val:.2f}mm"
        print(f"\n>>> [{i}/{total_steps}] Spouštím krok: feed_inset = {inset_val:.3f} mm (balíček: {export_name}) <<<")

        custom_params = {
            'feed_inset': inset_val,
            'patch_L': patch_l,
            'patch_W': patch_w,
        }

        try:
            # 1. Spuštění simulační pipeline (clean=True zajistí vždy čisté prostředí)
            main(custom_params=custom_params, skip_simulation=skip_simulation, clean=True)

            # 2. Automatický export ParaView balíčku, pokud simulace reálně proběhla
            if export_each and not skip_simulation:
                if export_paraview_package is not None:
                    print(f"--- Exportuji výsledky kroku do balíčku: {export_name} ---")
                    try:
                        ok = export_paraview_package(output_name=export_name)
                        if ok:
                            print(f"Balíček {export_name}.zip byl úspěšně vytvořen.")
                    except Exception as exp_err:
                        print(f"Varování: Export balíčku {export_name} selhal: {exp_err}")
                else:
                    print("Varování: Modul export_package není dostupný, export přeskočen.")

            successful_runs += 1
            time.sleep(1)

        except Exception as e:
            print(f"[CHYBA] Krok s feed_inset={inset_val} mm selhal: {e}")

    print("\n" + "=" * 65)
    print(f"SWEEP ZANOŘENÍ DOKONČEN! Úspěšně proběhlo {successful_runs}/{total_steps} běhů.")
    print("Všechny výsledky jsou zaznamenány v MLflow (spusťte: mlflow ui).")
    if export_each and not skip_simulation:
        print("Vyexportované ZIP archivy naleznete ve složce: export/")
    print("=" * 65)


def run_patch_length_sweep(patch_lengths=None, export_each=False, skip_simulation=False):
    """
    Parametrický sweep pro délku flíčku patch_L (původní sweep).
    """
    if patch_lengths is None:
        patch_lengths = generate_sweep_patch_lengths()

    print("=" * 65)
    print("ZAHÁJENÍ PARAMETRICKÉHO SWEEPU PRO PATCH_L")
    print(f"Hodnoty k testování: {patch_lengths} mm")
    print("Čištění data/postpro před každým krokem: VŽDY AKTIVNÍ")
    print("=" * 65)

    for i, length in enumerate(patch_lengths, start=1):
        print(f"\n[{i}/{len(patch_lengths)}] Spouštím simulaci pro patch_L = {length} mm")
        custom_params = {
            'patch_L': length,
            'patch_W': length
        }

        try:
            main(custom_params=custom_params, skip_simulation=skip_simulation, clean=True)
            if export_each and not skip_simulation and export_paraview_package:
                export_paraview_package(output_name=f"antena_patchL_{length:.2f}mm")
            time.sleep(1)
        except Exception as e:
            print(f"Při běhu s patch_L={length} došlo k chybě: {e}")

    print("\n" + "=" * 65)
    print("Sweep patch_L dokončen! Výsledky jsou uloženy a zalogovány v MLflow.")
    print("=" * 65)


def run_sweep(patch_lengths=None):
    """Zpětná kompatibilita pro původní volání run_sweep()."""
    run_patch_length_sweep(patch_lengths=patch_lengths)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parametrický sweep mikropáskové antény (Feed Inset / Patch L)")
    parser.add_argument(
        "--param",
        choices=["inset", "patch_l"],
        default="inset",
        help="Parametr pro sweepování: 'inset' (zanoření napáječe) nebo 'patch_l' (délka flíčku). Výchozí: inset.",
    )
    parser.add_argument(
        "--insets",
        type=float,
        nargs="+",
        default=None,
        help="Explicitní seznam hodnot zanoření v mm (např. --insets 0.0 3.0 4.8 5.0).",
    )
    parser.add_argument(
        "--patch-l",
        type=float,
        default=30.3,
        dest="patch_l",
        help="Délka flíčku v mm při sweepu zanoření (výchozí: 30.3 mm).",
    )
    parser.add_argument(
        "--no-export",
        dest="export_each",
        action="store_false",
        default=True,
        help="Zakázat automatické balení výsledků do ZIP archivů po každém kroku.",
    )
    parser.add_argument(
        "--skip-simulation",
        "--no-docker",
        dest="skip_simulation",
        action="store_true",
        default=False,
        help="Generovat pouze geometrii a síť lokálně bez spouštění simulace v Dockeru.",
    )

    args = parser.parse_args()

    if args.param == "inset":
        run_inset_sweep(
            insets=args.insets,
            patch_l=args.patch_l,
            export_each=args.export_each,
            skip_simulation=args.skip_simulation,
        )
    else:
        run_patch_length_sweep(
            export_each=args.export_each,
            skip_simulation=args.skip_simulation,
        )
