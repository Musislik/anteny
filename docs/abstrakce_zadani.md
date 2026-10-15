# Abstrakce zadání: Návrh LHCP mikropáskové flíčkové antény

## 1. Cíle a požadavky
- **Frekvenční pásmo S:** 2.32 – 2.345 GHz (střední frekvence fc ≈ 2.3325 GHz)
- **Polarizace:** LHCP (levotočivá kruhová polarizace)
- **Zisk:** Minimálně 5.5 dBi
- **Činitel odrazu (S₁₁):** < -10 dB ve vymezeném pásmu
- **Osový poměr (Axial Ratio):** Co nejmenší, ideálně < 3 dB
- **Impedance napáječe:** 50 Ω

## 2. Parametry substrátu (FR4)
- **Relativní permitivita (ε_r):** 4.3
- **Ztrátový činitel (tan δ):** 0.02
- **Výška substrátu (h):** 1.52 mm
- **Tloušťka mědi (t):** 36 μm (možnost modelovat jako 2D hraniční vrstvu)

## 3. Geometrie a napájecí síť
- **Typ zářiče:** Čtvercový mikropáskový flíček (Square microstrip patch, obě délky hran L = W).
- **Způsob napájení:** Napájení ze dvou ortogonálních stran přes mikropáskový fázovací dělič výkonu (Cross-fed patch dle [`napajeni.png`](napajeni.png)).
- **Princip generování LHCP (z napajeni.png):**
  - Výkon z hlavního vstupu je rozdělen symetricky (poměr 1:1) do dvou ortogonálních větví buzených s fázovým posuvem Δφ = -90°.
  - Referenční větev (spodní hrana flíčku, buzení pole Ey) má referenční délku Δ (fáze 0°).
  - Zpožďovací větev (levá hrana flíčku, buzení pole Ex) má prodlouženou délku Δ + λg/4, čímž vnáší dodatečné fázové zpoždění -90°.
  - Kombinace ortogonálního prostorového uspořádání a kvadraturního fázování generuje požadovanou levotočivou kruhovou polarizaci (LHCP).
- **Segmenty vedení a specifikace tří šířek spojů:**
  Napájecí obvod obsahuje tři odlišné šířky mikropáskových spojů:
  1. **Hlavní vstupní vedení (šířka w₁ – impedance 50 Ω):**
     - Přivádí signál od budicího portu (např. 50 Ω přívod / konektor) k T-uzlu děliče výkonu.
     - Šířka spoje w₁ se získá ze syntézy mikropásku pro požadovanou charakteristickou impedanci Z₁ = 50 Ω na použitém substrátu FR4 (h = 1.52 mm, ε_r = 4.3).
     - Analytická hodnota šířky je w₁ ≈ 2.98 mm.
  2. **Větve děliče výkonu (šířka w₂ – impedance 100 Ω):**
     - V T-uzlu se hlavní přívod dělí do dvou symetrických paralelních ramen.
     - Impedance každé z větví musí být dvakrát větší než hlavního vstupu, tedy Z₂ = 2 × Z₁ = 100 Ω.
     - Díky paralelnímu řazení dvou 100 Ω větví v uzlu je výsledná vstupní impedance děliče:
       `Z_in,T = Z₂ ∥ Z₂ = (100 Ω · 100 Ω) / (100 Ω + 100 Ω) = 50 Ω`
       Tím je přímo dosaženo přirozeného impedančního přizpůsobení k 50 Ω hlavnímu vstupu bez nutnosti dodatečného transformačního úseku v T-uzlu.
     - Šířka spoje w₂ se získá syntézou mikropásku pro Z₂ = 100 Ω na substrátu FR4 (analytická hodnota w₂ ≈ 0.69 mm).
     - Efektivní vlnová délka λg pro fázovací čtvrtvlnný úsek λg/4 se počítá z efektivní permitivity tohoto 100 Ω mikropásku (ε_eff ≈ 2.97, λg/4 ≈ 18.66 mm při fc = 2.3325 GHz).
  3. **Vodič k samotné anténě (šířka w₃ – optimalizační stupeň volnosti):**
     - Úsek vedení propojující výstupy fázovacího děliče s jednotlivými vstupními branami zářiče (flíčku).
     - Šířka w₃ představuje **stupeň volnosti** v návrhu – lze s ní hýbat a ladit ji pro optimalizaci přizpůsobení a minimalizaci činitele odrazu S₁₁.
     - **Meze šířky spoje:**
       - *Maximální mez:* Může být maximálně stejná jako pro vedení děliče (w₃ ≤ w₂, tj. w₃ ≤ 0.69 mm).
       - *Minimální mez:* Dána technologickými limity výroby DPS (typicky min. šířka spoje cca 0.15 až 0.2 mm).
- **Poznámka pro další výzkum (zatím neimplementovat!) – Ovlivňování impedance antény zasunutím napaječe (Inset feed):**
  - Vstupní impedance na vnější hraně mikropáskového flíčku bývá vysoká (R_edge ≈ 150 až 300 Ω).
  - Impedanci antény bude možné ovlivňovat a přizpůsobovat **zasunutím napaječe** (zářezem / inset feedem) o hloubku y₀ směrem do středu flíčku, kde impedance klesá podle vztahu:
    `R_in(y₀) ≈ R_edge · cos²(π · y₀ / L)`
  - Volbou hloubky zasunutí napaječe v kombinaci s volbou třetí šířky spoje w₃ lze dosáhnout přímého přizpůsobení antény na impedanci 100 Ω (nebo jinou cílovou hodnotu), což slouží jako námět pro navazující etapu výzkumu a ladění parametrů.

## 4. Klasifikace domén pro solver (dle směrnice)
- **Aktivní materiály:** FR4 substrát.
- **Vnější prostředí:** Otevřená vyzařující struktura vyžaduje vzduchový box o velikosti min. λ₀/4 od struktury.
- **Vodivé prvky:** Flíček, dělič a zemní plocha (spodní strana substrátu). Lze zjednodušit jako beztloušťkové plochy díky nízkému poměru t/λ.
- **Buzení:** 1 port (Lumped nebo Wave port) připojený na vstupní vedení.
- **Ohraničení simulační oblasti:** Na vnější stěny boxu bude aplikována absorpční (Radiation) podmínka pro simulaci volného prostoru.

## 5. Cílové technologické zajištění (Toolchain)
- **Geometrie:** Algoritmické sestavení v OpenCASCADE (CAD) se zaměřením na Boolean Fragments pro konformní síťování.
- **Mesh:** Hrubé prvotní síťování v Gmsh s ohledem na fyzikální skupiny (těžiště, bounding box).
- **Solver:** FEM simulace v Palace řízená pomocí AMR (Adaptive Mesh Refinement).
