#!/usr/bin/env python3
"""
export_gerber.py - Skript pro automatizovaný export výrobních podkladů Gerber a vrtacích (drill) souborů.

Podporuje:
  1. Lokální běh přes 'kicad-cli' (pokud je KiCad 8 nainstalován na hostiteli).
  2. Běh v Docker kontejneru přes 'docker compose' (obraz kicad/kicad:8.0, profil kicad-export).
  3. Automatické zabalení do ZIP archivu připraveného k odeslání do výroby (JLCPCB, PCBWay, Eurocircuits).
  4. Automatické předgenerování .kicad_pcb souboru, pokud ještě neexistuje.

Použití:
    python3 scripts/export_gerber.py
    python3 scripts/export_gerber.py --output-dir export/kicad/gerber/
    python3 scripts/export_gerber.py --force-docker
    python3 scripts/export_gerber.py --dry-run
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile
from typing import Any, Dict, List, Optional, Tuple

# Automatické nastavení sys.path pro import z src/ a scripts/
try:
    import _env  # noqa: F401
except ImportError:
    try:
        import scripts._env  # noqa: F401
    except ImportError:
        pass

from postpro_utils import get_export_dir, get_project_root, load_env


def find_kicad_runner(force_docker: bool = False) -> Tuple[str, List[str]]:
    """
    Detekuje, zda je k dispozici lokální 'kicad-cli' nebo Docker Compose.
    Vrací tuple (runner_type, base_cmd):
      - ("local", ["kicad-cli"])
      - ("docker", ["docker", "compose", "--profile", "kicad-export", "run", "--rm", "kicad"])
      - ("none", [])
    """
    if not force_docker and shutil.which("kicad-cli") is not None:
        return ("local", ["kicad-cli"])

    docker_bin = shutil.which("docker")
    if docker_bin is not None:
        return ("docker", [docker_bin, "compose", "--profile", "kicad-export", "run", "--rm", "kicad"])

    return ("none", [])


def sanitize_docker_env() -> Dict[str, str]:
    """
    Připraví proměnné prostředí pro Docker Compose.
    Pokud běžíme na Linuxu a EXPORT_DIR obsahuje Windows drive písmeno (např. D:\\...),
    nahradí jej bezpečnou relativní cestou './export'.
    """
    env = os.environ.copy()
    export_dir = env.get("EXPORT_DIR", "")
    if sys.platform != "win32" and len(export_dir) >= 2 and export_dir[1] == ":" and export_dir[0].isalpha():
        env["EXPORT_DIR"] = "./export"
    conf_dir = env.get("CONF_DIR", "")
    if sys.platform != "win32" and len(conf_dir) >= 2 and conf_dir[1] == ":" and conf_dir[0].isalpha():
        env["CONF_DIR"] = "."
    return env


def map_path_to_container(host_path: str, root_dir: str) -> str:
    """
    Převede absolutní nebo relativní cestu hostitele na cestu uvnitř Docker kontejneru (/workspace/...).
    """
    abs_host = os.path.abspath(host_path)
    abs_root = os.path.abspath(root_dir)

    try:
        rel = os.path.relpath(abs_host, abs_root)
        if not rel.startswith(".."):
            return f"/workspace/{rel.replace(os.sep, '/')}"
    except ValueError:
        pass

    # Fallback pokud cesta leží mimo root
    basename = os.path.basename(host_path)
    return f"/workspace/export/kicad/{basename}"


def ensure_pcb_exists(pcb_path: str, root_dir: str) -> bool:
    """
    Ověří existenci .kicad_pcb souboru. Pokud neexistuje, pokusí se jej vygenerovat
    pomocí scripts/export_kicad.py.
    """
    if os.path.exists(pcb_path):
        return True

    print(f"Soubor DPS '{pcb_path}' nebyl nalezen. Spouštím generování pomocí export_kicad.py ...")
    export_script = os.path.join(root_dir, "scripts", "export_kicad.py")
    if not os.path.exists(export_script):
        print(f"CHYBA: Generovací skript '{export_script}' nebyl nalezen.", file=sys.stderr)
        return False

    pcb_dir = os.path.dirname(os.path.abspath(pcb_path))
    cmd = [sys.executable, export_script, "--output-dir", pcb_dir, "--pcb"]
    res = subprocess.run(cmd, cwd=root_dir)
    return res.returncode == 0 and os.path.exists(pcb_path)


def package_gerbers_zip(output_dir: str, zip_filename: Optional[str] = None) -> Optional[str]:
    """
    Zabalí všechny Gerber a Drill soubory ve výstupní složce do přehledného ZIP archivu.
    Vrací cestu k vytvořenému ZIP souboru.
    """
    if not os.path.exists(output_dir):
        return None

    valid_exts = {".gbr", ".gerber", ".drl", ".xln", ".gbrjob", ".pdf", ".txt"}
    files_to_zip = [
        f for f in os.listdir(output_dir)
        if os.path.splitext(f)[1].lower() in valid_exts and os.path.isfile(os.path.join(output_dir, f))
    ]

    if not files_to_zip:
        return None

    if zip_filename is None:
        zip_filename = "antenna_model4_fabrication.zip"

    zip_path = os.path.join(output_dir, zip_filename)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname in sorted(files_to_zip):
            fpath = os.path.join(output_dir, fname)
            zf.write(fpath, arcname=fname)

    return zip_path


def run_export(
    pcb_path: str,
    output_dir: str,
    include_drill: bool = True,
    create_zip: bool = True,
    force_docker: bool = False,
    dry_run: bool = False,
) -> int:
    """
    Hlavní orchestrační funkce pro export Gerberů a vrtacích dat.
    """
    root_dir = get_project_root()
    pcb_path = os.path.abspath(pcb_path)
    output_dir = os.path.abspath(output_dir)

    print("=" * 80)
    print(" AUTOMATIZOVANÝ EXPORT VÝROBNÍCH PODKLADŮ GERBER A DRILL (KICAD 8)")
    print("=" * 80)
    print(f"Vstupní DPS:     {pcb_path}")
    print(f"Cílová složka:   {output_dir}")

    # 1. Kontrola a případné vygenerování PCB
    if not dry_run:
        if not ensure_pcb_exists(pcb_path, root_dir):
            print(f"CHYBA: Nepodařilo se najít ani vygenerovat soubor DPS '{pcb_path}'.", file=sys.stderr)
            return 1
        os.makedirs(output_dir, exist_ok=True)

    # 2. Detekce runneru (lokální vs Docker)
    runner_type, runner_cmd = find_kicad_runner(force_docker=force_docker)
    if runner_type == "none":
        print("\nCHYBA: Nebyl nalezen žádný nástroj pro běh KiCad CLI:", file=sys.stderr)
        print("  1. 'kicad-cli' není nainstalován v systému (PATH).", file=sys.stderr)
        print("  2. 'docker' není nainstalován ani spuštěn pro běh v kontejneru.", file=sys.stderr)
        print("\nPro export nainstalujte KiCad 8 nebo spusťte Docker daemon.", file=sys.stderr)
        return 2

    print(f"Zvolený runner:  {runner_type.upper()} ({' '.join(runner_cmd)})")
    print("-" * 80)

    # 3. Příprava příkazů
    env = sanitize_docker_env() if runner_type == "docker" else os.environ.copy()

    if runner_type == "local":
        gerber_cmd = [
            "kicad-cli", "pcb", "export", "gerbers",
            "--output", output_dir,
            pcb_path,
        ]
        drill_cmd = [
            "kicad-cli", "pcb", "export", "drill",
            "--output", output_dir,
            "--format", "excellon",
            "--drill-origin", "absolute",
            pcb_path,
        ] if include_drill else None

        cmds_to_run = [("Gerber vrstvy", gerber_cmd)]
        if drill_cmd:
            cmds_to_run.append(("Vrtací data (Drill Excellon)", drill_cmd))

        for desc, cmd in cmds_to_run:
            print(f"Spouštím: {desc} ...")
            print(f"  $ {' '.join(cmd)}")
            if dry_run:
                continue
            res = subprocess.run(cmd, cwd=root_dir)
            if res.returncode != 0:
                print(f"CHYBA: Příkaz pro '{desc}' selhal s kódem {res.returncode}.", file=sys.stderr)
                return res.returncode

    else:
        # Docker runner - převedeme cesty na /workspace/...
        c_output = map_path_to_container(output_dir, root_dir)
        c_pcb = map_path_to_container(pcb_path, root_dir)

        # Spustíme gerbery i drill v jednom běhu kontejneru pro maximální rychlost
        shell_inner = f"kicad-cli pcb export gerbers --output {c_output} {c_pcb}"
        if include_drill:
            shell_inner += f" && kicad-cli pcb export drill --output {c_output} --format excellon --drill-origin absolute {c_pcb}"

        docker_full_cmd = runner_cmd + ["sh", "-c", shell_inner]
        print("Spouštím KiCad v Docker kontejneru (Gerber + Drill) ...")
        print(f"  $ {' '.join(docker_full_cmd)}")

        if dry_run:
            print("\n[Dry-run] Příkaz nebyl spuštěn.")
            return 0

        res = subprocess.run(docker_full_cmd, cwd=root_dir, env=env)
        if res.returncode != 0:
            print(f"CHYBA: Spuštění Docker kontejneru selhalo s kódem {res.returncode}.", file=sys.stderr)
            return res.returncode

    # 4. Zabalení do ZIP archivu
    if create_zip and not dry_run:
        print("\nBalím výrobní podklady do ZIP archivu ...")
        zip_path = package_gerbers_zip(output_dir)
        if zip_path:
            zip_size = os.path.getsize(zip_path)
            print(f"  -> Vytvořen výrobní archiv: {zip_path} ({zip_size} B)")
        else:
            print("  Upozornění: Ve složce nebyly nalezeny žádné soubory pro zabalení.")

    # 5. Rekapitulace vygenerovaných souborů
    if not dry_run and os.path.exists(output_dir):
        print("-" * 80)
        print(" PŘEHLED VYGENEROVANÝCH VÝROBNÍCH SOUBORŮ:")
        print("-" * 80)
        for fname in sorted(os.listdir(output_dir)):
            fpath = os.path.join(output_dir, fname)
            if os.path.isfile(fpath):
                size = os.path.getsize(fpath)
                print(f"  - {fname:<40} ({size:>8} B)")

    print("=" * 80)
    print(" Export výrobních podkladů byl úspěšně dokončen.")
    print("=" * 80)
    return 0


def main() -> int:
    root_dir, _ = load_env()
    default_pcb_path = os.path.join(get_export_dir(root_dir), "kicad", "antenna_model4.kicad_pcb")
    default_gerber_dir = os.path.join(get_export_dir(root_dir), "kicad", "gerber")

    parser = argparse.ArgumentParser(
        description="Automatizovaný export Gerber a vrtacích (drill) souborů pro KiCad 8 (lokálně nebo přes Docker)."
    )
    parser.add_argument(
        "--pcb",
        default=default_pcb_path,
        help=f"Cesta k souboru .kicad_pcb (výchozí: {default_pcb_path})",
    )
    parser.add_argument(
        "--output-dir",
        default=default_gerber_dir,
        help=f"Cílová složka pro Gerber soubory (výchozí: {default_gerber_dir})",
    )
    parser.add_argument(
        "--no-drill",
        action="store_true",
        help="Přeskočit export vrtacích dat (drill)",
    )
    parser.add_argument(
        "--no-zip",
        action="store_true",
        help="Nevytvářet finální výrobní ZIP archiv",
    )
    parser.add_argument(
        "--force-docker",
        action="store_true",
        help="Vynutit běh přes Docker Compose i v případě přítomnosti lokálního kicad-cli",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Pouze vypsat příkazy bez jejich skutečného spuštění",
    )

    args = parser.parse_args()

    return run_export(
        pcb_path=args.pcb,
        output_dir=args.output_dir,
        include_drill=not args.no_drill,
        create_zip=not args.no_zip,
        force_docker=args.force_docker,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
