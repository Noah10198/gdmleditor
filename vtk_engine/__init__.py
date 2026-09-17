"""
gdmleditor.vtk_engine - VTK Rendering Engine

Uses VTK for 3D display and interaction of GDML geometry solids.
"""

from typing import Tuple

# ── Shared appearance constants ──────────────────────────────────────────
# Colour of the world reference box (the wireframe frame marking the world
# volume).  Every place that draws a world box — per-WORLD_NODE boxes, the
# unified multi-file box and the Redefine World preview — uses this one
# yellow, so the world volume is recognisable as the same frame everywhere
# (cad2gdml draws it as a fixed-colour frame too).
WORLD_BOX_COLOR: Tuple[float, float, float] = (1.0, 0.9, 0.1)
