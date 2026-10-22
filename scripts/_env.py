"""
_env.py - Pomocný inicializátor cest pro skripty ve složce scripts/.
Zajišťuje, že všechny skripty v této složce mohou přímo importovat
moduly z projektové knihovny v src/ bez nutnosti opakovat nastavování sys.path.
"""

import os
import sys

_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC_DIR = os.path.join(_ROOT_DIR, "src")

if os.path.exists(_SRC_DIR) and _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
if os.path.exists(_ROOT_DIR) and _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)
