# Abstrakce zadání: Návrh LHCP mikropáskové flíčkové antény

## 1. Cíle a požadavky
- **Frekvenční pásmo S:** 2.32 – 2.345 GHz (střední frekvence $f_c \approx 2.3325$ GHz)
- **Polarizace:** LHCP (levotočivá kruhová polarizace)
- **Zisk:** Minimálně 5.5 dBi
- **Činitel odrazu ($S_{11}$):** < -10 dB ve vymezeném pásmu
- **Osový poměr (Axial Ratio):** Co nejmenší, ideálně < 3 dB
- **Impedance napáječe:** $50\ \Omega$

## 2. Parametry substrátu (FR4)
- **Relativní permitivita ($\varepsilon_r$):** 4.3
- **Ztrátový činitel ($\tan\delta$):** 0.02
- **Výška substrátu ($h$):** 1.52 mm
- **Tloušťka mědi ($t$):** $36\ \mu\text{m}$ (možnost modelovat jako 2D hraniční vrstvu)

## 3. Geometrie a napájecí síť
- **Typ zářiče:** Čtvercový mikropáskový flíček (Square microstrip patch, obě délky hran $L=W$).
- **Způsob napájení:** Napájení ze dvou ortogonálních stran přes mikropáskový dělič výkonu (Cross-fed patch).
- **Topologie napájecího obvodu (z napajeni.png):**
  - T-uzel dělící výkon do dvou větví.
  - Větve mají rozdílnou délku: jedna $\Delta$, druhá $\Delta + \lambda_g/4$. Tento dodatečný čtvrtvlnný úsek způsobuje fázový posuv $-90^\circ$ mezi ortogonálními hranami zářiče, což generuje kruhovou polarizaci.
  - Hlavní přívodní vedení využívá impedanční čtvrtvlnný transformátor (o délce $\lambda_g/4$) pro impedanční přizpůsobení na $50\ \Omega$.

## 4. Klasifikace domén pro solver (dle směrnice)
- **Aktivní materiály:** FR4 substrát.
- **Vnější prostředí:** Otevřená vyzařující struktura vyžaduje vzduchový box o velikosti min. $\lambda_0/4$ od struktury.
- **Vodivé prvky:** Flíček, dělič a zemní plocha (spodní strana substrátu). Lze zjednodušit jako beztloušťkové plochy díky nízkému poměru $t/\lambda$.
- **Buzení:** 1 port (Lumped nebo Wave port) připojený na vstupní vedení.
- **Ohraničení simulační oblasti:** Na vnější stěny boxu bude aplikována absorpční (Radiation) podmínka pro simulaci volného prostoru.

## 5. Cílové technologické zajištění (Toolchain)
- **Geometrie:** Algoritmické sestavení v OpenCASCADE (CAD) se zaměřením na Boolean Fragments pro konformní síťování.
- **Mesh:** Hrubé prvotní síťování v Gmsh s ohledem na fyzikální skupiny (těžiště, bounding box).
- **Solver:** FEM simulace v Palace řízená pomocí AMR (Adaptive Mesh Refinement).
