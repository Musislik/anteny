"""
Jednoduchý skript pro zabalení (export) interaktivní ParaView prezentace do jednoho ZIP archivu.

Použití:
    python scripts/export_package.py
Nebo:
    python scripts/export_package.py moje_antena.zip
"""

import os
import sys
import shutil
import zipfile

def export_paraview_package(output_zip="export/antena_paraview_balicek.zip"):
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_dir)

    # 1. Nalezení zdrojových dat
    boundary_dir = os.path.join("data", "postpro", "paraview", "driven_boundary")

    if not os.path.exists(boundary_dir):
        print(f"[CHYBA] Složka se simulovanými daty nebyla nalezena: {boundary_dir}")
        print("Nejprve spusťte simulaci (např. python src/main.py).")
        return False

    script_path = os.path.join("scripts", "paraview_dynamic_phase.py")
    if not os.path.exists(script_path):
        print(f"[CHYBA] Skript {script_path} nebyl nalezen!")
        return False

    # Příprava výstupní složky
    out_dir = os.path.dirname(output_zip)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # Dočasná exportní složka pro sestavení balíčku
    temp_pack_dir = os.path.join(out_dir, "antena_paraview")
    if os.path.exists(temp_pack_dir):
        shutil.rmtree(temp_pack_dir)
    os.makedirs(temp_pack_dir, exist_ok=True)

    print(f"--- 1. Kopíruji soubory do balíčku ---")

    # A) Skript pro ParaView
    shutil.copy2(script_path, os.path.join(temp_pack_dir, "paraview_dynamic_phase.py"))
    print("  + paraview_dynamic_phase.py")

    # B) Simulační data povrchu (driven_boundary)
    dest_boundary = os.path.join(temp_pack_dir, "driven_boundary")
    shutil.copytree(boundary_dir, dest_boundary)
    print(f"  + driven_boundary/ (kompletní 3D data všech frekvencí)")

    # C) Doplňkové výsledky (GIF animace a S-parametry, pokud existují)
    gif_src = os.path.join("data", "postpro", "lhcp_rotation.gif")
    if os.path.exists(gif_src):
        shutil.copy2(gif_src, os.path.join(temp_pack_dir, "lhcp_rotation.gif"))
        print("  + lhcp_rotation.gif (náhledová animace)")

    s11_src = os.path.join("data", "postpro", "port-S.csv")
    if os.path.exists(s11_src):
        shutil.copy2(s11_src, os.path.join(temp_pack_dir, "port-S.csv"))
        print("  + port-S.csv (tabulka S11)")

    # D) Jednoduchý návod k použití (README.txt)
    readme_content = """======================================================================
LHCP PATCH ANTENA — INTERAKTIVNI PARAVIEW PREZENTACE
======================================================================

OBSAH SLOZKY:
- paraview_dynamic_phase.py  ... Ridici skript pro ParaView
- driven_boundary/           ... Kompletni FEM simulace z resice Palace
- lhcp_rotation.gif          ... Rychly nahled rotace pole
- port-S.csv                 ... Prubeh S11 napric pasmem

JAK ZOBRAZIT INTERAKTIVNI MODEL V PARAVIEW:
1. Otevrete ParaView (libovolna verze 5.x nebo 6.x).
2. V hornim menu zvolte:
      Tools -> Python Shell -> Run Script
3. Vyberte soubor:
      paraview_dynamic_phase.py (primo z teto slozky)

OVLADANI:
- Posuvnik dole ve 3D okne: prepina frekvenci (2.320 az 2.345 GHz)
- Tlacitko PLAY [ > ] v horni liste: spusti plynulou rotaci faze (0 az 360 stupnu)
======================================================================
"""
    with open(os.path.join(temp_pack_dir, "README.txt"), "w", encoding="utf-8") as f:
        f.write(readme_content)
    print("  + README.txt (návod k použití)")

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
    print(f"1. ZIP archiv k odeslání/archivaci:")
    print(f"   -> {os.path.abspath(output_zip)} ({zip_size_mb:.1f} MB)")
    print(f"2. Připravená rozbalená složka k okamžitému použití:")
    print(f"   -> {os.path.abspath(temp_pack_dir)}")
    print("======================================================================")
    return True

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "export/antena_paraview_balicek.zip"
    export_paraview_package(out)
