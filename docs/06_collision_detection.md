# 6. Collision / Interference Detection

## Overview

Fast AABB (Axis-Aligned Bounding Box) based interference detection. Pure computation module with no Qt dependency. Supports interactive range selection and result browsing via the UI panel.

## Core Algorithms

### compute_half_size(node) → (hx, hy, hz)

Conservative half-size computation per solid type:

- **box**: Directly from x/y/z parameters
- **sphere/orb**: rmax for all three axes
- **tube**: rmax (radial) × z/2 (axial)
- **cone**: Max of rmax1, rmax2
- **polycone**: Scan all zplanes for max radius
- **tessellated**: Scan all vertices for bounding extent
- **Others**: First three numeric values from solid_params

### compute_world_aabb(node) → (xmin, xmax, ymin, ymax, zmin, zmax)

1. Walk up the parent chain, accumulating physvol transforms
2. Supports `override_provider` callback (for user-edited placement overrides)
3. Without rotation: directly translate the 8 corners
4. With rotation: use `vtkTransform` matching actor orientation
5. Transform order: `Translate → RotateZ → RotateX → RotateY` (same as VtkScene)

### aabb_overlap(aabb1, aabb2) → (ox, oy, oz) or None

Returns the overlap extents if the two AABBs intersect on all three axes, or `None` if they are separated on any axis.

## Detection Modes

### Full Pair Generation (generate_full_pairs)

Generates all unique (i, j) pairs with i < j. O(n²) complexity.

### Sampled Pair Generation (generate_sampled_pairs)

- Randomly samples up to 5% of total pairs (min 2, max 50)
- In multi-file scenarios, guarantees at least one cross-file pair
- Falls back to full mode when total pairs ≤ sample count

## UI Interaction (InterferencePanel)

1. **Select scope**: Choose volumes in the interference panel tree
2. **Run detection**: Click "Run" — `_CollisionWorker` computes in a background thread
3. **View results**:
   - Table of interfering pairs with (ox, oy, oz) overlap dimensions
4. **Highlight**: Click a result row to highlight the colliding volumes in the 3D scene

## Comparison with cad2gdml

| Feature | gdmleditor | cad2gdml |
|---------|-----------|---------|
| Algorithm | AABB overlap | vtkImplicitPolyDataDistance / vtkClipPolyData / vtkIntersectionPolyDataFilter |
| Precision | Conservative (bounding box) | Exact (mesh-level) |
| Speed | Fast (simple O(n²) math) | Slow (heavy O(n²) mesh ops) |
| Distance info | Overlap depth (ox, oy, oz) | Exact min distance / intersection region |
| Heatmap | No | Yes (blue=near → red=far) |
| Use case | Quick filtering of candidates | Exact collision determination |

> Detailed comparison: `cad2gdml/doc/need-check-update.md`
