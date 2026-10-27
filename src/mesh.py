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
    model_version = int(params.get('antenna_model', 1))
    
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
    port1_surfs = []
    port2_surfs = []
    absorbing_surfs = []
    
    # Pokud geometry.py předala přesné tagy z Boolean Fragment operace, použijeme je přednostně
    if params.get('pec_tags'):
        pec_surfs = list(params['pec_tags'])
    if params.get('port1_tags'):
        port1_surfs = list(params['port1_tags'])
    if params.get('port2_tags'):
        port2_surfs = list(params['port2_tags'])
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
                in_patch = (abs(com[0]) <= params['patch_W']/2 + GEOM_TOL and abs(com[1]) <= params['patch_L']/2 + GEOM_TOL)
                in_feed_zone = (com[0] <= max(0.0, port_x + feed_w) and com[1] <= params['patch_L']/2 + GEOM_TOL)
                if in_patch or in_feed_zone:
                    pec_surfs.append(tag)
                    
        if not params.get('port_tags') and not params.get('port1_tags'):
            # Port 1 (XZ rovina na spodním kraji substrátu y = -L_sub/2)
            if abs(ymin - (-params['sub_L']/2)) < GEOM_TOL and abs(ymax - (-params['sub_L']/2)) < GEOM_TOL and \
               abs(zmax - h) < GEOM_TOL and abs(zmin) < GEOM_TOL:
                if xmin >= port_x - feed_w/2 - EDGE_CLEARANCE_TOL and xmax <= port_x + feed_w/2 + EDGE_CLEARANCE_TOL:
                    port1_surfs.append(tag)
                    port_surfs.append(tag)

        if not params.get('port2_tags') and model_version == 2:
            # Port 2 (YZ rovina na levém kraji substrátu x = -W_sub/2)
            if abs(xmin - (-params['sub_W']/2)) < GEOM_TOL and abs(xmax - (-params['sub_W']/2)) < GEOM_TOL and \
               abs(zmax - h) < GEOM_TOL and abs(zmin) < GEOM_TOL:
                if ymin >= -feed_w/2 - EDGE_CLEARANCE_TOL and ymax <= feed_w/2 + EDGE_CLEARANCE_TOL:
                    port2_surfs.append(tag)

    # 2. Klasifikace ploch (3: PEC, 4: Port / Port1, 5: Absorbing, 6: Port2 pro Model 2)
    gmsh.model.addPhysicalGroup(2, list(set(pec_surfs)), tag=3, name="PEC")
    
    if model_version == 2 and port1_surfs and port2_surfs:
        gmsh.model.addPhysicalGroup(2, list(set(port1_surfs)), tag=4, name="Port1")
        gmsh.model.addPhysicalGroup(2, list(set(port2_surfs)), tag=6, name="Port2")
        all_port_surfs = list(set(port1_surfs + port2_surfs))
    else:
        if port_surfs:
            gmsh.model.addPhysicalGroup(2, list(set(port_surfs)), tag=4, name="Port")
        all_port_surfs = port_surfs

    gmsh.model.addPhysicalGroup(2, list(set(absorbing_surfs)), tag=5, name="Absorbing")
    
    # 3. Nastavení lokálního adaptivního zjemnění (Distance / Threshold pole)
    top_conductors = []
    for dim, tag in surfs:
        bbox = gmsh.model.getBoundingBox(dim, tag)
        if abs(bbox[2] - h) < 1e-4 and abs(bbox[5] - h) < 1e-4:
            if tag in pec_surfs:
                top_conductors.append(tag)

    active_surfs = list(set(top_conductors + all_port_surfs))
    if active_surfs:
        f_dist = gmsh.model.mesh.field.add("Distance")
        gmsh.model.mesh.field.setNumbers(f_dist, "SurfacesList", active_surfs)
        gmsh.model.mesh.field.setNumber(f_dist, "Sampling", 25)

        mesh_min = float(params['mesh_size_min'])
        mesh_max = float(params['mesh_size_max'])
        d_min = float(params.get('mesh_dist_min', 0.5))
        d_max = float(params.get('mesh_dist_max', 6.0))

        f_thresh = gmsh.model.mesh.field.add("Threshold")
        gmsh.model.mesh.field.setNumber(f_thresh, "InField", f_dist)
        gmsh.model.mesh.field.setNumber(f_thresh, "SizeMin", mesh_min)
        gmsh.model.mesh.field.setNumber(f_thresh, "SizeMax", mesh_max)
        gmsh.model.mesh.field.setNumber(f_thresh, "DistMin", d_min)
        gmsh.model.mesh.field.setNumber(f_thresh, "DistMax", d_max)

        gmsh.model.mesh.field.setAsBackgroundMesh(f_thresh)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)

    # 4. Globální meze a kompatibilní export pro MFEM / Palace (MSH 2.2)
    gmsh.option.setNumber("Mesh.MeshSizeMax", params['mesh_size_max'])
    gmsh.option.setNumber("Mesh.MeshSizeMin", params['mesh_size_min'])
    gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
    gmsh.option.setNumber("Mesh.Binary", 0)
    
    gmsh.model.mesh.generate(3)
    gmsh.write("data/mesh.msh")
    gmsh.finalize()
