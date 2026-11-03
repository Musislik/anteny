import os
import json

# Fyzikalni a konfiguracni konstanty
SCALE_MM_TO_M = 1e-3
DEFAULT_PORT_IMPEDANCE_V1 = 50.0
DEFAULT_PORT_IMPEDANCE_V2 = 100.0

def build_palace_config(params):
    model_version = int(params.get('antenna_model', 1))
    
    if model_version == 2:
        port_r = float(params.get('port_impedance', DEFAULT_PORT_IMPEDANCE_V2))
        driven_mode = str(params.get('driven_port', os.getenv('DRIVEN_PORT', 'all'))).lower().strip()

        # Volba buzení portů pro Model 2:
        # '1', 'b', 'bottom', 'ey' -> budit pouze Port 1 (spodní, Ey) pro čisté S11 a S21
        # '2', 'l', 'left', 'ex'   -> budit pouze Port 2 (levý, Ex) pro čisté S22 a S12
        # 'simultaneous', 'dual'   -> budit oba porty současně
        # 'all', 'both', 'matrix'  -> výchozí 2-krokové buzení z main.py (staticky v config.json buzen Port 1)
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
            # Pro 'all', 'both', 'matrix' je v samostatném config.json přednastaven Port 1
            exc1 = True
            exc2 = False

        lumped_ports = [
            {
                "Index": 1,
                "Attributes": [4],  # 4: Spodní port (Port 1, pole Ey)
                "Direction": "+Z",  # Vektor excitace od z=0 do z=h
                "R": port_r,
                "Excitation": exc1
            },
            {
                "Index": 2,
                "Attributes": [6],  # 6: Levý port (Port 2, pole Ex)
                "Direction": "+Z",  # Vektor excitace od z=0 do z=h
                "R": port_r,
                "Excitation": exc2
            }
        ]
    else:
        port_r = float(params.get('port_impedance', DEFAULT_PORT_IMPEDANCE_V1))
        lumped_ports = [
            {
                "Index": 1,
                "Attributes": [4],  # 4: Port (Model 1)
                "Direction": "+Z",  # Vektor excitace od z=0 do z=h
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
            "Order": 2,
            "Driven": {
                "MinFreq": params['freq_min'],
                "MaxFreq": params['freq_max'],
                "FreqStep": params['freq_step'],
                "SaveStep": save_step,
                "AdaptiveTol": 1e-3
            },
            "Linear": {
                "Type": "SuperLU",
                "KSPType": "FGMRES",
                "Tol": linear_tol,
                "MaxIts": linear_max_its
            }
        }
    }
    
    with open("data/config.json", "w") as f:
        json.dump(config, f, indent=4)
