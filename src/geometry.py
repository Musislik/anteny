import gmsh
import numpy as np

def build_model(params):
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1)
    gmsh.model.add("lhcp_antenna")
    
    L = params['patch_L']
    W = params['patch_W']
    h = params['sub_h']
    L_sub = params.get('sub_L', params.get('sub_l', 100.0))
    W_sub = params.get('sub_W', params.get('sub_w', 100.0))
    margin = params['air_margin']
    
    # 1. Objemová tělesa
    # Substrát
    sub_tag = gmsh.model.occ.addBox(-W_sub/2, -L_sub/2, 0, W_sub, L_sub, h)
    
    # Vzduchový box
    air_tag = gmsh.model.occ.addBox(-W_sub/2 - margin, -L_sub/2 - margin, -margin, 
                                    W_sub + 2*margin, L_sub + 2*margin, h + 2*margin)
    
    # 2. Plošné entity (2D) pro flíček a napájení (z = h)
    # Zanoření napaječe (inset feed)
    inset = float(params.get('inset', params.get('feed_inset', 0.0)))

    # Napájecí dělič dle specifikace v docs/abstrakce_zadani.md (Cross-fed patch dle napajeni.png)
    # Tři šířky spojů:
    # 1. w1: 50 Ohm hlavní přívod od portu k T-uzlu (přirozené přizpůsobení, bez transformátoru)
    # 2. w2: 100 Ohm větve fázovacího děliče (referenční spodní větev Ey, zpožďovací levá větev Ex s délkou + lambda_g/4)
    # 3. w3: vodič k samotné anténě (stupeň volnosti, w3 <= w2)

    w1 = params.get('w1')
    w2 = params.get('w2')
    w3 = params.get('w3')

    # Šířka mezery zářezu (gap g po obou stranách pásku w3, nebo odvozeno z celkové šířky výřezu)
    if params.get('inset_width') is not None or params.get('feed_inset_width') is not None:
        total_w = float(params.get('inset_width', params.get('feed_inset_width')))
        inset_gap = max((total_w - w3) / 2.0, 0.05)
    else:
        inset_gap = float(params.get('inset_gap', params.get('feed_inset_gap', w3)))

    params['inset_gap'] = inset_gap
    params['inset_width'] = float(np.round(w3 + 2.0 * inset_gap, 3))

    # Patch (s volitelným zanořením napájecího vedení / zářezy)
    if inset > 0:
        patch_base = gmsh.model.occ.addRectangle(-W/2, -L/2, h, W, L)
        # Zářez pro spodní větev (na x = 0, y od -L/2 do -L/2 + inset, šířka w3 + 2*inset_gap)
        notch_b = gmsh.model.occ.addRectangle(-(w3/2 + inset_gap), -L/2 - 0.05, h, w3 + 2*inset_gap, inset + 0.05)
        # Zářez pro levou větev (na y = 0, x od -W/2 do -W/2 + inset, výška w3 + 2*inset_gap)
        notch_l = gmsh.model.occ.addRectangle(-W/2 - 0.05, -(w3/2 + inset_gap), h, inset + 0.05, w3 + 2*inset_gap)
        cut_surfs, _ = gmsh.model.occ.cut([(2, patch_base)], [(2, notch_b), (2, notch_l)])
        patch_tag = cut_surfs[0][1]
    else:
        patch_tag = gmsh.model.occ.addRectangle(-W/2, -L/2, h, W, L)

    # Získání délek vedení l1 až l8 (musí být definovány v params)
    l1 = float(params['l1'])
    l2 = float(params['l2'])
    l3 = float(params['l3'])
    l4 = float(params['l4'])
    l5 = float(params['l5'])
    l6 = float(params['l6'])
    l7 = float(params['l7'])
    l8 = float(params['l8'])

    # Poloha T-uzlu (x_T, y_T) odvozená z délek l2, l3, l4
    # Spodní větev vede z T-uzlu doprava na osu flíčku x = 0 (l2 + l3 = |x_T|)
    x_T = float(params.get('feed_x_T'))
    # Vertikální úsek l4 vede od y_T k dolní hraně flíčku y = -L/2
    y_T = float(params.get('feed_y_T'))

    params['port_x'] = x_T
    params['feed_x_T'] = x_T
    params['feed_y_T'] = y_T
    params['w1'] = w1
    params['w2'] = w2
    params['w3'] = w3

    metal_surfs = [patch_tag]

    # 1. Hlavní přívod (50 Ohm, šířka w1): úsek l1 od vstupního portu k T-uzlu
    y_port = -L_sub / 2.0
    f_main = gmsh.model.occ.addRectangle(x_T - w1/2, y_port, h, w1, abs(y_T - y_port) + w2/2)
    metal_surfs.append(f_main)

    # 2. Spodní referenční větev (fáze 0°, pole Ey):
    # a) Segment l2 (šířka w2, délka l2): z T-uzlu doprava ke skoku w2 -> w3
    f_b_l2 = gmsh.model.occ.addRectangle(x_T - w2/2, y_T - w2/2, h, l2 + w2/2, w2)
    # b) Segment l3 (šířka w3, délka l3): od skoku k ohybu na ose x = 0
    f_b_l3 = gmsh.model.occ.addRectangle(x_T + l2, y_T - w3/2, h, l3 + w3/2, w3)
    # c) Segment l4 (šířka w3, délka l4): od ohybu nahoru k dolní hraně flíčku (y = -L/2)
    f_b_l4 = gmsh.model.occ.addRectangle(-w3/2, y_T - w3/2, h, w3, l4 + w3/2 + 0.1)
    metal_surfs.extend([f_b_l2, f_b_l3, f_b_l4])

    # 3. Levá zpožďovací větev (fáze -90°, pole Ex, zpoždění o lambda_g/4):
    # a) Segment l5 (šířka w2, délka l5): z T-uzlu doleva k rohovému ohybu (x = x_T - l5)
    f_l_l5 = gmsh.model.occ.addRectangle(x_T - l5 - w2/2, y_T - w2/2, h, l5 + w2/2, w2)
    # b) Segment l6 (šířka w2, délka l6): od ohybu nahoru ke skoku na w3 (y = y_T + l6)
    f_l_l6 = gmsh.model.occ.addRectangle(x_T - l5 - w2/2, y_T - w2/2, h, w2, l6 + w2/2)
    # c) Segment l7 (šířka w3, délka l7): od skoku nahoru k hornímu ohybu (y = 0)
    f_l_l7 = gmsh.model.occ.addRectangle(x_T - l5 - w3/2, y_T + l6, h, w3, l7 + w3/2)
    # d) Segment l8 (šířka w3, délka l8): od horního ohybu doprava k levé hraně flíčku (x = -W/2)
    f_l_l8 = gmsh.model.occ.addRectangle(x_T - l5 - w3/2, -w3/2, h, l8 + w3/2 + 0.1, w3)
    metal_surfs.extend([f_l_l5, f_l_l6, f_l_l7, f_l_l8])

    gmsh.model.occ.synchronize()

    # Vytvoření portové plochy (XZ rovina na kraji substrátu y = -L_sub/2)
    w_port_entry = w1
    params['port_w'] = w_port_entry
    p1 = gmsh.model.occ.addPoint(x_T - w_port_entry/2, y_port, 0)
    p2 = gmsh.model.occ.addPoint(x_T + w_port_entry/2, y_port, 0)
    p3 = gmsh.model.occ.addPoint(x_T + w_port_entry/2, y_port, h)
    p4 = gmsh.model.occ.addPoint(x_T - w_port_entry/2, y_port, h)
    l1 = gmsh.model.occ.addLine(p1, p2)
    l2 = gmsh.model.occ.addLine(p2, p3)
    l3 = gmsh.model.occ.addLine(p3, p4)
    l4 = gmsh.model.occ.addLine(p4, p1)
    cl = gmsh.model.occ.addCurveLoop([l1, l2, l3, l4])
    port_tag = gmsh.model.occ.addPlaneSurface([cl])
    
    # 3. Zemní plocha (GND) na spodku substrátu (z = 0)
    gnd_tag = gmsh.model.occ.addRectangle(-W_sub/2, -L_sub/2, 0, W_sub, L_sub)
    
    gmsh.model.occ.synchronize()
    
    # 4. Topologická fúze (Boolean Fragments)
    # Sloučíme všechny objemy a plochy dohromady, aby na sebe navazovaly v síti
    vols = gmsh.model.occ.getEntities(3)
    input_surfs = [(2, s) for s in metal_surfs] + [(2, gnd_tag), (2, port_tag)]
    
    _, out_map = gmsh.model.occ.fragment(vols, input_surfs)
    gmsh.model.occ.synchronize()
    
    # Přesná evidence fragmentů pro fyzikální skupiny
    pec_tags = []
    for idx, (dim, s_tag) in enumerate(input_surfs):
        frag_entities = out_map[len(vols) + idx]
        frag_tags = [tag for d, tag in frag_entities if d == 2]
        if s_tag == port_tag:
            params['port_tags'] = frag_tags
        else:
            pec_tags.extend(frag_tags)
            
    params['pec_tags'] = list(set(pec_tags))
    
    return sub_tag, air_tag
