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

def calc_feed_lengths(L, W, h, lambda_g, w1, w2, w3):
    """
    Uživatelská funkce pro výpočet jednotlivých délek mikropáskového vedení l1 až l8
    napájecí sítě cross-fed patch antény (kruhová polarizace LHCP dle napajeni.png).

    Přiřazení a definice délek l1 až l8:
    -----------------------------------
    1. Vstupní přívod (šířka w1 = 50 Ohm, budicí port -> T-uzel):
       - l1: Délka přívodního vedení od budicího portu na okraji substrátu (y = -L_sub/2)
             k T-uzlu děliče (x_T, y_T).

    2. Spodní referenční větev (fáze 0°, buzení pole Ey, spodní hrana flíčku):
       - l2: Horizontální úsek z T-uzlu doprava ke skoku šířky (šířka w2 = 100 Ohm, délka Delta).
       - l3: Horizontální úsek od skoku šířky k rohovému ohybu (šířka w3, přechod k ose flíčku x = 0).
       - l4: Vertikální úsek od rohového ohybu nahoru k dolní hraně flíčku (šířka w3, y = -L/2).

    3. Levá zpožďovací větev (fáze -90°, buzení pole Ex, levá hrana flíčku):
       - l5: Horizontální úsek z T-uzlu doleva k rohovému ohybu (šířka w2 = 100 Ohm, vybočení jog).
       - l6: Vertikální úsek od ohybu nahoru ke skoku šířky (šířka w2 = 100 Ohm, délka Delta + lambda_g/4).
       - l7: Vertikální úsek od skoku šířky k hornímu rohovému ohybu (šířka w3, k úrovni y = 0).
       - l8: Horizontální úsek od horního ohybu doprava k levé hraně flíčku (šířka w3, x = -W/2).

    Vstupní parametry:
        L (float): délka rezonančního flíčku [mm]
        W (float): šířka rezonančního flíčku [mm]
        h (float): výška dielektrického substrátu [mm]
        lambda_g (float): efektivní vlnová délka mikropásku v 100 Ohm větvi [mm]
                          (lambda_g = c_0 / (f_c * sqrt(eps_eff_w2)))
        w1 (float): šířka hlavního 50 Ohm přívodu [mm]
        w2 (float): šířka 100 Ohm ramen děliče výkonu [mm]
        w3 (float): šířka propojovacího vedení k anténě [mm]

    Návratová hodnota:
        dict: {'l1': float, 'l2': float, ..., 'l8': float} (všechny rozměry v mm)
    """

    l1 = 5*h + w2/2
    l2 = 5*h + w1/2
    l3 = W/4 + lambda_g/8 - 5*h - w1/2
    l4 = 5*h + w1/2 + lambda_g/8 - L/4
    l5 = 5*h + w1/2
    l6 = lambda_g/4
    l7 = L/4 + lambda_g/8 - 5*h - w1/2
    l8 = 5*h + w1/2 + lambda_g/8 - W/4

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

    # 2. Vyhodnocení upozornění: nedodržení minimálního odstupu 5*h + w3/2
    limit = 5.0 * h + (w3 / 2.0)
    if l8 < limit:
        msg = f"Nedodržena podmínka odstupu l8: l8 ({l8:.3f} mm) < 5*h + w3/2 ({limit:.3f} mm). Hrozí parazitní vazba flíčku s napájecím vedením!"
        warnings.warn(msg, UserWarning, stacklevel=2)
        print(f"[VAROVÁNÍ] {msg}")
    if l4 < limit:
        msg = f"Nedodržena podmínka odstupu l4: l4 ({l4:.3f} mm) < 5*h + w3/2 ({limit:.3f} mm). Hrozí parazitní vazba flíčku s napájecím vedením!"
        warnings.warn(msg, UserWarning, stacklevel=2)
        print(f"[VAROVÁNÍ] {msg}")
    return lengths

def calc_feed_network_dimensions(patch_w, patch_l, h, eps_r, freq_ghz=DESIGN_FREQ_GHZ, port_z0=PORT_Z0, w3=None, sub_margin=None):
    """
    Vypočte rozměry napájecí sítě dle specifikace v docs/abstrakce_zadani.md:
    1. w1: Hlavní vstupní vedení (50 Ohm, přirozeně přizpůsobeno T-uzlu 100 || 100 = 50 Ohm).
    2. w2: Větve děliče výkonu (100 Ohm), ze kterých se počítá fázovací zpoždění lambda_g/4.
    3. w3: Vodič k samotné anténě (optimalizační stupeň volnosti, w3 <= w2).
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

    # Výpočet délek vedení l1 až l8 uživatelskou funkcí s efektivní vlnovou délkou mikropásku lambda_g2
    feed_lengths = calc_feed_lengths(L=patch_l, W=patch_w, h=h, lambda_g=lambda_g2, w1=w1, w2=w2, w3=w3)

    l1 = float(feed_lengths['l1'])
    l2 = float(feed_lengths['l2'])
    l3 = float(feed_lengths['l3'])
    l4 = float(feed_lengths['l4'])
    l5 = float(feed_lengths['l5'])

    # Poloha T-uzlu odvozená přímo z délek spodní větve:
    # Dolní ohyb je na x=0, y=y_T. Spodní větev vede od T-uzlu (x_T, y_T) doprava: x_T + l2 + l3 = 0 -> x_T = -(l2 + l3)
    # Vertikální úsek l4 vede od y_T k dolní hraně flíčku -L/2: y_T = -L/2 - l4
    x_T = -(l2 + l3)
    y_T = -(patch_l / 2.0) - l4

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
        'feed_lengths': feed_lengths,
    }
    # Pro přímý přístup k l1 až l8 v params
    if isinstance(feed_lengths, dict):
        res.update(feed_lengths)
    elif isinstance(feed_lengths, (list, tuple)):
        for idx, val in enumerate(feed_lengths, start=1):
            res[f'l{idx}'] = val

    return res

