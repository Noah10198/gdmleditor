# 1. System Architecture Overview

## Layered Architecture

gdmleditor follows a clean four-layer design:

```
┌──────────────────────────────────────────┐
│ main.py (Entry point)                    │
│   QApplication + MainWindow + Logger     │
├──────────────────────────────────────────┤
│ app/ (Application layer)                 │
│   MainWindow: layout, signal routing,     │
│   workflow orchestration                  │
├──────────────────────────────────────────┤
│ core/ (Core layer)                       │
│   GdmlAgent → Parser/Writer/Evaluator    │
│   MaterialsLib / CollisionDetector       │
├──────────────────────────────────────────┤
│ ui/ (UI widget layer)                    │
│   Qt components: ProjectTree,            │
│   PropertyPanel, VtkWidget, dialogs      │
├──────────────────────────────────────────┤
│ vtk_engine/ (Rendering engine)           │
│   VtkScene: scene management / pick/highlight
│   VtkSolidFactory: geometry → vtkActor   │
├──────────────────────────────────────────┤
│ utils/ (Utility layer)                   │
│   AsyncLogger: non-blocking logging      │
└──────────────────────────────────────────┘
```

## Key Design Patterns

### 1. Singleton Orchestrator — GdmlAgent

`GdmlAgent` is the central singleton that manages all GDML data:

- Maintains `_root_node` (the root of the scene tree)
- Maps `entry_id → GdmlNode` via `_entry_id_map`
- Keeps `_file_nodes` list of loaded files
- Stores `_placement_overrides` for non-destructive edit overlays
- Provides `load_gdml_file()`, `get_root_node()`, `get_node_by_entry_id()`, etc.

### 2. Physical Instance Cloning (Geant4 Pattern)

Follows Geant4's `G4LogicalVolumeStore` pattern:

- Each `<volume>` definition lives as a LOGICAL VOLUME definition child of the file node (the "store")
- Each `<physvol>` creates a **recursively cloned subtree** rather than referencing the original node
- The same logical volume can be referenced by multiple physvols independently, transforms don't interfere

### 3. Edit Overlay Layer

All user edits are stored as overlays without modifying the original parse tree:

- **Transform overrides**: `_placement_overrides: Dict[str, Placement]` — user-adjusted transforms
- **Material overrides**: Applied during export via `GdmlWriter`
- Guarantees data integrity and lossless export

### 4. Background Thread Loading

Files >500KB are parsed in a `QThread`:

- `_ImportWorker(QObject)` worker runs `parse_file_only()` in the background
- Main thread safely calls `add_parsed_file_node()` via signal-slot
- `QProgressDialog` shows marquee animation during wait

## Complete Data Flow

```
File Import:
  [.gdml file]
       ↓
  GdmIParser.parse_file()    ← XML → GdmlNode tree
       ↓
  GdmlAgent.load_gdml_file() ← register into global tree
       ↓
  MainWindow._rebuild_ui()   ← rebuild tree + 3D scene

3D Rendering:
  GdmlAgent.get_root_node()
       ↓
  VtkWidget.build_scene()
       ↓
  VtkScene.build_from_tree()
       ↓
  VtkSolidFactory (per-node vtkActor creation)
       ↓
  vtkRenderer → QVTKRenderWindowInteractor

File Export:
  GdmlAgent.get_root_node() + _placement_overrides
       ↓
  GdmlWriter.write()
       ↓
  [.gdml file]
```

## Module Dependencies

```
main_window.py
  ├── gdml_agent.py → gdml_parser.py → gdml_tree.py → gdml_evaluator.py
  │                 → gdml_writer.py
  │                 → collision_detector.py
  │                 → materials_lib.py
  ├── vtk_widget.py → vtk_scene.py → vtk_solid_factory.py
  ├── project_tree.py
  ├── property_panel.py
  ├── interference_panel.py → collision_detector.py
  └── ribbon_toolbar.py
```
