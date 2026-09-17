"""
RedefineWorldDialog - Dialog for redefining world volume size

Based on cad2gdml's ExportGdmlDialog design: an embedded 3D preview on the
left, controls on the right.  Changing the factor re-sizes the world
wireframe box in the preview *live* (no scene rebuild - only the world box
actor is re-sized), so the user sees the effect before applying.

Layout:
  Left:    Embedded VTK preview (geometry + world wireframe box)
  Right:   Current bounding box info / factor selection / computed size
           Apply / Cancel / Fit View
"""

from typing import List, Optional, Tuple

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QWidget, QFrame,
)
from PyQt6.QtCore import Qt, QTimer

from core.gdml_tree import GdmlNode
from vtk_engine import WORLD_BOX_COLOR


class RedefineWorldDialog(QDialog):
    """Redefine World Volume Dialog (with live 3D preview)."""

    # ×1 = tight fit (the box then exactly encloses the geometry extent)
    FACTORS = [1, 3, 5, 10, 100]
    DEFAULT_FACTOR = 5

    def __init__(
        self,
        bbox: Tuple[float, float, float, float, float, float],
        current_world_size: float = 0.0,
        root_node: Optional[GdmlNode] = None,
        parent=None,
        world_count: int = 1,
        current_world_sizes: Optional[List[float]] = None,
        dark_theme: bool = True,
        override_provider=None,
    ):
        """
        Args:
            bbox: (xmin, xmax, ymin, ymax, zmin, zmax) — all geometry in WORLD space
            current_world_size: Current world volume size (edge length), 0 = unknown
            root_node: GdmlNode tree root; when given, a live 3D preview of the
                geometry + world box is shown on the left.
            parent: Parent widget
            override_provider: callable(entry_id) -> Optional[Placement], the
                same one the main view uses so the preview geometry matches it.
                Without it the preview would draw every physvol at its original
                GDML placement and ignore transform edits (the bbox passed in
                here comes from the main scene, which DOES include them, so the
                two would disagree).
            world_count: Number of WORLD_NODEs that will be resized (>1 = the
                multi-file mode, where every file's world is set to one size).
            current_world_sizes: Current world sizes, one per WORLD_NODE. Used
                to warn when the files currently disagree.
            dark_theme: True when the app is in dark mode. The preview viewport
                then follows the theme (deep navy / mid grey), one step away
                from the main viewer's colours.
        """
        super().__init__(parent)
        self.setWindowTitle("Redefine World Volume")
        self.setMinimumSize(880, 520)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self._bbox = bbox
        self._current_world_size = current_world_size
        self._selected_factor: int = self.DEFAULT_FACTOR
        self._root_node = root_node
        self._override_provider = override_provider
        self._world_count = max(int(world_count), 1)
        if current_world_sizes:
            # One entry per world node, de-duplicated and sorted
            self._world_sizes = sorted({round(float(s), 6)
                                        for s in current_world_sizes})
        elif current_world_size > 0:
            self._world_sizes = [float(current_world_size)]
        else:
            self._world_sizes = []

        # Live preview state (created lazily on first show)
        self._dark_theme = bool(dark_theme)
        self._preview = None
        self._box_source = None
        self._world_box_actor = None
        self._world_center: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._preview_started = False

        # Compute scene extent AND max distance from origin
        xmin, xmax, ymin, ymax, zmin, zmax = bbox
        self._scene_extent = max(
            xmax - xmin, ymax - ymin, zmax - zmin, 1.0
        )
        # Furthest point from origin in any axis — needed when geometry
        # has been translated away from (0,0,0)
        self._max_radius = max(
            abs(xmin), abs(xmax),
            abs(ymin), abs(ymax),
            abs(zmin), abs(zmax),
            1.0
        )

        self._build_ui()
        self._update_size_label()

    # ---- UI construction ----

    def _build_ui(self):
        root_layout = QHBoxLayout(self)
        root_layout.setSpacing(12)
        root_layout.setContentsMargins(12, 12, 12, 12)

        # ── Left: live 3D preview ──
        self._preview_host: Optional[QWidget] = None
        self._preview_layout: Optional[QVBoxLayout] = None
        self._preview_ph: Optional[QLabel] = None

        if self._root_node is not None:
            left = QVBoxLayout()
            left.setSpacing(4)

            cap = QLabel("World Volume Preview")
            cap.setStyleSheet("font-weight: bold; font-size: 13px;")
            left.addWidget(cap)

            self._preview_host = QWidget()
            self._preview_host.setMinimumSize(420, 400)
            self._preview_layout = QVBoxLayout(self._preview_host)
            self._preview_layout.setContentsMargins(0, 0, 0, 0)
            self._preview_ph = QLabel("Building preview…")
            self._preview_ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._preview_layout.addWidget(self._preview_ph)
            left.addWidget(self._preview_host, 1)

            hint = QLabel(
                "Yellow wireframe = world volume   ·   "
                "left-drag rotate · wheel zoom"
            )
            hint.setStyleSheet("color: #a6adc8; font-size: 11px;")
            left.addWidget(hint)

            root_layout.addLayout(left, 3)

        # ── Right: controls ──
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # Current scene bounding box info
        xmin, xmax, ymin, ymax, zmin, zmax = self._bbox
        has_scene = not (xmin == xmax == ymin == ymax == zmin == zmax == 0)
        if has_scene:
            sx = xmax - xmin
            sy = ymax - ymin
            sz = zmax - zmin
            bbox_info = (
                f"Scene bounding box:  {sx:.1f} × {sy:.1f} × {sz:.1f} mm\n"
                f"Range X: [{xmin:.1f}, {xmax:.1f}]    "
                f"Y: [{ymin:.1f}, {ymax:.1f}]    "
                f"Z: [{zmin:.1f}, {zmax:.1f}]"
            )
        else:
            bbox_info = "No geometry loaded – using default size."

        self._bbox_label = QLabel(bbox_info)
        self._bbox_label.setWordWrap(True)
        layout.addWidget(self._bbox_label)

        # Multi-file mode: every loaded file owns a world volume, and all of
        # them are resized to the same value, so say it up front.
        if self._world_count > 1:
            multi_label = QLabel(
                f"Multi-file mode: {self._world_count} world volumes "
                f"will all be resized to the same size."
            )
            multi_label.setWordWrap(True)
            multi_label.setStyleSheet("color: #ffb86c; font-size: 12px;")
            layout.addWidget(multi_label)

        # Current world size(s)
        if len(self._world_sizes) == 1:
            cur_text = f"Current world size:  {self._world_sizes[0]:.1f} mm"
        elif len(self._world_sizes) > 1:
            joined = " / ".join(f"{s:.1f}" for s in self._world_sizes)
            cur_text = f"Current world sizes (mixed):  {joined} mm"
        else:
            cur_text = ""
        if cur_text:
            cur_label = QLabel(cur_text)
            cur_label.setWordWrap(True)
            layout.addWidget(cur_label)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        # Factor selection
        factor_layout = QHBoxLayout()
        factor_layout.addWidget(QLabel("World volume factor:"))
        self._factor_combo = QComboBox()
        for f in self.FACTORS:
            self._factor_combo.addItem(f"× {f}  (×{f} the scene extent)", f)
        self._factor_combo.setCurrentIndex(
            self.FACTORS.index(self.DEFAULT_FACTOR))
        self._factor_combo.currentIndexChanged.connect(self._on_factor_changed)
        factor_layout.addWidget(self._factor_combo, 1)
        layout.addLayout(factor_layout)

        # Computed new world size
        self._size_label = QLabel()
        self._size_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self._size_label)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        fit_btn = QPushButton("Fit View")
        fit_btn.clicked.connect(self._fit_preview)
        btn_layout.addWidget(fit_btn)
        btn_layout.addStretch()

        ok_btn = QPushButton("Apply")
        ok_btn.setStyleSheet(
            "background-color: #0078d4; color: white; "
            "border: none; border-radius: 6px; padding: 8px 24px; "
            "font-weight: bold; font-size: 13px;"
        )
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        root_layout.addLayout(layout, 2)

    # ---- live preview ----

    def showEvent(self, event):
        """Build the 3D preview once the dialog is on screen."""
        super().showEvent(event)
        if self._preview_started or self._root_node is None:
            return
        self._preview_started = True
        # Defer: the VTK widget must be created after the dialog's native
        # window exists, otherwise a stray top-level window is created.
        QTimer.singleShot(0, self._init_preview)

    def _init_preview(self):
        """Create the preview widget, hide the tree's world boxes and add ours."""
        if self._preview is not None or self._preview_host is None:
            return
        try:
            from ui.vtk_widget import VtkPreviewWidget
        except Exception as e:
            if self._preview_ph is not None:
                self._preview_ph.setText(f"3D preview unavailable:\n{e}")
            return

        self._preview = VtkPreviewWidget(self._preview_host)
        # Follow the app theme: the preview keeps its own palette, one step
        # away from the main viewer's (mid grey in light mode, deeper navy in
        # dark mode — see VtkPreviewWidget.BG_LIGHT / BG_DARK).
        self._preview.set_dark_theme(self._dark_theme)
        idx = self._preview_layout.indexOf(self._preview_ph)
        self._preview_layout.removeWidget(self._preview_ph)
        self._preview_ph.deleteLater()
        self._preview_ph = None
        self._preview_layout.insertWidget(idx, self._preview, 1)
        self._preview.show()

        # Geometry + world boxes, as in the main view (no duplicate definitions).
        # Must be set BEFORE build_scene: placements are applied while binding.
        self._preview.set_override_provider(self._override_provider)
        self._preview.build_scene(self._root_node)
        scene = self._preview.get_scene()

        # The tree already draws the current world box: one per WORLD_NODE, or
        # a single unified box in multi-file mode. Read their centres before
        # dropping them - the preview keeps exactly one box of its own, so a
        # factor change only re-sizes that actor (no scene rebuild at all).
        builtin = scene.world_box_actors
        centers = []
        for a in builtin:
            b = a.GetBounds()
            if b and b[1] >= b[0]:
                centers.append(((b[0] + b[1]) * 0.5,
                                (b[2] + b[3]) * 0.5,
                                (b[4] + b[5]) * 0.5))
        if centers:
            c0 = centers[0]
            same_center = all(
                max(abs(c[i] - c0[i]) for i in range(3)) < 1e-6
                for c in centers)
            # One shared centre (the usual case, and the unified multi-file
            # case) -> keep it. Different centres mean one box per file placed
            # apart from the others: after Apply the main view draws a single
            # origin-centred box (see VtkScene.build_from_tree), so preview
            # that same box instead of an arbitrary file's one.
            self._world_center = c0 if same_center else (0.0, 0.0, 0.0)
        for a in builtin:
            scene.renderer.RemoveActor(a)

        # Cube-axes ruler follows the geometry only (stable while the factor
        # changes) — computed after the built-in world boxes are gone.
        self._preview._update_cube_axes_bounds()

        from vtkmodules.vtkFiltersSources import vtkCubeSource
        from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper
        from vtkmodules.vtkCommonTransforms import vtkTransform

        self._box_source = vtkCubeSource()
        self._box_source.SetXLength(1.0)
        self._box_source.SetYLength(1.0)
        self._box_source.SetZLength(1.0)
        self._box_source.Update()

        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(self._box_source.GetOutputPort())
        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetRepresentationToWireframe()
        actor.GetProperty().SetColor(*WORLD_BOX_COLOR)
        actor.GetProperty().SetLineWidth(2)
        transform = vtkTransform()
        transform.Translate(*self._world_center)
        actor.SetUserTransform(transform)
        scene.renderer.AddActor(actor)
        self._world_box_actor = actor

        self._update_preview_box()

    def _update_preview_box(self):
        """Re-size the preview world box to the currently selected factor."""
        if self._box_source is None or self._preview is None:
            return
        edge = self.world_half_size * 2.0
        self._box_source.SetXLength(edge)
        self._box_source.SetYLength(edge)
        self._box_source.SetZLength(edge)
        self._box_source.Update()
        # Keep the (possibly much larger/smaller) world box in view, exactly
        # like cad2gdml re-fits its preview after every factor change.
        self._fit_preview()

    def _fit_preview(self):
        if self._preview is not None:
            try:
                self._preview.fit_all()
            except Exception:
                pass

    def done(self, result: int):
        """Release VTK resources before the dialog goes away."""
        if self._preview is not None:
            try:
                self._preview.cleanup()
            except Exception:
                pass
            self._preview = None
        super().done(result)

    # ---- Events ----

    def _on_factor_changed(self):
        """Update size display and the live preview when factor changes"""
        self._update_size_label()
        self._update_preview_box()

    def _update_size_label(self):
        """Update new world size label"""
        factor = self._factor_combo.currentData()
        self._selected_factor = factor
        # Use max_radius: ensure the world box (centered at origin) covers
        # both (0,0,0) and the furthest geometry point, with factor padding
        half = self._max_radius * factor
        full = half * 2.0
        self._size_label.setText(
            f"New world:  {full:.1f} × {full:.1f} × {full:.1f} mm\n"
            f"(half = {half:.1f} mm)\n"
            f"Max distance from origin: {self._max_radius:.1f} mm"
        )

    # ---- Public interface ----

    @property
    def selected_factor(self) -> int:
        """User-selected factor"""
        return self._selected_factor

    @property
    def world_half_size(self) -> float:
        """Computed world volume half-size — based on max distance from origin."""
        return self._max_radius * self._selected_factor
