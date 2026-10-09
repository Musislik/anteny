import gmsh
import numpy as np

# Konstanty geometrické přesnosti a tolerancí
GEOM_TOL = 1e-6
EDGE_CLEARANCE_TOL = 1e-3

def assign_physical_groups_and_mesh(params):
    vols = gmsh.model.getEntities(3)
    surfs = gmsh.model.getEntities(2)
    
    h = params['sub_h']
    margin = params['air_margin']
    
    sub_vols = []
    air_vols = []
    
    # 1. Klasifikace objemů podle těžiště a bounding boxu
    for dim, tag in vols:
        bbox = gmsh.model.getBoundingBox(dim, tag)
        if abs(bbox[2]) < GEOM_TOL and abs(bbox[5] - h) < GEOM_TOL:
            sub_vols.append(tag)
        else:
            air_vols.append(tag)
            
    gmsh.model.addPhysicalGroup(3, sub_vols, tag=1, name="Substrate")
    gmsh.model.addPhysicalGroup(3, air_vols, tag=2, name="Air")
    
    # 2. Klasifikace ploch (PEC, Port, Absorbing)
    pec_surfs = []
    port_surfs = []
    absorbing_surfs = []
    
    # Pokud geometry.py předala přesné tagy z Boolean Fragment operace, použijeme je přednostně
    if params.get('pec_tags'):
        pec_surfs = list(params['pec_tags'])
    if params.get('port_tags'):
        port_surfs = list(params['port_tags'])
        
    port_x = params.get('port_x', params.get('feed_x_T', -params['patch_W']/2 - 10.0))
    feed_w = params.get('port_w', params.get('feed_W', 3.0))

    for dim, tag in surfs:
        bbox = gmsh.model.getBoundingBox(dim, tag)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox
        
        # Absorpční stěny (vnější hranice vzduchového boxu)
        if abs(zmax - (h + margin)) < GEOM_TOL or abs(zmin - (-margin)) < GEOM_TOL or \
           abs(xmax - (params['sub_W']/2 + margin)) < GEOM_TOL or abs(xmin - (-params['sub_W']/2 - margin)) < GEOM_TOL or \
           abs(ymax - (params['sub_L']/2 + margin)) < GEOM_TOL or abs(ymin - (-params['sub_L']/2 - margin)) < GEOM_TOL:
            absorbing_surfs.append(tag)
            continue
            
        # Fallback detekce PEC a Portu, pokud by nebyly předány z geometry.py
        if not params.get('pec_tags'):
            # GND na z = 0
            if abs(zmax) < GEOM_TOL and abs(zmin) < GEOM_TOL:
                pec_surfs.append(tag)
            # Patch a přívody na z = h (testujeme, zda plocha neleží vně kovových obrysů)
            elif abs(zmin - h) < GEOM_TOL and abs(zmax - h) < GEOM_TOL:
                com = gmsh.model.occ.getCenterOfMass(dim, tag)
                # Uvnitř patche nebo v zóně přívodu
                in_patch = (abs(com[0]) <= params['patch_W']/2 + GEOM_TOL and abs(com[1]) <= params['patch_L']/2 + GEOM_TOL)
                in_feed_zone = (com[0] <= max(0.0, port_x + feed_w) and com[1] <= params['patch_L']/2 + GEOM_TOL)
                if in_patch or in_feed_zone:
                    pec_surfs.append(tag)
                    
        if not params.get('port_tags'):
            # Port (XZ rovina na spodním kraji substrátu y = -L_sub/2)
            if abs(ymin - (-params['sub_L']/2)) < GEOM_TOL and abs(ymax - (-params['sub_L']/2)) < GEOM_TOL and \
               abs(zmax - h) < GEOM_TOL and abs(zmin) < GEOM_TOL:
                if xmin >= port_x - feed_w/2 - EDGE_CLEARANCE_TOL and xmax <= port_x + feed_w/2 + EDGE_CLEARANCE_TOL:
                    port_surfs.append(tag)

    # 2. Klasifikace ploch (3: PEC, 4: Port, 5: Absorbing)
    gmsh.model.addPhysicalGroup(2, list(set(pec_surfs)), tag=3, name="PEC")
    if port_surfs:
        gmsh.model.addPhysicalGroup(2, list(set(port_surfs)), tag=4, name="Port")
    gmsh.model.addPhysicalGroup(2, list(set(absorbing_surfs)), tag=5, name="Absorbing")
    
    # 3. Nastavení sítě a kompatibilní export pro MFEM / Palace (MSH 2.2)
    gmsh.option.setNumber("Mesh.MeshSizeMax", params['mesh_size_max'])
    gmsh.option.setNumber("Mesh.MeshSizeMin", params['mesh_size_min'])
    gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
    gmsh.option.setNumber("Mesh.Binary", 0)
    
    gmsh.model.mesh.generate(3)
    gmsh.write("mesh.msh")
    gmsh.finalize()
