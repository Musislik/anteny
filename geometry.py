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
    x_T = -25.4
    y_T = -L/2 - 15.0
    x_L = x_T - (lambda_g_4 / 2.0)  # Tím docílíme celkového rozdílu dráhy lambda_g / 4 pro LHCP
    
    # Hlavní přívod (od portu nahoru k T-uzlu)
    feed_main = gmsh.model.occ.addRectangle(x_T - feed_W/2, -L_sub/2, h, feed_W, L_sub/2 + y_T + feed_W/2)
    
    # Pravá větev (k bottom edge, fáze 0 deg)
    # Horizontální část z T-uzlu doprava k x=0
    f_r_h = gmsh.model.occ.addRectangle(x_T - feed_W/2, y_T - feed_W/2, h, abs(x_T) + feed_W, feed_W)
    # Vertikální část nahoru k patchi
    f_r_v = gmsh.model.occ.addRectangle(-feed_W/2, y_T - feed_W/2, h, feed_W, abs(y_T) - L/2)
    
    # Levá větev (k levé edge, fáze -90 deg)
    # Horizontální část zlevnění (do x_L)
    f_l_h1 = gmsh.model.occ.addRectangle(x_L - feed_W/2, y_T - feed_W/2, h, (x_T - x_L) + feed_W, feed_W)
    # Vertikální část nahoru (až k y=0)
    f_l_v = gmsh.model.occ.addRectangle(x_L - feed_W/2, y_T - feed_W/2, h, feed_W, abs(y_T) + feed_W/2)
    # Horizontální část doprava k patchi
    f_l_h2 = gmsh.model.occ.addRectangle(x_L - feed_W/2, -feed_W/2, h, abs(x_L) - W/2, feed_W)
    
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
