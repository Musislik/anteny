"""
postpro_utils.py - Sdílené pomocné funkce pro správu cest, .env konfiguraci
a automatické propojování výstupů adaptivního zjemnění (AMR) pro ParaView.
"""

import os
import sys
import glob
import subprocess

# Automatické přidání kořene projektu a složky src do sys.path
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_SCRIPT_DIR, ".."))
_SRC_DIR = os.path.join(_ROOT_DIR, "src")

if _SRC_DIR not in sys.path and os.path.exists(_SRC_DIR):
    sys.path.insert(0, _SRC_DIR)
if _ROOT_DIR not in sys.path and os.path.exists(_ROOT_DIR):
    sys.path.insert(0, _ROOT_DIR)


def get_project_root():
    """Vrátí absolutní cestu ke kořenovému adresáři projektu."""
    current_file = os.path.abspath(__file__)
    parent = os.path.dirname(current_file)
    if os.path.basename(parent) in ("src", "scripts", "export", "antena_paraview") or os.path.basename(parent).startswith("antena_export"):
        return os.path.abspath(os.path.join(parent, ".."))
    return os.path.abspath(parent)


def load_env(env_path=None):
    """
    Načte proměnné prostředí ze souboru .env v kořeni projektu.
    Vrací tuple (root_dir, data_dir).
    """
    root_dir = get_project_root()
    if env_path is None:
        env_path = os.path.join(root_dir, ".env")

    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception as e:
            print(f"Upozornění při čtení .env: {e}")

    env_data_dir = os.getenv("DATA_DIR")
    # Pokud zadaná cesta existuje v aktuálním souborovém systému, použijeme ji.
    # Pokud neexistuje (např. hostitelská cesta jako /mnt/data-nosync/... spuštěná uvnitř Docker kontejneru),
    # použijeme lokální složku projektu data/ (v kontejneru odpovídá /workspace/data).
    if env_data_dir and os.path.exists(env_data_dir):
        data_dir = os.path.abspath(env_data_dir)
    else:
        data_dir = os.path.abspath(os.path.join(root_dir, "data"))

    return root_dir, data_dir


def get_latest_iteration_dir(data_dir=None):
    """
    Najde podsložku s nejnovější dokončenou AMR iterací (např. 'data/postpro/iteration1').
    Vrací cestu k ní nebo None, pokud žádné složky iteration* neexistují.
    """
    if data_dir is None:
        _, data_dir = load_env()

    postpro_dir = os.path.join(data_dir, "postpro")
    iter_dirs = glob.glob(os.path.join(postpro_dir, "iteration*"))
    if not iter_dirs:
        return None

    def iter_key(path):
        base = os.path.basename(path)
        num_part = "".join(c for c in base if c.isdigit())
        return int(num_part) if num_part else 0

    sorted_iters = sorted(iter_dirs, key=iter_key)
    return os.path.abspath(sorted_iters[-1])


def ensure_paraview_linked(data_dir=None):
    """
    Zajistí, že 'data/postpro/paraview' odkazuje na složku paraview v nejnovější AMR iteraci.
    Pokud složka paraview již existuje jako normální adresář a neexistují iteration*, nic nemění.
    Pokud existují iteration*, vytvoří/aktualizuje junction (Windows) nebo symlink (Linux).
    Vrací cestu k aktivní složce paraview.
    """
    if data_dir is None:
        _, data_dir = load_env()

    postpro_dir = os.path.abspath(os.path.join(data_dir, "postpro"))
    target_link = os.path.join(postpro_dir, "paraview")

    latest_iter = get_latest_iteration_dir(data_dir)
    if not latest_iter:
        return target_link if os.path.exists(target_link) else None

    latest_pv = os.path.join(latest_iter, "paraview")
    if not os.path.exists(latest_pv):
        return target_link if os.path.exists(target_link) else None

    needs_relink = False
    if os.path.exists(target_link):
        try:
            current_real = os.path.realpath(target_link)
            target_real = os.path.realpath(latest_pv)
            if os.path.normcase(current_real) != os.path.normcase(target_real):
                needs_relink = True
        except Exception:
            needs_relink = True
    else:
        needs_relink = True

    if needs_relink:
        if os.path.exists(target_link) or os.path.islink(target_link):
            try:
                if sys.platform == "win32":
                    subprocess.run(
                        ["cmd", "/c", "rmdir", target_link],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    os.unlink(target_link)
            except Exception:
                pass

        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J", target_link, latest_pv],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                os.symlink(latest_pv, target_link)
            print(f"[postpro_utils] Propojeno: {target_link} -> {latest_pv}")
        except Exception as e:
            print(f"[postpro_utils] Upozornění: Nepodařilo se vytvořit odkaz pro paraview: {e}")

    return target_link


def get_driven_boundary_pvd(data_dir=None, caller_file=None):
    """
    Vrátí cestu k driven_boundary.pvd.
    Nejprve zajistí propojení paraview na poslední iteraci.
    Pokud existuje lokální fallback (rozbalený přenosný balíček), použije ten.
    """
    if data_dir is None:
        _, data_dir = load_env()

    ensure_paraview_linked(data_dir)

    direct_pvd = os.path.join(data_dir, "postpro", "paraview", "driven_boundary", "driven_boundary.pvd")
    if os.path.exists(direct_pvd):
        return os.path.abspath(direct_pvd)

    search_dirs = [os.getcwd()]
    if caller_file:
        search_dirs.insert(0, os.path.dirname(os.path.abspath(caller_file)))

    for sd in search_dirs:
        local_pvd = os.path.join(sd, "driven_boundary", "driven_boundary.pvd")
        if os.path.exists(local_pvd):
            return os.path.abspath(local_pvd)

    return None
