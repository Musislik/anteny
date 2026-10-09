import gmsh
import numpy as np

def build_model(params):
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1)
    gmsh.model.add("lhcp_antenna")
    
    L = params['patch_L']
    W = params['patch_W']
    h = params['sub_h']
    L_sub = params['sub_L']
    W_sub = params['sub_W']
    margin = params['air_margin']
    feed_W = params['feed_W']
    
    # 1. Objemová tělesa
    # Substrát
    sub_tag = gmsh.model.occ.addBox(-W_sub/2, -L_sub/2, 0, W_sub, L_sub, h)
    
    # Vzduchový box
    air_tag = gmsh.model.occ.addBox(-W_sub/2 - margin, -L_sub/2 - margin, -margin, 
                                    W_sub + 2*margin, L_sub + 2*margin, h + 2*margin)
    
    # 2. Plošné entity (2D) pro flíček a napájení (z = h)
    # Patch
    patch_tag = gmsh.model.occ.addRectangle(-W/2, -L/2, h, W, L)
    
    # Napájecí dělič dle obrázku (cross-fed patch)
    # Výpočet efektivní permitivity a čtvrtvlnné délky z parametrů mikropásku při návrhové frekvenci fc
    from rf_calc import calc_microstrip_eps_eff, calc_quarter_wave_length, DESIGN_FREQ_GHZ
    eps_r = params['eps_r']
    f_design = params.get('design_freq_ghz', DESIGN_FREQ_GHZ)
    eps_eff_feed = calc_microstrip_eps_eff(feed_W, h, eps_r)
    lambda_g_4 = calc_quarter_wave_length(f_design, eps_eff_feed)
    
    # Port je dole na y = -L_sub/2, x = x_T
    # Port a poloha T-uzlu
    x_T = -25.4
    y_T = -L/2 - 15.0
    
    # Pro LHCP dle IEEE standardu musí spodní větev (Ey) mít fázové zpoždění -90 deg
    # oproti levé větvi (Ex). Čtvrtvlnné zpoždění lambda_g/4 náleží spodní větvi.
    delay_offset = lambda_g_4 / 4.0  # svislé snížení spodního vedení pro celkové prodloužení lambda_g_4
    y_delay = y_T - delay_offset

    # Hlavní přívod (od portu nahoru k T-uzlu)
    feed_main = gmsh.model.occ.addRectangle(x_T - feed_W/2, -L_sub/2, h, feed_W, L_sub/2 + y_T + feed_W/2)
    
    # Levá větev (k levé hraně x = -W/2, fáze 0 deg - referenční přímá větev)
    # Vertikální část nahoru k y=0
    f_l_v = gmsh.model.occ.addRectangle(x_T - feed_W/2, y_T - feed_W/2, h, feed_W, abs(y_T) + feed_W/2)
    # Horizontální část doprava k patchi - opraveno: prodlouženo o feed_W pro spolehlivý kontakt bez mezery
    f_l_h = gmsh.model.occ.addRectangle(x_T - feed_W/2, -feed_W/2, h, abs(x_T) - W/2 + feed_W, feed_W)
    
    # Spodní větev (k dolní hraně y = -L/2, fáze -90 deg - zpožděná o lambda_g/4)
    # Vertikální sestup z T-uzlu na zpožďovací úroveň y_delay
    f_r_v_down = gmsh.model.occ.addRectangle(x_T - feed_W/2, y_delay - feed_W/2, h, feed_W, delay_offset + feed_W)
    # Horizontální část doprava k x=0 na úrovni y_delay
    f_r_h = gmsh.model.occ.addRectangle(x_T - feed_W/2, y_delay - feed_W/2, h, abs(x_T) + feed_W, feed_W)
    # Vertikální část nahoru z y_delay k dolní hraně patche (y = -L/2) - opraveno: prodlouženo o feed_W bez mezery
    f_r_v_up = gmsh.model.occ.addRectangle(-feed_W/2, y_delay - feed_W/2, h, feed_W, abs(y_delay) - L/2 + feed_W)
    
    gmsh.model.occ.synchronize()
    
    # Vytvoření portové plochy (XZ rovina na kraji substrátu y = -L_sub/2)
    p1 = gmsh.model.occ.addPoint(x_T - feed_W/2, -L_sub/2, 0)
    p2 = gmsh.model.occ.addPoint(x_T + feed_W/2, -L_sub/2, 0)
    p3 = gmsh.model.occ.addPoint(x_T + feed_W/2, -L_sub/2, h)
    p4 = gmsh.model.occ.addPoint(x_T - feed_W/2, -L_sub/2, h)
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
    surfs = gmsh.model.occ.getEntities(2)
    
    gmsh.model.occ.fragment(vols, surfs)
    gmsh.model.occ.synchronize()
    
    return sub_tag, air_tag
