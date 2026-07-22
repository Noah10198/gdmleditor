"""
RedefineWorldDialog - Non-modal dialog for redefining world volume size

Based on cad2gdml's ExportGdmlDialog design, provides factor selection (x3, x5, x10, x100),
computing recommended world size from all geometry bounding boxes.

Layout:
  - Current bounding box info
  - Factor combo box selection
  - Computed new world size display
  - Apply / Cancel buttons
"""

from typing import List, Optional, Tuple

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QWidget, QFrame, QMessageBox,
)
from PyQt6.QtCore import Qt


class RedefineWorldDialog(QDialog):
    """Redefine World Volume Dialog"""

    FACTORS = [3, 5, 10, 100]

    def __init__(
        self,
        bbox: Tuple[float, float, float, float, float, float],
        current_world_size: float = 0.0,
        parent=None,
    ):
        """
        Args:
            bbox: (xmin, xmax, ymin, ymax, zmin, zmax) — all geometry in WORLD space
            current_world_size: Current world volume size (edge length), 0 = unknown
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Redefine World Volume")
        self.setMinimumSize(360, 220)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self._bbox = bbox
        self._current_world_size = current_world_size
        self._selected_factor: int = 5  # default

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
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

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

        # Current world size
        if self._current_world_size > 0:
            cur_label = QLabel(
                f"Current world size:  {self._current_world_size:.1f} mm"
            )
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
        self._factor_combo.setCurrentIndex(1)  # Default x5
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

    # ---- Events ----

    def _on_factor_changed(self):
        """Update size display when factor changes"""
        self._update_size_label()

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
