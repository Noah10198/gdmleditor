# gdmleditor — GDML Geometry Editor

## Overview

gdmleditor is a **PyQt6 + VTK** based [GDML](https://geant4.web.cern.ch/support/source_geometry_manuals) (Geometry Description Markup Language) 3D geometry editor, part of the Easy2Rad project. It supports GDML file parsing, 3D visualization, browsing, editing, and export.

## Features

### File Operations
- **Import GDML** — Single/multiple `.gdml` files, background loading, no UI freeze for large files
- **Export GDML** — Full GDML export preserving original XML structure and user edit overlays
- **Multi-file Merge** — Auto-merge scene trees from multiple imports

### 3D Visualization
- **VTK Rendering** — High-performance 3D rendering engine
- **Interaction** — Rotate/pan/zoom, node picking (click to highlight)
- **View Controls** — X/Y/Z axis views, orthographic/perspective toggle, Fit All
- **Clipping Plane** — Real-time X/Y/Z axis clipping with slider control
- **Visual Effects** — Edge lines toggle, transparency toggle, dark/light themes
- **GPU Diagnostics** — Auto-detect OpenGL info on startup, graceful fallback to software rendering

### Geometry Support
- 9 solid types fully supported (box, sphere, orb, tube, cone, tessellated, torus, ellipsoid, polycone)
- ~25 other standard types preserved for round-trip export (no 3D rendering)
- Unsupported types trigger warning dialog

### Editing
- **Transform Editing** — Position/rotation editing for physvol and file nodes (non-destructive overlays)
- **World Redefine** — Auto-compute bounding box, redefine world volume
- **Material Assignment** — Batch NIST + custom material assignment
- **Local Materials** — Create/edit/delete custom elements, compounds, mixtures; JSON import/export

### Collision Detection
- **AABB-based** — Fast axis-aligned bounding box overlap detection
- **Full/Sample Modes** — Full O(n²) or random sample (5%) with cross-file pair guarantee
- **Batch Highlight** — Colliding volumes highlighted in 3D view

## System Architecture

```
main.py
  └── app/                  (Application layer)
       └── main_window.py
  ├── core/                 (Core data model + logic)
  │    ├── gdml_agent.py         [Singleton orchestrator]
  │    ├── gdml_parser.py        [XML → node tree]
  │    ├── gdml_tree.py          [GdmlNode types]
  │    ├── gdml_writer.py        [Node tree → XML]
  │    ├── gdml_evaluator.py     [Math expression evaluator]
  │    ├── materials_lib.py      [Material library]
  │    └── collision_detector.py [AABB collision detection]
  ├── ui/                   (Qt widgets)
  ├── vtk_engine/           (Rendering engine)
  └── data/                 (Element/Material data)
```

## Installation

### Requirements
- Python ≥ 3.10
- PyQt6 ≥ 6.5.0
- VTK ≥ 9.2.0

### Quick Start

```bash
pip install -r requirements.txt
python main.py
```

## Key Design Decisions

1. **Instance Cloning (Geant4 Pattern)** — Each physvol creates a cloned subtree; source volume remains in the logical volume store
2. **Edit Overlay Layer** — All edits stored as overlays, original parse tree untouched
3. **Background Threading** — Files >500KB parsed in QThread with marquee progress
4. **GPU Auto-detection** — On-screen GPU rendering with off-screen software fallback
5. **Lossless Round-trip** — Unsupported solids preserved as raw XML for perfect export
