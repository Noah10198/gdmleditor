# GDMLEditor

**GDML geometry editor** — Import, browse, edit and export Geant4 GDML geometry in an interactive 3D view, with collision checking and scene building.

> **Version 0.1.0** ｜ Last updated 2026-09-30 ｜ Chinese version: [README.zh.md](README.zh.md)

## Overview

GDMLEditor is a **PyQt6 + VTK** based [GDML](https://geant4.web.cern.ch/support/source_geometry_manuals) (Geometry Description Markup Language) 3D geometry editor, part of the Easy2Rad project. It supports GDML file parsing, 3D visualization, browsing, editing, and export.

> **Platform note**: Currently developed and tested on **Windows**. Linux support will be verified in future releases.

## Features

### File Operations

- **Import GDML** — Single/multiple `.gdml` files, background threading for large files
- **Export GDML** — Full GDML export preserving original XML structure and user edit overlays
- **Multi-file merge** — Auto-merge scene trees from multiple imports

### 3D Visualization

- **VTK rendering** — Hardware-accelerated 3D rendering via VTK + OpenGL 2 backend
- **Interaction** — Mouse rotate/pan/zoom, node picking (click to highlight)
- **View controls** — X/Y/Z axis views, orthographic/perspective toggle, Fit All, Reset View
- **Clipping plane** — Real-time X/Y/Z axis clipping with slider position control
- **Visual effects** — Edge lines toggle, transparency toggle, dark/light themes
- **GPU diagnostics** — OpenGL information is printed at startup; an on-screen GPU context is preferred and falls back to off-screen software rendering

### Scene Building

- **Detectors** — **🧊 Box** / **🌐 Sphere** create a simple detector volume as its own GDML file, previewed in the main view against the world box it will get
- **Solid preview** — right-click a solid → standalone VTK preview window
- **Delete / Clear** — remove a single imported file from the tree, or **🗑️ Clear All** to empty the scene

### Editing

- **Transform editing** — Position/rotation overrides for physvol and file nodes (non-destructive)
- **World redefinition** — Auto-compute scene bounding box, resize world volume
- **Material assignment** — Batch NIST + custom material assignment
- **Local materials** — Create/edit/delete custom elements, compounds, mixtures from the tree; JSON import/export

### Collision Detection

- **AABB-based** — Fast axis-aligned bounding box overlap detection
- **Full / sample modes** — Full O(n²) or random 5% sample (min 2, max 50 pairs)
- **Cross-file guarantee** — At least one cross-file pair in sample mode
- **Batch highlight** — Colliding volumes highlighted in 3D scene

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
| genericPolycone | ✅ | ✅ | ✅ | Polycone from generic parameters |
| ~25 other types | ✅ | ❌ | ✅ | Raw XML preserved, round-trip safe |
| Bool / multiUnion | ✅ | ❌ | ✅ | Raw XML preserved |

> Importing unsupported solid types triggers a `QMessageBox` warning listing all unsupported items.

## Requirements

| Dependency | Version |
|---|---|
| Python | >= 3.10 |
| PyQt6 | == 6.4.2 (`environment.yml` pins it; newer versions are not tested) |
| VTK | >= 9.2.0 |
| numpy | any recent version |

> There is no `requirements.txt` for this module — `environment.yml` is the reference environment.

## Installation

```bash
conda env create -f environment.yml
conda activate easy2rad-env
python main.py
```

## Usage

1. **Import**: click **📂 Import GDML** in the toolbar and select one or more `.gdml` files
2. **Browse**: left tree panel for the hierarchy, centre 3D view for visual inspection
3. **Select**: click a tree node or pick in 3D — the right property panel shows details
4. **Edit transform**: right-click a tree node → Transform dialog (position/rotation)
5. **Collision test**: click **🔌 Interference** → select volumes → Run
6. **Assign materials**: click **🧪 Material** → batch assignment dialog
7. **Add a detector**: click **🧊 Box** / **🌐 Sphere** → detector volume as its own GDML file
8. **Redefine world**: click **📐 Redefine World** → resize the world volume to the scene
9. **Export**: click **💾 Export GDML** → choose the save path

> The left dock is titled `Project Tree`. Its root row is named `Project of GDMLEditor`; the
> imported geometry hangs under that row.

## Project Structure

```
gdmleditor/
├── main.py                     Entry point (QApplication + main window)
├── app/
│   └── main_window.py          Application main window, tree/scene orchestration
├── core/                       Core layer — data model + logic
│   ├── gdml_agent.py           Singleton orchestrator (parse tree + edit overlays)
│   ├── gdml_parser.py          XML → GdmlNode tree
│   ├── gdml_tree.py            GdmlNode types + Placement
│   ├── gdml_writer.py          Node tree → XML
│   ├── gdml_evaluator.py       Math expression evaluator
│   ├── detector_factory.py     Box / sphere detector generation
│   ├── materials_lib.py        NIST + local material library
│   └── collision_detector.py   AABB collision detection
├── ui/                         Qt widget layer
│   ├── vtk_widget.py           Embedded VTK 3D view
│   ├── vtk_view_window.py      Standalone VTK preview window
│   ├── project_tree.py         Tree panel
│   ├── property_panel.py       Property panel
│   ├── ribbon_toolbar.py       Ribbon toolbar
│   ├── interference_panel.py   Collision detection panel
│   ├── detector_dialog.py      Add detector dialog
│   ├── transform_dialog.py     Position / rotation dialog
│   ├── redefine_world_dialog.py  World volume resize dialog
│   └── ...                     Material dialogs, ...
├── vtk_engine/                 Rendering engine
│   ├── vtk_scene.py            Scene manager
│   └── vtk_solid_factory.py    Solid type → vtkActor factory
├── utils/
│   └── logger.py               Async logger
├── tests/                      Export round-trip test
├── docs/                       Developer documentation
├── icon/                       Application icon (gdmleditor.svg)
├── output/                     Exported GDML files
├── data/                       Element + material data files
│   ├── element.xml
│   ├── nist.txt
│   └── local_materials.json    Written when the user saves local materials
├── environment.yml             Conda environment (name: easy2rad-env)
├── README.md                   This file
└── README.zh.md                Chinese version of this file
```

## Architecture

The application is layered: `app/` wires the workflow, `core/` owns the data model and logic,
`vtk_engine/` turns the model into actors, `ui/` holds the Qt widgets, and `utils/` provides
shared helpers. The parse tree is never modified in place — every user edit is stored in an
overlay owned by `GdmlAgent`.

### Data Flow

1. **Import**: File → `GdmlParser.parse_file()` → `GdmlNode` tree → `GdmlAgent`
2. **Render**: `GdmlAgent.get_root_node()` → `VtkScene.build_from_tree()` → `VtkSolidFactory` creates `vtkActor` → `vtkRenderer`
3. **Edit**: UI → `GdmlAgent` (overlay layer) → scene rebuild
4. **Export**: `GdmlWriter.write()` → node tree + overlays → GDML XML

## Known Limitations

- Only the solid types listed above are rendered; roughly 25 other types (`polyhedra`,
  `xtru`, `cutTube`, `tet`, booleans, `multiUnion`, `scaledSolid`, ...) are parsed and written
  back verbatim but not drawn. An **"Incomplete Geometry Parsing"** dialog lists them on import.
- `<materials>` parsing is simplified (MVP): only `name` and the density value are read.
- The expression evaluator replaces undefined identifiers with `0`.
- Collision detection is pure **AABB**: full O(n²) or a random 5% sample (min 2, max 50 pairs).
  It is a conservative approximation, not an exact intersection test.
- Not implemented (documented in `docs/09_known_limitations.md`): `divisionvol`, `replicavol`,
  `parameterised`, `loop`, `matrix`, `bordersurface` / `skinsurface`, `isotope`.
- Files below 500 KB are parsed on the main thread; larger files use a background thread with a
  marquee progress dialog that has no cancel button.

## Development Notes

- **Instance cloning (Geant4 pattern)** — Each `<physvol>` creates a recursively cloned subtree;
  the source volume definition stays in the logical volume store.
- **Edit overlay layer** — `GdmlAgent` keeps `_placement_overrides` / `_material_overrides`
  dictionaries; the render layer receives an override provider injected into `VtkScene`, so the
  original parse tree stays untouched.
- **Background threading** — `_ImportWorker` parses in a `QThread` for files above 500 KB
  (`file_parsed` / `all_done` signals); the progress dialog is kept open until the tree and the
  3D scene have been rebuilt.
- **GPU auto-detection** — An on-screen GPU context is preferred; if it fails the view falls
  back to off-screen software rendering (`SetOffScreenRendering(True)`) and the OpenGL
  information is printed once for diagnosis. `VtkViewWindow` must not be styled with QSS — it
  breaks OpenGL composition and the window goes white.
- **Singletons** — `GdmlAgent`, `VtkSolidFactory`, `AsyncLogger`; `MaterialsLib` is
  singleton-style with a class-level element database.
- **Logger** — `AsyncLogger` broadcasts through the `log_received` signal and caches messages
  until a log widget is attached.
- **Lossless round-trip** — Unsupported solids are preserved as raw XML for export fidelity.

## Related Documents

- **Architecture overview**: [docs/01_architecture_overview.md](docs/01_architecture_overview.md)
- **VTK rendering engine**: [docs/03_vtk_rendering_engine.md](docs/03_vtk_rendering_engine.md)
- **Collision / interference detection**: [docs/06_collision_detection.md](docs/06_collision_detection.md)
- **Background thread loading**: [docs/07_background_threading.md](docs/07_background_threading.md)
- **Material system**: [docs/08_material_system.md](docs/08_material_system.md)
- **Known limitations and future directions**: [docs/09_known_limitations.md](docs/09_known_limitations.md)
- **Parser / writer capabilities**: [docs/parser_capabilities.md](docs/parser_capabilities.md)
- Chinese version of this file: [README.zh.md](README.zh.md)

## License

[MIT](LICENSE) © ready2run

## Acknowledgments

- [OpenCASCADE Technology](https://dev.opencascade.org/) — CAD kernel
- [GMSH](https://gmsh.info/) — Finite element mesh generator
- [VTK](https://vtk.org/) — Visualization Toolkit
- [PythonOCC](https://github.com/tpaviot/pythonocc-core) — Python bindings for OCC
- [Geant4](https://geant4.web.cern.ch/) — GDML geometry format
- [CodeBuddy](https://www.codebuddy.ai/) & [DeepSeek](https://deepseek.com/) — AI-assisted development throughout this project
