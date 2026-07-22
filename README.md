# gdmleditor — GDML Geometry Editor

## Overview

gdmleditor is a **PyQt6 + VTK** based [GDML](https://geant4.web.cern.ch/support/source_geometry_manuals) (Geometry Description Markup Language) 3D geometry editor, part of the Easy2Rad project. It supports GDML file parsing, 3D visualization, browsing, editing, and export.

## Features

### File Operations
- **Import GDML** — Single/multiple `.gdml` files, background threading for large files
- **Export GDML** — Full GDML export preserving original XML structure and user edit overlays
- **Multi-file merge** — Auto-merge scene trees from multiple imports

### 3D Visualization
- **VTK rendering** — Hardware-accelerated 3D rendering via VTK + OpenGL 2 backend
- **Interaction** — Mouse rotate/pan/zoom, node picking (click to highlight)
- **View controls** — X/Y/Z axis views, orthographic/perspective toggle, Fit All
- **Clipping plane** — Real-time X/Y/Z axis clipping with slider position control
- **Visual effects** — Edge lines toggle, transparency toggle, dark/light themes
- **GPU diagnostics** — Auto-detect OpenGL vendor/device/version/GLSL on startup; graceful fallback to software rendering if no GPU driver is available

### Supported Solid Types

| Type | Parse | Render | Export | Notes |
|------|:-----:|:------:|:------:|-------|
| box | ✅ | ✅ | ✅ | Rectangular solid |
| sphere | ✅ | ✅ | ✅ | Supports rmin/startphi/deltaphi/starttheta/deltatheta |
| orb | ✅ | ✅ | ✅ | Full sphere (single radius) |
| tube / tubs | ✅ | ✅ | ✅ | Cylindrical / phi-segment tube |
| cone | ✅ | ✅ | ✅ | Conical frustum |
| tessellated | ✅ | ✅ | ✅ | Triangular + quadrangular facets |
| torus | ✅ | ✅ | ✅ | Toroidal solid |
| ellipsoid | ✅ | ✅ | ✅ | Non-uniform scale |
| polycone | ✅ | ✅ | ✅ | Multi-section cone (approximate render) |
| ~25 other types | ✅ | ❌ | ✅ | Raw XML preserved, round-trip safe |
| Bool / multiUnion | ✅ | ❌ | ✅ | Raw XML preserved |

> Importing unsupported solid types triggers a `QMessageBox` warning listing all unsupported items.

### Editing
- **Transform editing** — Position/rotation overrides for physvol and file nodes (non-destructive)
- **World redefinition** — Auto-compute scene bounding box, resize world volume
- **Material assignment** — Batch NIST + custom material assignment
- **Local materials** — Create/edit/delete custom elements, compounds, mixtures; JSON import/export

### Collision Detection
- **AABB-based** — Fast axis-aligned bounding box overlap detection
- **Full / sample modes** — Full O(n²) or random 5% sample (min 2, max 50 pairs)
- **Cross-file guarantee** — At least one cross-file pair in sample mode
- **Batch highlight** — Colliding volumes highlighted in 3D scene

## Architecture

```
main.py
  └── app/                  (Application layer — MainWindow + workflow)
       └── main_window.py
  ├── core/                 (Core layer — data model + logic)
  │    ├── gdml_agent.py         [Singleton orchestrator]
  │    ├── gdml_parser.py        [XML → GdmlNode tree]
  │    ├── gdml_tree.py          [GdmlNode types + Placement]
  │    ├── gdml_writer.py        [Node tree → XML]
  │    ├── gdml_evaluator.py     [Math expression evaluator]
  │    ├── materials_lib.py      [NIST + local material library]
  │    └── collision_detector.py [AABB collision detection]
  ├── ui/                   (Qt widget layer)
  │    ├── vtk_widget.py         [Embedded VTK 3D view]
  │    ├── project_tree.py       [Tree panel]
  │    ├── property_panel.py     [Property panel]
  │    ├── ribbon_toolbar.py     [Ribbon toolbar]
  │    ├── interference_panel.py [Collision detection panel]
  │    └── ... dialogs
  ├── vtk_engine/           (Rendering engine)
  │    ├── vtk_scene.py          [Scene manager]
  │    └── vtk_solid_factory.py  [Solid type → vtkActor factory]
  ├── utils/                (Utilities)
  │    └── logger.py             [Async logger]
  ├── docs/                 (Documentation)
  └── data/                 (Element + material data files)
       ├── element.xml
       ├── nist.txt
       └── local_materials.json
```

### Data Flow

1. **Import**: File → `GdmIParser.parse_file()` → `GdmlNode` tree → `GdmlAgent`
2. **Render**: `GdmlAgent.get_root_node()` → `VtkScene.build_from_tree()` → `VtkSolidFactory` creates `vtkActor` → `vtkRenderer`
3. **Edit**: UI → `GdmlAgent` (overlay layer) → scene rebuild
4. **Export**: `GdmlWriter.write()` → node tree + overlays → GDML XML

## Installation

### Requirements
- Python ≥ 3.10
- PyQt6 ≥ 6.5.0
- VTK ≥ 9.2.0

### Setup

```bash
pip install -r requirements.txt
python main.py
```

## Usage

1. **Import**: Click toolbar "[📂 Import](https://github.com/)" button, select `.gdml` file(s)
2. **Browse**: Left tree panel for hierarchy, center 3D view for visual inspection
3. **Select**: Click tree node or 3D pick — right property panel shows details
4. **Edit transform**: Right-click tree node → Transform dialog (position/rotation)
5. **Collision test**: Click interference button → select volumes → Run
6. **Assign materials**: Click material button → batch assignment dialog
7. **Export**: Click "[💾 Export](https://github.com/)" → choose save path

## Key Design Decisions

1. **Instance cloning (Geant4 pattern)** — Each `<physvol>` creates a recursively cloned subtree; the source volume definition stays in the logical volume store
2. **Edit overlay layer** — All user edits stored as non-destructive overlays; original parse tree untouched
3. **Background threading** — Files >500KB parsed in `QThread` with marquee progress dialog
4. **GPU auto-detection** — On-screen GPU rendering with off-screen software fallback; OCC-style console output
5. **Lossless round-trip** — Unsupported solids preserved as raw XML for perfect export fidelity

## Performance Notes

- **Bottleneck**: Rendering very large numbers of independent physvols (e.g. 20k+) is CPU-bound on draw call submissions, not GPU fill-rate
- **Large file test**: A 4.5MB / 102k-line / ~20k-physvol file loads correctly; interactive frame rate is limited
- **Optimization path**: Actor merging (same-type solids → single PolyData) and instanced rendering (`vtkInstancedMapper`)
- See `docs/04_performance_analysis.md` for details

## License

Part of the Easy2Rad project.
