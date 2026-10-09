import json

def build_palace_config(params):
    config = {
        "Problem": {
            "Type": "Driven",
            "Verbose": 2,
            "Output": "postpro"
        },
        "Model": {
            "Mesh": "mesh.msh",
            "L0": 1e-3, # Gmsh používá mm, L0 to převede na metry
            "Refinement": {
                "MaxLevels": 2,
                "Tolerance": params.get('amr_threshold', 0.3)
            }
        },
        "Domains": {
            "Materials": [
                {
                    "Attributes": ["Substrate"],
                    "Permittivity": params['eps_r'],
                    "Permeability": 1.0,
                    "LossTan": params['tan_delta']
                },
                {
                    "Attributes": ["Air"],
                    "Permittivity": 1.0,
                    "Permeability": 1.0
                }
            ]
        },
        "Boundaries": {
            "PEC": {
                "Attributes": ["PEC"]
            },
            "Absorbing": {
                "Attributes": ["Absorbing"],
                "Order": 1
            },
            "LumpedPort": [
                {
                    "Index": 1,
                    "Attributes": ["Port"],
                    "Direction": [0.0, 0.0, 1.0], # Integrační čára od z=0 do z=h
                    "R": 50.0
                }
            ]
        },
        "Solver": {
            "Order": 1,
            "Driven": {
                "MinFreq": params['freq_min'],
                "MaxFreq": params['freq_max'],
                "FreqStep": params['freq_step'],
                "SaveStep": params['freq_step']
            },
            "Linear": {
                "Type": "SuperLU",
                "KSPType": "FGMRES",
                "Tol": 1e-6,
                "MaxIts": 100
            }
        }
    }
    
    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)
