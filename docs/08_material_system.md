# 8. Material System

## Overview

gdmleditor's material system supports NIST standard materials and user-defined custom materials (elements, compounds, mixtures), with batch material assignment and export.

## Material Sources

### 1. NIST Standard Materials

Loaded from `data/nist.txt`, containing Geant4 NIST material database entries:
- Predefined material names and densities
- Read-only, not editable

### 2. Chemical Elements

Loaded from `data/element.xml`, containing atomic number, symbol, atomic mass, etc. for all elements.

### 3. User-defined Local Materials

Three types:

| Type | Description | Key Attributes |
|------|-------------|----------------|
| **CustomElement** | Custom element | symbol, Z, A |
| **CustomCompound** | Compound (by atom count) | Component list + atom count |
| **CustomMixture** | Mixture (by mass fraction) | Component list + mass fraction |

Local materials are persisted as JSON files and can be exported/imported.

## Material Assignment

Through `AssignMaterialDialog`:

1. Select target volumes (single/multi/select-all)
2. Choose material from library
3. Apply assignment
4. 3D scene colors update automatically based on material

## Material Data Flow

```
AssignMaterialDialog
    ↓
MainWindow → GdmlAgent.set_material(volume_node, material_name)
    ↓
GdmlNode.material_name (overlay)
    ↓
VtkScene.build_from_tree() → assign colors by material
    ↓
GdmlWriter.write() → write <materialref> tags
```

## Export Strategy

- Preserves original `<materials>` XML verbatim
- User-defined local materials appended to the exported file's materials section
- Automatically skips duplicate material names
