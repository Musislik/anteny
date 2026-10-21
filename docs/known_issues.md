# 📋 Seznam známých problémů a úkolů (Known Issues)

Tento dokument slouží jako centrální sledovací seznam (checklist) identifikovaných vysokofrekvenčních a geometrických nedostatků anténního systému, které jsou naplánovány k dalšímu řešení a ladění.

---

- [ ] **1. Odstup napájecího vedení od vyzařující hrany flíčku (Parazitní vazba / Near-field coupling)**
  - **Kategorie:** Geometrie / EM pole
  - **Popis problému:** Svislý úsek zpožďovacího vedení na levé straně běží rovnoběžně s vyzařující hranou flíčku ve vzdálenosti $l_8 - \text{inset} \approx 10.7\text{ mm}$ (cca $7\cdot h$). Protože levá hrana je vyzařující štěrbinou pro pole $E_x$ dominantního módu $TM_{10}$ a na vedení existuje silné blízké pole, dochází k nežádoucí parazitní vazbě (cross-talk) mezi flíčkem a napájecím páskem. V simulaci pole je patrné propojení halo oblaku mezi flíčkem a vedením.
  - **Dopad:** Mírné zkreslení tvaru vyzařovacího diagramu a parazitní modulace amplitudy buzení.
  - **Navržené řešení:** Zvětšit odstup levého svislého vedení od hrany flíčku na $\ge 15 - 20\text{ mm}$ ($> 10 - 12\cdot h$), např. úpravou rozvržení děliče nebo zavedením odsazovacího prvku (jog) před vstupem do flíčku.

---

- [ ] **2. Orientace fázování kruhové polarizace (Záměna LHCP za RHCP)**
  - **Kategorie:** VF syntéza / Fázování
  - **Popis problému:** Pro vyzařování levotočivé kruhové polarizace (LHCP) do horního poloprostoru ($+Z$) musí elektrické pole $E_x$ fázově předbíhat pole $E_y$ o $+90^\circ$ (nebo $E_y$ musí být zpožděno o $-90^\circ$). V současném návrhu je čtvrtvlnná zpožďovací linka $\lambda_g/4$ umístěna na levé větvi ($E_x$). Pole $E_x$ se tím pádem za $E_y$ zpožďuje, což nutí vektor pole rotovat po směru hodinových ručiček. Dálkové pole (`farfield-rE.csv`) proto vykazuje dominantně pravotočivou složku ($|E_{\text{RHCP}}| \approx 5.9\text{ V}$) oproti žádané levotočivé ($|E_{\text{LHCP}}| \approx 3.1\text{ V}$) s vysokým osovým poměrem ($AR \approx 10.2\text{ dB}$).
  - **Dopad:** Anténa nesplňuje zadání na LHCP a vyzařuje opačnou eliptickou polarizaci.
  - **Navržené řešení:** Přeorientovat zpožďovací úsek $\lambda_g/4$ z levé větve ($E_x$) na spodní větev ($E_y$), čímž se dosáhne požadovaného fázového předstihu $+90^\circ$ pro $E_x$ a čisté levotočivé rotace LHCP s osovým poměrem $AR < 3\text{ dB}$.

---

- [ ] **3. Optimalizace hloubky zanoření napaječe (Inset Feed Tuning)**
  - **Kategorie:** Impedanční přizpůsobení
  - **Popis problému:** Vstupní impedance na vnější hraně mikropáskového flíčku je přirozeně vysoká ($R_{\text{edge}} \approx 200 - 300\,\Omega$). Přívodní větve děliče mají impedanci $Z_2 = Z_3 = 100\,\Omega$. Přímé napojení na hranu bez zanoření způsobuje odraz $\Gamma \approx 0.5 - 0.7$ a silnou stojatou vlnu podél napaječe.
  - **Aktuální stav:** Rovnice napáječe v `rf_calc.py`, CAD geometrie v `geometry.py` a řídicí pipeline v `main.py` byly parametrizovány jedním parametrem `FEED_INSET` (hloubka zářezu).
  - **Navržené řešení:** Provést parametrický sweep hloubky zanoření $y_0 \in [0.0, 5.0]\text{ mm}$ v krocích po $0.5\text{ mm}$ dle teoretického vztahu $R_{\text{in}}(y_0) \approx R_{\text{edge}} \cos^2(\pi y_0 / L)$ a najít bod perfektního přizpůsobení na $100\,\Omega$ ($S_{11} < -20\text{ dB}$, potlačení stojaté vlny na vedení).

---

- [ ] **4. Absence izolace mezi větvemi v T-děliči výkonu**
  - **Kategorie:** Mikrovlnné obvody
  - **Popis problému:** Použitý jednoduchý T-uzel je bezztrátový trojbran bez izolačního odporu. Jakýkoliv zbytkový odraz od jedné hrany flíčku se v uzlu dělí a proniká do druhého ramene i do vstupního portu.
  - **Navržené řešení:** Pokud po odladění zanoření zůstane zbytková asymetrie buzení, zvážit náhradu T-děliče Wilkinsonovým děličem výkonu s integrovaným rezistorem $100\,\Omega$.
