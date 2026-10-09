Ran command: List repository files (`Get-ChildItem -Recurse -File | Select-Object -First 100 FullName`)
Ran command: Find source and doc files (`Get-ChildItem -Path . -Recurse -Include *.py,*.md,*.txt,*.json,*.toml,*.yaml,*.yml | Where-Object { $_.FullName -notmatch "mlruns" -and $_.FullName -notmatch "\.system" } | Select-Object FullName`)
Viewed abstrakce_zadani.md:1-36
Ran command: List docs directory (`Get-ChildItem docs`)
Viewed report.md:1-107
Viewed d:\code\anteny\docs\smrnice.md:2-201
Ran command: Check exact filename in docs (`Get-ChildItem docs | Select-Object Name, Length`)
Ran command: Read smernice.md via powershell (`Get-Content (Get-ChildItem docs/*sm*rnice.md).FullName -Raw -Encoding utf8`)
Ran command: Read Zadání.pdf (`python -c "import pypdf; reader = pypdf.PdfReader('docs/Zadání.pdf'); print(''.join([page.extract_text() for page in reader.pages]))"`)
Ran command: Read Zadání.pdf with utf-8 (`python -c "import pypdf, sys; sys.stdout.reconfigure(encoding='utf-8'); reader = pypdf.PdfReader('docs/Zadání.pdf'); print(''.join([page.extract_text() for page in reader.pages]))"`)
Viewed config.json:1-81
Viewed geometry.py:1-90
Ran command: Check napajeni.png image info (`python -c "from PIL import Image; img = Image.open('docs/napajeni.png'); print(img.size, img.format)"`)
Viewed napajeni.png:1-800
Viewed mesh.py:1-79
Viewed palace_builder.py:1-74
Viewed mock_palace.py:1-91
Viewed visualization.py:1-81
Viewed tracker.py:1-78
Viewed sweep.py:1-38
Viewed plot_efield.py:1-47
Viewed runner.py:1-33
Viewed paraview_macro.py:1-78
Viewed main.py:1-98
Viewed docker-compose.yml:1-36
Viewed README.md:1-75

Byl proveden detailní audit veškerých výpočtů, geometrických relací, RF formulí a programového kódu napříč celým projektem. V souladu se zadáním **nebyly zatím prováděny žádné změny v souborech**.

Níže je uveden systematický soupis chyb rozdělený do kategorií s důrazem na **fyzikální správnost, jednotky a eliminaci magických čísel**.

---

## 1. Souhrnný přehled závažnosti

```
┌────────────────────────────────────────────────────────────────────────┐
│                        KLASIFIKACE NALEZENÝCH CHYB                     │
├─────────────────────────┬──────┬───────────────────────────────────────┤
│ Kategorie               │ Počet│ Dopad                                 │
├─────────────────────────┼──────┼───────────────────────────────────────┤
│ Kritické geometrické    │  2   │ Fyzické rozpojení napáječe a flíčku   │
│ RF a elektromagnetické  │  4   │ Špatná fázová délka, polarizace, Z0   │
│ Metriky a vyhodnocení   │  3   │ Falešné určení šířky pásma a pokrytí  │
│ Štábní kultura / Čísla  │ 18+  │ Tvrdě zakódovaná čísla bez odvození   │
└─────────────────────────┴──────┴───────────────────────────────────────┘
```

---

## 2. Kritické geometrické a topologické chyby

### Chyba 1: Fyzická mezera (rozpojení obvodu) mezi napáječem a flíčkem
* **Kde:** [`geometry.py` (řádky 52 a 60)](file:///d:/code/anteny/geometry.py#L52-L60)
* **Kód:**
  ```python
  # Pravá větev k dolní hraně:
  f_r_v = gmsh.model.occ.addRectangle(-feed_W/2, y_T - feed_W/2, h, feed_W, abs(y_T) - L/2)
  # Levá větev k levé hraně:
  f_l_h2 = gmsh.model.occ.addRectangle(x_L - feed_W/2, -feed_W/2, h, abs(x_L) - W/2, feed_W)
  ```
* **Výpočetní chyba:**
  * Dolní hrana flíčku leží na $y = -L/2$.
  * Obdélník `f_r_v` začíná na $y_{\text{start}} = y_T - \text{feed\_W}/2$ a má výšku $\Delta y = |y_T| - L/2 = -y_T - L/2$. Jeho horní souřadnice končí na:
    $$y_{\text{end}} = y_{\text{start}} + \Delta y = \left(y_T - \frac{\text{feed\_W}}{2}\right) + \left(-y_T - \frac{L}{2}\right) = -\frac{L}{2} - \frac{\text{feed\_W}}{2}$$
  * Mezi koncem přívodního pásku a flíčkem vzniká **prázdná vzduchová mezera o velikosti $\frac{\text{feed\_W}}{2} = 1.5\text{ mm}$**.
  * Zcela identická mezera $1.5\text{ mm}$ vzniká u levé větve `f_l_h2` na souřadnici $x = -W/2 - \text{feed\_W}/2$.
* **Důsledek:** Obě napájecí větve končí ve vzduchu. Flíček je galvanicky odpojen od portu (rozpojené vedení naprázdno).

---

## 3. Elektromagnetické a vysokofrekvenční výpočty

### Chyba 2: Chybný výpočet vlnové délky $\lambda_g$ pro napájecí mikropásek
* **Kde:** [`geometry.py` (řádky 31–38)](file:///d:/code/anteny/geometry.py#L31-L38)
* **Kód:**
  ```python
  eps_eff = (eps_r + 1) / 2 + (eps_r - 1) / 2 / np.sqrt(1 + 12 * h / W)
  delta_L = 0.412 * h * (eps_eff + 0.3) * (W/h + 0.264) / ((eps_eff - 0.258) * (W/h + 0.8))
  L_eff = L + 2 * delta_L
  lambda_g_4 = L_eff / 2.0
  ```
* **Výpočetní chyba:**
  1. Efektivní permitivita $\varepsilon_{\text{eff}}$ pro zpožďovací vedení je počítána ze šířky **flíčku** ($W \approx 30.8\text{ mm} \implies \varepsilon_{\text{eff,patch}} \approx 3.96$).
  2. Zpožďovací čtvrtvlnné vedení je však **úzký mikropásek** se šířkou $w = \text{feed\_W} = 3.0\text{ mm}$ ($w/h \approx 1.97 \implies \varepsilon_{\text{eff,line}} \approx 3.27$).
  3. Správná hodnota čtvrtvlnné délky mikropásku při $f_c = 2.3325\text{ GHz}$:
     $$\lambda_{g,\text{line}}/4 = \frac{c_0}{4 f_c \sqrt{\varepsilon_{\text{eff,line}}}} \approx \frac{299.792}{4 \cdot 2.3325 \cdot \sqrt{3.27}} \approx 17.77\text{ mm}$$
  4. V kódu je ale $\lambda_g/4 \approx L_{\text{eff}}/2 = 16.10\text{ mm}$.
* **Důsledek:** Chyba v délce činí $1.67\text{ mm}$ (odchylka téměř $10\,\%$). Fázový posun mezi ortogonálními buzeními nebude $-90^\circ$, ale přibližně $-81.5^\circ$, což způsobí degradaci osového poměru ($AR > 3\text{ dB}$).
* **Závislost v parametrickém sweepu:** Při změně délky flíčku $L$ v [`sweep.py`](file:///d:/code/anteny/sweep.py#L17) se tímto vzorcem mění i délka zpožďovacího úseku, ačkoliv fázové zpoždění má být vázáno striktně na střední kmitočet pásma $f_c = 2.3325\text{ GHz}$, nikoliv na geometrii flíčku.

---

### Chyba 3: Smysl kruhové polarizace (LHCP vs. RHCP dle IEEE)
* **Kde:** [`geometry.py` (řádky 40–60)](file:///d:/code/anteny/geometry.py#L40-L60)
* **Fyzikální rozbor:**
  * Zářič leží v rovině $xy$ a vyzařuje do poloprostoru $+z$.
  * Pravá větev budí hranu $(0, -L/2)$ v ose $y$ s fází $0^\circ \implies E_y(t) = E_0 \cos(\omega t)$.
  * Levá větev budí hranu $(-W/2, 0)$ v ose $x$ se zpožděním $-90^\circ \implies E_x(t) = E_0 \sin(\omega t)$.
  * Při pohledu ve směru šíření vlny ($+z$) se vektor $\vec{E}$ v čase stáčí od $+y$ k $+x$ (**po směru hodinových ručiček**).
  * Dle IEEE standardu představuje otáčení po směru hodinových ručiček ve směru šíření **pravotočivou polarizaci (RHCP)**. Zadání č. 22 striktně požaduje **levotočivou polarizaci (LHCP)** (ve směru šíření proti směru hodinových ručiček).
  * Vzniká tak záměna polarizace (opačný smysl).

---

### Chyba 4: Chybějící impedanční přizpůsobení napájecí sítě
* **Kde:** [`geometry.py`](file:///d:/code/anteny/geometry.py), [`main.py`](file:///d:/code/anteny/main.py)
* **Fyzikální rozbor:**
  * Veškeré úseky vedení mají konstantní šířku `feed_W = 3.0 mm` ($Z_0 \approx 50\,\Omega$).
  * Dvě paralelní větve $50\,\Omega$ spojené v T-uzlu dávají vstupní impedanci uzlu:
    $$Z_{\text{node}} = 50\,\Omega \parallel 50\,\Omega = 25\,\Omega$$
  * Vstupní $50\,\Omega$ vedení připojené přímo k uzlu vykazuje činitel odrazu $|\Gamma| \ge 0.33$ ($S_{11} \approx -9.5\text{ dB}$) jen v samotném uzlu.
  * Navíc vstupní impedance okraje flíčku $R_{\text{edge}}$ je typicky $150\ \Omega$ až $300\ \Omega$. Přímé napojení $50\,\Omega$ pásku na okraj flíčku bez čtvrtvlnného transformátoru či zářezu (inset feed) způsobí výrazné nepřizpůsobení ($S_{11} > -5\text{ dB}$). V předloze [napajeni.png](file:///d:/code/anteny/docs/napajeni.png) jsou jasně vyznačeny impedanční transformátory $\lambda/4$ různé šířky.

---

### Chyba 5: Matematický model $S_{11}$ v mock solveru
* **Kde:** [`mock_palace.py` (řádek 42)](file:///d:/code/anteny/mock_palace.py#L42)
* **Kód:**
  ```python
  delta = (freq - f_res) / f_res
  S11 = (1j * 2 * Q * delta) / (1 + 1j * 2 * Q * delta)
  ```
* **Chyba ve vzorci:**
  * Pro paralelní rezonanční obvod zatížený impedancí $Z_0$ je admittance $Y \approx G + j 2 Q G \delta$.
  * Činitel odrazu:
    $$\Gamma = \frac{Y_0 - Y}{Y_0 + Y} = \frac{1 - (1 + j 2 Q \delta)}{1 + (1 + j 2 Q \delta)} = \frac{-j 2 Q \delta}{2 + j 2 Q \delta} = \frac{-j Q \delta}{1 + j Q \delta}$$
  * V kódu je ve jmenovateli faktor $2Q\delta$ namísto $Q\delta$. Tím je šířka pásma v simulovaném modelu uměle zúžena na polovinu.

---

## 4. Výpočty metrik, statistiky a logování

### Chyba 6: Kritérium pokrytí pásma SDARS v trackeru
* **Kde:** [`tracker.py` (řádek 50)](file:///d:/code/anteny/tracker.py#L50)
* **Kód:**
  ```python
  covers_band = bool(f_low <= 2.330 and f_high >= 2.330)
  ```
* **Výpočetní chyba:**
  * Zadání č. 22 definuje pásmo SDARS: $f_{\text{band,min}} = 2.320\text{ GHz}$ až $f_{\text{band,max}} = 2.345\text{ GHz}$.
  * Podmínka v kódu testuje pouze to, zda interval $[f_{\text{low}}, f_{\text{high}}]$ obsahuje **jediný bod $2.330\text{ GHz}$**.
  * Anténa s úzkým pásmem např. $2.329 - 2.331\text{ GHz}$ (šířka pouze $2\text{ MHz}$) projde jako vyhovující (`True`), ačkoliv nepokrývá požadovaných $25\text{ MHz}$ pásma ($2.320 - 2.345\text{ GHz}$).
* **Správná podmínka:** `bool(f_low <= 2.320 and f_high >= 2.345)`.

---

### Chyba 7: Nekorektní mezní hodnoty šířky pásma bez průchodu $-10\text{ dB}$
* **Kde:** [`tracker.py` (řádky 35–48)](file:///d:/code/anteny/tracker.py#L35-L48)
* **Kód:**
  ```python
  f_low = freqs[0]
  f_high = freqs[-1]
  # ... pokud cyklus nenajde průchod pod -10 dB, zůstane freqs[0] / freqs[-1] ...
  bw_mhz = (f_high - f_low) * 1000
  ```
* **Chyba ve výpočtu:**
  * Pokud $S_{11}$ neklesne pod $-10\text{ dB}$ na okraji simulačního okna (např. rezonance je široká nebo na kraji pásma), hodnota `f_low` nebo `f_high` se neinicializuje skutečným průsečíkem, ale zůstane na krajním bodu frekvenčního sweepu.
  * Metrika pak vrátí umělou šířku pásma odpovídající celému sweepu (např. $500\text{ MHz}$), což zkreslí optimalizaci.

---

### Chyba 8: Nekonzistence formátu výstupu vs. načítání v trackeru
* **Kde:** [`tracker.py` (řádky 11, 21)](file:///d:/code/anteny/tracker.py#L11-L21) a [`main.py` (řádek 71)](file:///d:/code/anteny/main.py#L71)
* **Popis:**
  * Parametr funkce je pojmenován `s1p_filepath`, ale načítá se pomocí `np.loadtxt(..., delimiter=',', skiprows=1)`, což očekává CSV tabulku. Pokud by byl předán skutečný Touchstone soubor `.s1p`, skript selže.

---

## 5. Geometrická klasifikace domén a sítí ([mesh.py](file:///d:/code/anteny/mesh.py))

### Chyba 9: Heuristické rozpoznávání PEC zkratuje dielektrikum
* **Kde:** [`mesh.py` (řádky 47–51)](file:///d:/code/anteny/mesh.py#L47-L51)
* **Kód:**
  ```python
  if abs(zmin - h) < 1e-6 and abs(zmax - h) < 1e-6:
      if xmax < params['sub_W']/2 - 1e-3 and ymax < params['sub_L']/2 - 1e-3 and xmin > -params['sub_W']/2 + 1e-3:
          pec_surfs.append(tag)
  ```
* **Chyba:**
  * Po provedení `gmsh.model.occ.fragment` vzniknou na horní ploše substrátu $z = h$ nejen plochy kovu, ale i fragmenty **odkrytého dielektrika** ležící mezi pásky a flíčkem.
  * Jakýkoliv vnitřní dielektrický fragment, který se přímo nedotýká vnějšího okraje desky, splní nerovnosti a je **chybně označen jako PEC**.

---

### Chyba 10: Duplikace magické souřadnice portu
* **Kde:** [`mesh.py` (řádek 55)](file:///d:/code/anteny/mesh.py#L55)
* **Kód:**
  ```python
  x_T = -25.4
  ```
* **Chyba:**
  * Hodnota `x_T = -25.4` je natvrdo zduplikována v [`geometry.py`](file:///d:/code/anteny/geometry.py#L41) i [`mesh.py`](file:///d:/code/anteny/mesh.py#L55). Změna v geometrii způsobí, že v [`mesh.py`](file:///d:/code/anteny/mesh.py) nebude nalezen žádný element portu a síť se vyexportuje bez budicí brány.

---

## 6. Vizualizace a ParaView makra

### Chyba 11: Vizualizace kreslí jinou geometrii než generátor
* **Kde:** [`visualization.py` (řádky 37–48)](file:///d:/code/anteny/visualization.py#L37-L48)
* **Chyba:**
  * Skript [`visualization.py`](file:///d:/code/anteny/visualization.py) vůbec neobsahuje dělič výkonu ani zpožďovací linku. Kreslí starý zjednodušený koncept (dva přímé pásky vedené přímo k okrajům substrátu). Obrázek `geometry_iso.png` tak neodpovídá reálně simulované geometrii.

### Chyba 12: Tvrdě zakódovaná souřadnice řezu v ParaView
* **Kde:** [`paraview_macro.py` (řádek 35)](file:///d:/code/anteny/paraview_macro.py#L35)
* **Kód:**
  ```python
  slice_patch.SliceType.Origin = [0.0, 0.0, 0.00152]
  ```
* **Chyba:**
  * Hodnota $0.00152\text{ m}$ ($1.52\text{ mm}$) je natvrdo vložena do makra. Při parametrické změně tloušťky substrátu $h$ bude řez umístěn mimo rozhraní.

---

## 7. Audit štábní kultury – Katalog magických čísel bez definice

Následující konstanty a koeficienty jsou v kódu použity přímo v těle funkcí bez zavedení pojmenovaných proměnných nebo konfiguračních parametrů:

| Soubor | Řádek | Magická hodnota | Fyzikální / technický význam | Správné řešení |
| :--- | :--- | :--- | :--- | :--- |
| [`geometry.py`](file:///d:/code/anteny/geometry.py#L41) | 41 | `-25.4` | Pozice T-uzlu napáječe v ose $x$ | Odvodit ze souřadnic flíčku a délek větví |
| [`geometry.py`](file:///d:/code/anteny/geometry.py#L42) | 42 | `-15.0` | Odsazení T-uzlu pod spodní hranu | Zadefinovat např. `FEED_OFFSET_Y` |
| [`geometry.py`](file:///d:/code/anteny/geometry.py#L33) | 33 | `0.412`, `0.3`, `0.264`, `0.258`, `0.8` | Hammerstadovy koeficienty rozptylu | Zastřešit do analytického RF modulu s dokumentací |
| [`mesh.py`](file:///d:/code/anteny/mesh.py#L17) | 17, 36, 47, 54, 61 | `1e-6` | Geometrická tolerance přesnosti | Definovat konstantu `GEOM_TOL = 1e-6` |
| [`mesh.py`](file:///d:/code/anteny/mesh.py#L49) | 49, 56 | `1e-3` | Odsazení od okrajů substrátu | Definovat konstantu `EDGE_CLEARANCE_TOL = 1e-3` |
| [`mock_palace.py`](file:///d:/code/anteny/mock_palace.py#L24) | 24 | `50.0` | Činitel jakosti flíčku $Q$ | Převzít z parametrů nebo analytického výpočtu |
| [`mock_palace.py`](file:///d:/code/anteny/mock_palace.py#L34) | 34 | `299.792` | Rychlost světla $c_0$ v $\text{mm}\cdot\text{GHz}$ | Použít `scipy.constants.c` nebo `C_0 = 299.792458` |
| [`mock_palace.py`](file:///d:/code/anteny/mock_palace.py#L46) | 46 | `0.05` | Minimální útlum odrazu ($-26\text{ dB}$) | Definovat parametr `S11_FLOOR_LINEAR` |
| [`palace_builder.py`](file:///d:/code/anteny/palace_builder.py#L16) | 16 | `1e-3` | Měřítko délky sítě na metry | Definovat `SCALE_MM_TO_M = 1e-3` |
| [`palace_builder.py`](file:///d:/code/anteny/palace_builder.py#L50) | 50 | `50.0` | Impedance portu | Převzít z `params['port_impedance']` |
| [`tracker.py`](file:///d:/code/anteny/tracker.py#L34) | 34, 39, 40, 44 | `-10` | Prahová hodnota $S_{11}$ pro šířku pásma | Definovat konstantu `S11_BW_THRESHOLD_DB = -10.0` |
| [`tracker.py`](file:///d:/code/anteny/tracker.py#L48) | 48, 69 | `1000` | Přepočet GHz na MHz / krok MLflow | Definovat konstantu `GHZ_TO_MHZ = 1000.0` |
| [`main.py`](file:///d:/code/anteny/main.py#L24) | 24 | `35.0` | Vzdálenost stěn vzduchového boxu | Počítat dynamicky jako $\ge \lambda_0 / 4$ |
| [`main.py`](file:///d:/code/anteny/main.py#L21) | 21, 22 | `70.8` | Rozměry substrátu | Odvodit z velikosti flíčku a napájecí sítě |
| [`main.py`](file:///d:/code/anteny/main.py#L23) | 23 | `3.0` | Šířka mikropásku napáječe | Vypočítat syntézou mikropásku pro $Z_0 = 50\,\Omega$ |

---

## 8. Doporučený návrh nápravy (Architektura „štábní kultury“)

Pro odstranění všech výše uvedených chyb se doporučuje zavést modul **`rf_calc.py`** a centralizovaný soubor fyzikálních a geometrických konstant:

1. **`rf_calc.py`:**
   * Analytický výpočet šířky mikropásku $w$ pro zadanou impedanci $Z_0$ a substrát ($h, \varepsilon_r$).
   * Přesný výpočet $\lambda_{g,\text{line}}/4$ pro mikropásek dané šířky při $f_c = 2.3325\text{ GHz}$.
   * Výpočet čtvrtvlnných impedančních transformátorů pro napojení flíčku dle [napajeni.png](file:///d:/code/anteny/docs/napajeni.png).
2. **Oprava geometrie v `geometry.py`:**
   * Prodloužit obdélníky napájecích větví až do těla flíčku (překrytí o $\text{feed\_W}/2$ namísto zkrácení), aby nevznikala vzduchová mezera.
   * Přehodit fázové zpoždění na správnou větev pro dodržení **LHCP**.
3. **Oprava klasifikace v `mesh.py`:**
   * Určovat PEC plochy na $z=h$ podle původních tagů vytvořených entit (případně testem polohy těžiště uvnitř obrysů vodivých pásků a flíčku), nikoliv vylučovací metodou od okrajů substrátu.
4. **Oprava `tracker.py`:**
   * Upravit podmínku pokrytí na celé pásmo $2.320 - 2.345\text{ GHz}$.

*Kód zůstává v původním stavu bez zásahů.*