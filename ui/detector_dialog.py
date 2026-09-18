"""
DetectorDialog - add a simple box / sphere detector as its own GDML file.

The dialog has no 3D viewport of its own.  The detector is previewed in the
*main* view instead (see VtkScene.show_detector_preview), so it is seen in
place - same camera, same project geometry, against the world box the new file
will actually get - and the user can pan / zoom / rotate while the sizes are
tuned.  This is the same arrangement the Transform dialog uses, and it drops a
second render window plus its own full scene build per detector.

Usage:
    dialog = DetectorDialog(...)
    dialog.preview_changed.connect(on_preview)   # object -> dict
    dialog.finished.connect(on_closed)           # commit / drop the ghost
    dialog.show()                                # keep a reference to `dialog`!

The caller owns the ghost actor: the dialog itself keeps no side effects on the
scene, so commit/drop is entirely up to the caller (a Cancel, an Esc and a
window close all report Rejected through finished()).

Layout:
  Solid name / dimensions in mm
  Cancel / Add
"""

from typing import Dict, Optional, Sequence, Set, Tuple

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QDoubleSpinBox, QPushButton, QFrame, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal

from core.detector_factory import SHAPES, derive_world_size, is_valid_name


class DetectorDialog(QDialog):
    """Add Box / Sphere detector dialog.

    Non-modal on purpose: the geometry being defined is drawn into the main 3D
    view, which is meant to be panned / zoomed / rotated while the spin boxes
    are adjusted.  The dialog only reports what the form currently says; the
    caller owns the preview and is responsible for dropping it when the dialog
    is not accepted.
    """

    #: Current form contents, emitted on every size change.
    #: object = dict with keys "shape", "params_mm", "world_size".
    preview_changed = pyqtSignal(object)

    def __init__(
        self,
        shape: str,
        default_name: str,
        existing_names: Optional[Set[str]] = None,
        world_size: Optional[Sequence[float]] = None,
        parent=None,
    ):
        """
        Args:
            shape: BOX or SPHERE.
            default_name: Prefilled solid name (already made unique).
            existing_names: Names already used in the project, for validation.
            world_size: (x, y, z) mm of the world box to place the detector in.
                When None, the world is derived from the detector size - the
                project has no world volume to copy a size from yet.
        """
        super().__init__(parent)
        if shape not in SHAPES:
            raise ValueError(f"unsupported detector shape: {shape!r}")

        self._shape = shape
        self._spec = SHAPES[shape]
        self._default_name = default_name
        self._existing_names: Set[str] = set(existing_names or ())
        self._world_from_project: Optional[Tuple[float, float, float]] = (
            tuple(float(v) for v in world_size) if world_size else None)

        self._spins: Dict[str, QDoubleSpinBox] = {}

        self.setWindowTitle(f"Add {self._spec['label']} Detector")
        # Non-modal on purpose: the values are tuned while the 3D view behind
        # the dialog is still being panned / zoomed. The caller owns the ghost
        # preview via preview_changed() / finished(), and must keep a reference
        # to this dialog.
        self.setModal(False)
        self.setMinimumWidth(380)
        self._build_ui()
        self._update_summary()

    # ---- Results ----

    @property
    def shape(self) -> str:
        """BOX or SPHERE."""
        return self._shape

    @property
    def detector_name(self) -> str:
        """Solid name typed by the user — also names the new .gdml file."""
        return self._name_edit.text().strip()

    @property
    def params_mm(self) -> Dict[str, float]:
        """Detector dimensions in millimetres."""
        return self._read_params_mm()

    @property
    def world_size(self) -> Tuple[float, float, float]:
        """World box the detector will be placed in, in millimetres."""
        return self._current_world_mm()

    def preview(self) -> dict:
        """Snapshot of the current form, for the main view's ghost actor."""
        return {
            "shape": self._shape,
            "params_mm": self._read_params_mm(),
            "world_size": self._current_world_mm(),
        }

    # ---- UI construction ----

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        title = QLabel("Detector")
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self._name_edit = QLineEdit(self._default_name)
        self._name_edit.setPlaceholderText("e.g. box1")
        self._name_edit.textChanged.connect(self._update_summary)
        form.addRow("Solid name", self._name_edit)

        defaults = self._spec["defaults"]
        for key, label in self._spec["params"]:
            spin = QDoubleSpinBox()
            spin.setDecimals(3)
            spin.setRange(0.001, 1.0e7)
            spin.setSingleStep(1.0)
            spin.setValue(float(defaults.get(key, 1.0)))
            spin.setSuffix(" mm")
            # Connected after setValue(): the initial fill is not a user edit.
            spin.valueChanged.connect(self._on_params_changed)
            self._spins[key] = spin
            form.addRow(label, spin)

        layout.addLayout(form)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        self._summary_label = QLabel("")
        self._summary_label.setWordWrap(True)
        layout.addWidget(self._summary_label)

        layout.addStretch(1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        ok_btn = QPushButton("Add")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_accept)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

    # ---- Form handling ----

    def _on_params_changed(self):
        """A size changed -> let the caller re-draw the ghost in the main view."""
        self._update_summary()
        self.preview_changed.emit(self.preview())

    def _read_params_mm(self) -> Dict[str, float]:
        """The spin boxes carry millimetres, so this is a plain read."""
        return {key: spin.value() for key, spin in self._spins.items()}

    def _current_world_mm(self) -> Tuple[float, float, float]:
        if self._world_from_project is not None:
            return self._world_from_project
        return derive_world_size(self._read_params_mm())

    def _update_summary(self):
        """Show the resulting sizes, or where they came from, in millimetres."""
        params = self._read_params_mm()
        mm_text = " × ".join(f"{v:g}" for v in params.values())
        lines = [f"Detector:  {mm_text} mm"]

        world = self._current_world_mm()
        lines.append(f"World:  {world[0]:g} × {world[1]:g} × {world[2]:g} mm")
        lines.append("(world size taken from the existing project)"
                     if self._world_from_project is not None
                     else "(no world in the project — sized around this detector)")

        if params and min(world) < max(params.values()):
            lines.append("Warning: the detector is larger than its world box.")
        self._summary_label.setText("\n".join(lines))

    # ---- Accept ----

    def _on_accept(self):
        name = self.detector_name
        if not is_valid_name(name):
            QMessageBox.warning(
                self, "Invalid name",
                "The solid name must be non-empty and may only contain "
                "letters, digits, '_' and '-'.")
            return
        if name in self._existing_names:
            QMessageBox.warning(
                self, "Name already used",
                f"'{name}' is already used in this project.\n"
                "Pick another name — it names both the solid and the new file.")
            return
        if any(spin.value() <= 0 for spin in self._spins.values()):
            QMessageBox.warning(
                self, "Invalid size", "All dimensions must be greater than zero.")
            return
        self.accept()
