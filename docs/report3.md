# Technická zpráva č. 3: Revizní audit výpočtů, geometrie a štábní kultury

**Datum:** 9. října 2026  
**Projekt:** Zadání č. 22 – Návrh LHCP mikropáskové flíčkové antény pro pásmo SDARS (2.320 – 2.345 GHz)  
**Autor:** Antigravity (Pair Programming Review)  
**Předmět:** Ověření stavu dříve identifikovaných chyb po refaktoringu, analýza nově vzniklých vad a audit dodržení inženýrských standardů (eliminace magických čísel).

---

## 1. Manažerské shrnutí (Executive Summary)

Po provedení série opravných commitů (`d000fee` až `32af111`) byla znovu prověřena veškerá zdrojová data, analytické vztahy a simulační skripty. 

* **Pozitivní posun:**
  * Byl úspěšně zaveden samostatný analytický modul [`rf_calc.py`](file:///d:/code/anteny/rf_calc.py), který centralizuje vysokofrekvenční vztahy a fyzikální konstanty ($c_0$, $\eta_0$, syntézu mikropásku $Z_0 \leftrightarrow w$, efektivní permitivitu $\varepsilon_{\text{eff}}$ a rezonanci flíčku).
  * Byla odstraněna galvanická vzduchová mezera ($1.5\text{ mm}$) u flíčku.
  * Zpřesnila se klasifikace PEC a portu v [`mesh.py`](file:///d:/code/anteny/mesh.py) díky přímému využití mapování z CAD jádra OpenCASCADE (`fragment`).
  * Byly opraveny metriky v [`tracker.py`](file:///d:/code/anteny/tracker.py) (pásmo SDARS, interpolace $-10\text{ dB}$, zaokrouhlování kroků).
  * Byla sjednocena geometrie v 3D vizualizaci [`visualization.py`](file:///d:/code/anteny/visualization.py) s reálným modelem.
* **Kritické přetrvávající vady:**
  * **Chyba ve fázovém zpoždění pro LHCP:** V důsledku chybného dělení 4.0 namísto 2.0 je zaveden fázový posun **pouze $45^\circ$ namísto $90^\circ$**.
  * **Geometrické selhání čtvrtvlnných transformátorů:** Zvolená statická odsazení T-uzlu a rozměry desky neposkytují dostatek prostoru pro umístění transformátorů $\lambda_g/4 \approx 17.4 - 18.5\text{ mm}$. Levý transformátor se vůbec nevytvoří, spodní se vytvoří (vzniká těžká asymetrie buzení hran) a vstupní transformátor je useknut, přičemž vzniká převis kovu přes budicí port.

---

## 2. Matice stavu chyb (Srovnání Auditu č. 2 a Auditu č. 3)

| # | Identifikovaný problém z Auditu č. 2 | Stav v Auditu č. 3 | Důvod / Aktuální nález |
|---|---|:---:|---|
| **1** | Vzduchová mezera $1.5\text{ mm}$ mezi pásky a flíčkem | ✅ **OPRAVENO** | Pásky v [`geometry.py`](file:///d:/code/anteny/geometry.py) nově přesahují do flíčku o `feed_W/2` a jsou spojeny konformní operací `fragment`. |
| **2** | $\lambda_g$ počítána z flíčku namísto mikropásku | ✅ **OPRAVENO** | Využívá se [`rf_calc.py`](file:///d:/code/anteny/rf_calc.py); $\varepsilon_{\text{eff}}$ a $\lambda_g/4$ se počítají ze šířky mikropásku při fixní frekvenci $f_c = 2.3325\text{ GHz}$. |
| **3** | Záměna smyslu kruhové polarizace (RHCP vs LHCP) | ⚠️ **ČÁSTEČNĚ / NOVÁ CHYBA** | Smysl zpoždění byl přehozen na spodní větev ($E_y$), což odpovídá LHCP. **Avšak velikost posuvu je chybná ($45^\circ$ místo $90^\circ$)!** |
| **4** | Absence impedančního přizpůsobení sítě | ⚠️ **NOVÁ CHYBA** | Vzorce pro transformátory byly přidány, ale **kvůli malým rozměrům se levý transformátor nevytvoří a vstupní je useknut**. |
| **5** | Chybný rezonanční vzorec $S_{11}$ v mock solveru | ✅ **OPRAVENO** | Model v [`mock_palace.py`](file:///d:/code/anteny/mock_palace.py) byl upraven na korektní paralelní RLC se zápornou imaginární složkou a nenulovou fází. |
| **6** | Test pokrytí pásma testoval jen 1 bod $2.330\text{ GHz}$ | ✅ **OPRAVENO** | V [`tracker.py`](file:///d:/code/anteny/tracker.py) je zavedena striktní kontrola celého pásma `f_low <= 2.320 and f_high >= 2.345`. |
| **7** | Zkreslení šířky pásma při nedosažení $-10\text{ dB}$ | ✅ **OPRAVENO** | Inicializace na `None`; pokud chybí průřez na obou stranách, vrací se `bw_mhz = 0.0`. |
| **8** | Zkratování dielektrika horní plochy (PEC) | ✅ **OPRAVENO** | [`mesh.py`](file:///d:/code/anteny/mesh.py) používá přesné mapování `out_map` z Boolean Fragments. |
| **9** | Duplikovaná magická souřadnice portu `-25.4` | ✅ **OPRAVENO** | Souřadnice `port_x` je dynamicky předávána v parametrech. |
| **10**| Vizualizace kreslila starý nepropojený koncept | ✅ **OPRAVENO** | [`visualization.py`](file:///d:/code/anteny/visualization.py) bylo aktualizováno a odpovídá topologii v `geometry.py`. |
| **11**| ParaView řez na fixní výšce $0.00152\text{ m}$ | ✅ **OPRAVENO** | Makro [`paraview_macro.py`](file:///d:/code/anteny/paraview_macro.py) čte skutečnou výšku $h$ z `config.json`. |
| **12**| Ztráta frekvenčního kroku v MLflow | ✅ **OPRAVENO** | Použito bezpečné zaokrouhlování `int(round(f_val * GHZ_TO_MHZ))`. |

---

## 3. Detailní rozbor přetrvávajících a nově vzniklých vad

### 🔴 Vada A: Zpožďovací linka realizuje pouze $45^\circ$ fázový posun (Chyba dělení 4.0)

* **Soubory:** [`geometry.py` (řádek 74)](file:///d:/code/anteny/geometry.py#L74) a [`visualization.py` (řádek 71)](file:///d:/code/anteny/visualization.py#L71)
* **Zdrojový kód:**
  ```python
  delay_offset = lambda_g_4 / 4.0  # svislé snížení spodního vedení pro celkové prodloužení lambda_g_4
  ```
* **Analytický rozbor chyby:**
  1. Funkce `calc_quarter_wave_length` v modulu `rf_calc.py` vrací přímo čtvrtvlnnou délku:
     $$\text{lambda\_g\_4} = \frac{\lambda_g}{4} \approx 17.77\text{ mm}$$
  2. Spodní napájecí větev odbočuje z T-uzlu na souřadnici $y_T$, klesá svisle dolů na úroveň $y_{\text{delay}} = y_T - \text{delay\_offset}$, pokračuje vodorovně pod flíček a následně stoupá svisle nahoru k dolní hraně flíčku na $y = -L/2$.
  3. Prodloužení dráhy spodní větve oproti levé větvi je tvořeno dvojnásobkem tohoto vertikálního rozdílu:
     * Pokles z $y_T$ do $y_{\text{delay}}$: délka $\text{delay\_offset}$.
     * Dodatečný výstup z $y_{\text{delay}}$ do $y_T$: délka $\text{delay\_offset}$.
     $$\Delta d = 2 \cdot \text{delay\_offset}$$
  4. Pokud je do vzorce dosazeno `delay_offset = lambda_g_4 / 4.0`, celkový rozdíl délek drah je:
     $$\Delta d = 2 \cdot \left(\frac{\lambda_{g,4}}{4}\right) = \frac{\lambda_{g,4}}{2} = \frac{\lambda_g}{8} \approx 8.88\text{ mm}$$
  5. Vzniklý fázový posun na kmitočtu $f_c$ činí:
     $$\Delta \phi = \beta \cdot \Delta d = \frac{2\pi}{\lambda_g} \cdot \frac{\lambda_g}{8} = \frac{\pi}{4} = 45^\circ$$
* **Fyzikální dopad:** Ortogonální složky pole $E_x$ a $E_y$ jsou buzeny s fázovým posunem $45^\circ$ namísto $90^\circ$. Anténa generuje silně eliptickou polarizaci; osový poměr (Axial Ratio) bude výrazně přesahovat mezní požadavek $3\text{ dB}$.
* **Náprava:**
  ```python
  # Správný vztah: rozdíl drah má být přesně lambda_g_4, proto:
  delay_offset = lambda_g_4 / 2.0
  ```

---

### 🔴 Vada B: Geometrické selhání a asymetrie impedančních transformátorů

* **Soubory:** [`geometry.py` (řádky 80–120)](file:///d:/code/anteny/geometry.py#L80-L120), [`visualization.py`](file:///d:/code/anteny/visualization.py) a [`main.py` (řádky 44–46)](file:///d:/code/anteny/main.py#L44-L46)
* **Příčina:** Pevně zakódovaná odsazení T-uzlu (`FEED_OFFSET_X = 10.0`, `FEED_OFFSET_Y = 15.0`) a okraj substrátu (`sub_margin_side = 20.0`) jsou menší než potřebná fyzická délka čtvrtvlnných transformátorů ($\lambda_{g,\text{trans}}/4 \approx 17.4$ až $18.5\text{ mm}$).

#### 1. Ztráta transformátoru na levé větvi (Asymetrie buzení)
* Levý transformátor má přizpůsobit $50\,\Omega$ na vstupní odpor hrany flíčku $R_{\text{edge}} \approx 150\,\Omega$. Jeho vypočtené parametry jsou $Z_{\text{trans}} \approx 86.6\,\Omega$, šířka $w_{p,\text{trans}} \approx 1.0\text{ mm}$ a délka $\lambda_{p,\text{trans}}/4 \approx 18.47\text{ mm}$.
* Vzdálenost od T-uzlu k levé hraně flíčku je však pevně nastavena na:
  $$\text{FEED\_OFFSET\_X} = 10.0\text{ mm} < 18.47\text{ mm}$$
* Řádek 97 v `geometry.py`:
  ```python
  x_p_trans_l = -W/2 - min(lambda_p_trans_4, abs(x_T - (-W/2)))
  ```
  Vzhledem k tomu, že $|x_T - (-W/2)| = 10.0\text{ mm}$, je minimum rovno $10.0\text{ mm}$, a tedy $x_{p,\text{trans},l} = x_T$.
* Podmínka na řádku 98:
  ```python
  if x_p_trans_l > x_T:
      # vytvoření transformátoru
  else:
      # přímé vedení bez transformátoru
  ```
  vyhodnotí výraz jako **nepravdivý** a spadne do větve `else`. **Levý transformátor se vůbec nevytvoří!** Levá hrana flíčku je napájena přímo $50\,\Omega$ vedením o šířce $3.0\text{ mm}$.
* **Asymetrický kontrast na spodní větvi:** Spodní větev má díky zpožďovací smyčce vertikální prostor cca $19.4\text{ mm} > 18.47\text{ mm}$, takže podmínka projde a spodní transformátor o šířce $1.0\text{ mm}$ se vytvoří.
* **Fyzikální důsledek:** Levá hrana je buzena ze zdroje s impedancí $50\,\Omega$ (pásek $3.0\text{ mm}$), spodní hrana je buzena přes transformátor $86.6\,\Omega$ (pásek $1.0\text{ mm}$). Amplitudy a fáze buzení obou polarizačních módů jsou vzájemně nevyvážené, což znemožňuje dosažení kruhové polarizace.

#### 2. Ořezání vstupního transformátoru $50\,\Omega \to 25\,\Omega$ a přesah přes port
* Dvě paralelní $50\,\Omega$ větve v T-uzlu představují zatěžovací impedanci $Z_{\text{node}} = 25\,\Omega$.
* K přizpůsobení na $50\,\Omega$ port je nutný čtvrtvlnný transformátor:
  $$Z_T = \sqrt{50 \cdot 25} = 35.35\,\Omega \implies w_{T} \approx 5.06\text{ mm}, \quad \lambda_T/4 \approx 17.38\text{ mm}$$
* Vzdálenost T-uzlu od okraje substrátu:
  $$y_T - (-L_{\text{sub}}/2) = -30.4\text{ mm} - (-35.4\text{ mm}) = 5.0\text{ mm}$$
* Podmínka na řádku 81 `if y_trans_start > -L_sub/2:` selže ($y_T - 17.38 = -47.78\text{ mm} < -35.4\text{ mm}$). Kód spadne do `else` a transformátor je **násilně ořezán na délku pouhých $6.5\text{ mm}$** namísto $17.38\text{ mm}$.
* **Kolize s portem:** Pásek transformátoru o šířce $5.06\text{ mm}$ sahá až na okraj substrátu. Budicí plocha portu vytvořená na řádcích 125–134 má však pevně zakódovanou šířku `feed_W = 3.0 mm`. Vzniká tak geometrický nesoulad, kdy kovový pásek o šířce $5.06\text{ mm}$ přesahuje přes hranice portu o $1.03\text{ mm}$ na každé straně.

---

## 4. Přetrvávající prohřešky proti „Štábní kultuře“ (Magická čísla)

Ačkoliv modul [`rf_calc.py`](file:///d:/code/anteny/rf_calc.py) představuje vynikající základ, v řídicích skriptech stále přetrvávají statické a neprovázané hodnoty:

| Soubor | Řádek | Magická konstanta | Technický problém | Požadovaný inženýrský přístup |
|---|---|---|---|---|
| [`geometry.py`](file:///d:/code/anteny/geometry.py#L5-L6) | 5, 6 | `FEED_OFFSET_X = 10.0`<br>`FEED_OFFSET_Y = 15.0` | Pevná čísla, která fyzicky nepojmou transformátory $\approx 18.5\text{ mm}$. | Dynamicky: `FEED_OFFSET_X = lambda_p_trans_4 + 5.0`, `FEED_OFFSET_Y = lambda_t_trans_4 + delay_offset + 5.0`. |
| [`main.py`](file:///d:/code/anteny/main.py#L44) | 44 | `sub_margin_side = 20.0` | Nestačí pro umístění napájecí sítě pod flíčkem. | Odvodit $L_{\text{sub}}$ a $W_{\text{sub}}$ z celkového Bounding Boxu napájecí sítě + manipulační rezerva. |
| [`main.py`](file:///d:/code/anteny/main.py#L33-L34) | 33, 34 | `patch_l = 30.8`<br>`patch_w = 30.8` | Zadáno natvrdo, nikoliv z výpočtu v `rf_calc.py`. | Inicializovat pomocí analytické rezonance `calc_patch_resonance` pro střed pásma $2.3325\text{ GHz}$. |
| [`geometry.py`](file:///d:/code/anteny/geometry.py#L125-L128) | 125 | `feed_W` pro port | Port má šířku $3.0\text{ mm}$, i když na něj navazuje pásek $5.06\text{ mm}$. | Šířka portu musí odpovídat šířce mikropásku vstupujícího do portu (`w_port_entry`). |
| [`sweep.py`](file:///d:/code/anteny/sweep.py#L6) | 6 | `[30.0, 30.4, ...]` | Pevný seznam rozměrů. | Generovat pole kolem analytické rezonance $L_0 \pm \Delta L$. |

---

## 5. Doporučený plán finální nápravy

Pro dosažení plné funkčnosti a stoprocentní „štábní kultury“ doporučujeme provést tyto kroky:

1. **Oprava fázovací smyčky:**
   * V [`geometry.py`](file:///d:/code/anteny/geometry.py) a [`visualization.py`](file:///d:/code/anteny/visualization.py) nahradit:
     ```python
     delay_offset = lambda_g_4 / 2.0
     ```
2. **Parametrický prostor pro napájecí síť:**
   * V [`geometry.py`](file:///d:/code/anteny/geometry.py) odvodit odsazení T-uzlu přímo z délek transformátorů:
     ```python
     FEED_OFFSET_X = lambda_p_trans_4 + 6.0
     FEED_OFFSET_Y = lambda_p_trans_4 + 6.0
     ```
   * V [`main.py`](file:///d:/code/anteny/main.py) zvětšit velikost substrátu $L_{\text{sub}}$ tak, aby bezpečně pojala celou napájecí síť:
     ```python
     # Potřebný prostor v ose Y pod flíčkem:
     y_needed = (patch_l / 2.0) + FEED_OFFSET_Y + delay_offset + lambda_t_trans_4 + 10.0
     sub_l = 2.0 * y_needed
     sub_w = patch_w + 2.0 * (FEED_OFFSET_X + 15.0)
     ```
3. **Konzistentní šířka portu:**
   * Pokud hlavní přívod začíná $50\,\Omega$ úsekem před transformátorem, musí být délka $50\,\Omega$ úseku kladná a port mít šířku `feed_w = 2.98 mm`.
   * Pokud transformátor sahá až k portu, musí mít plocha portu šířku shodnou se šířkou transformátoru ($5.06\text{ mm}$) a impedance portu v `config.json` musí být nastavena na odpovídajících $35.35\,\Omega$. Standardnější a správnější je ponechat vstupní $50\,\Omega$ úsek alespoň $5\text{ mm}$ dlouhý a teprve poté zařadit $\lambda/4$ transformátor.
