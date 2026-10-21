# 📡 Anténní Simulační Pipeline

Tento projekt poskytuje plně kontejnerizovaný nástroj pro parametrický návrh, simulaci a analýzu mikrovlnných patch antén. O návrh geometrie se stará **OpenCASCADE**, o síťování **Gmsh**, fyzikální simulace běží v řešiči **Palace** a výsledky jsou automaticky sledovány přes **MLflow**.

Veškeré skripty a závislosti běží izolovaně v Dockeru, takže lokálně ve Windows nepotřebujete řešit žádné instalace Python balíčků.

---

## 🛠 Požadavky na systém
1. **Docker Desktop** (s povoleným WSL2 nebo Hyper-V) – pro běh simulací a MLflow.
2. **ParaView** (nainstalováno ve Windows) – pro 3D vizualizaci elektromagnetických polí.
3. **[METAS VNA Data Explorer](https://www.metas.ch/vnatools)** (nainstalováno ve Windows) – pro detailní interaktivní prohlížení S-parametrů a Smithových diagramů.

---

## 🚀 1. Spuštění vizualizačního serveru (MLflow)
Před spouštěním simulací je ideální zapnout server pro sběr dat (MLflow).
Otevřete terminál v této složce a zadejte:

```powershell
docker compose up -d mlflow
```

* Dashboard s výsledky následně otevřete v prohlížeči na adrese: **[http://localhost:5000](http://localhost:5000)**

---

## ⚡ 2. Spouštění simulací
Simulace se spouští zevnitř kontejneru `pipeline`, který si sám zorganizuje přípravu dat (Gmsh) a zavolání kontejneru s výpočetním řešičem (Palace).

**Pro spuštění jedné simulace (s výchozími parametry):**
```powershell
docker compose run --rm pipeline python main.py
```

**Pro spuštění dávkového výpočtu (Sweep) pro různé rozměry antény:**
```powershell
docker compose run --rm pipeline python sweep.py
```
*Tento skript automaticky projde předem definované délky patche a výsledky zanese do MLflow, kde si je můžete hezky graficky porovnat (překrývání křivek).*

---

## 📊 3. Analýza výsledků

Projekt je navržen tak, aby se o výsledky staraly 3 specializované nástroje:

### A) Rychlé srovnání parametrů (MLflow)
*   Podívejte se na [http://localhost:5000](http://localhost:5000).
*   Najdete zde klíčové metriky pro každý běh (Rezonanční frekvence $f_0$, Minimální odraz $S_{11}$, Šířka pásma) a v záložce artefaktů vygenerovaný PNG graf.

### B) Profesionální RF analýza (METAS VNA)
*   Surové S-parametry se ukládají do složky `postpro/` jako soubory typu `.s1p`.
*   Otevřete **METAS VNA Data Explorer** a jednoduše do něj tyto soubory přetáhněte myší.
*   Získáte perfektní zobrazení fázových posunů a interaktivní Smithův diagram bez nutnosti psát pro to vlastní kód.

### C) 3D Vizualizace EM polí (ParaView)
Simulátor generuje `.vtu` soubory prostorových polí do složky `postpro/paraview/driven/`. Pro usnadnění práce byl připraven makro-skript, který jedním kliknutím nastaví hezkou vizuální scénu (řezy a barvy).

1. Otevřete 3D výsledky ve Windows přes **ParaView**.
2. Skript můžete spustit přes **Tools -> Python Shell -> Run Script** (vyberte [paraview_macro.py](file:///d:/code/anteny/paraview_macro.py)), nebo si jej přidat do lišty přes **Macros -> Add new macro...**.
3. Cesta k projektu je v souboru definována proměnnou `PROJECT_DIR = r"D:\code\anteny"`, kterou skript při spuštění nastaví jako aktuální pracovní adresář (`os.chdir`).
4. Skript automaticky načte `.vtu` soubor, aplikuje řezy v rovině patche, zprůhlední vzduchový box a obarví elektrické pole (`E_real`) paletou *Cool to Warm*.

---

## 📁 Struktura klíčových souborů
*   `main.py` / `sweep.py` - Hlavní řídící skripty simulace.
*   `tracker.py` - Propojení na databázi MLflow a výpočet rezonance.
*   `geometry.py` - Definuje tvary antény pomocí knihovny OpenCASCADE (CAD).
*   `mesh.py` - Stará se o vygenerování výpočetní tetrahedral sítě (Gmsh).
*   `runner.py` / `palace_builder.py` - Spouští řešič (simulovaný přes `mock_palace.py`).
*   `paraview_macro.py` - Automatizační makro pro 3D ParaView.
*   `docker-compose.yml` - Definuje izolované prostředí pro běh celého řešení.
*   `docs/known_issues.md` - Odškrtávací seznam známých nedostatků a naplánovaných úkolů.
