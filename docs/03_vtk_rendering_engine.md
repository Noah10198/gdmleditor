# 3. VTK Rendering Engine

## Component Structure

The rendering engine consists of two main components:

### vtk_scene.py — Scene Manager

`VtkScene` handles:

- **Scene construction**: `build_from_tree(root_node)` — recursively walks the `GdmlNode` tree
- **Node selection/highlight**: `select_node(entry_id)` / `highlight_volumes(entry_ids)`
- **Visibility control**: `set_visibility(entry_id, visible)`
- **World transform**: `get_world_polydata(node)` — computes world-space position for a node
- **Picking callback**: `pick_handler` signal bridge

### vtk_solid_factory.py — Geometry Factory

`VtkSolidFactory` creates the appropriate `vtkActor` for each solid type:

| GDML Type | VTK Implementation |
|-----------|--------------------|
| box | `vtkCubeSource` |
| sphere | `vtkSphereSource` + rmin/rmax/angle parameters |
| orb | `vtkSphereSource` (full sphere) |
| tube / tubs | `vtkCylinderSource` + phi-segment rotation |
| cone | `vtkConeSource` (top/bottom radius) |
| tessellated | `vtkPolyData` built from triangle/quad vertex data |
| torus | `vtkParametricTorus` + `vtkParametricFunctionSource` |
| ellipsoid | Unit sphere with non-uniform scaling |
| polycone | Stacked cylindrical sections via `vtkAppendPolyData` |

## Rendering Pipeline

```
GdmlNode tree
    ↓
VtkScene.build_from_tree()
    ├── Compute world transform path
    ├── VtkSolidFactory.create_actor(node) → vtkActor
    │   ├── Create vtkPolyData (type-specific)
    │   ├── Create vtkPolyDataMapper
    │   └── Create vtkActor
    ├── Apply transform (vtkTransform: Translate + RotateZXY)
    ├── Set color (material-based or random fallback)
    └── vtkRenderer.AddActor(vtkActor)
    ↓
QVTKRenderWindowInteractor.Render()
```

## Selection and Highlighting

1. **Renderer picking**: VTK's `vtkPropPicker` via `Pick()` method
2. **Entry ID mapping**: Each actor stores `entry_id` metadata via `SetPropertyKeys()`
3. **Highlight style**: Modified edge color + width on selected actor

## Clipping Plane

- Uses `vtkPlane` + `vtkMapper.AddClippingPlane()`
- X/Y/Z axis selection with slider position control
- Reset via `RemoveAllClippingPlanes()`

## CubeAxes Coordinates

- `vtkCubeAxesActor` for dimension labels
- RGB axis coloring: X→red, Y→green, Z→blue
- Auto-updates bounds to follow scene content
- Large font + shadow for readability
