"""
VtkSolidFactory - VTK Solid Factory

Converts parsed GDML solid parameters to vtkActor. Supports:
  - box -> vtkCubeSource
  - sphere -> vtkSphereSource
  - tube -> vtkCylinderSource + vtkCylinderSource (inner/outer cylinder boolean subtract)
  - tessellated -> vtkPolyData (triangle mesh direct construction)

Following cad2gdml style, a single factory class manages all type creation.
"""

from typing import Dict, List, Tuple, Optional
import math

from vtkmodules.vtkCommonDataModel import vtkPolyData
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkFiltersSources import (
    vtkCubeSource,
    vtkSphereSource,
    vtkCylinderSource,
)
from vtkmodules.vtkFiltersModeling import vtkLinearExtrusionFilter
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPolyDataMapper,
    vtkProperty,
)
from vtkmodules.vtkFiltersGeneral import vtkBooleanOperationPolyDataFilter

from core.gdml_tree import GdmlNode, GdmlNodeType, Placement


class VtkSolidFactory:
    """
    VTK Solid Factory (Singleton)

    Responsibilities:
      - Create vtkActor based on GdmlNode type and parameters
      - Manage VTK colors, transparency and other rendering properties
      - Provide basic preset color schemes
    """

    _instance: Optional['VtkSolidFactory'] = None

    # VTK rendering precision control
    THETA_RESOLUTION: int = 48
    PHI_RESOLUTION: int = 48

    # Preset colors (R, G, B 0-1)
    _COLORS = {
        "default": (0.7, 0.7, 0.7),
        "world": (0.9, 0.9, 0.95),
        "selected": (1.0, 0.8, 0.0),
        "G4_AIR": (0.85, 0.85, 0.9),
        "G4_Al": (0.8, 0.8, 0.9),
        "G4_Cu": (0.9, 0.6, 0.4),
        "G4_Si": (0.6, 0.7, 0.8),
        "G4_WATER": (0.3, 0.5, 0.9),
        "G4_POLYETHYLENE": (0.85, 0.85, 0.7),
        "G4_Galactic": (0.95, 0.95, 1.0),
        "SSteel": (0.7, 0.7, 0.75),
        "Iron": (0.7, 0.65, 0.6),
        "Lead": (0.5, 0.5, 0.55),
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

    # ==================== Main creation interface ====================

    def create_actor(self, node: GdmlNode) -> Optional[vtkActor]:
        """
        Create VTK Actor based on node type and parameters.

        Args:
            node: GdmlNode (usually VOLUME_NODE type, must have solid_params)

        Returns:
            vtkActor object, or None if creation fails
        """
        gdml_tag = node.gdml_tag
        params = node.solid_params

        if gdml_tag == "box":
            poly_data = self._create_box(params)
        elif gdml_tag == "sphere":
            poly_data = self._create_sphere(params)
        elif gdml_tag == "tube":
            poly_data = self._create_tube(params)
        elif gdml_tag == "cone":
            poly_data = self._create_cone(params)
        elif gdml_tag == "tessellated":
            poly_data = self._create_tessellated(node)
        else:
            return None

        if poly_data is None:
            return None

        mapper = vtkPolyDataMapper()
        mapper.SetInputData(poly_data)

        actor = vtkActor()
        actor.SetMapper(mapper)

        # Set color
        color = self._get_color_for_material(node.material_name)
        actor.GetProperty().SetColor(*color)

        # ── Material properties for realistic shading ──
        prop = actor.GetProperty()
        prop.SetAmbient(0.20)
        prop.SetDiffuse(0.75)
        prop.SetSpecular(0.35)
        prop.SetSpecularPower(32)
        prop.SetInterpolationToPhong()      # smooth shading

        # World volume is semi-transparent
        if node.node_type == GdmlNodeType.WORLD_NODE:
            actor.GetProperty().SetOpacity(0.15)
            actor.GetProperty().SetRepresentationToWireframe()

        return actor

    # ==================== Per-type creation methods ====================

    def _create_box(self, params: Dict[str, float]) -> vtkPolyData:
        """Create a box solid"""
        x = params.get("x", 1.0)
        y = params.get("y", 1.0)
        z = params.get("z", 1.0)

        source = vtkCubeSource()
        source.SetXLength(x)
        source.SetYLength(y)
        source.SetZLength(z)
        source.Update()
        return source.GetOutput()

    def _create_sphere(self, params: Dict[str, float]) -> vtkPolyData:
        """Create a sphere solid"""
        rmax = params.get("rmax", 1.0)
        rmin = params.get("rmin", 0.0)
        startphi = params.get("startphi", 0.0)
        deltaphi = params.get("deltaphi", 360.0)
        starttheta = params.get("starttheta", 0.0)
        deltatheta = params.get("deltatheta", 180.0)

        # VTK vtkSphereSource only supports full spheres or longitude/latitude slices
        # For hollow spheres (rmin > 0), simplified: outer sphere only
        source = vtkSphereSource()
        source.SetRadius(rmax)
        source.SetThetaResolution(self.THETA_RESOLUTION)
        source.SetPhiResolution(self.PHI_RESOLUTION)

        # Handle angle ranges
        # VTK ThetaRange is longitude (0-360), PhiRange is latitude (0-180)
        source.SetStartTheta(startphi)
        source.SetEndTheta(startphi + deltaphi)
        source.SetStartPhi(starttheta)
        source.SetEndPhi(starttheta + deltatheta)

        source.Update()

        if rmin > 0:
            # Inner hole processing: could add vtkBooleanOperationPolyDataFilter here
            pass

        return source.GetOutput()

    def _create_tube(self, params: Dict[str, float]) -> vtkPolyData:
        """Create a tube solid (cylindrical pipe)"""
        rmin = params.get("rmin", 0.0)
        rmax = params.get("rmax", 1.0)
        z = params.get("z", 1.0)
        startphi = params.get("startphi", 0.0)
        deltaphi = params.get("deltaphi", 360.0)

        if rmin <= 0:
            # Solid cylinder
            source = vtkCylinderSource()
            source.SetRadius(rmax)
            source.SetHeight(z)
            source.SetResolution(self.THETA_RESOLUTION)
            source.Update()

            # If deltaphi < 360, clipping is needed
            # MVP: handle full cylinder for now
            return source.GetOutput()
        else:
            # Hollow tube: outer cylinder - inner cylinder
            outer = vtkCylinderSource()
            outer.SetRadius(rmax)
            outer.SetHeight(z)
            outer.SetResolution(self.THETA_RESOLUTION)
            outer.Update()

            inner = vtkCylinderSource()
            inner.SetRadius(rmin)
            inner.SetHeight(z * 1.01)  # Slightly taller to ensure complete subtraction
            inner.SetResolution(self.THETA_RESOLUTION)
            inner.Update()

            boolean_op = vtkBooleanOperationPolyDataFilter()
            boolean_op.SetOperationToDifference()
            boolean_op.SetInputData(0, outer.GetOutput())
            boolean_op.SetInputData(1, inner.GetOutput())
            boolean_op.Update()

            return boolean_op.GetOutput()

    def _create_cone(self, params: Dict[str, float]) -> vtkPolyData:
        """Create a cone solid (G4Cons)"""
        rmin1 = params.get("rmin1", 0.0)
        rmax1 = params.get("rmax1", 1.0)
        rmin2 = params.get("rmin2", 0.0)
        rmax2 = params.get("rmax2", 1.0)
        z = params.get("z", 1.0)

        # Use conical segment approximation: subdivide height, each segment is a frustum
        # Simple approach: approximate with vtkConeSource or linear transition frustum
        # MVP: if rmax1 == rmax2 and rmin1 == rmin2, treat as tube
        if abs(rmax1 - rmax2) < 0.001 and abs(rmin1 - rmin2) < 0.001:
            params_simple = {"rmin": rmin1, "rmax": rmax1, "z": z,
                             "startphi": 0, "deltaphi": 360}
            return self._create_tube(params_simple)

        # Temporarily use multi-segment cylinder approximation
        segments = 16
        from vtkmodules.vtkFiltersCore import vtkAppendPolyData
        append = vtkAppendPolyData()

        for i in range(segments):
            t0 = i / segments
            t1 = (i + 1) / segments
            r0 = rmax1 + (rmax2 - rmax1) * t0
            r1 = rmax1 + (rmax2 - rmax1) * t1
            h = z / segments
            z0 = -z / 2 + t0 * z

            if r0 > 0.001:
                seg_source = vtkCylinderSource()
                seg_source.SetRadius((r0 + r1) / 2)
                seg_source.SetHeight(h)
                seg_source.SetResolution(self.THETA_RESOLUTION // 4)
                seg_source.Update()

                # Translate each segment
                from vtkmodules.vtkCommonTransforms import vtkTransform
                from vtkmodules.vtkFiltersGeneral import vtkTransformPolyDataFilter
                transform = vtkTransform()
                transform.Translate(0, 0, z0)
                tfilter = vtkTransformPolyDataFilter()
                tfilter.SetInputData(seg_source.GetOutput())
                tfilter.SetTransform(transform)
                tfilter.Update()
                append.AddInputData(tfilter.GetOutput())

        append.Update()
        return append.GetOutput()

    def _create_tessellated(self, node: GdmlNode) -> vtkPolyData:
        """Create a tessellated solid"""
        # Extract triangle mesh info from node attributes
        # Note: tessellated vertices reference positions defined in <define> section
        # We need to look up from parsed positions
        # Simplified: extract triangle data from gdml_attrs

        points = vtkPoints()
        poly_data = vtkPolyData()

        # Build vertex list and triangles
        # Get positions from <define>
        # This requires access to parser's _positions via GdmlAgent
        all_positions: Dict[str, Tuple[float, float, float]] = {}
        # This will be passed in from external during actual use, empty for now

        triangles_str = node.gdml_attrs.get("_triangles", "[]")
        quadrangles_str = node.gdml_attrs.get("_quadrangles", "[]")

        # Simplified: MVP extracts vertices from gdml_attrs
        # Should use _positions dict lookup in production
        # Returns empty polydata, VtkScene will build with full context
        return poly_data

    def _get_color_for_material(self, material_name: str) -> Tuple[float, float, float]:
        """Get color by material name"""
        if not material_name:
            return self._COLORS["default"]

        # Exact match
        if material_name in self._COLORS:
            return self._COLORS[material_name]

        # Prefix match (e.g. G4_AIR, G4_Al ...)
        for key, color in self._COLORS.items():
            if material_name.startswith(key) or key.startswith(material_name):
                return color

        # Generate stable color from name hash
        import hashlib
        h = hashlib.md5(material_name.encode()).hexdigest()
        r = (int(h[0:2], 16) % 156 + 100) / 255.0
        g = (int(h[2:4], 16) % 156 + 100) / 255.0
        b = (int(h[4:6], 16) % 156 + 100) / 255.0
        return (r, g, b)
