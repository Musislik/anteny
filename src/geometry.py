"""
geometry.py - Router for microstrip patch antenna geometric models.
Depending on the 'antenna_model' parameter (or ANTENNA_MODEL in .env), delegates to:
  - Model 1 (geometry_v1.py): Original model with shared T-junction power divider and 1 port (50 Ohm).
  - Model 2 (geometry_v2.py): Two-port model with two independent 100 Ohm microstrip lines and LHCP phasing.
  - Model 3 (geometry_v3.py): Hybrid two-stage matching (Path B: shallow inset + lambda_g/4 transformer + 100 Ohm feed with phaser).
  - Model 4 (geometry_v4.py): Final model completing Model 3 (joining both 100 Ohm branches with smooth arcs into a T-junction to a 50 Ohm port).
  - Model 5 (geometry_v5.py): Two-port model with curved branches without a T-junction (two separate 100 Ohm ports).
  - Model 6 (geometry_v6.py): Two-port model with curved branches from Model 4 and internal 100 Ohm ports.
  - Model 7 (geometry_v7.py): Model 4 mirrored across the Y-axis for opposite polarization (RHCP, 50 Ohm port on the right).
"""

import os
from postpro_utils import load_env

def build_model(params):
    load_env()
    model_version = int(params.get('antenna_model', os.getenv('ANTENNA_MODEL', '1')))
    if model_version == 7:
        from geometry_v7 import build_model_v7
        return build_model_v7(params)
    elif model_version == 6:
        from geometry_v6 import build_model_v6
        return build_model_v6(params)
    elif model_version == 5:
        from geometry_v5 import build_model_v5
        return build_model_v5(params)
    elif model_version == 4:
        from geometry_v4 import build_model_v4
        return build_model_v4(params)
    elif model_version == 3:
        from geometry_v3 import build_model_v3
        return build_model_v3(params)
    elif model_version == 2:
        from geometry_v2 import build_model_v2
        return build_model_v2(params)
    else:
        from geometry_v1 import build_model_v1
        return build_model_v1(params)
