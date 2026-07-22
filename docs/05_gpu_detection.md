# 5. GPU Detection and Fallback

## Overview

On startup, the application auto-detects the GPU driver state. If no GPU driver is available, it gracefully falls back to off-screen software rendering. Output format matches OCC (OpenCASCADE) style for consistency with cad2gdml's `Viewer3d` log output.

## Implementation

`gdmleditor/ui/vtk_widget.py` → `VtkWidget.__init__()` → lines 99-160

## Detection Flow

```
                   Startup
                      |
                      ▼
            SetOffScreenRendering(False)
                      |
                      ▼
                  Render()
                      |
                      ▼
          ReportCapabilities()
                      |
                      ▼
            ┌─ Parse OpenGL info ─┐
            │ vendor / device     │
            │ version / GLSL      │
            │ pixel format        │
            └─────────────────────┘
              Success?      Fail?
                 |            |
                 ▼            ▼
              GPU active  Fallback to off-screen
              (HW accel)      |
                              ▼
                    Try software/Mesa
                              |
                    Success?      Fail?
                       |            |
                       ▼            ▼
                Software render  Render unavailable
                (usable)        (degraded)
```

## Sample Output

Normal GPU mode:
```
#########################################
OpenGl information (VTK):
  GLvendor:  NVIDIA Corporation
  GLdevice:  NVIDIA GeForce GTX 960/PCIe/SSE2
  GLversion: 4.6.0 NVIDIA 390.77
  GLSL:      4.60 NVIDIA
  depth: 32  stencil: 8  double buffer: 1
#########################################
```

Software fallback mode:
```
#########################################
OpenGl information (VTK, off-screen/software):
  GLvendor:  Mesa/X.org
  GLdevice:  llvmpipe (LLVM 10.0, 128 bits)
#########################################
```

## Regex Parsing

```python
import re as _re
_s = _re.search
m_vdr = _s(r"OpenGL vendor string:\s*(.+)", raw_caps)
m_dev = _s(r"OpenGL renderer string:\s*(.+)", raw_caps)
m_ver = _s(r"OpenGL version string:\s*(.+)", raw_caps)
m_glsl = _s(r"GLSL version \(if available\):\s*(.+)", raw_caps)
```

## Design Considerations

1. **Graceful degradation**: No crash when GPU driver is missing; automatically falls back to software rendering
2. **Transparent diagnostics**: GPU info visible to the user for debugging
3. **Compatibility**: Works under remote desktop, headless servers, VMs, and basic display adapters
