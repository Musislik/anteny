"""
_env.py - Helper path initializer for scripts in the scripts/ directory.
Ensures all scripts in this folder can directly import modules from the project
library in src/ without repeating sys.path setup.
"""

import os
import sys

_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC_DIR = os.path.join(_ROOT_DIR, "src")

if os.path.exists(_SRC_DIR) and _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
if os.path.exists(_ROOT_DIR) and _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)
