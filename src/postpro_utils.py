"""
postpro_utils.py - Sdílené pomocné funkce pro správu cest, .env konfiguraci
a automatické propojování výstupů adaptivního zjemnění (AMR) pro ParaView.
"""

import os
import sys
import glob
import subprocess

# Automatické přidání kořene projektu a složek src a scripts do sys.path
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_SCRIPT_DIR, ".."))
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
_SCRIPTS_DIR = os.path.join(_ROOT_DIR, "scripts")

if _SRC_DIR not in sys.path and os.path.exists(_SRC_DIR):
    sys.path.insert(0, _SRC_DIR)
if _SCRIPTS_DIR not in sys.path and os.path.exists(_SCRIPTS_DIR):
    sys.path.insert(0, _SCRIPTS_DIR)
if _ROOT_DIR not in sys.path and os.path.exists(_ROOT_DIR):
    sys.path.insert(0, _ROOT_DIR)


def get_project_root():
    """Vrátí absolutní cestu ke kořenovému adresáři projektu."""
    current_file = os.path.abspath(__file__)
    parent = os.path.dirname(current_file)
    if os.path.basename(parent) in ("src", "scripts", "export", "antena_paraview") or os.path.basename(parent).startswith("antena_export"):
        return os.path.abspath(os.path.join(parent, ".."))
    return os.path.abspath(parent)


def _resolve_env_dir(env_dir, root_dir, default_subdir):
    """
    Vyhodnotí cestu ke složce z proměnné prostředí s bezpečným fallbackem
    do <root_dir>/<default_subdir> (např. pro kontejner nebo Unixovou cestu na Windows).
    """
    default_dir = os.path.abspath(os.path.join(root_dir, default_subdir))
    if not env_dir:
        return default_dir

    is_container = os.path.exists("/.dockerenv") or os.path.exists("/workspace")
    is_win_unix_path = sys.platform == "win32" and env_dir.startswith("/")

    if not os.path.exists(env_dir) and (is_container or is_win_unix_path or not os.path.isabs(env_dir)):
        return default_dir
    if os.path.isabs(env_dir):
        if not os.path.exists(env_dir) and os.path.exists(default_dir):
            return default_dir
        return os.path.abspath(env_dir)
    return os.path.abspath(os.path.join(root_dir, env_dir))


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

    # Pokud zadaná cesta existuje v aktuálním souborovém systému, použijeme ji.
    # Pokud neexistuje (např. hostitelská cesta jako /host/cesta/k/datum spuštěná uvnitř Docker kontejneru
    # nebo Unixová cesta na Windows), použijeme lokální složku projektu data/ (v kontejneru /workspace/data).
    data_dir = _resolve_env_dir(os.getenv("DATA_DIR"), root_dir, "data")

    return root_dir, data_dir


def get_export_dir(root_dir=None):
    """
    Vrátí platnou lokální cestu k exportní složce pro aktuální běhové prostředí podle EXPORT_DIR v .env.
    Pokud EXPORT_DIR z .env ukazuje na hostitelskou cestu, která v kontejneru neexistuje
    (např. /host/cesta/k/exportu), automaticky použije /workspace/export (připojený svazek).
    """
    if root_dir is None:
        root_dir = get_project_root()

    export_dir = _resolve_env_dir(os.getenv("EXPORT_DIR"), root_dir, "export")

    os.makedirs(export_dir, exist_ok=True)
    return os.path.abspath(export_dir)


def load_env_paths(env_path=None):
    """
    Načte .env a vrátí tuple (root_dir, data_dir, export_dir).
    """
    root_dir, data_dir = load_env(env_path)
    export_dir = get_export_dir(root_dir)
    return root_dir, data_dir, export_dir


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


def copy_postpro_directory(src_dir, dst_dir):
    """
    Bezpečně zkopíruje obsah výstupní složky simulace (včetně symlinků/junctions a CSV souborů).
    """
    import shutil
    if not os.path.exists(src_dir):
        return
    os.makedirs(dst_dir, exist_ok=True)
    for item in os.listdir(src_dir):
        s = os.path.join(src_dir, item)
        d = os.path.join(dst_dir, item)
        try:
            if os.path.islink(s):
                if sys.platform == "win32":
                    target = os.path.realpath(s)
                    subprocess.run(
                        ["cmd", "/c", "mklink", "/J", d, target],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    os.symlink(os.readlink(s), d)
            elif os.path.isdir(s):
                shutil.copytree(s, d, symlinks=True, dirs_exist_ok=True)
            elif os.path.isfile(s):
                shutil.copy2(s, d)
        except Exception as e:
            print(f"[postpro_utils] Upozornění při kopírování {s} -> {d}: {e}")


def merge_two_port_simulations(p1_dir, p2_dir, output_dir):
    """
    Sloučí výstupy ze dvou dílčích simulací Palace pro Model 2:
      - p1_dir: běh s buzeným Portem 1 (spodní, Ey) a pasivně zakončeným Portem 2 (100 Ohm)
      - p2_dir: běh s buzeným Portem 2 (levý, Ex) a pasivně zakončeným Portem 1 (100 Ohm)
    do kompletní 2-portové S-matice v output_dir/port-S.csv a superponovaného
    dálkového pole v output_dir/farfield-rE.csv.
    """
    import numpy as np
    import shutil

    os.makedirs(output_dir, exist_ok=True)

    # 1. SLOUČENÍ S-PARAMETRŮ (port-S.csv)
    s1_path = os.path.join(p1_dir, "port-S.csv")
    s2_path = os.path.join(p2_dir, "port-S.csv")
    s_out = os.path.join(output_dir, "port-S.csv")

    if os.path.exists(s1_path) and os.path.exists(s2_path):
        try:
            with open(s1_path, 'r', encoding='utf-8') as f:
                h1 = [c.strip().lower() for c in f.readline().split(',')]
            with open(s2_path, 'r', encoding='utf-8') as f:
                h2 = [c.strip().lower() for c in f.readline().split(',')]

            d1 = np.loadtxt(s1_path, delimiter=',', skiprows=1)
            d2 = np.loadtxt(s2_path, delimiter=',', skiprows=1)
            if d1.ndim == 1:
                d1 = d1.reshape(1, -1)
            if d2.ndim == 1:
                d2 = d2.reshape(1, -1)

            def get_col(header, patterns):
                for idx, col in enumerate(header):
                    for pat in patterns:
                        if pat in col:
                            return idx
                return None

            # Z p1_dir hledáme S11 a S21
            s11_idx = get_col(h1, ["|s[1][1]|", "s[1][1]", "s11"])
            if s11_idx is None:
                s11_idx = 1
            s11_deg_idx = get_col(h1, ["arg(s[1][1])", "phase(s[1][1])"])
            if s11_deg_idx is None and d1.shape[1] > 2:
                s11_deg_idx = 2

            s21_idx = get_col(h1, ["|s[2][1]|", "s[2][1]", "s21"])
            if s21_idx is None and d1.shape[1] > 3:
                s21_idx = 3
            s21_deg_idx = get_col(h1, ["arg(s[2][1])", "phase(s[2][1])"])
            if s21_deg_idx is None and d1.shape[1] > 4:
                s21_deg_idx = 4

            # Z p2_dir hledáme S12 a S22
            s12_idx = get_col(h2, ["|s[1][2]|", "s[1][2]", "s12"])
            if s12_idx is None and d2.shape[1] > 1:
                s12_idx = 1
            s12_deg_idx = get_col(h2, ["arg(s[1][2])", "phase(s[1][2])"])
            if s12_deg_idx is None and d2.shape[1] > 2:
                s12_deg_idx = 2

            s22_idx = get_col(h2, ["|s[2][2]|", "s[2][2]", "s22"])
            if s22_idx is None and d2.shape[1] > 3:
                s22_idx = 3
            s22_deg_idx = get_col(h2, ["arg(s[2][2])", "phase(s[2][2])"])
            if s22_deg_idx is None and d2.shape[1] > 4:
                s22_deg_idx = 4

            n_rows = min(len(d1), len(d2))
            freqs = d1[:n_rows, 0]

            s11_val = d1[:n_rows, s11_idx]
            s11_deg_val = d1[:n_rows, s11_deg_idx] if s11_deg_idx is not None else np.zeros(n_rows)

            s21_val = d1[:n_rows, s21_idx] if s21_idx is not None else np.zeros(n_rows)
            s21_deg_val = d1[:n_rows, s21_deg_idx] if s21_deg_idx is not None else np.zeros(n_rows)

            s12_val = d2[:n_rows, s12_idx] if s12_idx is not None else s21_val
            s12_deg_val = d2[:n_rows, s12_deg_idx] if s12_deg_idx is not None else s21_deg_val

            s22_val = d2[:n_rows, s22_idx] if s22_idx is not None else np.zeros(n_rows)
            s22_deg_val = d2[:n_rows, s22_deg_idx] if s22_deg_idx is not None else np.zeros(n_rows)

            header_str = (
                "        f (GHz),             |S[1][1]| (dB),        arg(S[1][1]) (deg.),"
                "             |S[2][1]| (dB),        arg(S[2][1]) (deg.),"
                "             |S[1][2]| (dB),        arg(S[1][2]) (deg.),"
                "             |S[2][2]| (dB),        arg(S[2][2]) (deg.)\n"
            )

            with open(s_out, 'w', encoding='utf-8') as f_out:
                f_out.write(header_str)
                for i in range(n_rows):
                    f_out.write(
                        f" {freqs[i]:15.8e}, {s11_val[i]:26.12e}, {s11_deg_val[i]:+26.12e},"
                        f" {s21_val[i]:26.12e}, {s21_deg_val[i]:+26.12e},"
                        f" {s12_val[i]:26.12e}, {s12_deg_val[i]:+26.12e},"
                        f" {s22_val[i]:26.12e}, {s22_deg_val[i]:+26.12e}\n"
                    )

            shutil.copy2(s1_path, os.path.join(output_dir, "port-S_port1.csv"))
            shutil.copy2(s2_path, os.path.join(output_dir, "port-S_port2.csv"))
            print(f"[postpro_utils] S-matice úspěšně sloučena: {s_out} (Port 1 + Port 2)")

        except Exception as e:
            print(f"[postpro_utils] Chyba při slučování port-S.csv: {e}")
    elif os.path.exists(s1_path):
        shutil.copy2(s1_path, s_out)
    elif os.path.exists(s2_path):
        shutil.copy2(s2_path, s_out)

    # 2. SLOUČENÍ DÁLKOVÉHO POLE (farfield-rE.csv)
    ff1_path = os.path.join(p1_dir, "farfield-rE.csv")
    ff2_path = os.path.join(p2_dir, "farfield-rE.csv")
    ff_out = os.path.join(output_dir, "farfield-rE.csv")

    if os.path.exists(ff1_path) and os.path.exists(ff2_path):
        try:
            d_ff1 = np.loadtxt(ff1_path, delimiter=',', skiprows=1)
            d_ff2 = np.loadtxt(ff2_path, delimiter=',', skiprows=1)
            if d_ff1.ndim == 1:
                d_ff1 = d_ff1.reshape(1, -1)
            if d_ff2.ndim == 1:
                d_ff2 = d_ff2.reshape(1, -1)

            if d_ff1.shape == d_ff2.shape and d_ff1.shape[1] >= 10:
                merged_ff = d_ff1.copy()
                merged_ff[:, 1] = 1  # exc
                # Sloupce 4:10 obsahují r*Re/Im složek pole Ex, Ey, Ez
                merged_ff[:, 4:10] = d_ff1[:, 4:10] + d_ff2[:, 4:10]

                ff_header = (
                    "        f (GHz),     exc,               theta (deg.),                 phi (deg.),"
                    "              r*Re{E_x} (V),              r*Im{E_x} (V),"
                    "              r*Re{E_y} (V),              r*Im{E_y} (V),"
                    "              r*Re{E_z} (V),              r*Im{E_z} (V)"
                )
                fmt = ['%15.8e', '%8d', '%26.12e', '%26.12e',
                       '%26.12e', '%26.12e', '%26.12e', '%26.12e', '%26.12e', '%26.12e']
                np.savetxt(ff_out, merged_ff, delimiter=',', header=ff_header, comments='', fmt=fmt)

                shutil.copy2(ff1_path, os.path.join(output_dir, "farfield_p1-rE.csv"))
                shutil.copy2(ff2_path, os.path.join(output_dir, "farfield_p2-rE.csv"))
                print(f"[postpro_utils] Dálkové pole úspěšně superponováno do: {ff_out}")
            else:
                shutil.copy2(ff1_path, ff_out)
        except Exception as e:
            print(f"[postpro_utils] Chyba při slučování farfield-rE.csv: {e}")
    elif os.path.exists(ff1_path):
        shutil.copy2(ff1_path, ff_out)
    elif os.path.exists(ff2_path):
        shutil.copy2(ff2_path, ff_out)

    # 3. ZÁLOHA A PROPOJENÍ DALŠÍCH SOUBORŮ
    for f_name in ["port-V.csv", "port-I.csv", "terminal-V.csv", "terminal-I.csv"]:
        f1 = os.path.join(p1_dir, f_name)
        f2 = os.path.join(p2_dir, f_name)
        stem, ext = os.path.splitext(f_name)
        if os.path.exists(f1):
            shutil.copy2(f1, os.path.join(output_dir, f"{stem}_port1{ext}"))
        if os.path.exists(f2):
            shutil.copy2(f2, os.path.join(output_dir, f"{stem}_port2{ext}"))

    pv1 = os.path.join(p1_dir, "paraview")
    pv_out = os.path.join(output_dir, "paraview")
    if os.path.exists(pv1) and not os.path.exists(pv_out):
        try:
            shutil.copytree(pv1, pv_out, symlinks=True, dirs_exist_ok=True)
        except Exception:
            pass

