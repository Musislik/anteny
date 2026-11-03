"""
Jednoduchý skript pro zabalení (export) interaktivní ParaView prezentace do jednoho ZIP archivu.

Použití:
    python scripts/export_package.py
    (automaticky vytvoří export s inkrementovaným číslem: export/antena_export_1.zip, export/antena_export_2.zip, ...)

Nebo se zadáním jména:
    python scripts/export_package.py moje_antena
    python scripts/export_package.py --name moje_antena.zip
    (pokud již soubor existuje, vytvoří se automaticky další s číslem 2 a výše: moje_antena_2.zip, moje_antena_3.zip, ...)
"""

import os
import sys
import shutil
import zipfile
import re
import argparse

try:
    import _env
except ImportError:
    try:
        import scripts._env
    except ImportError:
        pass
from postpro_utils import load_env, ensure_paraview_linked, get_export_dir


def get_next_default_export_path(export_dir, base_name="antena_export"):
    """
    Nalezne nejbližší volný název souboru s inkrementovaným číslem, např. antena_export_1.zip.
    """
    os.makedirs(export_dir, exist_ok=True)
    pattern = re.compile(rf"^{base_name}_(\d+)\.zip$", re.IGNORECASE)
    fallback_pattern = re.compile(r"^ante[nt]a_export_(\d+)\.zip$", re.IGNORECASE)

    existing_nums = []
    for fname in os.listdir(export_dir):
        m = pattern.match(fname) or fallback_pattern.match(fname)
        if m:
            existing_nums.append(int(m.group(1)))

    next_num = max(existing_nums, default=0) + 1
    while os.path.exists(os.path.join(export_dir, f"{base_name}_{next_num}.zip")):
        next_num += 1

    return os.path.join(export_dir, f"{base_name}_{next_num}.zip")


def resolve_export_path(root_dir, output_name=None, default_base="antena_export", export_dir=None):
    """
    Určí cílovou cestu k ZIP souboru podle konfigurace EXPORT_DIR z .env.
    - Pokud output_name není zadáno: vrací <export_dir>/antena_export_<N>.zip (od 1).
    - Pokud output_name je zadáno:
        - pokud soubor <name>.zip neexistuje, použije se <name>.zip
        - pokud soubor <name>.zip již existuje, vytvoří se <name>_2.zip, <name>_3.zip atd.
    """
    if export_dir is None:
        export_dir = get_export_dir(root_dir)
    os.makedirs(export_dir, exist_ok=True)

    if not output_name:
        return get_next_default_export_path(export_dir, default_base)

    if not os.path.isabs(output_name):
        dirname, basename = os.path.split(output_name)
        if dirname:
            target_dir = os.path.abspath(os.path.join(root_dir, dirname))
        else:
            target_dir = export_dir
    else:
        target_dir, basename = os.path.split(output_name)

    os.makedirs(target_dir, exist_ok=True)

    stem = basename[:-4] if basename.lower().endswith(".zip") else basename
    base_zip = os.path.join(target_dir, f"{stem}.zip")

    if not os.path.exists(base_zip):
        return base_zip

    # Soubor již existuje -> hledáme číslo 2 a výše
    pattern = re.compile(rf"^{re.escape(stem)}_(\d+)\.zip$", re.IGNORECASE)
    existing_nums = []
    for fname in os.listdir(target_dir):
        m = pattern.match(fname)
        if m:
            existing_nums.append(int(m.group(1)))

    next_num = max(existing_nums, default=1) + 1
    while os.path.exists(os.path.join(target_dir, f"{stem}_{next_num}.zip")):
        next_num += 1

    return os.path.join(target_dir, f"{stem}_{next_num}.zip")


def export_paraview_package(output_name=None, output_zip=None):
    root_dir, data_dir = load_env()
    os.chdir(root_dir)

    # Zajistíme propojení na poslední AMR iteraci
    ensure_paraview_linked(data_dir)

    target_name = output_name if output_name is not None else output_zip
    output_zip = resolve_export_path(root_dir, target_name)

    # 1. Kontrola dostupných dat v DATA_DIR
    postpro_dir = os.path.abspath(os.path.join(data_dir, "postpro"))
    boundary_dir = os.path.abspath(os.path.join(postpro_dir, "paraview", "driven_boundary"))
    has_boundary = os.path.exists(boundary_dir) and os.path.isdir(boundary_dir)

    s11_file = os.path.join(postpro_dir, "port-S.csv")
    step_file = os.path.join(data_dir, "antenna_model.step")
    config_file = os.path.join(data_dir, "config.json")

    has_any_data = (
        has_boundary
        or (os.path.exists(s11_file) and os.path.getsize(s11_file) > 0)
        or (os.path.exists(step_file) and os.path.getsize(step_file) > 0)
        or (os.path.exists(config_file) and os.path.getsize(config_file) > 0)
    )

    if not has_any_data:
        print(f"[CHYBA] Ve složce {data_dir} nebyla nalezena žádná výstupní simulační data ani CAD model.")
        print("Zkontrolujte parametr DATA_DIR v souboru .env nebo nejprve spusťte simulaci.")
        return False

    script_path = os.path.join(root_dir, "scripts", "paraview_dynamic_phase.py")

    # Příprava výstupní složky
    out_dir = os.path.dirname(output_zip)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # Dočasná exportní složka pro sestavení balíčku
    zip_stem = os.path.splitext(os.path.basename(output_zip))[0]
    temp_pack_dir = os.path.join(out_dir, f"{zip_stem}_temp")
    if os.path.exists(temp_pack_dir):
        shutil.rmtree(temp_pack_dir, ignore_errors=True)
    os.makedirs(temp_pack_dir, exist_ok=True)

    try:
        print(f"--- 1. Kopíruji soubory do balíčku z {data_dir} ---")

        # A) Skript pro ParaView a pomocné utility
        if has_boundary and os.path.exists(script_path):
            shutil.copy2(script_path, os.path.join(temp_pack_dir, "paraview_dynamic_phase.py"))
            print("  + paraview_dynamic_phase.py")

        utils_path = os.path.join(root_dir, "src", "postpro_utils.py")
        if os.path.exists(utils_path):
            shutil.copy2(utils_path, os.path.join(temp_pack_dir, "postpro_utils.py"))
            print("  + postpro_utils.py")

        # B) Simulační data povrchu (driven_boundary)
        if has_boundary:
            dest_boundary = os.path.join(temp_pack_dir, "driven_boundary")
            shutil.copytree(boundary_dir, dest_boundary)
            print("  + driven_boundary/ (kompletní 3D data všech frekvencí)")
        else:
            print("  i driven_boundary/ není k dispozici (simulace proběhla se SAVE_STEP=0, 3D pole nebyla ukládána)")

        # C) Doplňkové výsledky a klíčová data simulace
        gif_src = os.path.join(postpro_dir, "lhcp_rotation.gif")
        if os.path.exists(gif_src):
            shutil.copy2(gif_src, os.path.join(temp_pack_dir, "lhcp_rotation.gif"))
            print("  + lhcp_rotation.gif (náhledová animace)")

        # Důležité CSV a konfigurační výstupy z postpro
        important_postpro = [
            ("port-S.csv", "S-parametry / činitel odrazu S11"),
            ("farfield-rE.csv", "dálkové pole (zisk, LHCP/RHCP, osový poměr AR)"),
            ("port-V.csv", "napětí na budicím portu"),
            ("port-I.csv", "proud na budicím portu"),
            ("domain-E.csv", "energie a dielektrické ztráty v doménách"),
            ("error-indicators.csv", "indikátory chyb adaptivního zjemnění AMR"),
            ("config_resolved.json", "vyřešená konfigurace řešiče"),
            ("palace.json", "konfigurace FEM řešiče Palace"),
        ]
        for fname, desc in important_postpro:
            fsrc = os.path.join(postpro_dir, fname)
            if os.path.exists(fsrc) and os.path.getsize(fsrc) > 0:
                shutil.copy2(fsrc, os.path.join(temp_pack_dir, fname))
                print(f"  + {fname} ({desc})")

        # CAD STEP model, 2D graf S11 a vstupní konfigurace (z kořene složky data)
        extra_models = [
            ("antenna_model.step", "3D CAD model antény"),
            ("geometry_iso.png", "2D náhled geometrie antény"),
            ("S11_graf.png", "2D graf činitele odrazu S11"),
            ("config.json", "vstupní konfigurace FEM řešiče Palace"),
        ]
        for fname, desc in extra_models:
            fsrc = os.path.join(data_dir, fname)
            if os.path.exists(fsrc) and os.path.getsize(fsrc) > 0:
                shutil.copy2(fsrc, os.path.join(temp_pack_dir, fname))
                print(f"  + {fname} ({desc})")

        # D) Podrobný návod k použití a popis souborů (README.txt)
        if has_boundary:
            readme_content = """======================================================================
LHCP PATCH ANTENA — KOMPLETNÍ EXPORTNÍ BALÍČEK VÝSLEDKŮ
======================================================================

OBSAH BALÍČKU:
1. 3D Model a animace polí:
   - paraview_dynamic_phase.py  ... Řídicí makro pro ParaView
   - driven_boundary/           ... Kompletní FEM síť a 3D pole pro všechny frekvence
   - lhcp_rotation.gif          ... Rychlý náhled rotace pole
   - antenna_model.step         ... 3D CAD model geometrie (pro CAD / výrobu DPS)
   - geometry_iso.png           ... 2D náhled geometrie antény

2. Vysokofrekvenční parametry a vyzařování:
   - port-S.csv                 ... Průběh S11 napříč pásmem (amplituda v dB a fáze)
   - farfield-rE.csv            ... Vektorové dálkové pole (zisk, LHCP/RHCP, osový poměr AR)
   - port-V.csv, port-I.csv     ... Komplexní napětí a proud na portu (Zin = V / I)
   - domain-E.csv               ... Energie pole a ztráty v dielektriku / vzduchu
   - S11_graf.png               ... Graf S11 s vyznačenou mezí -10 dB

3. Konfigurace a vygenerované grafy:
   - config.json                ... Vstupní konfigurace řešiče pro reprodukovatelnost
   - config_resolved.json       ... Vyřešená konfigurace řešiče (pokud existuje)
   - graf_S_parametry.png        ... Graf S11, S22 a vstupní impedance portů Zin
   - vyzarovaci_diagram_2d.png   ... 2D polární diagramy řezů X-Z a Y-Z (LHCP/RHCP) + AR
   - vyzarovaci_diagram_3d.png   ... 3D prostorový vyzařovací diagram v dBi

JAK ZOBRAZIT INTERAKTIVNÍ MODEL V PARAVIEW:
1. Otevřete ParaView.
2. V horním menu zvolte: Tools -> Python Shell -> Run Script
3. Vyberte soubor: paraview_dynamic_phase.py (přímo z této složky)
4. Posuvníkem přepínejte frekvenci, tlačítkem PLAY spusťte rotaci fáze.

JAK PŘEGENEROVAT GRAFY (pomocí skriptů ze složky scripts/):
1. S-parametry a impedance:
   python scripts/plot_s_parameters.py export/<slozka_exportu>
2. 2D a 3D vyzařovací diagram:
   python scripts/plot_radiation_pattern.py export/<slozka_exportu> --freq 2.333
======================================================================
"""
        else:
            readme_content = """======================================================================
LHCP PATCH ANTENA — EXPORTNÍ BALÍČEK VÝSLEDKŮ (BEZ 3D POLÍ)
======================================================================

POZNÁMKA:
Balíček byl vygenerován z běhu s parametrem SAVE_STEP=0 (rychlý výpočet S-parametrů
a dálkového pole bez ukládání 3D prostorových polí pro ParaView).

OBSAH BALÍČKU:
1. Vysokofrekvenční parametry a vyzařování:
   - port-S.csv                 ... Průběh S11 napříč pásmem (amplituda v dB a fáze)
   - farfield-rE.csv            ... Vektorové dálkové pole (zisk, LHCP/RHCP, osový poměr AR)
   - port-V.csv, port-I.csv     ... Komplexní napětí a proud na portu (Zin = V / I)
   - domain-E.csv               ... Energie pole a ztráty v dielektriku / vzduchu
   - S11_graf.png               ... Graf S11 s vyznačenou mezí -10 dB

2. Geometrie a modely:
   - antenna_model.step         ... 3D CAD model geometrie (pro CAD / výrobu DPS)
   - geometry_iso.png           ... 2D náhled geometrie antény
   - config.json                ... Vstupní konfigurace řešiče pro reprodukovatelnost
   - config_resolved.json       ... Vyřešená konfigurace řešiče (pokud existuje)
======================================================================
"""
        with open(os.path.join(temp_pack_dir, "README.txt"), "w", encoding="utf-8") as f:
            f.write(readme_content)
        print("  + README.txt (návod k použití a popis souborů)")

        # 2. Vytvoření ZIP archivu
        print(f"--- 2. Komprimuji do ZIP archivu: {output_zip} ---")
        if os.path.exists(output_zip):
            os.remove(output_zip)

        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(temp_pack_dir):
                for file in files:
                    abs_path = os.path.join(root, file)
                    rel_path = os.path.relpath(abs_path, temp_pack_dir)
                    zf.write(abs_path, rel_path)

        zip_size_mb = os.path.getsize(output_zip) / (1024 * 1024)

        print("======================================================================")
        print("BALÍČEK BYL ÚSPĚŠNĚ VYTVOŘEN!")
        print(f"ZIP archiv k odeslání/archivaci:")
        print(f"   -> {os.path.abspath(output_zip)} ({zip_size_mb:.1f} MB)")
        print("Dočasná nezazipovaná složka byla smazána.")
        print("======================================================================")
        return True
    finally:
        # 3. Úklid dočasné rozbalené složky
        if os.path.exists(temp_pack_dir):
            shutil.rmtree(temp_pack_dir, ignore_errors=True)
            print(f"--- 3. Nezazipovaná složka {os.path.basename(temp_pack_dir)} byla smazána ---")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Zabalení interaktivní ParaView prezentace do ZIP archivu."
    )
    parser.add_argument(
        "filename",
        nargs="?",
        default=None,
        help="Volitelné jméno výstupního zip souboru (např. moje_antena nebo moje_antena.zip).",
    )
    parser.add_argument(
        "-n",
        "--name",
        dest="name",
        default=None,
        help="Specifikace jména výstupního zip souboru.",
    )
    args = parser.parse_args()
    target_name = args.name or args.filename
    export_paraview_package(output_name=target_name)
