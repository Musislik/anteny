"""
geometry.py - Router geometrických modelů mikropáskové flíčkové antény.
Podle parametru 'antenna_model' (nebo ANTENNA_MODEL v .env) deleguje na:
  - Model 1 (geometry_v1.py): Původní model se společným T-děličem výkonu a 1 portem (50 Ohm).
  - Model 2 (geometry_v2.py): Dvouportový model se dvěma nezávislými 100 Ohm mikropásky a LHCP fázováním.
  - Model 3 (geometry_v3.py): Hybridní dvoustupňové přizpůsobení (Cesta B: mělký zářez + lambda_g/4 transformátor + 100 Ohm napaječ s fázovačem).
  - Model 4 (geometry_v4.py): Finální model dokončující Model 3 (spojení obou 100 Ohm větví plynulými oblouky do T-článku na 50 Ohm port).
"""

import os
from postpro_utils import load_env

def build_model(params):
    load_env()
    model_version = int(params.get('antenna_model', os.getenv('ANTENNA_MODEL', '1')))
    if model_version == 4:
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
