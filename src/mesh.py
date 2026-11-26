import os
import gmsh

# Geometric precision and tolerance constants
GEOM_TOL = 1e-6
EDGE_CLEARANCE_TOL = 1e-3

def assign_physical_groups_and_mesh(params, data_dir=None):
    vols = gmsh.model.getEntities(3)
    surfs = gmsh.model.getEntities(2)
    
    h = params['sub_h']
    margin = params['air_margin']
    model_version = int(params.get('antenna_model', 1))
    
    sub_vols = []
    air_vols = []
    
    # 1. Volume classification by center of mass and bounding box
    for dim, tag in vols:
        bbox = gmsh.model.getBoundingBox(dim, tag)
        if abs(bbox[2]) < GEOM_TOL and abs(bbox[5] - h) < GEOM_TOL:
            sub_vols.append(tag)
        else:
            air_vols.append(tag)
            
    gmsh.model.addPhysicalGroup(3, sub_vols, tag=1, name="Substrate")
    gmsh.model.addPhysicalGroup(3, air_vols, tag=2, name="Air")
    
    # 2. Surface classification (PEC, Port, Absorbing)
    pec_surfs = []
    port_surfs = []
    port1_surfs = []
    port2_surfs = []
    absorbing_surfs = []
    
    # If geometry.py passed exact tags from Boolean Fragment, use them with priority
    if params.get('pec_tags'):
        pec_surfs = list(params['pec_tags'])
    if params.get('port1_tags'):
        port1_surfs = list(params['port1_tags'])
    if params.get('port2_tags'):
        port2_surfs = list(params['port2_tags'])
    if params.get('port_tags'):
        port_surfs = list(params['port_tags'])
        
    port_x = params.get('port_x', params.get('feed_x_T', -params['patch_W']/2 - 10.0))
    port_y = params.get('port_y', params.get('y_port', params.get('feed_y_T', 0.0)))
    feed_w = params.get('port_w', params.get('feed_W', 3.0))

    for dim, tag in surfs:
        bbox = gmsh.model.getBoundingBox(dim, tag)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox
        
        # Absorbing boundaries (outer boundary of the air box)
        if abs(zmax - (h + margin)) < GEOM_TOL or abs(zmin - (-margin)) < GEOM_TOL or \
           abs(xmax - (params['sub_W']/2 + margin)) < GEOM_TOL or abs(xmin - (-params['sub_W']/2 - margin)) < GEOM_TOL or \
           abs(ymax - (params['sub_L']/2 + margin)) < GEOM_TOL or abs(ymin - (-params['sub_L']/2 - margin)) < GEOM_TOL:
            absorbing_surfs.append(tag)
            continue
            
        # Fallback PEC and Port detection if not provided by geometry.py
        if not params.get('pec_tags'):
            # GND at z = 0
            if abs(zmax) < GEOM_TOL and abs(zmin) < GEOM_TOL:
                pec_surfs.append(tag)
            # Patch and feed lines at z = h (test whether surface lies within metallic outlines)
            elif abs(zmin - h) < GEOM_TOL and abs(zmax - h) < GEOM_TOL:
                com = gmsh.model.occ.getCenterOfMass(dim, tag)
                in_patch = (abs(com[0]) <= params['patch_W']/2 + GEOM_TOL and abs(com[1]) <= params['patch_L']/2 + GEOM_TOL)
                in_feed_zone = (com[0] <= max(0.0, port_x + feed_w) + GEOM_TOL and com[1] <= params['patch_L']/2 + GEOM_TOL)
                if in_patch or in_feed_zone:
                    pec_surfs.append(tag)
                    
        if not params.get('port_tags') and not params.get('port1_tags'):
            if model_version == 6:
                # Model 6: Port 1 (internal vertical surface in XZ plane at y = y_T - d_t)
                x_T_val = params.get('feed_x_T', params.get('x_T'))
                y_p1 = params.get('port1_y', params.get('y_port_1'))
                if y_p1 is None and params.get('feed_y_T') is not None and params.get('d_t') is not None:
                    y_p1 = params['feed_y_T'] - params['d_t']
                if y_p1 is not None and x_T_val is not None:
                    if abs(ymin - y_p1) < GEOM_TOL and abs(ymax - y_p1) < GEOM_TOL and \
                       abs(zmax - h) < GEOM_TOL and abs(zmin) < GEOM_TOL:
                        if xmin >= x_T_val - feed_w/2 - EDGE_CLEARANCE_TOL and xmax <= x_T_val + feed_w/2 + EDGE_CLEARANCE_TOL:
                            port1_surfs.append(tag)
                            port_surfs.append(tag)
            elif model_version == 7:
                # Model 7: single 50 Ohm port (YZ plane on right substrate edge x = +W_sub/2 around port_y)
                if abs(xmin - (params['sub_W']/2)) < GEOM_TOL and abs(xmax - (params['sub_W']/2)) < GEOM_TOL and \
                   abs(zmax - h) < GEOM_TOL and abs(zmin) < GEOM_TOL:
                    if ymin >= port_y - feed_w/2 - EDGE_CLEARANCE_TOL and ymax <= port_y + feed_w/2 + EDGE_CLEARANCE_TOL:
                        port_surfs.append(tag)
            elif model_version == 4:
                # Model 4: single 50 Ohm port (YZ plane on left substrate edge x = -W_sub/2 around port_y)
                if abs(xmin - (-params['sub_W']/2)) < GEOM_TOL and abs(xmax - (-params['sub_W']/2)) < GEOM_TOL and \
                   abs(zmax - h) < GEOM_TOL and abs(zmin) < GEOM_TOL:
                    if ymin >= port_y - feed_w/2 - EDGE_CLEARANCE_TOL and ymax <= port_y + feed_w/2 + EDGE_CLEARANCE_TOL:
                        port_surfs.append(tag)
            elif model_version == 5:
                # Model 5: Port 1 (YZ plane on left substrate edge x = -W_sub/2 around y_port_1)
                port_y_1 = params.get('y_port_1', port_y)
                if abs(xmin - (-params['sub_W']/2)) < GEOM_TOL and abs(xmax - (-params['sub_W']/2)) < GEOM_TOL and \
                   abs(zmax - h) < GEOM_TOL and abs(zmin) < GEOM_TOL:
                    if ymin >= port_y_1 - feed_w/2 - EDGE_CLEARANCE_TOL and ymax <= port_y_1 + feed_w/2 + EDGE_CLEARANCE_TOL:
                        port1_surfs.append(tag)
                        port_surfs.append(tag)
            else:
                # Port 1 (XZ plane on bottom substrate edge y = -L_sub/2)
                if abs(ymin - (-params['sub_L']/2)) < GEOM_TOL and abs(ymax - (-params['sub_L']/2)) < GEOM_TOL and \
                   abs(zmax - h) < GEOM_TOL and abs(zmin) < GEOM_TOL:
                    if xmin >= port_x - feed_w/2 - EDGE_CLEARANCE_TOL and xmax <= port_x + feed_w/2 + EDGE_CLEARANCE_TOL:
                        port1_surfs.append(tag)
                        port_surfs.append(tag)

        if not params.get('port2_tags') and model_version in (2, 3, 5, 6):
            if model_version == 6:
                # Model 6: Port 2 (internal vertical surface in XZ plane at y = y_T + d_t)
                x_T_val = params.get('feed_x_T', params.get('x_T'))
                y_p2 = params.get('port2_y', params.get('y_port_2'))
                if y_p2 is None and params.get('feed_y_T') is not None and params.get('d_t') is not None:
                    y_p2 = params['feed_y_T'] + params['d_t']
                if y_p2 is not None and x_T_val is not None:
                    if abs(ymin - y_p2) < GEOM_TOL and abs(ymax - y_p2) < GEOM_TOL and \
                       abs(zmax - h) < GEOM_TOL and abs(zmin) < GEOM_TOL:
                        if xmin >= x_T_val - feed_w/2 - EDGE_CLEARANCE_TOL and xmax <= x_T_val + feed_w/2 + EDGE_CLEARANCE_TOL:
                            port2_surfs.append(tag)
            else:
                # Port 2 (YZ plane on left substrate edge x = -W_sub/2)
                port_y_2 = params.get('y_port_2', 0.0)
                if abs(xmin - (-params['sub_W']/2)) < GEOM_TOL and abs(xmax - (-params['sub_W']/2)) < GEOM_TOL and \
                   abs(zmax - h) < GEOM_TOL and abs(zmin) < GEOM_TOL:
                    if ymin >= port_y_2 - feed_w/2 - EDGE_CLEARANCE_TOL and ymax <= port_y_2 + feed_w/2 + EDGE_CLEARANCE_TOL:
                        port2_surfs.append(tag)

    # 2. Surface classification (3: PEC, 4: Port / Port1, 5: Absorbing, 6: Port2 for Model 2, 3, 5, and 6)
    gmsh.model.addPhysicalGroup(2, list(set(pec_surfs)), tag=3, name="PEC")

    if model_version in (2, 3, 5, 6) and port1_surfs and port2_surfs:
        gmsh.model.addPhysicalGroup(2, list(set(port1_surfs)), tag=4, name="Port1")
        gmsh.model.addPhysicalGroup(2, list(set(port2_surfs)), tag=6, name="Port2")
        all_port_surfs = list(set(port1_surfs + port2_surfs))
    else:
        if port_surfs:
            gmsh.model.addPhysicalGroup(2, list(set(port_surfs)), tag=4, name="Port")
        all_port_surfs = port_surfs

    gmsh.model.addPhysicalGroup(2, list(set(absorbing_surfs)), tag=5, name="Absorbing")
    
    # 3. Local adaptive refinement setup (Distance / Threshold field)
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

    # 4. Global bounds and compatible export for MFEM / Palace (MSH 2.2)
    gmsh.option.setNumber("Mesh.MeshSizeMax", params['mesh_size_max'])
    gmsh.option.setNumber("Mesh.MeshSizeMin", params['mesh_size_min'])
    gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
    gmsh.option.setNumber("Mesh.Binary", 0)
    
    target_dir = data_dir or "data"
    os.makedirs(target_dir, exist_ok=True)
    gmsh.model.mesh.generate(3)
    gmsh.write(os.path.join(target_dir, "mesh.msh"))
    gmsh.finalize()
