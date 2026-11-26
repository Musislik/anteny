import os
import json

# Physical and configuration constants
SCALE_MM_TO_M = 1e-3
DEFAULT_PORT_IMPEDANCE_V1 = 50.0   # Model 1, Model 4, and Model 7 (single 50 Ohm port)
DEFAULT_PORT_IMPEDANCE_V2 = 100.0  # Model 2, Model 3, Model 5, and Model 6 (two 100 Ohm ports)

def build_palace_config(params, data_dir=None):
    model_version = int(params.get('antenna_model', 1))
    
    if model_version in (2, 3, 5, 6):
        port_r = float(params.get('port_impedance', DEFAULT_PORT_IMPEDANCE_V2))
        driven_mode = str(params.get('driven_port', os.getenv('DRIVEN_PORT', 'all'))).lower().strip()

        # Port excitation selection for Model 2, Model 3, Model 5, and Model 6:
        # '1', 'b', 'bottom', 'ey' -> excite only Port 1 (bottom, Ey) for pure S11 and S21
        # '2', 'l', 'left', 'ex'   -> excite only Port 2 (left, Ex) for pure S22 and S12
        # 'simultaneous', 'dual'   -> excite both ports simultaneously
        # 'all', 'both', 'matrix'  -> default 2-step excitation from main.py (static config.json excites Port 1)
        if driven_mode in ('1', 'b', 'bottom', 'ey', 'port1'):
            exc1 = True
            exc2 = False
        elif driven_mode in ('2', 'l', 'left', 'ex', 'port2'):
            exc1 = False
            exc2 = True
        elif driven_mode in ('simultaneous', 'dual'):
            exc1 = True
            exc2 = True
        else:
            # For 'all', 'both', 'matrix', Port 1 is preset in standalone config.json
            exc1 = True
            exc2 = False

        lumped_ports = [
            {
                "Index": 1,
                "Attributes": [4],  # 4: Bottom port (Port 1, Ey field)
                "Direction": "+Z",  # Excitation vector from z=0 to z=h
                "R": port_r,
                "Excitation": exc1
            },
            {
                "Index": 2,
                "Attributes": [6],  # 6: Left port (Port 2, Ex field)
                "Direction": "+Z",  # Excitation vector from z=0 to z=h
                "R": port_r,
                "Excitation": exc2
            }
        ]
    else:
        # Single-port model (Model 1, Model 4, or Model 7 with 50 Ohm T-junction)
        port_r = float(params.get('port_impedance', DEFAULT_PORT_IMPEDANCE_V1))
        lumped_ports = [
            {
                "Index": 1,
                "Attributes": [4],  # 4: Input/output 50 Ohm port
                "Direction": "+Z",  # Excitation vector from z=0 to z=h
                "R": port_r,
                "Excitation": True
            }
        ]

    amr_max_its = int(params.get('amr_max_its', 2))
    amr_tol = float(params.get('amr_threshold', params.get('amr_tol', 0.2)))
    farfield_nsample = int(params.get('farfield_nsample', 16200))
    save_step = int(params.get('save_step', 1))
    linear_tol = float(params.get('linear_tol', 1e-6))
    linear_max_its = int(params.get('linear_max_its', 100))
    linear_max_size_raw = params.get('linear_max_size', os.getenv('LINEAR_MAX_SIZE'))
    linear_max_size = int(linear_max_size_raw) if linear_max_size_raw else None
    
    model_config = {
        "Mesh": "data/mesh.msh",
        "L0": SCALE_MM_TO_M
    }
    if amr_max_its > 0:
        ref_dict = {
            "MaxIts": amr_max_its,
            "SaveAdaptMesh": True,
            "SaveAdaptIterations": True
        }
        if amr_tol > 0:
            ref_dict["Tol"] = amr_tol
        model_config["Refinement"] = ref_dict

    linear_solver_dict = {
        "Type": "SuperLU",
        "KSPType": "FGMRES",
        "Tol": linear_tol,
        "MaxIts": linear_max_its,
    }
    if linear_max_size:
        linear_solver_dict["MaxSize"] = linear_max_size

    config = {
        "Problem": {
            "Type": "Driven",
            "Verbose": 2,
            "Output": "data/postpro"
        },
        "Model": model_config,
        "Domains": {
            "Materials": [
                {
                    "Attributes": [1],  # 1: Substrate
                    "Permittivity": params['eps_r'],
                    "Permeability": 1.0,
                    "LossTan": params['tan_delta']
                },
                {
                    "Attributes": [2],  # 2: Air
                    "Permittivity": 1.0,
                    "Permeability": 1.0
                }
            ]
        },
        "Boundaries": {
            "Postprocessing": {
                "FarField": {
                    "Attributes": [5],
                    "NSample": farfield_nsample
                }
            },
            "PEC": {
                "Attributes": [3]  # 3: PEC
            },
            "Absorbing": {
                "Attributes": [5],  # 5: Absorbing outer boundary
                "Order": 2
            },
            "LumpedPort": lumped_ports
        },
        "Solver": {
            "Order": int(params.get('solver_order', os.getenv('SOLVER_ORDER', 2))),
            "Driven": {
                "MinFreq": params['freq_min'],
                "MaxFreq": params['freq_max'],
                "FreqStep": params['freq_step'],
                "SaveStep": save_step,
                "AdaptiveTol": 1e-3
            },
            "Linear": linear_solver_dict
        }
    }
    
    target_dir = data_dir or "data"
    os.makedirs(target_dir, exist_ok=True)
    with open(os.path.join(target_dir, "config.json"), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)
