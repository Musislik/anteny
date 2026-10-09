import gmsh

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
    
    # Napájecí dělič - T-uzel a fázovací vedení pro LHCP
    # Port je na x = -W_sub/2, y = 0
    feed_main = gmsh.model.occ.addRectangle(-W_sub/2, -feed_W/2, h, W_sub/2 - W/2 - 15, feed_W)
    
    split_x = -W/2 - 15
    # Levá větev (delší o cca lambda_g/4 pro LHCP fázování -90 deg)
    # Meandr: Nahoru, doprava, dolů, k patchi
    f_l1 = gmsh.model.occ.addRectangle(split_x, feed_W/2, h, feed_W, 20)
    f_l2 = gmsh.model.occ.addRectangle(split_x, 20 + feed_W/2, h, 15, feed_W)
    f_l3 = gmsh.model.occ.addRectangle(split_x + 15 - feed_W, -feed_W/2, h, feed_W, 20 + feed_W)
    f_l4 = gmsh.model.occ.addRectangle(split_x + 15 - feed_W, -feed_W/2, h, feed_W + 5, feed_W) # připojení k -W/2
    
    # Spodní větev (kratší, fáze 0 deg)
    # Dolů, doprava, nahoru k patchi
    f_b1 = gmsh.model.occ.addRectangle(split_x, -L/2 - 10, h, feed_W, L/2 + 10 - feed_W/2)
    f_b2 = gmsh.model.occ.addRectangle(split_x, -L/2 - 10, h, W/2 + 15 + feed_W/2, feed_W)
    f_b3 = gmsh.model.occ.addRectangle(-feed_W/2, -L/2 - 10, h, feed_W, 10)
    
    # Abychom simulovali celé prostředí, vytvoříme na kraji feed_main lumped port.
    # Port plocha mezi zemí (z=0) a napáječem (z=h) na okraji x = -W_sub/2
    
    gmsh.model.occ.synchronize()
    
    # Vytvoření portové plochy přes addSurfaceFilling nebo přidáním bodů/čar.
    p1 = gmsh.model.occ.addPoint(-W_sub/2, -feed_W/2, 0)
    p2 = gmsh.model.occ.addPoint(-W_sub/2, feed_W/2, 0)
    p3 = gmsh.model.occ.addPoint(-W_sub/2, feed_W/2, h)
    p4 = gmsh.model.occ.addPoint(-W_sub/2, -feed_W/2, h)
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
