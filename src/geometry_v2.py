import gmsh
import numpy as np

from rf_calc import (
    synth_microstrip_w,
    calc_microstrip_eps_eff,
    calc_quarter_wave_length,
    DESIGN_FREQ_GHZ,
)

def build_model_v2(params):
    """
    Model 2: Dvouportový model mikropáskové flíčkové antény LHCP.
    - Dva přímé mikropásky o impedanci 100 Ohm (šířka w ≈ 0.69 mm).
    - Spodní napáječ (Port 1, pole Ey) fyzicky prodloužený o lambda_g/4 pro správné zpoždění -90° (čistá LHCP).
    - Levý napáječ (Port 2, pole Ex) s referenční délkou L_ref.
    - Dva nezávislé zářezy: inset_b (spodní) a inset_l (levý).
    - Dva nezávislé lumped porty (Port 1 na spodní hraně, Port 2 na levé hraně).
    """
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1)
    gmsh.model.add("lhcp_antenna_model2")

    L = float(params['patch_L'])
    W = float(params['patch_W'])
    h = float(params['sub_h'])
    eps_r = float(params['eps_r'])
    margin = float(params['air_margin'])
    f_design = float(params.get('design_freq_ghz', DESIGN_FREQ_GHZ))

    # 1. Šířka mikropásku 100 Ohm a čtvrtvlnná délka lambda_g/4
    # Obě ramena mají impedanci 100 Ohm (Z0_feed = 100.0)
    w_feed = synth_microstrip_w(100.0, h, eps_r)
    eps_eff = calc_microstrip_eps_eff(w_feed, h, eps_r)
    lambda_g_4 = calc_quarter_wave_length(f_design, eps_eff)

    # 2. Nezávislá zanoření (insets) a šířky mezer (gaps)
    inset_b = float(params.get('feed_inset_b', params.get('inset_b', params.get('feed_inset', params.get('inset', 0.0)))))
    inset_l = float(params.get('feed_inset_l', params.get('inset_l', params.get('feed_inset', params.get('inset', 0.0)))))

    if inset_b < 0.0 or inset_l < 0.0:
        raise ValueError(f"Hloubka zanoření (inset) musí být nezáporná: inset_b={inset_b}, inset_l={inset_l}")

    inset_gap_b = float(params.get('inset_gap_b', params.get('feed_inset_gap_b', params.get('inset_gap', params.get('feed_inset_gap', w_feed)))))
    inset_gap_l = float(params.get('inset_gap_l', params.get('feed_inset_gap_l', params.get('inset_gap', params.get('feed_inset_gap', w_feed)))))

    # 3. Dimenzování napaječů a substrátu
    # Minimální doporučený odstup substrátu od flíčku (10*h od hrany flíčku, min. 15 mm)
    min_w_sub = W + 2.0 * max(15.0, 10.0 * h)

    # Načtení případných explicitních délek napaječů
    raw_len_l = params.get('feed_len_l', params.get('feed_length_l', params.get('L_feed_l', params.get('l_feed_l'))))
    raw_len_b = params.get('feed_len_b', params.get('feed_length_b', params.get('L_feed_b', params.get('l_feed_b'))))
    raw_delta_l = params.get('feed_delta_l', params.get('delta_l', params.get('phase_delay_mm', params.get('feed_delta'))))

    # Základní šířka substrátu pro výpočet výchozího L_ref
    W_sub_base = float(params.get('sub_W', params.get('sub_w', 80.0)))
    if W_sub_base < min_w_sub:
        W_sub_base = float(np.round(min_w_sub, 1))

    # Výchozí referenční délka levého přívodu (od x = -W_sub_base/2 k zářezu na x = -W/2 + inset_l)
    L_ref_default = (W_sub_base / 2.0) - (W / 2.0) + inset_l

    if raw_len_l is not None:
        feed_len_l = float(raw_len_l)
        L_ref = feed_len_l
    else:
        feed_len_l = L_ref_default
        L_ref = L_ref_default

    if raw_delta_l is not None:
        feed_delta_l = float(raw_delta_l)
    else:
        feed_delta_l = lambda_g_4

    if raw_len_b is not None:
        feed_len_b = float(raw_len_b)
        if raw_len_l is not None or raw_delta_l is None:
            feed_delta_l = feed_len_b - feed_len_l
    else:
        feed_len_b = feed_len_l + feed_delta_l

    L_feed_bottom = feed_len_b

    if feed_len_b <= 0.0 or feed_len_l <= 0.0:
        raise ValueError(f"Délky napaječů musí být kladné (> 0 mm): feed_len_b={feed_len_b}, feed_len_l={feed_len_l}")

    if feed_len_l <= inset_l:
        raise ValueError(
            f"Délka levého napaječe feed_len_l={feed_len_l:.2f} mm musí být větší než zanoření inset_l={inset_l:.2f} mm "
            f"(převis napaječe mimo flíček musí být kladný, jinak port leží uvnitř flíčku)."
        )
    if feed_len_b <= inset_b:
        raise ValueError(
            f"Délka spodního napaječe feed_len_b={feed_len_b:.2f} mm musí být větší než zanoření inset_b={inset_b:.2f} mm "
            f"(převis napaječe mimo flíček musí být kladný, jinak port leží uvnitř flíčku)."
        )

    # Umístění portů:
    # Levý port (Port 2): x_port = -W/2 + inset_l - feed_len_l
    # Spodní port (Port 1): y_port = -L/2 + inset_b - feed_len_b
    x_port = -W / 2.0 + inset_l - feed_len_l
    y_port = -L / 2.0 + inset_b - feed_len_b

    # Dynamické přizpůsobení rozměrů substrátu tak, aby oba porty ležely na hraně substrátu
    # a byl zachován symetrický odstup substrátu od flíčku:
    # Levá hrana je na -W_sub/2 = x_port => W_sub = 2 * abs(x_port)
    # Spodní hrana je na -L_sub/2 = y_port => L_sub = 2 * abs(y_port)
    W_sub = 2.0 * abs(x_port)
    L_sub = 2.0 * abs(y_port)

    # Uložení odvozených rozměrů do params
    params['w1'] = float(np.round(w_feed, 3))
    params['w2'] = float(np.round(w_feed, 3))
    params['w3'] = float(np.round(w_feed, 3))
    params['w_feed'] = float(np.round(w_feed, 3))
    params['feed_W'] = float(np.round(w_feed, 3))
    params['port_w'] = float(np.round(w_feed, 3))
    params['sub_W'] = float(np.round(W_sub, 2))
    params['sub_w'] = params['sub_W']
    params['sub_L'] = float(np.round(L_sub, 2))
    params['sub_l'] = params['sub_L']
    params['inset_b'] = float(np.round(inset_b, 3))
    params['inset_l'] = float(np.round(inset_l, 3))
    params['feed_inset_b'] = params['inset_b']
    params['feed_inset_l'] = params['inset_l']
    params['inset_gap_b'] = float(np.round(inset_gap_b, 3))
    params['inset_gap_l'] = float(np.round(inset_gap_l, 3))
    params['feed_len_b'] = float(np.round(feed_len_b, 3))
    params['feed_len_l'] = float(np.round(feed_len_l, 3))
    params['feed_length_b'] = params['feed_len_b']
    params['feed_length_l'] = params['feed_len_l']
    params['L_feed_b'] = params['feed_len_b']
    params['L_feed_l'] = params['feed_len_l']
    params['feed_delta_l'] = float(np.round(feed_delta_l, 3))
    params['delta_l'] = params['feed_delta_l']
    params['phase_delay_mm'] = params['feed_delta_l']
    params['L_ref'] = float(np.round(L_ref, 3))
    params['L_feed_bottom'] = float(np.round(L_feed_bottom, 3))
    params['lambda_g_4'] = float(np.round(lambda_g_4, 3))
    params['lambda_g'] = float(np.round(4.0 * lambda_g_4, 3))
    params['x_port'] = float(np.round(x_port, 3))
    params['y_port'] = float(np.round(y_port, 3))
    params['antenna_model'] = 2

    # 4. Objemová tělesa
    # Substrát (z = 0 až h)
    sub_tag = gmsh.model.occ.addBox(-W_sub/2, -L_sub/2, 0, W_sub, L_sub, h)

    # Vzduchový box s absorpčními stěnami
    air_tag = gmsh.model.occ.addBox(-W_sub/2 - margin, -L_sub/2 - margin, -margin,
                                    W_sub + 2*margin, L_sub + 2*margin, h + 2*margin)

    # 5. Plošné entity: Patch se dvěma nezávislými zářezy (z = h)
    patch_base = gmsh.model.occ.addRectangle(-W/2, -L/2, h, W, L)

    tool_notches = []
    # Spodní zářez notch_b (na x = 0, y od -L/2 do -L/2 + inset_b)
    if inset_b > 0.0:
        notch_b_w = w_feed + 2.0 * inset_gap_b
        notch_b = gmsh.model.occ.addRectangle(-notch_b_w/2, -L/2 - 0.05, h, notch_b_w, inset_b + 0.05)
        tool_notches.append((2, notch_b))

    # Levý zářez notch_l (na y = 0, x od -W/2 do -W/2 + inset_l)
    if inset_l > 0.0:
        notch_l_h = w_feed + 2.0 * inset_gap_l
        notch_l = gmsh.model.occ.addRectangle(-W/2 - 0.05, -notch_l_h/2, h, inset_l + 0.05, notch_l_h)
        tool_notches.append((2, notch_l))

    if tool_notches:
        cut_surfs, _ = gmsh.model.occ.cut([(2, patch_base)], tool_notches)
        patch_tag = cut_surfs[0][1]
    else:
        patch_tag = patch_base

    # 6. Dva přímé mikropásky
    # Spodní přívod (Port 1): od y = y_port do -L/2 + inset_b podél x = 0
    dy_bottom = (-L / 2.0 + inset_b) - y_port
    feed_b = gmsh.model.occ.addRectangle(-w_feed/2, y_port, h, w_feed, dy_bottom)

    # Levý přívod (Port 2): od x = x_port do -W/2 + inset_l podél y = 0
    dx_left = (-W / 2.0 + inset_l) - x_port
    feed_l = gmsh.model.occ.addRectangle(x_port, -w_feed/2, h, dx_left, w_feed)

    metal_surfs = [patch_tag, feed_b, feed_l]

    gmsh.model.occ.synchronize()

    # 7. Dvě portové plochy (LumpedPort, excitace od z = 0 do z = h ve směru +Z)
    # Port 1 (spodní): XZ plocha na y = y_port, x od -w_feed/2 do +w_feed/2
    p1_1 = gmsh.model.occ.addPoint(-w_feed/2, y_port, 0)
    p1_2 = gmsh.model.occ.addPoint(+w_feed/2, y_port, 0)
    p1_3 = gmsh.model.occ.addPoint(+w_feed/2, y_port, h)
    p1_4 = gmsh.model.occ.addPoint(-w_feed/2, y_port, h)
    l1_1 = gmsh.model.occ.addLine(p1_1, p1_2)
    l1_2 = gmsh.model.occ.addLine(p1_2, p1_3)
    l1_3 = gmsh.model.occ.addLine(p1_3, p1_4)
    l1_4 = gmsh.model.occ.addLine(p1_4, p1_1)
    cl1 = gmsh.model.occ.addCurveLoop([l1_1, l1_2, l1_3, l1_4])
    port1_tag = gmsh.model.occ.addPlaneSurface([cl1])

    # Port 2 (levý): YZ plocha na x = x_port, y od -w_feed/2 do +w_feed/2
    p2_1 = gmsh.model.occ.addPoint(x_port, -w_feed/2, 0)
    p2_2 = gmsh.model.occ.addPoint(x_port, +w_feed/2, 0)
    p2_3 = gmsh.model.occ.addPoint(x_port, +w_feed/2, h)
    p2_4 = gmsh.model.occ.addPoint(x_port, -w_feed/2, h)
    l2_1 = gmsh.model.occ.addLine(p2_1, p2_2)
    l2_2 = gmsh.model.occ.addLine(p2_2, p2_3)
    l2_3 = gmsh.model.occ.addLine(p2_3, p2_4)
    l2_4 = gmsh.model.occ.addLine(p2_4, p2_1)
    cl2 = gmsh.model.occ.addCurveLoop([l2_1, l2_2, l2_3, l2_4])
    port2_tag = gmsh.model.occ.addPlaneSurface([cl2])

    # 8. Zemní plocha GND (z = 0)
    gnd_tag = gmsh.model.occ.addRectangle(-W_sub/2, -L_sub/2, 0, W_sub, L_sub)

    gmsh.model.occ.synchronize()

    # 9. Topologická fúze (Boolean Fragments)
    vols = gmsh.model.occ.getEntities(3)
    input_surfs = [(2, s) for s in metal_surfs] + [(2, gnd_tag), (2, port1_tag), (2, port2_tag)]

    _, out_map = gmsh.model.occ.fragment(vols, input_surfs)
    gmsh.model.occ.synchronize()

    # 10. Evidence fragmentů pro fyzikální skupiny
    pec_tags = []
    port1_tags = []
    port2_tags = []

    for idx, (dim, s_tag) in enumerate(input_surfs):
        frag_entities = out_map[len(vols) + idx]
        frag_tags = [tag for d, tag in frag_entities if d == 2]
        if s_tag == port1_tag:
            port1_tags.extend(frag_tags)
        elif s_tag == port2_tag:
            port2_tags.extend(frag_tags)
        else:
            pec_tags.extend(frag_tags)

    params['port1_tags'] = list(set(port1_tags))
    params['port2_tags'] = list(set(port2_tags))
    params['port_tags'] = list(set(port1_tags + port2_tags))
    params['pec_tags'] = list(set(pec_tags))

    return sub_tag, air_tag

build_model = build_model_v2
