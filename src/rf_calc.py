"""
rf_calc.py - Analytické vysokofrekvenční výpočty a syntéza mikropáskových struktur
Založeno na standardních modelech (Hammerstad & Jensen, Wheeler, Bahl & Bhartia).
"""

import numpy as np

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

def calc_feed_network_dimensions(patch_w, patch_l, h, eps_r, freq_ghz=DESIGN_FREQ_GHZ, port_z0=PORT_Z0):
    """
    Vypočte veškeré rozměry napájecí sítě (vedení, čtvrtvlnné transformátory, zpožďovací linku,
    odsazení T-uzlu a doporučené rozměry substrátu).
    """
    feed_w = synth_microstrip_w(port_z0, h, eps_r)
    eps_eff_feed = calc_microstrip_eps_eff(feed_w, h, eps_r)
    lambda_g_4 = calc_quarter_wave_length(freq_ghz, eps_eff_feed)
    delay_offset = lambda_g_4 / 2.0

    r_edge = calc_patch_edge_impedance(patch_w, patch_l, h, eps_r)
    z_p_trans = calc_quarter_wave_transformer_z(port_z0, r_edge)
    w_p_trans = synth_microstrip_w(z_p_trans, h, eps_r)
    eps_eff_p_trans = calc_microstrip_eps_eff(w_p_trans, h, eps_r)
    lambda_p_trans_4 = calc_quarter_wave_length(freq_ghz, eps_eff_p_trans)

    z_t_node = port_z0 / 2.0
    z_t_trans = calc_quarter_wave_transformer_z(port_z0, z_t_node)
    w_t_trans = synth_microstrip_w(z_t_trans, h, eps_r)
    eps_eff_t_trans = calc_microstrip_eps_eff(w_t_trans, h, eps_r)
    lambda_t_trans_4 = calc_quarter_wave_length(freq_ghz, eps_eff_t_trans)

    feed_offset_x = float(np.round(lambda_p_trans_4 + 6.0, 1))
    feed_offset_y = float(np.round(lambda_p_trans_4 + 6.0, 1))

    # Potřebný prostor v ose Y pod flíčkem: polovina flíčku + FEED_OFFSET_Y + delay_offset + lambda_t_trans_4 + vstupní rezerva
    y_needed = (patch_l / 2.0) + feed_offset_y + delay_offset + lambda_t_trans_4 + 10.0
    sub_l = float(np.round(2.0 * y_needed, 1))
    sub_w = float(np.round(patch_w + 2.0 * (feed_offset_x + 15.0), 1))

    return {
        'feed_w': float(np.round(feed_w, 2)),
        'lambda_g_4': lambda_g_4,
        'delay_offset': delay_offset,
        'w_t_trans': float(np.round(w_t_trans, 2)),
        'lambda_t_trans_4': lambda_t_trans_4,
        'w_p_trans': float(np.round(w_p_trans, 2)),
        'lambda_p_trans_4': lambda_p_trans_4,
        'feed_offset_x': feed_offset_x,
        'feed_offset_y': feed_offset_y,
        'sub_l': sub_l,
        'sub_w': sub_w,
    }
