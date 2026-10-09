import json

# Fyzikální a konfigurační konstanty
SCALE_MM_TO_M = 1e-3  # Měřítko délky ze sítě (mm) na metry pro Palace solver
DEFAULT_PORT_IMPEDANCE = 50.0

def build_palace_config(params):
    port_r = params.get('port_impedance', DEFAULT_PORT_IMPEDANCE)
    
    config = {
        "_Metadata": {
            "patch_L": params.get('patch_L', 30.0),
            "patch_W": params.get('patch_W', 30.0),
            "sub_h": params.get('sub_h', 1.52),
            "port_impedance": port_r
        },
        "Problem": {
            "Type": "Driven",
            "Verbose": 2,
            "Output": "data/postpro"
        },
        "Model": {
            "Mesh": "data/mesh.msh",
            "L0": SCALE_MM_TO_M, # Gmsh používá mm, L0 to převede na metry
            "Refinement": {
                "MaxLevels": 2,
                "Tolerance": params.get('amr_threshold', 0.3)
            }
        },
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
            "PEC": {
                "Attributes": [3]  # 3: PEC
            },
            "Absorbing": {
                "Attributes": [5],  # 5: Absorbing outer boundary
                "Order": 1
            },
            "LumpedPort": [
                {
                    "Index": 1,
                    "Attributes": [4],  # 4: Port
                    "Direction": "+Z",  # Vektor excitace od z=0 do z=h
                    "R": port_r,
                    "Excitation": True
                }
            ]
        },
        "Solver": {
            "Order": 1,
            "Driven": {
                "MinFreq": params['freq_min'],
                "MaxFreq": params['freq_max'],
                "FreqStep": params['freq_step'],
                "SaveStep": max(1, int(params.get('save_step', 1)))
            },
            "Linear": {
                "Type": "SuperLU",
                "KSPType": "FGMRES",
                "Tol": 1e-6,
                "MaxIts": 100
            }
        }
    }
    
    with open("data/config.json", "w") as f:
        json.dump(config, f, indent=4)
