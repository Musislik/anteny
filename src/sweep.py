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

from postpro_utils import load_env
# Načtení proměnných prostředí z .env
load_env()

from main import main
from rf_calc import synth_square_patch_size, DESIGN_FREQ_GHZ
from tracker import print_summary_table

# Import exportní utility pro uložení balíčků po každém kroku
try:
    from export_package import export_paraview_package
except ImportError:
    export_paraview_package = None

# Výchozí parametry substrátu pro analytický odhad rezonance
DEFAULT_SUB_H = 1.52
DEFAULT_EPS_R = 4.3

# Cílená výchozí sada hodnot zanoření (v mm):
DEFAULT_INSET_VALUES = [0.0, 3.0, 4.5, 4.8, 5.0, 5.2]


def _parse_insets_env(val):
    """Převede řetězec čísel oddělených čárkou nebo mezerou z .env na seznam floatů."""
    if not val:
        return None
    tokens = val.replace(',', ' ').split()
    res = []
    for t in tokens:
        try:
            res.append(float(t))
        except ValueError:
            pass
    return res if res else None


def _resolve_env_float(sweep_key, base_key, default_val):
    val = os.getenv(sweep_key)
    if val is not None:
        try:
            return float(val)
        except ValueError:
            pass
    val = os.getenv(base_key)
    if val is not None:
        try:
            return float(val)
        except ValueError:
            pass
    return float(default_val)


def _resolve_env_int(sweep_key, base_key, default_val):
    val = os.getenv(sweep_key)
    if val is not None:
        try:
            return int(val)
        except ValueError:
            pass
    val = os.getenv(base_key)
    if val is not None:
        try:
            return int(val)
        except ValueError:
            pass
    return int(default_val)


def _resolve_env_bool(sweep_key, default_val=True):
    val = os.getenv(sweep_key)
    if val is None:
        return default_val
    return val.strip().lower() in ("true", "1", "yes", "y", "ano", "t")


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


def run_inset_sweep(
    insets=None,
    patch_l=None,
    patch_w=None,
    freq_min=None,
    freq_max=None,
    freq_step=None,
    amr_max_its=None,
    amr_threshold=None,
    save_step=None,
    linear_tol=None,
    linear_max_its=None,
    export_each=None,
    skip_simulation=False,
):
    """
    Parametrický sweep délky zanoření napáječe (feed_inset).
    Priorita parametrů: explicitní argument funkce/CLI > SWEEP_* z .env > standardní proměnné .env > výchozí hodnoty.
    """
    # 1. Vyhodnocení profilu pro sweep
    if insets is None:
        insets = _parse_insets_env(os.getenv("SWEEP_INSETS")) or DEFAULT_INSET_VALUES

    patch_l = patch_l if patch_l is not None else _resolve_env_float("SWEEP_PATCH_L", "PATCH_L", 30.3)
    patch_w = patch_w if patch_w is not None else _resolve_env_float("SWEEP_PATCH_W", "PATCH_W", patch_l)
    freq_min = freq_min if freq_min is not None else _resolve_env_float("SWEEP_FREQ_MIN", "FREQ_MIN", 2.280)
    freq_max = freq_max if freq_max is not None else _resolve_env_float("SWEEP_FREQ_MAX", "FREQ_MAX", 2.380)
    freq_step = freq_step if freq_step is not None else _resolve_env_float("SWEEP_FREQ_STEP", "FREQ_STEP", 0.005)
    amr_max_its = amr_max_its if amr_max_its is not None else _resolve_env_int("SWEEP_AMR_MAX_ITS", "AMR_MAX_ITS", 1)
    amr_threshold = amr_threshold if amr_threshold is not None else _resolve_env_float("SWEEP_AMR_THRESHOLD", "AMR_THRESHOLD", 0.3)
    save_step = save_step if save_step is not None else _resolve_env_int("SWEEP_SAVE_STEP", "SAVE_STEP", 1)
    linear_tol = linear_tol if linear_tol is not None else _resolve_env_float("SWEEP_LINEAR_TOL", "LINEAR_TOL", 1e-5)
    linear_max_its = linear_max_its if linear_max_its is not None else _resolve_env_int("SWEEP_LINEAR_MAX_ITS", "LINEAR_MAX_ITS", 100)
    export_each = export_each if export_each is not None else _resolve_env_bool("SWEEP_EXPORT_EACH", True)

    total_steps = len(insets)
    print("=" * 65)
    print("ZAHÁJENÍ PARAMETRICKÉHO SWEEPU ZANOŘENÍ NAPÁJEČE (FEED_INSET)")
    print("Aktivní profil sweepu (z .env / CLI):")
    print(f"  • Testované hodnoty zanoření: {insets} mm")
    print(f"  • Frekvenční rozsah:          {freq_min:.3f} - {freq_max:.3f} GHz (krok {freq_step:.4f} GHz)")
    print(f"  • Rozměry flíčku:             L = {patch_l:.2f} mm, W = {patch_w:.2f} mm")
    print(f"  • AMR zjemnění sítě:          {amr_max_its} iterací (Tolerance: {amr_threshold})")
    print(f"  • Solver Tol / MaxIts:        {linear_tol} / {linear_max_its} iterací")
    print(f"  • Ukládání 3D polí:           každých {save_step} kroků")
    print(f"  • Automatický export balíčku: {'ANO' if export_each else 'NE'}")
    print("  • Čištění data/postpro:       VŽDY AKTIVNÍ (před každým během)")
    print("=" * 65)

    successful_runs = 0

    for i, inset in enumerate(insets, start=1):
        inset_val = float(np.round(inset, 3))
        export_name = f"antena_inset_{inset_val:.2f}mm"
        print(f"\n>>> [{i}/{total_steps}] Spouštím krok: feed_inset = {inset_val:.3f} mm (balíček: {export_name}) <<<")

        # custom_params přebíjí výchozí parametry v main()
        custom_params = {
            'run_name': export_name,
            'feed_inset': inset_val,
            'patch_L': patch_l,
            'patch_W': patch_w,
            'freq_min': freq_min,
            'freq_max': freq_max,
            'freq_step': freq_step,
            'amr_max_its': amr_max_its,
            'amr_threshold': amr_threshold,
            'save_step': save_step,
            'linear_tol': linear_tol,
            'linear_max_its': linear_max_its,
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
    if export_each and not skip_simulation:
        print("Vyexportované ZIP archivy naleznete ve složce: export/")
    print("=" * 65)

    # Souhrnná tabulka výsledků (nahrazuje MLflow)
    print_summary_table()


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
        export_name = f"antena_patchL_{length:.2f}mm"
        print(f"\n[{i}/{len(patch_lengths)}] Spouštím simulaci pro patch_L = {length} mm (balíček: {export_name})")
        custom_params = {
            'run_name': export_name,
            'patch_L': length,
            'patch_W': length
        }

        try:
            main(custom_params=custom_params, skip_simulation=skip_simulation, clean=True)
            if export_each and not skip_simulation and export_paraview_package:
                export_paraview_package(output_name=export_name)
            time.sleep(1)
        except Exception as e:
            print(f"Při běhu s patch_L={length} došlo k chybě: {e}")

    print("\n" + "=" * 65)
    print("Sweep patch_L dokončen! Výsledky jsou uloženy v export/sweep_results.csv.")
    print("=" * 65)

    print_summary_table()


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
        help="Explicitní seznam hodnot zanoření v mm (přebíjí SWEEP_INSETS z .env).",
    )
    parser.add_argument(
        "--patch-l",
        type=float,
        default=None,
        dest="patch_l",
        help="Délka flíčku v mm při sweepu (přebíjí SWEEP_PATCH_L z .env).",
    )
    parser.add_argument(
        "--patch-w",
        type=float,
        default=None,
        dest="patch_w",
        help="Šířka flíčku v mm při sweepu (přebíjí SWEEP_PATCH_W z .env).",
    )
    parser.add_argument(
        "--freq-min",
        type=float,
        default=None,
        dest="freq_min",
        help="Minimální frekvence sweepu v GHz (přebíjí SWEEP_FREQ_MIN z .env).",
    )
    parser.add_argument(
        "--freq-max",
        type=float,
        default=None,
        dest="freq_max",
        help="Maximální frekvence sweepu v GHz (přebíjí SWEEP_FREQ_MAX z .env).",
    )
    parser.add_argument(
        "--freq-step",
        type=float,
        default=None,
        dest="freq_step",
        help="Frekvenční krok sweepu v GHz (přebíjí SWEEP_FREQ_STEP z .env).",
    )
    parser.add_argument(
        "--amr-its",
        type=int,
        default=None,
        dest="amr_max_its",
        help="Maximální počet AMR zjemnění (přebíjí SWEEP_AMR_MAX_ITS z .env).",
    )
    parser.add_argument(
        "--linear-tol",
        type=float,
        default=None,
        dest="linear_tol",
        help="Relativní tolerance lineárního řešiče FGMRES (výchozí: 1e-5 nebo z SWEEP_LINEAR_TOL).",
    )
    parser.add_argument(
        "--linear-its", "--linear-max-its",
        type=int,
        default=None,
        dest="linear_max_its",
        help="Maximální počet iterací lineárního řešiče (výchozí: 100 nebo z SWEEP_LINEAR_MAX_ITS).",
    )
    parser.add_argument(
        "--no-export",
        dest="export_each",
        action="store_false",
        default=None,
        help="Zakázat automatické balení výsledků do ZIP archivů po každém kroku (přebíjí SWEEP_EXPORT_EACH z .env).",
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
            patch_w=args.patch_w,
            freq_min=args.freq_min,
            freq_max=args.freq_max,
            freq_step=args.freq_step,
            amr_max_its=args.amr_max_its,
            linear_tol=args.linear_tol,
            linear_max_its=args.linear_max_its,
            export_each=args.export_each,
            skip_simulation=args.skip_simulation,
        )
    else:
        run_patch_length_sweep(
            export_each=args.export_each if args.export_each is not None else False,
            skip_simulation=args.skip_simulation,
        )
