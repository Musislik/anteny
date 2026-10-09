import gmsh
import numpy as np

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
        if abs(bbox[2]) < 1e-6 and abs(bbox[5] - h) < 1e-6:
            sub_vols.append(tag)
        else:
            air_vols.append(tag)
            
    gmsh.model.addPhysicalGroup(3, sub_vols, name="Substrate")
    gmsh.model.addPhysicalGroup(3, air_vols, name="Air")
    
    # 2. Klasifikace ploch (PEC, Port, Absorbing)
    pec_surfs = []
    port_surfs = []
    absorbing_surfs = []
    
    for dim, tag in surfs:
        bbox = gmsh.model.getBoundingBox(dim, tag)
        com = gmsh.model.occ.getCenterOfMass(dim, tag)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox
        
        # Zemnící plocha (z = 0)
        if abs(zmin) < 1e-6 and abs(zmax) < 1e-6:
            # Nechceme zahrnout hranici portu jako PEC, port je na kraji substrátu, ale má zmin=0 a zmax=h
            # Takže PEC GND je pouze to, co má zmax = 0. Ale moment, bounding box portu je zmin=0, zmax=h.
            pass # řešíme níže
            
        # Je to plocha ležící plně v z=0 (GND)
        if abs(zmax) < 1e-6:
            pec_surfs.append(tag)
            continue
            
        # Je to plocha ležící plně v z=h (Patch + Feed)
        if abs(zmin - h) < 1e-6 and abs(zmax - h) < 1e-6:
            cx, cy, cz = com
            in_patch = (abs(cx) <= params['patch_W']/2 + 1e-3 and abs(cy) <= params['patch_L']/2 + 1e-3)
            in_left = (cx <= -params['patch_W']/2 + 1e-3 and cx >= -params['sub_W']/2 - 1e-3 and abs(cy) <= params['feed_W']/2 + 1e-3)
            in_bot = (abs(cx) <= params['feed_W']/2 + 1e-3 and cy <= -params['patch_L']/2 + 1e-3 and cy >= -params['sub_L']/2 - 1e-3)
            if in_patch or in_left or in_bot:
                pec_surfs.append(tag)
            continue
            
        # Port (YZ rovina na kraji substrátu x = -W_sub/2)
        if abs(xmin - (-params['sub_W']/2)) < 1e-6 and abs(xmax - (-params['sub_W']/2)) < 1e-6 and abs(zmax - h) < 1e-6 and abs(zmin) < 1e-6:
            if ymin >= -params['feed_W']/2 - 1e-3 and ymax <= params['feed_W']/2 + 1e-3:
                port_surfs.append(tag)
            continue
            
        # Absorpční stěny (vnější hranice vzduchového boxu)
        if abs(zmax - (h + margin)) < 1e-6 or abs(zmin - (-margin)) < 1e-6 or \
           abs(xmax - (params['sub_W']/2 + margin)) < 1e-6 or abs(xmin - (-params['sub_W']/2 - margin)) < 1e-6 or \
           abs(ymax - (params['sub_L']/2 + margin)) < 1e-6 or abs(ymin - (-params['sub_L']/2 - margin)) < 1e-6:
            absorbing_surfs.append(tag)
            continue

    gmsh.model.addPhysicalGroup(2, pec_surfs, name="PEC")
    if port_surfs:
        gmsh.model.addPhysicalGroup(2, port_surfs, name="Port")
    gmsh.model.addPhysicalGroup(2, absorbing_surfs, name="Absorbing")
    
    # 3. Nastavení sítě a generování
    gmsh.option.setNumber("Mesh.MeshSizeMax", params['mesh_size_max'])
    gmsh.option.setNumber("Mesh.MeshSizeMin", params['mesh_size_min'])
    
    gmsh.model.mesh.generate(3)
    gmsh.write("mesh.msh")
    gmsh.finalize()
