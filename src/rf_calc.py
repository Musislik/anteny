"""
rf_calc.py - Analytické vysokofrekvenční výpočty a syntéza mikropáskových struktur
Založeno na standardních modelech (Hammerstad & Jensen, Wheeler, Bahl & Bhartia).
"""

import numpy as np
import warnings

# Základní fyzikální a technické konstanty
C_0_MM_GHZ = 299.792458       # Rychlost světla ve vakuu [mm * GHz]
ETA_0 = 376.7303135           # Vlnová impedance vakua [Ohm]
DESIGN_FREQ_GHZ = 2.3325      # Střední frekvence pásma SDARS (2.320 - 2.345 GHz) [GHz]
PORT_Z0 = 50.0                # Jmenovitá impedance portu [Ohm]

def calc_microstrip_eps_eff(w, h, eps_r):
    """
    Vypočte efektivní permitivitu mikropáskového vedení (Hammerstad & Jensen).
    :param w: Šířka mikropásku [mm]
    :param h: Výška substrátu [mm]
    :param eps_r: Relativní permitivita substrátu [-]
    :return: eps_eff [-]
    """
    u = w / h
    eps_eff = (eps_r + 1.0) / 2.0 + ((eps_r - 1.0) / 2.0) * (1.0 / np.sqrt(1.0 + 12.0 / u))
    return float(eps_eff)

def calc_microstrip_z0(w, h, eps_r):
    """
    Vypočte charakteristickou impedanci mikropáskového vedení Z0.
    """
    u = w / h
    eps_eff = calc_microstrip_eps_eff(w, h, eps_r)
    if u <= 1.0:
        z0 = (60.0 / np.sqrt(eps_eff)) * np.log(8.0 / u + 0.25 * u)
    else:
        z0 = (120.0 * np.pi / np.sqrt(eps_eff)) / (u + 1.393 + 0.667 * np.log(u + 1.444))
    return float(z0)

def synth_microstrip_w(z0_target, h, eps_r):
    """
    Syntetizuje šířku mikropásku w pro cílovou charakteristickou impedanci Z0 (Wheeler/Bahl).
    """
    a = (z0_target / 60.0) * np.sqrt((eps_r + 1.0) / 2.0) + ((eps_r - 1.0) / (eps_r + 1.0)) * (0.23 + 0.11 / eps_r)
    b = (377.0 * np.pi) / (2.0 * z0_target * np.sqrt(eps_r))
    
    # Počáteční odhad u = w / h
    if a > 1.52:
        u = 8.0 * np.exp(a) / (np.exp(2.0 * a) - 2.0)
    else:
        u = (2.0 / np.pi) * (b - 1.0 - np.log(2.0 * b - 1.0) + ((eps_r - 1.0) / (2.0 * eps_r)) * (np.log(b - 1.0) + 0.39 - 0.61 / eps_r))
        
    w = u * h
    
    # Newtonova zpřesňující iterace
    for _ in range(5):
        current_z0 = calc_microstrip_z0(w, h, eps_r)
        diff = current_z0 - z0_target
        if abs(diff) < 1e-4:
            break
        # Numerická derivace
        dw = 1e-4
        z0_plus = calc_microstrip_z0(w + dw, h, eps_r)
        dz_dw = (z0_plus - current_z0) / dw
        w -= diff / dz_dw

    return float(w)

def calc_quarter_wave_length(freq_ghz, eps_eff):
    """
    Vypočte čtvrtvlnnou délku vedení lambda_g / 4 pro danou frekvenci a efektivní permitivitu.
    :param freq_ghz: Frekvence v GHz
    :param eps_eff: Efektivní permitivita vedení
    :return: lambda_g / 4 v mm
    """
    lambda_0 = C_0_MM_GHZ / freq_ghz
    lambda_g = lambda_0 / np.sqrt(eps_eff)
    return float(lambda_g / 4.0)

def calc_quarter_wave_transformer_z(z_source, z_load):
    """
    Vypočte impedanci čtvrtvlnného přizpůsobovacího transformátoru:
    Z_trans = sqrt(Z_source * Z_load)
    """
    return float(np.sqrt(z_source * z_load))

def calc_patch_fringing(w, h, eps_r):
    """
    Vypočte prodloužení flíčku delta_L způsobené rozptylovým polem (Hammerstad).
    """
    eps_eff = calc_microstrip_eps_eff(w, h, eps_r)
    u = w / h
    delta_l = 0.412 * h * ((eps_eff + 0.3) * (u + 0.264)) / ((eps_eff - 0.258) * (u + 0.8))
    return float(delta_l), float(eps_eff)

def calc_patch_resonance(patch_w, patch_l, h, eps_r):
    """
    Vypočte efektivní délku a rezonanční frekvenci flíčku.
    """
    delta_l, eps_eff = calc_patch_fringing(patch_w, h, eps_r)
    l_eff = patch_l + 2.0 * delta_l
    f_res = C_0_MM_GHZ / (2.0 * l_eff * np.sqrt(eps_eff))
    return float(f_res), float(l_eff), float(eps_eff)

def synth_square_patch_size(freq_ghz, h, eps_r):
    """
    Syntetizuje rozměr čtvercového mikropáskového flíčku L = W pro požadovanou rezonanční frekvenci.
    Využívá analytický model rozptylu a Newtonovu iterační metodu.
    """
    l = C_0_MM_GHZ / (2.0 * freq_ghz * np.sqrt(eps_r))
    for _ in range(20):
        f_cur, _, _ = calc_patch_resonance(l, l, h, eps_r)
        diff = f_cur - freq_ghz
        if abs(diff) < 1e-6:
            break
        dl = 1e-3
        f_plus, _, _ = calc_patch_resonance(l + dl, l + dl, h, eps_r)
        df_dl = (f_plus - f_cur) / dl
        l -= diff / df_dl
    return float(l)

def synth_patch_length(freq_ghz, patch_w, h, eps_r):
    """
    Syntetizuje rezonanční délku flíčku L pro zadanou šířku patch_w.
    """
    delta_l, eps_eff = calc_patch_fringing(patch_w, h, eps_r)
    l_eff = C_0_MM_GHZ / (2.0 * freq_ghz * np.sqrt(eps_eff))
    l = l_eff - 2.0 * delta_l
    return float(l)

def calc_patch_edge_impedance(patch_w, patch_l, h, eps_r):
    """
    Orientační vstupní odpor na okraji mikropáskového flíčku (Bahl & Bhartia).
    Typicky se pohybuje mezi 150 a 300 Ohmy.
    """
    # Pro čtvercový/blízce čtvercový flíček:
    g1 = (patch_w / 120.0) * (1.0 - (1.0 / 24.0) * (2.0 * np.pi * DESIGN_FREQ_GHZ * h / C_0_MM_GHZ)**2)
    # R_in = 1 / (2 * G1)
    r_in = 1.0 / max(2.0 * g1, 1e-4)
    # Zastropujeme do fyzikálně realistického rozsahu
    return float(np.clip(r_in, 150.0, 300.0))

def calc_feed_lengths(L, W, h, lambda_g, w1, w2, w3, inset=0.0):
    """
    Uživatelská funkce pro výpočet jednotlivých délek mikropáskového vedení l1 až l8
    napájecí sítě cross-fed patch antény (kruhová polarizace LHCP dle napajeni.png).
    Umožňuje zanoření napaječe (inset feed) o hloubku inset do vyzařujícího flíčku.

    Přiřazení a definice délek l1 až l8:
    -----------------------------------
    1. Vstupní přívod (šířka w1 = 50 Ohm, budicí port -> T-uzel):
       - l1: Délka přívodního vedení od budicího portu na okraji substrátu (y = -L_sub/2)
             k T-uzlu děliče (x_T, y_T).

    2. Spodní referenční větev (fáze 0°, buzení pole Ey, spodní hrana flíčku):
       - l2: Horizontální úsek z T-uzlu doprava ke skoku šířky (šířka w2 = 100 Ohm, délka Delta).
       - l3: Horizontální úsek od skoku šířky k rohovému ohybu (šířka w3, přechod k ose flíčku x = 0).
       - l4: Vertikální úsek od rohového ohybu nahoru k napájecímu bodu flíčku (šířka w3, y = -L/2 + inset).

    3. Levá zpožďovací větev (fáze -90°, buzení pole Ex, levá hrana flíčku):
       - l5: Horizontální úsek z T-uzlu doleva k rohovému ohybu (šířka w2 = 100 Ohm, vybočení jog).
       - l6: Vertikální úsek od ohybu nahoru ke skoku šířky (šířka w2 = 100 Ohm, délka Delta + lambda_g/4).
       - l7: Vertikální úsek od skoku šířky k hornímu rohovému ohybu (šířka w3, k úrovni y = 0).
       - l8: Horizontální úsek od horního ohybu doprava k napájecímu bodu flíčku (šířka w3, x = -W/2 + inset).

    Vstupní parametry:
        L (float): délka rezonančního flíčku [mm]
        W (float): šířka rezonančního flíčku [mm]
        h (float): výška dielektrického substrátu [mm]
        lambda_g (float): efektivní vlnová délka mikropásku v 100 Ohm větvi [mm]
                          (lambda_g = c_0 / (f_c * sqrt(eps_eff_w2)))
        w1 (float): šířka hlavního 50 Ohm přívodu [mm]
        w2 (float): šířka 100 Ohm ramen děliče výkonu [mm]
        w3 (float): šířka propojovacího vedení k anténě [mm]
        inset (float): hloubka zanoření napaječe do flíčku [mm] (výchozí: 0.0)

    Návratová hodnota:
        dict: {'l1': float, 'l2': float, ..., 'l8': float} (všechny rozměry v mm)
    """

    l1 = 10*h + w2/2
    l2 = 15*h + w1/2
    l3 = W/4 + lambda_g/8 - 5*h - w1/2
    l4 = 15*h + w1/2 + lambda_g/8 - L/4 + inset
    l5 = 5*h + w1/2
    l6 = lambda_g/4
    l7 = L/4 + 15*h + w1/2 - lambda_g/8
    l8 = 15*h + w1/2 + lambda_g/8 - W/4 + inset

    lengths = {
        'l1': float(np.round(l1, 3)),
        'l2': float(np.round(l2, 3)),
        'l3': float(np.round(l3, 3)),
        'l4': float(np.round(l4, 3)),
        'l5': float(np.round(l5, 3)),
        'l6': float(np.round(l6, 3)),
        'l7': float(np.round(l7, 3)),
        'l8': float(np.round(l8, 3)),
    }

    # 1. Vyhodnocení chyby: nulový nebo záporný rozměr
    for name, val in lengths.items():
        if val <= 0.0:
            raise ValueError(f"Chyba návrhu napájecího obvodu: Rozměr {name} nesmí být nulový ani záporný ({name} = {val:.3f} mm)!")

    # 2. Vyhodnocení upozornění: nedodržení minimálního odstupu 5*h + w3/2 vně flíčku
    limit = 5.0 * h + (w3 / 2.0)
    if (l8 - inset) < limit:
        msg = f"Nedodržena podmínka odstupu l8 vně flíčku: ({l8 - inset:.3f} mm) < 5*h + w3/2 ({limit:.3f} mm). Hrozí parazitní vazba flíčku s napájecím vedením!"
        warnings.warn(msg, UserWarning, stacklevel=2)
        print(f"[VAROVÁNÍ] {msg}")
    if (l4 - inset) < limit:
        msg = f"Nedodržena podmínka odstupu l4 vně flíčku: ({l4 - inset:.3f} mm) < 5*h + w3/2 ({limit:.3f} mm). Hrozí parazitní vazba flíčku s napájecím vedením!"
        warnings.warn(msg, UserWarning, stacklevel=2)
        print(f"[VAROVÁNÍ] {msg}")
    return lengths

def calc_feed_network_dimensions(patch_w, patch_l, h, eps_r, freq_ghz=DESIGN_FREQ_GHZ, port_z0=PORT_Z0, w3=None, sub_margin=None, inset=0.0):
    """
    Vypočte rozměry napájecí sítě dle specifikace v docs/abstrakce_zadani.md:
    1. w1: Hlavní vstupní vedení (50 Ohm, přirozeně přizpůsobeno T-uzlu 100 || 100 = 50 Ohm).
    2. w2: Větve děliče výkonu (100 Ohm), ze kterých se počítá fázovací zpoždění lambda_g/4.
    3. w3: Vodič k samotné anténě (optimalizační stupeň volnosti, w3 <= w2).
    4. inset: Zanoření napájecího vedení do flíčku (jediný parametr pro inset feed).
    """
    # 1. Hlavní přívodní vedení (w1, 50 Ohm)
    w1 = synth_microstrip_w(port_z0, h, eps_r)
    eps_eff_w1 = calc_microstrip_eps_eff(w1, h, eps_r)

    # 2. Větve děliče výkonu (w2, 100 Ohm)
    # Z2 = 2 * Z1 = 100 Ohm -> Z_in,T = 100 || 100 = 50 Ohm (přirozené přizpůsobení, bez transformátoru)
    z_branch = 2.0 * port_z0
    w2 = synth_microstrip_w(z_branch, h, eps_r)
    eps_eff_w2 = calc_microstrip_eps_eff(w2, h, eps_r)
    lambda_g2_4 = calc_quarter_wave_length(freq_ghz, eps_eff_w2)
    lambda_g2 = 4.0 * lambda_g2_4

    # 3. Vodič k anténě (w3, stupeň volnosti, mez: w3 <= w2)
    if w3 is None:
        w3 = w2

    eps_eff_w3 = calc_microstrip_eps_eff(w3, h, eps_r)
    lambda_g3_4 = calc_quarter_wave_length(freq_ghz, eps_eff_w3)

    # Vlnová délka rovinné vlny v dielektriku (TEM)
    lambda_0 = C_0_MM_GHZ / freq_ghz
    lambda_sub = lambda_0 / np.sqrt(eps_r)

    # Výpočet délek vedení l1 až l8 uživatelskou funkcí s efektivní vlnovou délkou mikropásku lambda_g2 a parametrem inset
    feed_lengths = calc_feed_lengths(L=patch_l, W=patch_w, h=h, lambda_g=lambda_g2, w1=w1, w2=w2, w3=w3, inset=inset)

    l1 = float(feed_lengths['l1'])
    l2 = float(feed_lengths['l2'])
    l3 = float(feed_lengths['l3'])
    l4 = float(feed_lengths['l4'])
    l5 = float(feed_lengths['l5'])

    # Poloha T-uzlu odvozená přímo z délek spodní větve:
    # Dolní ohyb je na x=0, y=y_T. Spodní větev vede od T-uzlu (x_T, y_T) doprava: x_T + l2 + l3 = 0 -> x_T = -(l2 + l3)
    # Vertikální úsek l4 vede od y_T k napájecímu bodu (-L/2 + inset): y_T = -(patch_l / 2.0) + inset - l4
    x_T = -(l2 + l3)
    y_T = -(patch_l / 2.0) + inset - l4

    feed_offset_x = float(np.round(abs(x_T) - (patch_w / 2.0), 1))
    feed_offset_y = float(np.round(abs(y_T) - (patch_l / 2.0), 1))

    # Fyzikální rezerva dielektrika substrátu za kovem (standardní odstup 5*h pro doznění rozptylových polí)
    if sub_margin is None:
        sub_margin = 5.0 * h

    # Rozměry substrátu odvozené z reálného dosahu vedení l1 až l8 a šířek w1, w2, w3:
    # V ose Y: od portu (y_T - l1) k horní hraně patche (+L/2) s rezervou sub_margin
    y_needed = max(abs(y_T - l1), (patch_l / 2.0) + sub_margin)
    sub_l = float(np.round(2.0 * y_needed, 1))

    # V ose X: od levého okraje vedení (x_T - l5 - w2/2) k pravé hraně patche (+W/2) s rezervou sub_margin
    x_needed = max(abs(x_T - l5) + (w2 / 2.0), (patch_w / 2.0)) + sub_margin
    sub_w = float(np.round(2.0 * x_needed, 1))

    res = {
        'w1': float(np.round(w1, 2)),
        'w2': float(np.round(w2, 2)),
        'w3': float(np.round(w3, 2)),
        'feed_w': float(np.round(w1, 2)),          # Zpětná kompatibilita pro port
        'eps_eff_w1': float(np.round(eps_eff_w1, 3)),
        'eps_eff_w2': float(np.round(eps_eff_w2, 3)),
        'eps_eff_w3': float(np.round(eps_eff_w3, 3)),
        'lambda_g': float(np.round(lambda_g2, 3)),
        'lambda_g2_4': float(np.round(lambda_g2_4, 3)),
        'lambda_g3_4': float(np.round(lambda_g3_4, 3)),
        'lambda_g_4': float(np.round(lambda_g2_4, 3)),  # Zpětná kompatibilita
        'lambda_sub': float(np.round(lambda_sub, 3)),
        'feed_x_T': float(np.round(x_T, 3)),
        'feed_y_T': float(np.round(y_T, 3)),
        'feed_offset_x': feed_offset_x,
        'feed_offset_y': feed_offset_y,
        'sub_l': sub_l,
        'sub_w': sub_w,
        'sub_L': sub_l,
        'sub_W': sub_w,
        'inset': float(np.round(inset, 3)),
        'feed_lengths': feed_lengths,
    }
    # Pro přímý přístup k l1 až l8 v params
    if isinstance(feed_lengths, dict):
        res.update(feed_lengths)
    elif isinstance(feed_lengths, (list, tuple)):
        for idx, val in enumerate(feed_lengths, start=1):
            res[f'l{idx}'] = val

    return res


def calc_microstrip_propagation(w, h, eps_r, tan_delta=0.02, freqs_ghz=DESIGN_FREQ_GHZ):
    """
    Vypočte vlnové parametry mikropáskového vedení:
    Z0, eps_eff, fázovou konstantu beta [rad/mm], konstantu útlumu alpha [Np/mm]
    a komplexní konstantu šíření gamma = alpha + j*beta [1/mm].

    :param w: Šířka mikropásku [mm]
    :param h: Výška substrátu [mm]
    :param eps_r: Relativní permitivita substrátu [-]
    :param tan_delta: Ztrátový činitel dielektrika [-]
    :param freqs_ghz: Frekvence v GHz (skalár nebo numpy pole)
    :return: (Z0, eps_eff, beta, alpha, gamma)
    """
    w = float(w)
    h = float(h)
    eps_r = float(eps_r)
    tan_delta = float(tan_delta)

    eps_eff = calc_microstrip_eps_eff(w, h, eps_r)
    z0 = calc_microstrip_z0(w, h, eps_r)

    is_scalar = np.ndim(freqs_ghz) == 0
    freqs = np.atleast_1d(np.asarray(freqs_ghz, dtype=float))

    # Vlnové číslo ve vakuu k0 [rad/mm]
    k0 = (2.0 * np.pi * freqs) / C_0_MM_GHZ

    # Fázová konstanta beta [rad/mm]
    beta = k0 * np.sqrt(eps_eff)

    # Útlum dielektrikem alpha_d [Np/mm]
    if eps_r > 1.0 and tan_delta > 0.0:
        alpha_d = (k0 * eps_r * (eps_eff - 1.0) * tan_delta) / (2.0 * np.sqrt(eps_eff) * (eps_r - 1.0))
    else:
        alpha_d = np.zeros_like(freqs)

    # Útlum vodičem alpha_c [Np/mm] (měď: sigma = 5.8e7 S/m)
    # R_s = sqrt(pi * f * mu0 / sigma)
    mu_0 = 4.0 * np.pi * 1e-7
    sigma_cu = 5.8e7
    r_s = np.sqrt(np.pi * (freqs * 1e9) * mu_0 / sigma_cu)
    w_m = max(w * 1e-3, 1e-6)
    alpha_c = (r_s / (z0 * w_m)) * 1e-3

    alpha = alpha_d + alpha_c
    gamma = alpha + 1j * beta

    if is_scalar:
        return float(z0), float(eps_eff), float(beta[0]), float(alpha[0]), complex(gamma[0])
    return z0, eps_eff, beta, alpha, gamma


def deembed_transmission_line(zin, z0_line, gamma, length_mm):
    """
    Provede analytický de-embedding úseku přenosového vedení (zpětná transformace impedance/odrazu).
    Posouvá referenční rovinu směrem k zátěži (odečtení délky vedení length_mm).

    Využívá zpětnou transformaci komplexního činitele odrazu:
    Gamma_L = Gamma_in * exp(+2 * gamma * length_mm)
    a následný přepočet na impedanci zátěže:
    Z_L = Z0_line * (1 + Gamma_L) / (1 - Gamma_L)

    :param zin: Komplexní vstupní impedance před de-embeddingem [Ohm]
    :param z0_line: Charakteristická impedance de-embedovaného vedení [Ohm]
    :param gamma: Komplexní konstanta šíření vedení gamma = alpha + j*beta [1/mm]
    :param length_mm: Fyzická délka úseku vedení k odečtení [mm]
    :return: Komplexní impedance Z_L v de-embedované rovině [Ohm]
    """
    zin_arr = np.asarray(zin, dtype=complex)
    is_scalar = np.ndim(zin) == 0

    if length_mm is None or abs(length_mm) < 1e-9:
        return complex(zin_arr) if is_scalar else zin_arr

    z0 = float(z0_line)
    length = float(length_mm)

    # Vstupní činitel odrazu vztažený k impedanci daného vedení Z0
    gamma_in = (zin_arr - z0) / (zin_arr + z0 + 1e-12)

    # Posun roviny k zátěži (odstranění fázového zpoždění a útlumu: exp(+2 * gamma * length))
    gamma_l = gamma_in * np.exp(2.0 * gamma * length)

    # Zpětný přepočet na impedanci zátěže
    denom = 1.0 - gamma_l
    safe_denom = np.where(np.abs(denom) < 1e-12, 1e-12, denom)
    z_load = z0 * (1.0 + gamma_l) / safe_denom

    if is_scalar:
        return complex(z_load)
    return z_load


def calculate_deembedding_model3(freqs, s11_complex, s22_complex=None, params=None):
    """
    Provede kompletní kaskádní de-embedding impedančních skoků pro Model 3 (i Model 2 a Model 1 fallback)
    přes 3 referenční roviny:
      - RP1 (Port): svorka lumped portu na okraji substrátu (Z0_port = 100 Ohm)
      - RP2 (Svorka transformátoru): po odečtení délky vnějšího 100 Ohm vedení L_100
      - RP3 (Vstup do flíčku): po odečtení čtvrtvlnného transformátoru w_T, l_T (cíl ~140 Ohm)

    :param freqs: Pole frekvencí [GHz]
    :param s11_complex: Komplexní odraz Portu 1 (spodní rameno Ey) na RP1
    :param s22_complex: Komplexní odraz Portu 2 (levé rameno Ex) na RP1 (volitelné)
    :param params: Slovník parametrů modelu (geometrie, substrát, délky)
    :return: Slovník s výsledky pro RP1, RP2, RP3
    """
    if params is None:
        params = {}

    model = int(params.get('antenna_model', 3))
    h = float(params.get('sub_h', 1.52))
    eps_r = float(params.get('eps_r', 4.3))
    tan_delta = float(params.get('tan_delta', 0.02))
    f_design = float(params.get('design_freq_ghz', DESIGN_FREQ_GHZ))

    default_z0 = 100.0 if model in (2, 3) else PORT_Z0
    port_z0 = float(params.get('port_impedance', default_z0))

    freqs_arr = np.atleast_1d(np.asarray(freqs, dtype=float))
    s11_arr = np.atleast_1d(np.asarray(s11_complex, dtype=complex))
    s22_arr = np.atleast_1d(np.asarray(s22_complex, dtype=complex)) if s22_complex is not None else None

    # --- 1. RP1: Rovina portu ---
    z1_rp1 = port_z0 * (1.0 + s11_arr) / (1.0 - s11_arr + 1e-12)
    gamma1_rp1_db = 20.0 * np.log10(np.clip(np.abs(s11_arr), 1e-10, 10.0))

    if s22_arr is not None:
        z2_rp1 = port_z0 * (1.0 + s22_arr) / (1.0 - s22_arr + 1e-12)
        gamma2_rp1_db = 20.0 * np.log10(np.clip(np.abs(s22_arr), 1e-10, 10.0))
    else:
        z2_rp1 = None
        gamma2_rp1_db = None

    # Fallback pro Model 1
    if model == 1:
        return {
            'freqs': freqs_arr,
            'model': 1,
            'rp1': {
                'name': 'RP1 (Port 50 Ω)',
                'z1': z1_rp1,
                'z2': None,
                'gamma1_db': gamma1_rp1_db,
                'gamma2_db': None,
                'z0_ref': port_z0,
            },
            'rp2': {
                'name': 'RP2 (T-dělič)',
                'z1': z1_rp1,
                'z2': None,
                'gamma1_db': gamma1_rp1_db,
                'gamma2_db': None,
                'z0_ref': port_z0,
            },
            'rp3': {
                'name': 'RP3 (Flíček)',
                'z1': z1_rp1,
                'z2': None,
                'gamma1_db': gamma1_rp1_db,
                'gamma2_db': None,
                'z0_ref': port_z0,
            },
            'params_used': {'antenna_model': 1, 'port_z0': port_z0}
        }

    # Parametry vnějšího 100 Ohm mikropáskového vedení
    w_feed = float(params.get('w_feed', params.get('feed_W', synth_microstrip_w(100.0, h, eps_r))))
    z0_feed, eps_eff_feed, _, _, gamma_feed = calc_microstrip_propagation(w_feed, h, eps_r, tan_delta, freqs_arr)

    # Odvození délek vnějšího 100 Ohm úseku
    l_T_default_val = None
    w_T_def = float(params.get('trans_w', params.get('w_T', 0.42)))
    if model == 3:
        eps_eff_tdef = calc_microstrip_eps_eff(w_T_def, h, eps_r)
        l_T_default_val = calc_quarter_wave_length(f_design, eps_eff_tdef)

    l_T_b = float(params.get('trans_l_b', params.get('l_T_b', params.get('trans_l', params.get('l_T', l_T_default_val if model == 3 else 0.0)))))
    l_T_l = float(params.get('trans_l_l', params.get('l_T_l', params.get('trans_l', params.get('l_T', l_T_default_val if model == 3 else 0.0)))))

    if model == 2:
        l_T_b = 0.0
        l_T_l = 0.0

    raw_L_100_b = params.get('L_100_b')
    raw_L_100_l = params.get('L_100_l')

    if raw_L_100_b is not None:
        L_100_b = float(raw_L_100_b)
    elif params.get('feed_len_b') is not None:
        L_100_b = float(params['feed_len_b']) - l_T_b
    else:
        # Výchozí geometrie
        W = float(params.get('patch_W', params.get('patch_L', 28.8)))
        W_sub = float(params.get('sub_W', params.get('sub_w', 80.0)))
        inset_b = float(params.get('feed_inset_b', params.get('inset_b', 2.5 if model == 3 else 0.0)))
        feed_delta_l = float(params.get('feed_delta_l', calc_quarter_wave_length(f_design, eps_eff_feed)))
        L_100_l_def = max(8.0, (W_sub / 2.0) - (W / 2.0) + inset_b - l_T_l)
        L_100_b = L_100_l_def + feed_delta_l

    if raw_L_100_l is not None:
        L_100_l = float(raw_L_100_l)
    elif params.get('feed_len_l') is not None:
        L_100_l = float(params['feed_len_l']) - l_T_l
    else:
        W = float(params.get('patch_W', params.get('patch_L', 28.8)))
        W_sub = float(params.get('sub_W', params.get('sub_w', 80.0)))
        inset_l = float(params.get('feed_inset_l', params.get('inset_l', 2.5 if model == 3 else 0.0)))
        L_100_l = max(8.0, (W_sub / 2.0) - (W / 2.0) + inset_l - l_T_l)

    # --- 2. RP2: Svorka transformátoru (po odečtení L_100) ---
    z1_rp2 = deembed_transmission_line(z1_rp1, z0_feed, gamma_feed, L_100_b)
    gamma1_rp2 = (z1_rp2 - z0_feed) / (z1_rp2 + z0_feed + 1e-12)
    gamma1_rp2_db = 20.0 * np.log10(np.clip(np.abs(gamma1_rp2), 1e-10, 10.0))

    if z2_rp1 is not None:
        z2_rp2 = deembed_transmission_line(z2_rp1, z0_feed, gamma_feed, L_100_l)
        gamma2_rp2 = (z2_rp2 - z0_feed) / (z2_rp2 + z0_feed + 1e-12)
        gamma2_rp2_db = 20.0 * np.log10(np.clip(np.abs(gamma2_rp2), 1e-10, 10.0))
    else:
        z2_rp2 = None
        gamma2_rp2_db = None

    # --- 3. RP3: Vstup do flíčku (po odečtení l_T) ---
    if model == 3 and (l_T_b > 0.0 or l_T_l > 0.0):
        w_T_b = float(params.get('trans_w_b', params.get('w_T_b', params.get('trans_w', 0.42))))
        w_T_l = float(params.get('trans_w_l', params.get('w_T_l', params.get('trans_w', 0.42))))

        z0_Tb, _, _, _, gamma_Tb = calc_microstrip_propagation(w_T_b, h, eps_r, tan_delta, freqs_arr)
        z0_Tl, _, _, _, gamma_Tl = calc_microstrip_propagation(w_T_l, h, eps_r, tan_delta, freqs_arr)

        z1_rp3 = deembed_transmission_line(z1_rp2, z0_Tb, gamma_Tb, l_T_b)
        z2_rp3 = deembed_transmission_line(z2_rp2, z0_Tl, gamma_Tl, l_T_l) if z2_rp2 is not None else None

        # Cílová reference na flíčku v zářezu ~140 Ohm (R_patch = Z_T^2 / 100)
        z0_rp3 = float(params.get('z_target_rp3', (z0_Tb**2) / 100.0 if np.ndim(z0_Tb) == 0 else (z0_Tb[0]**2) / 100.0))
    else:
        # Pro Model 2 je l_T = 0, RP2 splývá s RP3
        w_T_b = None
        w_T_l = None
        z0_Tb = None
        z0_Tl = None
        z1_rp3 = z1_rp2
        z2_rp3 = z2_rp2
        z0_rp3 = 100.0

    gamma1_rp3 = (z1_rp3 - z0_rp3) / (z1_rp3 + z0_rp3 + 1e-12)
    gamma1_rp3_db = 20.0 * np.log10(np.clip(np.abs(gamma1_rp3), 1e-10, 10.0))

    if z2_rp3 is not None:
        gamma2_rp3 = (z2_rp3 - z0_rp3) / (z2_rp3 + z0_rp3 + 1e-12)
        gamma2_rp3_db = 20.0 * np.log10(np.clip(np.abs(gamma2_rp3), 1e-10, 10.0))
    else:
        gamma2_rp3_db = None

    return {
        'freqs': freqs_arr,
        'model': model,
        'rp1': {
            'name': 'RP1 (Port)',
            'z1': z1_rp1,
            'z2': z2_rp1,
            'gamma1_db': gamma1_rp1_db,
            'gamma2_db': gamma2_rp1_db,
            'z0_ref': port_z0,
        },
        'rp2': {
            'name': 'RP2 (Transformátor svorka)' if model == 3 else 'RP2 (Flíček)',
            'z1': z1_rp2,
            'z2': z2_rp2,
            'gamma1_db': gamma1_rp2_db,
            'gamma2_db': gamma2_rp2_db,
            'z0_ref': z0_feed,
        },
        'rp3': {
            'name': 'RP3 (Flíček vstup)',
            'z1': z1_rp3,
            'z2': z2_rp3,
            'gamma1_db': gamma1_rp3_db,
            'gamma2_db': gamma2_rp3_db,
            'z0_ref': z0_rp3,
        },
        'params_used': {
            'antenna_model': model,
            'port_z0': port_z0,
            'w_feed': w_feed,
            'z0_feed': float(np.mean(z0_feed)),
            'L_100_b': L_100_b,
            'L_100_l': L_100_l,
            'w_T_b': w_T_b,
            'w_T_l': w_T_l,
            'l_T_b': l_T_b,
            'l_T_l': l_T_l,
            'z0_rp3': z0_rp3,
        }
    }


