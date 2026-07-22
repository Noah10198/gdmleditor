# 9. Known Limitations and Future Directions

## Known Limitations

### 1. Non-renderable Solid Types

~25 standard GDML solid types (e.g. polyhedra, xtru, cutTube, tet, etc.) are preserved as raw XML but cannot be rendered in the 3D view:
- Warning dialog shown on import
- Export still works — these types are written back verbatim

### 2. Boolean Operation Visualization

Boolean solids (union/subtraction/intersection) are stored as raw XML; the 3D view cannot display boolean operation results.

### 3. Unimplemented GDML Features

| Feature | Notes |
|---------|-------|
| divisionvol | Not implemented |
| replicavol | Not implemented |
| parameterised | Not implemented |
| loop | Loop expansion not implemented |
| matrix | Transformation matrix not supported |
| bordersurface/skinsurface | Optical surfaces not supported |
| isotope | Isotope definitions skipped |

### 4. Expression Evaluator

- Based on Python's `eval()`, basic arithmetic only
- No user-defined function support
- May fail on complex nested expressions

### 5. Name Uniqueness

- All `entry_id` values are derived from node names
- Duplicate names may lead to ID conflicts
- Current workaround: `{name}_{counter}` suffix append

## Future Roadmap

### Short-term

1. **Actor merging**: Same-type/same-size geometry combined into single `vtkPolyData` for dramatic draw call reduction
2. **Frustum culling**: Skip off-screen volumes per frame
3. **Multi-file transform UX**: Drag-based file transform editing

### Medium-term

1. **Instanced rendering**: Use `vtkInstancedMapper` (VTK 9.x) for batch rendering of identical shapes
2. **GDML export validation**: Verify exported files against Geant4
3. **divisionvol/replicavol support**

### Long-term

1. **Boolean visualization**: VTK implicit function based 3D preview of boolean operations
2. **loop/matrix support**: Expanded loop unrolling and matrix transforms
3. **Isotope support**: Full `<isotope>` definition handling
4. **FreeCAD extension compatibility**: Extrude, revolve, mirror, array support
