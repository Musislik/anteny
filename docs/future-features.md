# 🚀 Plán budoucích funkcí a vylepšení (Future Features)

Tento dokument slouží jako přehled a specifikace pokročilých geometrických, obvodových a optimalizačních funkcí naplánovaných pro další rozvoj anténního systému.

---

## 1. Zkosení pravoúhlých ohybů napájecích vodičů (Mitered Bends)

* **Kategorie:** Mikrovlnné obvody / Geometrie vedení
* **Motivace a popis:**
  V současném návrhu jsou ohyby $100\,\Omega$ mikropáskového vedení modelovány jako ostré pravoúhlé rohy ($90^\circ$). V mikrovlnném pásmu ($2{,}33\text{ GHz}$) však ostrý roh způsobuje:
  - Parazitní hromadění náboje a přebytečnou kapacitu k zemi (kapacitní nespojitost).
  - Zvýšený činitel odrazu na každém ohybu ($S_{11,\text{bend}}$).
  - Parazitní fázové zpoždění odlišné od ideální elektrické délky.
  
  Protože levá (zpožďovací) větev má více ohybů než spodní referenční větev, neošetřené ohyby vnášejí nesymetrický útlum a fázovou chybu mezi oběma větvemi, což přímo degraduje osový poměr ($AR$).
* **Navržená realizace:**
  - Implementovat optimální zkosení rohu (tzv. *mitered bend* dle standardu Douville & James / IPC-2141):
    $$M = \frac{x}{w\sqrt{2}} \approx 0{,}52 + 0{,}65 \exp\left(-1{,}35 \frac{w}{h}\right)$$
    Pro $w_2 \approx 0{,}69\text{ mm}$ a $h = 1{,}52\text{ mm}$ ($w/h \approx 0{,}45$) odpovídá optimální odříznutí cca $50\text{–}60\,\%$ vnějšího rohu.
  - V OpenCASCADE (`geometry.py`) nahradit překrývající se obdélníky v rozích polygonem se seříznutou vnější hranou (nebo operací seříznutí / chamfer).
* **Očekávaný přínos:**
  - Minimalizace odrazů na ohybech vedení.
  - Vyrovnání přeneseného výkonu a fází mezi spodní a levou větví.
  - Zlepšení osového poměru ($AR$).

---

## 2. Možnost ladění rozdílným vnořením napaječe (Asymmetric / Independent Inset Feed Tuning)

* **Kategorie:** Impedanční přizpůsobení / Vyvážení amplitud
* **Motivace a popis:**
  V současné implementaci je hloubka zanoření řízena jedním globálním parametrem `FEED_INSET` ($y_0$), který aplikuje identickou hloubku zářezu pro spodní i levou hranu flíčku ($y_{0x} = y_{0y}$).
  
  V reálné struktuře však kvůli rozdílnému počtu ohybů, různé délce ramen a zbytkové parazitní vazbě vedení může docházet k drobné amplitudové asymetrii buzení ($|E_x| \neq |E_y|$). 
  
  Protože vstupní odpor flíčku strmě závisí na hloubce zanoření:
  $$R_{\text{in}}(y_0) \approx R_{\text{edge}} \cos^2\left(\frac{\pi y_0}{L}\right)$$
  umožňuje nezávislé nastavení hloubky zanoření pro každou osu samostatně řídit vstupní impedanci a množství absorbovaného výkonu pro daný ortogonální mód bez ovlivnění fázovací linky.
* **Navržená realizace:**
  - Rozšířit konfiguraci a CLI argumenty o nezávislé parametry:
    - `FEED_INSET_X` (nebo `feed_inset_left`) pro zářez na levé hraně ($E_x$, horizontální mód).
    - `FEED_INSET_Y` (nebo `feed_inset_bottom`) pro zářez na spodní hraně ($E_y$, vertikální mód).
    - Zachovat zpětnou kompatibilitu: pokud je zadán pouze `FEED_INSET`, použije se shodně pro obě hrany.
  - V [`rf_calc.py`](../src/rf_calc.py) a [`geometry.py`](../src/geometry.py) parametrizovat geometrické výřezy `notch_l` a `notch_b` samostatnými hloubkami `inset_x` a `inset_y`.
* **Očekávaný přínos:**
  - Možnost jemného vyrovnání amplitud $|E_x|$ a $|E_y|$ s přesností na desetiny dB nezávisle na fázovacím děliči.
  - Klíčový nástroj pro stlačení osového poměru ($AR$) pod mezní hodnotu $3\text{ dB}$ (ideálně $< 1{,}5\text{ dB}$).
