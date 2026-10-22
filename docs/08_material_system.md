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

## Material Data Flow

```
AssignMaterialDialog
    ↓
MainWindow → GdmlAgent.set_material_override(entry_id, material_name)
    ↓
GdmlAgent._material_overrides (overlay, entry_id → material name)
    ↓
GdmlWriter.write() → write <materialref> tags
```

> **Note**: 3D colors are *not* driven by the material. Each actor gets a stable color
> derived from the node's `entry_id` / `name` (curated palette, md5-based index), so the
> color identifies a volume, not its material.

## Export Strategy

- Preserves original `<materials>` XML verbatim
- User-defined local materials appended to the exported file's materials section
- Automatically skips duplicate material names
