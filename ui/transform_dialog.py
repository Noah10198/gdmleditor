"""
TransformDialog - Dialog for editing placement transforms.

Supports two modes:
1. Physvol override: editing the placement of a single PHYVOL_NODE entry
2. File transform: editing the file-level transform of a GDML_FILE node
   (translates/rotates all geometry in the file as a single group)

Usage:
    dialog = TransformDialog(entry_id, initial_placement, title, parent)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        new_placement = dialog.get_placement()
"""

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QDoubleSpinBox, QPushButton, QGroupBox, QDialogButtonBox
)
from PyQt6.QtCore import Qt

from core.gdml_tree import Placement


class TransformDialog(QDialog):
    """Dialog for editing position and rotation values."""

    def __init__(
        self,
        title: str,
        target_label: str,
        placement: Placement,
        parent=None,
    ):
        """
        Args:
            title: Dialog window title (e.g. "Edit Transform")
            target_label: Description of what is being edited
                          (e.g. "pv1 -> Detector" or "file: tess.gdml")
            placement: Initial Placement to edit
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(360)
        self.setModal(True)

        self._placement = Placement(
            x=placement.x, y=placement.y, z=placement.z,
            rot_x=placement.rot_x, rot_y=placement.rot_y, rot_z=placement.rot_z,
            unit=placement.unit, rot_unit=placement.rot_unit,
        )

        self._build_ui(target_label)

    def _build_ui(self, target_label: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Target label
        target_lbl = QLabel(target_label)
        target_lbl.setStyleSheet("font-weight: bold; font-size: 13px; padding: 4px 0;")
        layout.addWidget(target_lbl)

        # Position group
        pos_group = QGroupBox("Position")
        pos_grid = QGridLayout(pos_group)
        pos_grid.setSpacing(6)

        labels = ["X", "Y", "Z"]
        self._pos_spinboxes = {}
        values = [self._placement.x, self._placement.y, self._placement.z]
        for i, (lbl, val) in enumerate(zip(labels, values)):
            label = QLabel(lbl)
            label.setAlignment(Qt.AlignmentFlag.AlignRight |
                               Qt.AlignmentFlag.AlignVCenter)
            spin = QDoubleSpinBox()
            spin.setRange(-1e9, 1e9)
            spin.setDecimals(4)
            spin.setSingleStep(1.0)
            spin.setValue(val)
            unit_label = QLabel(self._placement.unit)
            pos_grid.addWidget(label, i, 0)
            pos_grid.addWidget(spin, i, 1)
            pos_grid.addWidget(unit_label, i, 2)
            self._pos_spinboxes[lbl.lower()] = spin

        layout.addWidget(pos_group)

        # Rotation group
        rot_group = QGroupBox("Rotation (degrees)")
        rot_grid = QGridLayout(rot_group)
        rot_grid.setSpacing(6)

        labels_r = ["X", "Y", "Z"]
        values_r = [
            self._placement.rot_x,
            self._placement.rot_y,
            self._placement.rot_z,
        ]
        self._rot_spinboxes = {}
        for i, (lbl, val) in enumerate(zip(labels_r, values_r)):
            label = QLabel(lbl)
            label.setAlignment(Qt.AlignmentFlag.AlignRight |
                               Qt.AlignmentFlag.AlignVCenter)
            spin = QDoubleSpinBox()
            spin.setRange(-360.0, 360.0)
            spin.setDecimals(2)
            spin.setSingleStep(1.0)
            spin.setValue(val)
            unit_label = QLabel(self._placement.rot_unit)
            rot_grid.addWidget(label, i, 0)
            rot_grid.addWidget(spin, i, 1)
            rot_grid.addWidget(unit_label, i, 2)
            self._rot_spinboxes[lbl.lower()] = spin

        layout.addWidget(rot_group)

        # Buttons
        btn_layout = QHBoxLayout()

        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self._on_reset)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)

        btn_layout.addWidget(reset_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(button_box)
        layout.addLayout(btn_layout)

    def _read_spinboxes(self) -> Placement:
        """Read current values from spinboxes into a Placement."""
        return Placement(
            x=self._pos_spinboxes["x"].value(),
            y=self._pos_spinboxes["y"].value(),
            z=self._pos_spinboxes["z"].value(),
            rot_x=self._rot_spinboxes["x"].value(),
            rot_y=self._rot_spinboxes["y"].value(),
            rot_z=self._rot_spinboxes["z"].value(),
            unit=self._placement.unit,
            rot_unit=self._placement.rot_unit,
        )

    def _on_accept(self):
        """Validate and accept."""
        self._placement = self._read_spinboxes()
        self.accept()

    def _on_reset(self):
        """Reset all spinboxes to zero."""
        for spin in self._pos_spinboxes.values():
            spin.setValue(0.0)
        for spin in self._rot_spinboxes.values():
            spin.setValue(0.0)

    def get_placement(self) -> Placement:
        """Return the edited Placement (call after exec() returns Accepted)."""
        return self._placement
