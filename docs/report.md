### 1. Závažné chyby v geometrických výpočtech a síťování

#### A) Výpočet domén: Vzduchový box byl chybně klasifikován jako substrát
* **Kde:** [`assign_physical_groups_and_mesh`](file:///d:/code/anteny/mesh.py#L4-L24) v [mesh.py](file:///d:/code/anteny/mesh.py)
* **Kód:**
  ```python
  com = gmsh.model.occ.getCenterOfMass(dim, tag)
  if 0 < com[2] < h:
      sub_vols.append(tag)
  else:
      air_vols.append(tag)
  ```
* **Chyba ve výpočtu:**
  * Substrát má rozsah v ose $z$ od $0$ do $h$, jeho těžiště je $z = h/2 = 0.76\text{ mm}$.
  * Vzduchový box má rozsah od $-margin$ do $h + margin$. Jeho těžiště v ose $z$ je:
    $$z_{\text{com}} = \frac{-margin + (h + margin)}{2} = \frac{h}{2} = 0.76\text{ mm}$$
  * Obě tělesa mají **shodné těžiště v ose $z$**, takže podmínka `0 < com[2] < h` vyhodnotí obě tělesa jako substrát.
  * **Faktický stav v síti:** `Substrate` obsahuje oba objemy, zatímco skupina `Air` je **zcela prázdná** (`[]`). V plnohodnotném EM řešiči by se simulovala anténa uvězněná v masivním bloku dielektrika FR-4 ($\varepsilon_r = 4.3$).
* **Náprava:** Rozlišovat objemy podle jejich Bounding Boxu (např. $z_{\max} > h$ nebo $z_{\min} < 0$) či celkového objemu $V$.

#### B) Plochy PEC: Celá horní plocha substrátu je zkratována
* **Kde:** [`assign_physical_groups_and_mesh`](file:///d:/code/anteny/mesh.py#L46-L49) v [mesh.py](file:///d:/code/anteny/mesh.py)
* **Kód:**
  ```python
  if abs(zmin - h) < 1e-6 and abs(zmax - h) < 1e-6:
      pec_surfs.append(tag)
  ```
* **Chyba ve výpočtu:**
  * Funkce `fragment` rozdělí rovinu $z = h$ na plochu patche, přívodní mikropásky a **zbývající plochu substrátu**.
  * Podmínka přidá do ideálního vodiče (PEC) **všechny plochy** ležící v $z = h$. Tím se celá horní plocha substrátu pokryje kovem. Patch je tím přímo zkratován a anténa nemůže vyzařovat do volného prostoru.
* **Náprava:** Do PEC zařadit v rovině $z=h$ pouze plochy ležící uvnitř rozměrů patche ($[-W/2, W/2] \times [-L/2, L/2]$) a napájecího mikropásku.

#### C) Výpočet plochy portu (Lumped Port)
* **Kde:** [`assign_physical_groups_and_mesh`](file:///d:/code/anteny/mesh.py#L51-L54) v [mesh.py](file:///d:/code/anteny/mesh.py)
* **Chyba:** Podmínka kontroluje pouze $x = -W_{\text{sub}}/2$ a $z \in [0, h]$, ale **nekontroluje rozsah v ose $y$**. Port je proto aplikován přes celou šířku desky ($70.8\text{ mm}$) místo na úzkou plochu pod mikropáskem o šířce $3.0\text{ mm}$ ($y \in [-1.5, 1.5]\text{ mm}$). Tím je impedance portu i budicí pole zkresleno.

---

### 2. Elektromagnetické a fyzikální výpočty

#### A) Výpočet rezonanční frekvence $f_0$ v mock řešiči
* **Kde:** [`generate_mock_touchstone`](file:///d:/code/anteny/mock_palace.py#L26-L30) v [mock_palace.py](file:///d:/code/anteny/mock_palace.py)
* **Použitý vzorec:**
  $$f_{\text{res}} = \frac{300}{2 \cdot L \cdot \sqrt{\varepsilon_r}}$$
* **Posouzení přesnosti:**
  * Jde o zjednodušený model ideální dutiny zcela vyplněné dielektrikem. Zanedbává **rozptylová pole (fringing fields)** na okrajích patche:
    1. Vlna se šíří částečně substrátem a částečně vzduchem $\implies$ uplatňuje se **efektivní permitivita** $\varepsilon_{\text{eff}} < \varepsilon_r$:
       $$\varepsilon_{\text{eff}} \approx \frac{\varepsilon_r + 1}{2} + \frac{\varepsilon_r - 1}{2} \frac{1}{\sqrt{1 + 12 h / W}}$$
       Pro parametry $W = 30.8\text{ mm}$, $h = 1.52\text{ mm}$, $\varepsilon_r = 4.3$ vychází $\varepsilon_{\text{eff}} \approx 3.96$.
    2. Rozptylová pole elektricky prodlužují délku patche o $2\Delta L$:
       $$\Delta L \approx 0.412 h \frac{(\varepsilon_{\text{eff}} + 0.3)(W/h + 0.264)}{(\varepsilon_{\text{eff}} - 0.258)(W/h + 0.8)} \approx 0.70\text{ mm}$$
       Efektivní délka je $L_{\text{eff}} = L + 2\Delta L \approx 32.2\text{ mm}$.
    3. Rychlost světla: konstanta $300\text{ mm}\cdot\text{GHz}$ namísto přesnější $299.792\text{ mm}\cdot\text{GHz}$.
  * V tomto konkrétním rozměru se oba vlivy (nižší $\varepsilon_{\text{eff}}$ frekvenci zvyšuje, delší $L_{\text{eff}}$ ji snižuje) zčásti kompenzují, avšak pro obecný sweep je zjednodušený vzorec fyzikálně nepřesný.

#### B) Nulová fáze odrazu $\angle S_{11}$
* **Kde:** [`generate_mock_touchstone`](file:///d:/code/anteny/mock_palace.py#L37-L42) v [mock_palace.py](file:///d:/code/anteny/mock_palace.py)
* **Kód:** `gamma_ang = 0.0`
* **Důsledek:** V Touchstone souboru `.s1p` je fáze činitele odrazu nulová. Na **Smithově diagramu** v programu METAS VNA (doporučovaném v [README.md](file:///d:/code/anteny/README.md)) se nezobrazí rezonanční kružnice, ale pouhá úsečka ležící na reálné ose. Nelze tak odečíst reaktanci ani fázi.

#### C) Topologie napájení a absence kruhové polarizace (LHCP)
* **Kde:** [`build_model`](file:///d:/code/anteny/geometry.py#L28-L38) v [geometry.py](file:///d:/code/anteny/geometry.py)
* **Zjištění:**
  * Skript kreslí dvě větve: `feed_left` a `feed_bottom`. Obě mají shodnou délku $20.0\text{ mm}$ ($W_{\text{sub}}/2 - W/2$). Neexistuje zde žádný délkový rozdíl $\lambda/4$ ani dělič výkonu.
  * Obě větve nejsou propojené. Port budí pouze `feed_left`, zatímco `feed_bottom` funguje jako otevřený pahýl (open stub) připojený k ortogonální hraně patche.
  * Anténa proto nevykazuje kruhovou polarizaci (LHCP), nýbrž lineární polarizaci s parazitním reaktivním zatížením.

---

### 3. Chyby ve statistických výpočtech a logování

#### A) Výpočet šířky pásma $\text{BW}_{-10\text{dB}}$ bez interpolace
* **Kde:** [`analyze_and_log_run`](file:///d:/code/anteny/tracker.py#L30-L38) v [tracker.py](file:///d:/code/anteny/tracker.py)
* **Kód:**
  ```python
  f_below = freqs[below_10]
  bw_mhz = (f_below[-1] - f_below[0]) * 1000
  ```
* **Chyby:**
  1. **Diskrétní zkreslení:** Odečítají se indexy diskrétních bodů, nikoliv přesný průsečík s $-10\text{ dB}$. Šířka pásma je podhodnocena až o 2 frekvenční kroky (v MLflow logu skáče mezi $14\text{ MHz}$ a $15\text{ MHz}$ čistě kvůli posunu mřížky vzorkování).
  2. **Nespojité pásmo:** Pokud by anténa měla dva zákmity (např. na $2.15\text{ GHz}$ a $2.55\text{ GHz}$), vzorec vrátí rozdíl $400\text{ MHz}$, ačkoliv mezi nimi je anténa nepřizpůsobená.
  3. **Kritérium pokrytí (`Covers_S_Band`):** Podmínka `f_below[0] <= 2.320 and f_below[-1] >= 2.345` vyžaduje šířku $25\text{ MHz}$, přičemž flíček s $Q=50$ má přirozenou šířku pásma pouze cca $15\text{ MHz}$. Metrika proto vrací vždy `0.0`.

#### B) Ztráta dat v MLflow kvůli zaokrouhlování floatu
* **Kde:** [`analyze_and_log_run`](file:///d:/code/anteny/tracker.py#L55-L57) v [tracker.py](file:///d:/code/anteny/tracker.py)
* **Kód:** `step = int(f_val * 1000)`
* **Chyba:** Kvůli nepřesnosti čísel s plovoucí řádovou čárkou v Pythonu ($2.102 \times 1000 = 2101.9999999999995$) vrací `int(...)` hodnotu `2101`. Krok `2102` byl přepsán a z 501 bodů se do MLflow uložilo jen 500.
* **Náprava:** Použít `int(round(f_val * 1000))`.

---

### 4. Nekonzistence v jednotkách a konfiguraci

| Oblast | Soubor | Problém |
| :--- | :--- | :--- |
| **Jednotky ParaView** | [`paraview_macro.py`](file:///d:/code/anteny/paraview_macro.py#L35) | V `config.json` je měřítko `"L0": 1e-3` (převod na metry). Reálný Palace ukládá pole v metrech, ale ParaView makro vytváří řez na $z = 1.52$ (což by bylo $1.52\text{ m}$ namísto $0.00152\text{ m}$). |
| **Formát výstupu** | [`main.py`](file:///d:/code/anteny/main.py#L69) | Reálný solver Palace ukládá S-parametry do `port-S.csv`, nikoliv `.s1p`. Soubor `.s1p` generuje pouze skript [mock_palace.py](file:///d:/code/anteny/mock_palace.py). |
| **Buzení portu** | [`palace_builder.py`](file:///d:/code/anteny/palace_builder.py#L45-L52) | V sekci `LumpedPort` chybí klíč `"Excitation": true`, který Palace vyžaduje pro aktivaci buzení na daném portu. |

---

### Závěr a doporučení

Výpočty v projektu fungují jako hrubý funkční prototyp, ale **pro seriózní fyzikální simulaci obsahují zásadní chyby**:
1. V síti je nutné opravit selekci **Air** (doména byla prázdná) a **PEC** (byla zkratována celá horní plocha substrátu).
2. Do výpočtu šířky pásma v [tracker.py](file:///d:/code/anteny/tracker.py) doplnit lineární interpolaci bodů na hladině $-10\text{ dB}$ a ošetřit spojitost pásma.
3. V [mock_palace.py](file:///d:/code/anteny/mock_palace.py) doplnit výpočet fáze činitele odrazu $\Gamma$ pro realistické zobrazení na Smithově diagramu.