# Provozní směrnice pro autonomního agenta: Univerzální 3D CAD modelování a vysokofrekvenční simulace (Palace + Gmsh + AMR)

## 1. Architektura mise a provozní filosofie

Cílem agenta je realizovat plně uzavřený a autonomní cyklus: od převzetí libovolné abstraktní specifikace vysokofrekvenční struktury až po získání fyzikálně validovaných $S$-parametrů a rozložení polí v solveru Palace.

Agent nepracuje metodou pokus-omyl ani nespoléhá na statické šablony. Celý postup se řídí pěti základními fázemi:
1. **Dekompozice a parametrizace zadání:** Formální rozklad specifikace na prostorové dimenze, materiály, porty a okrajové podmínky.
2. **Procedurální generování 3D CAD geometrie:** Konstrukce objemových a plošných těles v CAD jádře OpenCASCADE bez absolutních hardcodovaných hodnot.
3. **Topologická fúze a geometrická klasifikace:** Vytvoření konformních rozhraní a deterministické oštítkování entit (*Physical Groups*) na základě prostorových vztahů a invariantů po re-indexaci jádrem.
4. **Hrubé síťování a topologická verifikace:** Příprava základní nestrukturované tetraedrální sítě s kontrolou metrické kvality elementů.
5. **Konfigurace solveru, řízení AMR a fyzikální validace:** Nastavení adaptivního zjemňování sítě, spuštění výpočtu a verifikace fundamentálních zákonů elektromagnetismu (pasivita, reciprocita, kauzalita).

---

## 2. Abstrakce a dekompozice libovolného VF zadání

Před zahájením CAD operací agent provede formální rozbor zadání a klasifikuje všechny požadované prvky do čtyř univerzálních tříd:

### A. Objemové domény (3D Volumetric Domains)
* **Aktivní / funkční materiály:** Tělesa s permitivitou $\varepsilon_r \ne 1.0$, permeabilitou $\mu_r \ne 1.0$ nebo dielektrickým ztrátovým činitelem $\tan\delta > 0$.
* **Vnější výpočetní prostředí:**
  * *Uzavřené struktury (dutiny, vlnovodné sekce, stíněné krabičky):* Vnitřní prázdný prostor je modelován jako samostatné těleso (vzduch/vakuum) kopírující vnitřní stěny. Vnější obal se nevytváří.
  * *Otevřené a vyzařující struktury (antény, neuzavřené přechody):* Struktura musí být vložena do vzduchového obalu (krychle, kvádr, válec či koule), jehož stěny jsou ve všech směrech vzdáleny minimálně o čtvrtinu vlnové délky ve vakuu vůči nejnižší simulované frekvenci:
    $$d_{margin} \ge \frac{\lambda_{0,max}}{4} = \frac{c_0}{4 \cdot f_{min}}$$

### B. Vodivé prvky a materiálové vrstvy (Boundaries & Conductors)
* **Tenké vrstvy a beztloušťkové vodiče:** Pokud je tloušťka kovu zanedbatelná vůči celkovým rozměrům a podstatně menší než skin hloubka na pracovní frekvenci, agent modeluje vodič jako 2D plochu bez tloušťky s okrajovou podmínkou ideálního vodiče (PEC) nebo impedanční podmínkou povrchových ztrát.
* **Masivní vodiče:** Pokud geometrie kovu tvoří podstatnou část vlnovodu, rezonančních stěn nebo vyžaduje sledování objemových ztrát, modeluje se jako plnohodnotné 3D těleso.

### C. Budicí a snímací rozhraní (Ports & Excitations)
* **Vlnovodové porty (Wave Ports):** 2D plochy umístěné na vnějších hranicích domény, kde je předem znám nebo numericky řešen průřezový 2D vid vlnění (TEM, TE, TM). Vyžadují definici referenční roviny pro případný de-embedding.
* **Soustředěné porty (Lumped Ports):** 2D plochy vložené uvnitř domény mezi signálovou a referenční vodivou cestu. Vyžadují explicitní orientaci integrační linie napětí a zadanou referenční impedanci (typicky $50\,\Omega$).

### D. Hraniční podmínky ohraničení (Domain Truncation)
* **Absorpční stěny (Radiation / Absorbing):** Všechny vnější stěny otevřeného vzduchového boxu, které simulují volný prostor bez odrazů.
* **Symetrické roviny (PEC / PMC):** Plochy umožňující zmenšení výpočetního modelu na polovinu či čtvrtinu při symetrii polí $\vec{E}$ a $\vec{H}$.

---

## 3. Metodika parametrického generování 3D CAD modelu

Modelování musí probíhat striktně algoritmicky v jádře OpenCASCADE:

### Parametrická reprezentace
* Veškeré rozměry, tloušťky, poloměry a mezery musí být deklarovány jako symbolické proměnné v úvodním bloku zadání.
* Veškeré odvozené pozice se počítají relativně k referenčnímu souřadnému systému (nikdy se nepoužívají absolutní souřadnice zapsané napevno).
* Všechny délkové veličiny musí být normalizovány na základní jednotky SI (metry) nebo provázány s geometrickým měřítkem $L_0$ solveru.

### Konstrukční strategie těles
1. **Konstrukce zdola nahoru (Bottom-Up) a CSG:** Využívají se objemová primitiva (kvádry, válce) a operace tažení (extruze 2D skic podél vektoru, rotace profilů).
2. **Oddělení vrstev:** Každá materiálová vrstva nebo dielektrická vložka vzniká jako samostatné těleso.
3. **Plošné entity pro porty a vodiče:** Vnitřní signálové cesty a portové plochy se vytvářejí přímo na styčných rovinách příslušných objemů.
4. **Vytvoření ohraničujícího boxu:** U otevřených struktur se nakonec vytvoří vnější objem vzduchu, který plně obalí vnitřní strukturu.

---

## 4. Topologická fúze a konformita (Non-Manifold Boolean Fragments)

Dvě sousední domény (např. dielektrikum a okolní vzduch, nebo kovový pásek ležící na dielektriku) nesmí v modelu existovat jako dvě nezávislá tělesa se samostatnými stěnami. Pokud by tomu tak bylo, generátor sítě by vytvořil nezávislé sítě a uzly na rozhraní by nelícovaly, což by způsobilo únik pole.

### Povinný postup sjednocení:
1. **Aplikace Booleovských fragmentů (Boolean Fragments):** 
   Agent aplikuje operaci fragmentace na celou sestavu všech 3D objemů a všech vložených 2D ploch současně.
2. **Topologická synchronizace:**
   Operace protne všechna tělesa v místech jejich průniků a vytvoří jediné sdílené rozhraní (společnou 2D stěnu) mezi jakýmikoliv dvěma sousedícími 3D objemy.
3. **Výsledek:**
   Po této operaci vznikne ne-varietní (*non-manifold*) topologie, kde každý uzel sítě ležící na rozhraní patří současně elementům obou přilehlých domén.

---

## 5. Algoritmická prostorová klasifikace entit (Spatial Reasoning)

Po aplikaci Booleovských fragmentů jádro CAD přegeneruje interní identifikátory (tagy) všech bodů, křivek, ploch a objemů. Původní ID zanikají.

Agent **nesmí** spoléhat na fixní čísla tagů. Pro přiřazení materiálů a okrajových podmínek použije deterministické geometrické filtry vyhodnocované po synchronizaci topologie:

### Filtrační invarianty pro každou entitu:
1. **Těžiště entity ($[x_c, y_c, z_c]$):**
   * *Pro objemy:* Vyhodnotí se, uvnitř kterého z původních parametrických prostorů leží těžiště fragmentovaného objemu. Tím se jednoznačně určí, zda objem patří konkrétnímu dielektriku, dutině nebo vnějšímu vzduchu.
   * *Pro plochy:* Testuje se poloha těžiště vůči význačným rovinám (např. rozhraní substrátu, čelo portu, základna stínění).
2. **Hraniční box (Bounding Box):**
   Ověření prostorového rozsahu $[x_{min}, x_{max}] \times [y_{min}, y_{max}] \times [z_{min}, z_{max}]$. Umožňuje odlišit vnitřní prvky od vnějšího pláště.
3. **Orientace normálového vektoru a vnější stěny:**
   Plochy, které leží na hranici celkového ohraničujícího boxu simulační domény a jejichž normála směřuje ven z domény, jsou klasifikovány jako vnější hranice (Radiation boundary nebo stínicí plášť).
4. **Plošné integrály a rozměry:**
   Plocha s těžištěm na vstupu vedení a rozměry odpovídajícími definici portu je automaticky označena jako budicí brána.

### Vytvoření a export Physical Groups
Každá prostorově identifikovaná množina entit je sloučena do právě jedné pojmenované skupiny:
* Každý 3D objem musí patřit do odpovídající doménové skupiny (*Physical Volume*).
* Všechny funkční plochy (porty, zemnící plochy, absorpční stěny, roviny symetrie) musí patřit do odpovídajících hraničních skupin (*Physical Surface*).
* Vnitřní rozhraní mezi dvěma dielektriky, která nemají žádnou okrajovou podmínku (pole jimi volně prochází), se do žádné plošné skupiny nezařazují.

---

## 6. Strategie počátečního síťování a součinnost s AMR

Díky adaptivnímu zjemňování sítě (AMR) v solveru Palace není agent nucen vytvářet složitá lokální zjemňovací pole v CAD generátoru.

### Principy základní sítě:
* **Globální velikost elementu ($h_{init}$):** Volí se tak, aby síť spolehlivě zachytila geometrické detaily a zároveň zaručila minimálně 4 elementy na vlnovou délku v materiálu s nejvyšší permitivitou při maximální frekvenci:
  $$h_{init} \le \frac{c_0}{4 \cdot f_{max} \cdot \sqrt{\varepsilon_{r,max}}}$$
* **Nízká výpočetní náročnost počátku:** Počáteční síť má být lehká a rychlá na vygenerování, aby minimalizovala paměťovou zátěž při inicializaci solveru.

### Kontrola kvality sítě před exportem:
Před předáním sítě do solveru agent ověří:
1. Přítomnost výhradně 3D tetraedrů pro objemy a 2D trojúhelníků pro ohraničení.
2. Striktní absenci invertovaných elementů (minimální determinant Jakobiánu všech elementů musí být ostře větší než nula).
3. Že každá definovaná *Physical Group* obsahuje alespoň jeden element sítě.

---

## 7. Syntéza konfiguračního souboru pro Palace

Agent automaticky zkompiluje geometrická metadata a zadání simulace do hierarchické konfigurace pro Palace. Konfigurace musí obsahovat tyto provázané bloky:

### 1. Model a geometrické měřítko
* Odkaz na vygenerovaný soubor sítě.
* Definice normalizačního faktoru délky $L_0$ pro přepočet jednotek sítě na metry.

### 2. Domény a materiálové přiřazení
* Mapování identifikátorů doménových skupin (*Physical Volumes*) na fyzikální vlastnosti: relativní permitivitu $\varepsilon_r$, permeabilitu $\mu_r$ a dielektrický ztrátový činitel $\tan\delta$.

### 3. Hranice a buzení
* Přiřazení okrajové podmínky ideálního vodiče (PEC) příslušným plošným skupinám.
* Definice absorpčních stěn (Absorbing) s nastaveným řádem aproximace pro potlačení parazitních odrazů.
* Deklarace budicích portů: přiřazení ID plochy, charakteristické impedance a prostorového směru integračního vektoru napětí.

### 4. Řízení adaptivity (AMR)
* **Počet úrovní (MaxLevels):** Počet adaptačních kroků (obvykle 2 až 4).
* **Prahová hodnota zjemnění (Threshold):** Poměrná část nejvíce chybových elementů určených k rozsekání v každém cyklu (doporučený rozsah 0.25 až 0.4).
* **Metoda odhadu chyby (ErrorEstimate):** Zvolení energetické normy chyby nebo gradientního indikátoru reziduí Maxwellových rovnic.

### 5. Řešič a frekvenční sweep
* Volba typu problému (Driven simulation).
* Nastavení frekvenčního intervalu $[f_{min}, f_{max}]$, kroku vzorkování a typu lineárního iterativního řešiče s vhodným předpodmiňovačem pro Maxwellovy rovnice.

---

## 8. Fyzikální verifikace a samoopravná smyčka (Self-Healing Loop)

Ukončení výpočtu bez systémové chyby nezaručuje fyzikální správnost výsledku. Agent po doběhu simulace automaticky provede testy na výstupních datech:

```
[Konec simulace Palace]
          │
          ▼
[Kontrola běhových chyb v logu] ──► CHYBA ──► [Analýza konvergence / paměti]
          │
        BEZ CHYB
          │
          ▼
[Test pasivity: |S_ii|^2 + |S_ji|^2 ≤ 1.0] ──► SELHALO ──► [Korekce portů a absorpčních stěn]
          │
        PROŠLO
          │
          ▼
[Test reciprocity pasivního média: S_ij ≈ S_ji] ──► SELHALO ──► [Kontrola symetrie a orientace]
          │
        PROŠLO
          │
          ▼
[Ověření konvergence AMR: ΔS mezi cykly < limit] ──► SELHALO ──► [Zvýšení MaxLevels nebo změna prahu]
          │
        PROŠLO
          │
          ▼
[Generování finálních Touchstone dat a reportu]
```

### Diagnostické a nápravné akce při anomáliích:

1. **Detekce nepasivity ($|S| > 1.0$ neboli zisk v pasivní struktuře):**
   * *Příčina:* Nesprávná prostorová orientace integrační linie na portu (obrácená polarita fáze) nebo parazitní odrazy od vnějších absorpčních stěn umístěných příliš blízko struktury.
   * *Náprava:* Obrátit definovaný směr vektoru portu v konfiguraci; v případě potřeby zvětšit rozměry vnějšího vzduchového boxu.
2. **Divergence lineárního řešiče (`MaxIts reached`):**
   * *Příčina:* Špatně podmíněná soustava rovnic v důsledku příliš ostrých přechodů geometrie nebo blízkosti netlumené mezní rezonance.
   * *Náprava:* Zvýšit maximální povolený počet iterací, zjemnit toleranci předpodmiňovače nebo mírně upravit hustotu základní sítě v oblastech geometrických zlomů.
3. **AMR neprovádí žádné zjemňovací kroky:**
   * *Příčina:* Nastavený práh chyby je příliš přísný, nebo vstupní buzení nevybudilo v dané části sítě měřitelné pole.
   * *Náprava:* Snížit hodnotu parametru prahu zjemnění, zkontrolovat přítomnost a správné namapování buzení na vstupním portu.