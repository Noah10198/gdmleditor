"""
VtkScene - VTK 3D Scene Manager

Responsibilities:
  - Manage vtkRenderer / vtkRenderWindow
  - Expand GdmlNode tree into vtkActor and add to scene
  - Support mouse picking (selection highlight)
  - Support actor show/hide
  - Support placement updates (move/rotate)

Based on cad2gdml's occ_widget.py design style.
"""

from typing import Dict, Optional, List, Tuple, Callable
import math

from vtkmodules.vtkRenderingCore import (
    vtkRenderer,
    vtkRenderWindow,
    vtkRenderWindowInteractor,
    vtkActor,
    vtkActorCollection,
    vtkPolyDataMapper,
    vtkLight,
    vtkCamera,
)
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
from vtkmodules.vtkCommonCore import vtkCommand
from vtkmodules.vtkCommonTransforms import vtkTransform
from vtkmodules.vtkFiltersGeneral import vtkTransformPolyDataFilter
from vtkmodules.vtkRenderingCore import vtkCellPicker

from core.gdml_tree import GdmlNode, GdmlNodeType, Placement
from vtk_engine.vtk_solid_factory import VtkSolidFactory


class VtkScene:
    """
    VTK 3D Scene Manager

    Manages all VTK render object states, provides node-to-actor mapping.
    """

    def __init__(self):
        self._renderer = vtkRenderer()
        self._render_window: Optional[vtkRenderWindow] = None
        self._interactor: Optional[vtkRenderWindowInteractor] = None

        self._solid_factory = VtkSolidFactory()

        # entry_id -> vtkActor mapping
        self._actor_map: Dict[str, vtkActor] = {}

        # Selected entry_id
        self._selected_id: Optional[str] = None
        self._selected_actor: Optional[vtkActor] = None

        # Picking
        self._pick_handler: Optional[Callable[[str], None]] = None
        self._picker = vtkCellPicker()

        # Set gradient background
        self._renderer.SetBackground(0.12, 0.12, 0.15)
        self._renderer.SetBackground2(0.25, 0.25, 0.30)
        self._renderer.GradientBackgroundOn()

        # ── Lighting: 3-point setup for depth and shine ──
        # Remove any default lights
        self._renderer.RemoveAllLights()

        # 1) Headlight (camera key light) — main illumination
        key = vtkLight()
        key.SetLightTypeToHeadlight()
        key.SetIntensity(0.85)
        key.SetColor(1.0, 1.0, 0.95)  # slightly warm
        self._renderer.AddLight(key)

        # 2) Fill light — from the right, softer
        fill = vtkLight()
        fill.SetLightTypeToSceneLight()
        fill.SetPosition(100, 50, -50)
        fill.SetFocalPoint(0, 0, 0)
        fill.SetIntensity(0.40)
        fill.SetColor(0.90, 0.90, 1.0)  # slightly cool
        self._renderer.AddLight(fill)

        # 3) Back / rim light — from behind left, subtle
        rim = vtkLight()
        rim.SetLightTypeToSceneLight()
        rim.SetPosition(-80, 60, 80)
        rim.SetFocalPoint(0, 0, 0)
        rim.SetIntensity(0.25)
        rim.SetColor(0.85, 0.85, 1.0)
        self._renderer.AddLight(rim)

        # Two-sided lighting (see inside transparent/clipped surfaces)
        self._renderer.SetTwoSidedLighting(True)

    def set_render_window(self, render_window: vtkRenderWindow):
        """Set render window"""
        self._render_window = render_window
        self._render_window.AddRenderer(self._renderer)

    def set_interactor(self, interactor: vtkRenderWindowInteractor):
        """Set interactor and wire up picking observer."""
        self._interactor = interactor
        style = vtkInteractorStyleTrackballCamera()
        self._interactor.SetInteractorStyle(style)
        # Observer for picking on left click
        self._interactor.AddObserver(
            vtkCommand.LeftButtonPressEvent, self._on_left_click
        )

    # ==================== Node management ====================

    def add_node(self, node: GdmlNode) -> Optional[vtkActor]:
        """
        Add a single node to the scene.

        Only creates actor for VOLUME_NODE / WORLD_NODE (with solid_params).

        Args:
            node: GdmlNode

        Returns:
            Created vtkActor, or None
        """
        if node.node_type not in (GdmlNodeType.VOLUME_NODE,
                                   GdmlNodeType.WORLD_NODE):
            return None

        if not node.solid_params:
            return None

        actor = self._solid_factory.create_actor(node)
        if actor is None:
            return None

        # Compute and apply placement
        self._apply_node_placement(actor, node)

        self._actor_map[node.entry_id] = actor
        self._renderer.AddActor(actor)
        return actor

    def remove_node(self, entry_id: str) -> bool:
        """Remove node from scene"""
        actor = self._actor_map.pop(entry_id, None)
        if actor:
            self._renderer.RemoveActor(actor)
            return True
        return False

    def set_visibility(self, entry_id: str, visible: bool):
        """Set node visibility"""
        actor = self._actor_map.get(entry_id)
        if actor:
            actor.SetVisibility(visible)

    def clear(self):
        """Clear scene"""
        self._actor_map.clear()
        self._renderer.RemoveAllViewProps()
        self._selected_id = None
        self._selected_actor = None

    # ==================== Selection & Highlight ====================

    def select_node(self, entry_id: str):
        """Select node (highlight)"""
        if self._selected_actor:
            self._selected_actor.GetProperty().SetEdgeVisibility(False)

        self._selected_id = entry_id
        self._selected_actor = self._actor_map.get(entry_id)

        if self._selected_actor:
            self._selected_actor.GetProperty().SetEdgeColor(1.0, 0.8, 0.0)
            self._selected_actor.GetProperty().SetEdgeVisibility(True)
            self._selected_actor.GetProperty().SetLineWidth(3.0)

    def deselect_all(self):
        """Deselect all nodes"""
        if self._selected_actor:
            self._selected_actor.GetProperty().SetEdgeVisibility(False)
        self._selected_id = None
        self._selected_actor = None

    def get_selected_id(self) -> Optional[str]:
        return self._selected_id

    # ==================== Placement operations ====================

    def move_node(self, entry_id: str, dx: float, dy: float, dz: float):
        """Move node (relative displacement)"""
        actor = self._actor_map.get(entry_id)
        if actor is None:
            return
        actor.AddPosition(dx, dy, dz)

    def set_node_position(self, entry_id: str, x: float, y: float, z: float):
        """Set node absolute position"""
        actor = self._actor_map.get(entry_id)
        if actor is None:
            return
        actor.SetPosition(x, y, z)

    def rotate_node(self, entry_id: str, rx: float, ry: float, rz: float):
        """Rotate node (degrees)"""
        actor = self._actor_map.get(entry_id)
        if actor is None:
            return
        actor.SetOrientation(rx, ry, rz)

    def _apply_node_placement(self, actor: vtkActor, node: GdmlNode):
        """
        Collect all placement info from the node's parent chain.
        Accumulates placement from each PHYVOL_NODE encountered.
        """
        tx, ty, tz = 0.0, 0.0, 0.0
        rx, ry, rz = 0.0, 0.0, 0.0

        current = node.parent
        while current is not None:
            if current.node_type == GdmlNodeType.PHYVOL_NODE and current.placement:
                p = current.placement
                tx += p.x
                ty += p.y
                tz += p.z
                rx += p.rot_x
                ry += p.rot_y
                rz += p.rot_z
            current = current.parent

        actor.SetPosition(tx, ty, tz)
        # VTK's SetOrientation uses ZYX Euler angles
        if abs(rx) > 0.001 or abs(ry) > 0.001 or abs(rz) > 0.001:
            actor.SetOrientation(rx, ry, rz)

    def update_placement(self, node: GdmlNode):
        """Update node placement"""
        actor = self._actor_map.get(node.entry_id)
        if actor is None:
            return
        self._apply_node_placement(actor, node)

    # ==================== Picking ====================

    @property
    def pick_handler(self) -> Optional[Callable[[str], None]]:
        """Callback invoked when a node is picked (called with entry_id)."""
        return self._pick_handler

    @pick_handler.setter
    def pick_handler(self, handler: Optional[Callable[[str], None]]):
        self._pick_handler = handler

    def _on_left_click(self, obj, event):
        """Handle left click: pick actor and call pick_handler."""
        if not self._interactor or not self._pick_handler:
            return
        click_pos = self._interactor.GetEventPosition()
        self._picker.Pick(click_pos[0], click_pos[1], 0, self._renderer)
        actor = self._picker.GetActor()
        if actor:
            entry_id = self._find_entry_id_by_actor(actor)
            if entry_id:
                self._pick_handler(entry_id)

    def _find_entry_id_by_actor(self, actor: vtkActor) -> Optional[str]:
        """Reverse lookup: actor -> entry_id."""
        for eid, a in self._actor_map.items():
            if a == actor:
                return eid
        return None

    # ==================== View control ====================

    def reset_camera(self):
        """Reset camera to a position that views all objects"""
        self._renderer.ResetCamera()
        # Pull camera back slightly
        cam = self._renderer.GetActiveCamera()
        cam.Dolly(1.2)
        self._renderer.ResetCameraClippingRange()

    def set_background_color(self, r: float, g: float, b: float):
        """Set scene background color (single color, no gradient)"""
        self._renderer.SetBackground(r, g, b)
        self._renderer.GradientBackgroundOff()

    def render(self):
        """Refresh rendering"""
        if self._render_window:
            self._render_window.Render()

    # ==================== Scene building ====================

    def build_from_tree(self, root_node: GdmlNode):
        """
        Recursively build scene from GdmlNode tree.
        Traverses all VOLUME_NODE / WORLD_NODE and creates actors.

        Args:
            root_node: Root node
        """
        self.clear()

        if not root_node.children:
            return

        # Traverse file nodes
        for file_node in root_node.children:
            if file_node.node_type != GdmlNodeType.GDML_FILE:
                continue
            self._build_node_recursive(file_node)

        self.reset_camera()
        self.render()

    def _build_node_recursive(self, node: GdmlNode):
        """
        Recursively build scene nodes.

        Creates actor for VOLUME_NODE / WORLD_NODE with solid_params.
        GROUP nodes (like PHYVOL) have no special treatment -- children are recursed.
        """
        if (node.node_type in (GdmlNodeType.VOLUME_NODE, GdmlNodeType.WORLD_NODE)
                and node.solid_params):
            self.add_node(node)

        for child in node.children:
            self._build_node_recursive(child)

    def get_actor_for_node(self, entry_id: str) -> Optional[vtkActor]:
        """Get actor for a given node"""
        return self._actor_map.get(entry_id)

    @property
    def renderer(self) -> vtkRenderer:
        return self._renderer
