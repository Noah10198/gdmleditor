# GDML Parser / Writer Capabilities

> Based on analysis against Geant4 official examples under `Ref/gdmlexample/` and `Ref/GDML-Main/SampleFiles/`.
> Current as of 2026-07-22.

---

## Legend

| Icon | Meaning |
|---|---|
| ✅ Full | Fully supported (parse, export, visualize) |
| ✅ Raw XML | Round-trip preserved via raw XML (sub-elements intact, can't visualize) |
| ⚠️ Partial | Partially supported |
| ❌ | Not supported |

---

## 1. Solid Types

| Solid | Parse | Export | Visualize | Notes |
|---|---|---|---|---|
| **box** | ✅ Full | ✅ Full | ✅ | |
| **tube** | ✅ Full | ✅ Full | ✅ | |
| **tubs** (tube with φ-cut) | ✅ Full | ✅ Full | ✅ | Mapped to tube parser (rmin/rmax/z/startphi/deltaphi) |
| **cone** | ✅ Full | ✅ Full | ✅ | |
| **sphere** | ✅ Full | ✅ Full | ✅ | |
| **tessellated** | ✅ Full | ✅ Full | ✅ | Triangular and quadrangular facets |
| **orb** | ✅ Full | ✅ Full | ✅ | Mapped to sphere (single radius `r`) |
| **torus** | ✅ Full | ✅ Full | ✅ | vtkParametricTorus; hollow (rmin>0) diff subtraction |
| **ellipsoid** | ✅ Full | ✅ Full | ✅ | Unit sphere + non-uniform scale (ax, by, cz) |
| **polycone** / **genericPolycone** | ✅ Parse | ✅ Raw XML | ✅ | zplane sections stored for VTK; raw XML for export |
| **polyhedra** | ✅ Raw XML | ✅ Raw XML | ❌ | Sub-elements preserved |
| **xtru** (extruded) | ✅ Raw XML | ✅ Raw XML | ❌ | Sub-elements preserved |
| **cutTube** | ✅ Raw XML | ✅ Raw XML | ❌ | |
| **ellipticalTube** | ✅ Raw XML | ✅ Raw XML | ❌ | |
| **ellipticalCone** | ✅ Raw XML | ✅ Raw XML | ❌ | |
| **paraboloid** | ✅ Raw XML | ✅ Raw XML | ❌ | |
| **hype** (hyperboloid) | ✅ Raw XML | ✅ Raw XML | ❌ | |
| **twistedbox** | ✅ Raw XML | ✅ Raw XML | ❌ | |
| **twistedtrap** | ✅ Raw XML | ✅ Raw XML | ❌ | |
| **twistedtrd** | ✅ Raw XML | ✅ Raw XML | ❌ | |
| **twistedtubs** | ✅ Raw XML | ✅ Raw XML | ❌ | |
| **genericTrap** | ✅ Raw XML | ✅ Raw XML | ❌ | |
| **tet** (tetrahedron) | ✅ Raw XML | ✅ Raw XML | ❌ | |
| **arb8** | ✅ Raw XML | ✅ Raw XML | ❌ | |
| **extrudedPolygon** | ✅ Raw XML | ✅ Raw XML | ❌ | |
| **trap** (trapezoid) | ✅ Raw XML | ✅ Raw XML | ❌ | |
| **trd** | ✅ Raw XML | ✅ Raw XML | ❌ | |
| **para** (parallelepiped) | ✅ Raw XML | ✅ Raw XML | ❌ | |

---

## 2. Boolean Operations

| Operation | Parse | Export | Visualize | Notes |
|---|---|---|---|---|
| **union** | ✅ Raw XML | ✅ Raw XML | ❌ | first/second/position/rotation preserved |
| **subtraction** | ✅ Raw XML | ✅ Raw XML | ❌ | |
| **intersection** | ✅ Raw XML | ✅ Raw XML | ❌ | |

---

## 3. Special Solids

| Structure | Parse | Export | Visualize | Notes |
|---|---|---|---|---|
| **multiUnion** | ✅ Raw XML | ✅ Raw XML | ❌ | multiUnionNode sub-elements preserved |
| **scaledSolid** | ✅ Raw XML | ✅ Raw XML | ❌ | solidref + scale ref preserved |
| **scale** (transform) | ✅ Raw XML | ✅ Raw XML | ❌ | Stored in `<define>` |

---

## 4. Structural Elements

| Structure | Parse | Export | Visualize | Notes |
|---|---|---|---|---|
| **volume** | ✅ Full | ✅ Full | ✅ | |
| **physvol + volumeref** | ✅ Full | ✅ Full | ✅ | |
| **physvol + position/rotation** | ✅ Full | ✅ Full | ✅ | Inline position/rotation |
| **positionref / rotationref** | ✅ Full | ✅ Full | ✅ | Referenced from `<define>` |
| **assembly** | ✅ Full | ✅ Full | ✅ | Stored in `self._assemblies` dict; physvol can reference assembly; exported as `<assembly>` tag |
| **divisionvol** | ❌ | ❌ | ❌ | |
| **replicavol** | ❌ | ❌ | ❌ | |
| **parameterised** | ❌ | ❌ | ❌ | Contains `<ParamVol>` |

---

## 5. Special Elements

| Element | Parse | Export | Notes |
|---|---|---|---|
| **auxiliary** | ✅ Attribute level | ❌ Not exported | Stored on volume's `gdml_attrs` |
| **loop** | ❌ Not processed | ❌ | Expands repeated placements |
| **matrix** | ❌ Not processed | ❌ | Transformation matrices |
| **bordersurface** | ❌ | ❌ | Optical surface between volumes |
| **skinsurface** | ❌ | ❌ | Optical surface on volume skin |

---

## 6. Materials

| Structure | Parse | Export | Notes |
|---|---|---|---|
| **element + atom** | ✅ Full | ✅ Full | Now writes `unit="g/mole"` and `type="A"` |
| **isotope + atom** | ❌ Skipped | ❌ Not exported | Found in `temp.gdml` (cad2gdml output) |
| **element + fraction (isotope)** | ❌ Skipped | ❌ Not exported | Composite natural elements from isotopes |
| **material + D + composite** | ✅ Full | ✅ Full | Compounds (by atom count) |
| **material + D + fraction** | ✅ Full | ✅ Full | Mixtures (by mass fraction) |
| **material + T / MEE** (temp/excitation energy) | ❌ Skipped | ✅ Raw XML preserved | Cad2gdml-pattern: `T`, `MEE`, etc. |
| **Dref** | ❌ | ❌ | Density reference instead of inline `<D>` |

**Key design:** Export preserves original raw `<materials>` XML verbatim, then appends any user-defined local materials (custom elements, compounds, mixtures) that don't already have a matching `name`.

---

## Summary

### Fully functional (parse + export + visualize):
- **9 solid types:** box, sphere, orb, tube, tubs, cone, torus, ellipsoid, tessellated
- polycone: VTK approximate (stacked cylindrical sections)
- **Unsupported type detection:** importing solids outside the supported set triggers a `QMessageBox` warning with a detailed list. See `GdmlAgent.get_unsupported_solids()`.
- Standard volume-physvol chain with positionref/rotationref
- **Assembly** — full round-trip with physvol references
- Standard materials (element + atom, material + composite/fraction + D)

### Round-trip preserved (parse + export, no visualization):
- **All ~25 other standard GDML solid types** via raw XML storage
- Booleans, multiUnion, scaledSolid
- No data loss on save

### Not yet implemented:
- divisionvol, replicavol, parameterised
- loop, matrix
- Optical surfaces (bordersurface, skinsurface)
- Isotope definitions
- FreeCAD Non-GDML extensions (extrude, revolve, mirror, array)
