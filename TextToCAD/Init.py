"""
Non-GUI initialisation for the Text-to-CAD module.

FreeCAD imports this at startup (even in console mode). We only make the
package importable here; all GUI wiring lives in InitGui.py.
"""

import os
import sys

_HERE = os.path.dirname(__file__)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
