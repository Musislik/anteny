"""
postpro_utils.py - Shared helper utilities for path management, .env configuration,
and automatic linking of adaptive mesh refinement (AMR) outputs for ParaView.
"""

import os
import re
import sys
import glob
import subprocess

# Automatically add project root, src, and scripts directories to sys.path
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
    """Return absolute path to the project root directory."""
    current_file = os.path.abspath(__file__)
    parent = os.path.dirname(current_file)
    if os.path.basename(parent) in ("src", "scripts", "export", "antenna_paraview") or os.path.basename(parent).startswith("antenna_export"):
        return os.path.abspath(os.path.join(parent, ".."))
    return os.path.abspath(parent)


def _resolve_env_dir(env_dir, root_dir, default_subdir):
    """
    Resolve directory path from an environment variable with a safe fallback
    to <root_dir>/<default_subdir> (e.g., for containers or Unix paths on Windows).
    """
    default_dir = os.path.abspath(os.path.join(root_dir, default_subdir))
    if not env_dir:
        return default_dir

    is_container = os.path.exists("/.dockerenv") or os.path.exists("/workspace")
    is_win_unix_path = sys.platform == "win32" and env_dir.startswith("/")
    is_win_drive_on_linux = sys.platform != "win32" and len(env_dir) >= 2 and env_dir[1] == ":" and env_dir[0].isalpha()

    if is_win_unix_path:
        if not os.path.exists(env_dir):
            return default_dir
        return os.path.abspath(env_dir)

    if is_win_drive_on_linux:
        return default_dir

    if os.path.isabs(env_dir):
        if not os.path.exists(env_dir) and (is_container or os.path.exists(default_dir)):
            return default_dir
        return os.path.abspath(env_dir)

    return os.path.abspath(os.path.join(root_dir, env_dir))


_SAFE_PROFILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_ENV_FILE_APPLIED = {}


def _validate_safe_profile_name(profile_name):
    """Validate a safe profile name (no path traversal or path separators)."""
    if not isinstance(profile_name, str):
        raise ValueError(f"Invalid profile name: {profile_name!r}")
    name = profile_name.strip()
    if not name:
        raise ValueError("Profile name must not be empty.")
    if ".." in name or "/" in name or "\\" in name or "\x00" in name:
        raise ValueError(
            f"Invalid profile name (path traversal / path separators are not allowed): {profile_name!r}"
        )
    if not _SAFE_PROFILE_RE.match(name):
        raise ValueError(
            f"Invalid profile name {profile_name!r}: only characters [A-Za-z0-9._-] are allowed "
            f"and the name must start with an alphanumeric character."
        )
    return name


def _parse_env_file(path):
    """Load key=value pairs from a .env format file."""
    parsed = {}
    if not path or not os.path.exists(path):
        return parsed
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip("'\"")
                if k:
                    parsed[k] = v
    return parsed


def get_profile_env_path(profile_name, root_dir=None):
    """
    Return the absolute path to the profile configuration file:
      <root_dir>/results/<profile_name>/<profile_name>.env
    Also supports a direct path to an existing .env file (without '..' path traversal).
    Raises FileNotFoundError if the file does not exist.
    """
    if root_dir is None:
        root_dir = get_project_root()
    else:
        root_dir = os.path.abspath(root_dir)

    if not isinstance(profile_name, str) or not profile_name.strip():
        raise ValueError(f"Invalid profile name: {profile_name!r}")

    raw = profile_name.strip()
    if "\x00" in raw or ".." in raw:
        raise ValueError(f"Invalid profile name (path traversal is not allowed): {profile_name!r}")

    if raw.endswith(".env"):
        candidate = os.path.abspath(raw) if os.path.isabs(raw) else os.path.abspath(os.path.join(root_dir, raw))
        if os.path.isfile(candidate):
            return candidate
        raise FileNotFoundError(f"Profile configuration file not found: {candidate}")

    safe_name = _validate_safe_profile_name(raw)
    results_dir = os.path.abspath(os.path.join(root_dir, "results"))
    env_file = os.path.abspath(os.path.join(results_dir, safe_name, f"{safe_name}.env"))
    if os.path.commonpath([results_dir, env_file]) != results_dir:
        raise ValueError(f"Invalid profile name (path outside results/): {profile_name!r}")

    if not os.path.isfile(env_file):
        raise FileNotFoundError(
            f"Variant profile '{safe_name}' not found: expected file {env_file} does not exist."
        )
    return env_file


def get_profile_kicad_dir(profile_name, root_dir=None):
    """
    Return the absolute path to the KiCad output directory for the given profile:
      <root_dir>/results/<profile_name>/kicad
    """
    if root_dir is None:
        root_dir = get_project_root()
    else:
        root_dir = os.path.abspath(root_dir)

    if not isinstance(profile_name, str) or not profile_name.strip():
        raise ValueError(f"Invalid profile name: {profile_name!r}")

    raw = profile_name.strip()
    if "\x00" in raw or ".." in raw:
        raise ValueError(f"Invalid profile name (path traversal is not allowed): {profile_name!r}")

    if raw.endswith(".env"):
        candidate = os.path.abspath(raw) if os.path.isabs(raw) else os.path.abspath(os.path.join(root_dir, raw))
        return os.path.abspath(os.path.join(os.path.dirname(candidate), "kicad"))

    safe_name = _validate_safe_profile_name(raw)
    results_dir = os.path.abspath(os.path.join(root_dir, "results"))
    kicad_dir = os.path.abspath(os.path.join(results_dir, safe_name, "kicad"))
    if os.path.commonpath([results_dir, kicad_dir]) != results_dir:
        raise ValueError(f"Invalid profile name (path outside results/): {profile_name!r}")
    return kicad_dir


def load_env(env_path=None, profile=None):
    """
    Load environment variables from the .env file in the project root and optionally
    apply a manufacturing variant profile from results/<profile>/<profile>.env.

    Profile selection priority: explicit `profile` argument > `os.getenv("ANTENNA_PROFILE")`.
    Values from the profile override values loaded from root .env (even on repeated calls).
    Returns tuple (root_dir, data_dir).
    """
    if env_path is None:
        root_dir = get_project_root()
        env_path = os.path.join(root_dir, ".env")
    else:
        env_path = os.path.abspath(env_path)
        root_dir = os.path.dirname(env_path)

    root_vars = {}
    if os.path.exists(env_path):
        try:
            root_vars = _parse_env_file(env_path)
            for k, v in root_vars.items():
                if k not in os.environ:
                    os.environ[k] = v
                    _ENV_FILE_APPLIED[k] = v
        except Exception as e:
            print(f"Warning while reading .env: {e}")

    explicit_profile = profile is not None and str(profile).strip() != ""
    if explicit_profile:
        active_profile = str(profile).strip()
    else:
        env_profile = os.getenv("ANTENNA_PROFILE", "").strip()
        active_profile = env_profile if env_profile else None

    if active_profile:
        profile_env_path = get_profile_env_path(active_profile, root_dir=root_dir)
        if active_profile.endswith(".env"):
            profile_slug = os.path.splitext(os.path.basename(profile_env_path))[0]
            canonical_env_path = os.path.abspath(
                os.path.join(root_dir, "results", profile_slug, f"{profile_slug}.env")
            )
            env_profile_value = profile_slug if profile_env_path == canonical_env_path else profile_env_path
        else:
            profile_slug = active_profile
            env_profile_value = active_profile

        profile_vars = _parse_env_file(profile_env_path)
        for k, v in profile_vars.items():
            can_override = (
                k not in os.environ
                or _ENV_FILE_APPLIED.get(k) == os.environ.get(k)
                or (k in root_vars and os.environ.get(k) == root_vars[k])
            )
            if can_override:
                os.environ[k] = v
                _ENV_FILE_APPLIED[k] = v

        if (
            explicit_profile
            or "ANTENNA_PROFILE" not in os.environ
            or _ENV_FILE_APPLIED.get("ANTENNA_PROFILE") == os.environ.get("ANTENNA_PROFILE")
        ):
            os.environ["ANTENNA_PROFILE"] = env_profile_value
            _ENV_FILE_APPLIED["ANTENNA_PROFILE"] = env_profile_value

        desired_profile_name = profile_vars.get("PROFILE_NAME", "").strip() or profile_slug
        if (
            explicit_profile
            or "PROFILE_NAME" not in os.environ
            or _ENV_FILE_APPLIED.get("PROFILE_NAME") == os.environ.get("PROFILE_NAME")
            or ("PROFILE_NAME" in root_vars and os.environ.get("PROFILE_NAME") == root_vars["PROFILE_NAME"])
        ):
            os.environ["PROFILE_NAME"] = desired_profile_name
            _ENV_FILE_APPLIED["PROFILE_NAME"] = desired_profile_name

    # If the specified path exists in the current filesystem, use it.
    # If it does not exist (e.g., a host path such as /host/path/to/data inside a Docker container
    # or a Unix path on Windows), fall back to the local project directory data/ (in container /workspace/data).
    data_dir = _resolve_env_dir(os.getenv("DATA_DIR"), root_dir, "data")

    return root_dir, data_dir


def get_export_dir(root_dir=None):
    """
    Return a valid local path to the export directory for the current runtime environment per EXPORT_DIR in .env.
    If EXPORT_DIR from .env points to a host path that does not exist inside a container
    (e.g., /host/path/to/export), automatically fall back to /workspace/export (mounted volume).
    """
    if root_dir is None:
        root_dir = get_project_root()

    export_dir = _resolve_env_dir(os.getenv("EXPORT_DIR"), root_dir, "export")

    os.makedirs(export_dir, exist_ok=True)
    return os.path.abspath(export_dir)


def load_env_paths(env_path=None, profile=None):
    """
    Load .env (and optionally a profile) and return tuple (root_dir, data_dir, export_dir).
    """
    root_dir, data_dir = load_env(env_path, profile=profile)
    export_dir = get_export_dir(root_dir)
    return root_dir, data_dir, export_dir


def get_latest_iteration_dir(data_dir=None):
    """
    Find the subdirectory with the latest completed AMR iteration (e.g., 'data/postpro/iteration1').
    Returns its path or None if no iteration* directories exist.
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
    Ensure 'data/postpro/paraview' points to the paraview folder in the latest AMR iteration.
    If paraview already exists as a regular directory and no iteration* exist, leaves it untouched.
    If iteration* exist, creates/updates a junction (Windows) or symlink (Linux).
    Returns path to the active paraview directory.
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
            print(f"[postpro_utils] Linked: {target_link} -> {latest_pv}")
        except Exception as e:
            print(f"[postpro_utils] Warning: Failed to create paraview link: {e}")

    return target_link


def get_driven_boundary_pvd(data_dir=None, caller_file=None):
    """
    Return path to driven_boundary.pvd.
    First ensures paraview is linked to the latest iteration.
    If a local fallback exists (unpacked portable package), uses that.
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
    Safely copy contents of the simulation output directory (including symlinks/junctions and CSV files).
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
            print(f"[postpro_utils] Warning while copying {s} -> {d}: {e}")


def merge_two_port_simulations(p1_dir, p2_dir, output_dir):
    """
    Merge outputs from two partial Palace simulations for Model 2:
      - p1_dir: run with excited Port 1 (bottom, Ey) and passively terminated Port 2 (100 Ohm)
      - p2_dir: run with excited Port 2 (left, Ex) and passively terminated Port 1 (100 Ohm)
    into a complete 2-port S-matrix in output_dir/port-S.csv and superposed
    far-field in output_dir/farfield-rE.csv.
    """
    import numpy as np
    import shutil

    os.makedirs(output_dir, exist_ok=True)

    # 1. MERGING S-PARAMETERS (port-S.csv)
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

            # From p1_dir, look for S11 and S21
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

            # From p2_dir, look for S12 and S22
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
            print(f"[postpro_utils] S-matrix merged successfully: {s_out} (Port 1 + Port 2)")

        except Exception as e:
            print(f"[postpro_utils] Error merging port-S.csv: {e}")
    elif os.path.exists(s1_path):
        shutil.copy2(s1_path, s_out)
    elif os.path.exists(s2_path):
        shutil.copy2(s2_path, s_out)

    # 2. MERGING FAR-FIELD (farfield-rE.csv)
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
                # Columns 4:10 contain r*Re/Im of Ex, Ey, Ez field components
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
                print(f"[postpro_utils] Far-field superposed successfully into: {ff_out}")
            else:
                shutil.copy2(ff1_path, ff_out)
        except Exception as e:
            print(f"[postpro_utils] Error merging farfield-rE.csv: {e}")
    elif os.path.exists(ff1_path):
        shutil.copy2(ff1_path, ff_out)
    elif os.path.exists(ff2_path):
        shutil.copy2(ff2_path, ff_out)

    # 3. BACKUP AND LINKING OF ADDITIONAL FILES
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


def find_col_idx(header, patterns, exclude_patterns=None):
    """Find the index of the first column in header matching any pattern (with optional exclusions)."""
    for idx, col in enumerate(header):
        col_low = col.lower()
        if exclude_patterns and any(ep.lower() in col_low for ep in exclude_patterns):
            continue
        for pat in patterns:
            if pat.lower() in col_low:
                return idx
    return None


def load_port_v_voltages(v_path):
    """
    Load port-V.csv using column-name matching (with positional fallback) and compute
    complex S-parameters for one or two ports.

    Returns: (freqs, s11_complex, s22_complex, s21_complex, s12_complex)
    """
    import numpy as np

    if not v_path or not os.path.exists(v_path) or os.path.getsize(v_path) == 0:
        return None, None, None, None, None

    with open(v_path, "r", encoding="utf-8") as f:
        first_line = f.readline()
    v_header = [h.strip().lstrip("#").strip() for h in first_line.split(",")]

    v_data = np.loadtxt(v_path, delimiter=",", skiprows=1)
    if v_data.size == 0:
        return None, None, None, None, None
    if v_data.ndim == 1:
        v_data = v_data.reshape(1, -1)

    ncols = v_data.shape[1]
    if ncols < 2:
        return None, None, None, None, None

    freqs = v_data[:, 0]

    v1_inc_idx = find_col_idx(v_header, ["v_inc[1]", "v_inc1", "vinc1", "v_inc_1"])
    v2_inc_idx = find_col_idx(v_header, ["v_inc[2]", "v_inc2", "vinc2", "v_inc_2"])

    v1_re_idx = find_col_idx(
        v_header,
        ["re{v[1]}", "re(v[1])", "v[1]_re", "re_v1", "v1r", "rev1", "re{v_1}", "v1_re"],
        exclude_patterns=["inc"],
    )
    v1_im_idx = find_col_idx(
        v_header,
        ["im{v[1]}", "im(v[1])", "v[1]_im", "im_v1", "v1i", "imv1", "im{v_1}", "v1_im"],
        exclude_patterns=["inc"],
    )
    v2_re_idx = find_col_idx(
        v_header,
        ["re{v[2]}", "re(v[2])", "v[2]_re", "re_v2", "v2r", "rev2", "re{v_2}", "v2_re"],
        exclude_patterns=["inc"],
    )
    v2_im_idx = find_col_idx(
        v_header,
        ["im{v[2]}", "im(v[2])", "v[2]_im", "im_v2", "v2i", "imv2", "im{v_2}", "v2_im"],
        exclude_patterns=["inc"],
    )

    # Positional fallback only when headers could not be matched
    if v1_inc_idx is None and v2_inc_idx is None and v1_re_idx is None and v2_re_idx is None:
        if ncols >= 7:
            v1_inc_idx, v1_re_idx, v1_im_idx, v2_inc_idx, v2_re_idx, v2_im_idx = 1, 2, 3, 4, 5, 6
        elif ncols == 6:
            v1_inc_idx, v1_re_idx, v1_im_idx, v2_re_idx, v2_im_idx = 1, 2, 3, 4, 5
        elif ncols >= 4:
            v1_inc_idx, v1_re_idx, v1_im_idx = 1, 2, 3
    elif v1_re_idx is None and v2_re_idx is None:
        if v1_inc_idx is not None and v2_inc_idx is not None and ncols >= 7:
            if v1_inc_idx == 1 and v2_inc_idx == 2:
                v1_re_idx, v1_im_idx, v2_re_idx, v2_im_idx = 3, 4, 5, 6
            else:
                v1_re_idx, v1_im_idx, v2_re_idx, v2_im_idx = 2, 3, 5, 6
        elif v1_inc_idx is not None and v2_inc_idx is None:
            if ncols >= 6:
                v1_re_idx, v1_im_idx, v2_re_idx, v2_im_idx = 2, 3, 4, 5
            elif ncols >= 4:
                v1_re_idx, v1_im_idx = 2, 3
        elif v2_inc_idx is not None and v1_inc_idx is None:
            if ncols >= 6:
                v1_re_idx, v1_im_idx, v2_re_idx, v2_im_idx = 2, 3, 4, 5
            elif ncols >= 4:
                v2_re_idx, v2_im_idx = 2, 3

    def _extract_complex(re_idx, im_idx):
        if re_idx is None or re_idx >= ncols:
            return None
        re_vals = v_data[:, re_idx]
        im_vals = v_data[:, im_idx] if (im_idx is not None and im_idx < ncols) else np.zeros_like(re_vals)
        return re_vals + 1j * im_vals

    v1 = _extract_complex(v1_re_idx, v1_im_idx)
    v2 = _extract_complex(v2_re_idx, v2_im_idx)

    v_inc1 = v_data[:, v1_inc_idx] if (v1_inc_idx is not None and v1_inc_idx < ncols) else None
    v_inc2 = v_data[:, v2_inc_idx] if (v2_inc_idx is not None and v2_inc_idx < ncols) else None

    has_vinc1 = v_inc1 is not None and np.any(np.abs(v_inc1) >= 1e-12)
    has_vinc2 = v_inc2 is not None and np.any(np.abs(v_inc2) >= 1e-12)

    s11_complex = None
    s22_complex = None
    s21_complex = None
    s12_complex = None

    if has_vinc1:
        safe_vinc1 = np.where(np.abs(v_inc1) < 1e-12, 1e-12, v_inc1)
        if v1 is not None:
            s11_complex = (v1 - v_inc1) / safe_vinc1
        if not has_vinc2 and v2 is not None:
            s21_complex = v2 / safe_vinc1

    if has_vinc2:
        safe_vinc2 = np.where(np.abs(v_inc2) < 1e-12, 1e-12, v_inc2)
        if v2 is not None:
            s22_complex = (v2 - v_inc2) / safe_vinc2
        if not has_vinc1 and v1 is not None:
            s12_complex = v1 / safe_vinc2

    return freqs, s11_complex, s22_complex, s21_complex, s12_complex


