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
