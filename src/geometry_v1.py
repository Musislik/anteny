import gmsh
import numpy as np

def build_model_v1(params):
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1)
    gmsh.model.add("lhcp_antenna")
    
    L = params['patch_L']
    W = params['patch_W']
    h = params['sub_h']
    L_sub = params.get('sub_L', params.get('sub_l', 100.0))
    W_sub = params.get('sub_W', params.get('sub_w', 100.0))
    margin = params['air_margin']
    
    # 1. Volume bodies
    # Substrate
    sub_tag = gmsh.model.occ.addBox(-W_sub/2, -L_sub/2, 0, W_sub, L_sub, h)
    
    # Air box
    air_tag = gmsh.model.occ.addBox(-W_sub/2 - margin, -L_sub/2 - margin, -margin, 
                                    W_sub + 2*margin, L_sub + 2*margin, h + 2*margin)
    
    # 2. Surface entities (2D) for patch and feed network (z = h)
    # Feed inset
    inset = float(params.get('inset', params.get('feed_inset', 0.0)))

    # Feed T-divider for cross-fed patch antenna (LHCP circular polarization)
    # Three trace widths:
    # 1. w1: 50 Ohm main feed from port to T-junction (natural matching, no transformer)
    # 2. w2: 100 Ohm phasing divider branches (reference bottom branch Ey, delayed left branch Ex with +lambda_g/4 length)
    # 3. w3: feed line into the antenna itself (degree of freedom, w3 <= w2)

    w1 = params.get('w1')
    w2 = params.get('w2')
    w3 = params.get('w3')

    # Inset gap width (gap g on both sides of trace w3, or derived from total cutout width)
    if params.get('inset_width') is not None or params.get('feed_inset_width') is not None:
        total_w = float(params.get('inset_width', params.get('feed_inset_width')))
        inset_gap = max((total_w - w3) / 2.0, 0.05)
    else:
        inset_gap = float(params.get('inset_gap', params.get('feed_inset_gap', w3)))

    params['inset_gap'] = inset_gap
    params['inset_width'] = float(np.round(w3 + 2.0 * inset_gap, 3))

    # Patch (with optional feed inset / notches)
    if inset > 0:
        patch_base = gmsh.model.occ.addRectangle(-W/2, -L/2, h, W, L)
        # Notch for bottom branch (at x = 0, y from -L/2 to -L/2 + inset, width w3 + 2*inset_gap)
        notch_b = gmsh.model.occ.addRectangle(-(w3/2 + inset_gap), -L/2 - 0.05, h, w3 + 2*inset_gap, inset + 0.05)
        # Notch for left branch (at y = 0, x from -W/2 to -W/2 + inset, height w3 + 2*inset_gap)
        notch_l = gmsh.model.occ.addRectangle(-W/2 - 0.05, -(w3/2 + inset_gap), h, inset + 0.05, w3 + 2*inset_gap)
        cut_surfs, _ = gmsh.model.occ.cut([(2, patch_base)], [(2, notch_b), (2, notch_l)])
        patch_tag = cut_surfs[0][1]
    else:
        patch_tag = gmsh.model.occ.addRectangle(-W/2, -L/2, h, W, L)

    # Retrieve segment lengths l1 through l8 (must be defined in params)
    l1 = float(params['l1'])
    l2 = float(params['l2'])
    l3 = float(params['l3'])
    l4 = float(params['l4'])
    l5 = float(params['l5'])
    l6 = float(params['l6'])
    l7 = float(params['l7'])
    l8 = float(params['l8'])

    # T-junction position (x_T, y_T) derived from lengths l2, l3, l4
    # Bottom branch goes right from T-junction to patch centerline x = 0 (l2 + l3 = |x_T|)
    x_T = float(params.get('feed_x_T'))
    # Vertical section l4 goes from y_T to bottom patch edge y = -L/2
    y_T = float(params.get('feed_y_T'))

    params['port_x'] = x_T
    params['feed_x_T'] = x_T
    params['feed_y_T'] = y_T
    params['w1'] = w1
    params['w2'] = w2
    params['w3'] = w3

    metal_surfs = [patch_tag]

    # 1. Main feed (50 Ohm, width w1): section l1 from input port to T-junction
    y_port = -L_sub / 2.0
    f_main = gmsh.model.occ.addRectangle(x_T - w1/2, y_port, h, w1, abs(y_T - y_port) + w2/2)
    metal_surfs.append(f_main)

    # 2. Bottom reference branch (phase 0 deg, Ey field):
    # a) Segment l2 (width w2, length l2): from T-junction right to width step w2 -> w3
    f_b_l2 = gmsh.model.occ.addRectangle(x_T - w2/2, y_T - w2/2, h, l2 + w2/2, w2)
    # b) Segment l3 (width w3, length l3): from width step to bend on axis x = 0
    f_b_l3 = gmsh.model.occ.addRectangle(x_T + l2, y_T - w3/2, h, l3 + w3/2, w3)
    # c) Segment l4 (width w3, length l4): from bend upward to bottom patch edge (y = -L/2)
    f_b_l4 = gmsh.model.occ.addRectangle(-w3/2, y_T - w3/2, h, w3, l4 + w3/2 + 0.1)
    metal_surfs.extend([f_b_l2, f_b_l3, f_b_l4])

    # 3. Left delay branch (phase -90 deg, Ex field, delayed by lambda_g/4):
    # a) Segment l5 (width w2, length l5): from T-junction left to corner bend (x = x_T - l5)
    f_l_l5 = gmsh.model.occ.addRectangle(x_T - l5 - w2/2, y_T - w2/2, h, l5 + w2/2, w2)
    # b) Segment l6 (width w2, length l6): from bend upward to width step to w3 (y = y_T + l6)
    f_l_l6 = gmsh.model.occ.addRectangle(x_T - l5 - w2/2, y_T - w2/2, h, w2, l6 + w2/2)
    # c) Segment l7 (width w3, length l7): from width step upward to upper bend (y = 0)
    f_l_l7 = gmsh.model.occ.addRectangle(x_T - l5 - w3/2, y_T + l6, h, w3, l7 + w3/2)
    # d) Segment l8 (width w3, length l8): from upper bend right to left patch edge (x = -W/2)
    f_l_l8 = gmsh.model.occ.addRectangle(x_T - l5 - w3/2, -w3/2, h, l8 + w3/2 + 0.1, w3)
    metal_surfs.extend([f_l_l5, f_l_l6, f_l_l7, f_l_l8])

    gmsh.model.occ.synchronize()

    # Create port surface (XZ plane on substrate edge y = -L_sub/2)
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
    
    # 3. Ground plane (GND) at bottom of substrate (z = 0)
    gnd_tag = gmsh.model.occ.addRectangle(-W_sub/2, -L_sub/2, 0, W_sub, L_sub)
    
    gmsh.model.occ.synchronize()
    
    # 4. Topological fusion (Boolean Fragments)
    # Merge all volumes and surfaces together so they are conformal in the mesh
    vols = gmsh.model.occ.getEntities(3)
    input_surfs = [(2, s) for s in metal_surfs] + [(2, gnd_tag), (2, port_tag)]
    
    _, out_map = gmsh.model.occ.fragment(vols, input_surfs)
    gmsh.model.occ.synchronize()
    
    # Exact fragment tracking for physical groups
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

build_model = build_model_v1
