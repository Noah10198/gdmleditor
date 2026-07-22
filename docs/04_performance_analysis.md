# 4. Performance Analysis

## Problem

When loading a GDML file with a very large number of physical volumes (e.g. `g4e_output.geo.gdml`: 4.5 MB, 102k lines, ~20k physvols), the 3D scene becomes sluggish during interaction (rotate/pan/zoom).

## Root Cause

### Bottleneck: CPU draw call submission, NOT GPU rendering power

```
20,000 boxes, 24 triangles each
   → Total triangles: 480,000
   → Actor count: 20,000
   → Draw calls: 20,000/frame
   → ❌ Stutter

1 teapot, 50,000 triangles
   → Actor count: 1
   → Draw call: 1/frame
   → ✅ Smooth
```

### Key Numbers

| Item | Count | Cost |
|------|-------|------|
| Actor count | 20,000 | Per-frame traversal + state switching |
| Draw calls | 20,000/frame | Shader bind, transform upload, buffer switch |
| Python→C++ boundary crossing | ~10/actor | ~200,000 total calls |
| QTreeWidgetItem | 20,000+ | Qt tree insertion + layout |
| GPU utilization | 2~5% | Mostly idle, waiting for CPU |
| CPU (render core) | Near 100% | Limited to ~50% with VSync |

### Why CPU Doesn't Show 100% in Task Manager

1. **VSync limit**: At 60 Hz, each frame has 16.6 ms. CPU may finish in 8 ms and idle the rest
2. **Single-core bottleneck**: VTK actor traversal is single-threaded; Task Manager shows all-core average
3. **No idle Render**: VTK does not continuously render a static scene

```
State           GPU load     CPU total     Rendering core
No interaction  ~0%         Very low       Low (no Render triggered)
Dragging/rot.   ~5%         10~20%         Near 100%
File loading    ~0%         ~20%           Background thread
```

## Solution Directions

### Short-term (implemented)
- ✅ Background thread loading (UI doesn't freeze)

### Medium-term
- **Actor merging**: Same-type, same-size geometry merged into a single `vtkPolyData` with one actor
- **Frustum culling**: Only render volumes within the view frustum

### Long-term
- **Instanced rendering**: Upload geometry once, pass 20k transform matrices as instance data. Reduces 20k draw calls to single digits

## Expected Performance Comparison

| Approach | Draw calls | Interactive FPS (est.) | Complexity |
|----------|:----------:|:----------------------:|:----------:|
| Current (independent actors) | 20,000 | ~5-10 | — |
| Actor merging | ~10-50 | ~30-60 | Moderate |
| Instanced rendering | ~10-20 | ~60 | High |

## Key Takeaways

1. **Component count** is the primary bottleneck, not polygon count
2. GPU idling means the CPU is the bottleneck
3. Reducing draw calls is more effective than reducing triangles
