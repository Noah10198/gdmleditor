"""
LocalMaterialDialog -- dialog for adding local materials (Compound/Mixture).

Matches cad2gdml style and layout:
- QComboBox for type selection (Compound / Mixture)
- QHBoxLayout inline rows for element composition
- Light theme (#0078d4 accent color)
- Uses CompoundItem/MixtureItem data structures
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QDoubleSpinBox, QComboBox, QPushButton, QWidget, QGroupBox,
    QSizePolicy, QScrollArea, QFrame,
)
from PyQt6.QtCore import Qt, QTimer

from core.materials_lib import (
    MaterialsLib, CompoundMaterial, CompoundItem,
    MixtureMaterial, MixtureItem,
)

# Fixed widths of the ratio column, shared by the composition rows and their
# header so the two line up.
_RATIO_WIDTH = 120
_REMOVE_BTN_WIDTH = 28


class _CompositionRow:
    """One composition row: element combo + ratio spinbox."""
    def __init__(self, combo: QComboBox, spin: QDoubleSpinBox):
        self.combo = combo
        self.spin = spin


class LocalMaterialDialog(QDialog):
    """Dialog for adding local materials, matching cad2gdml layout/colors."""

    # Mass fractions have to sum to exactly 1. An epsilon rather than a plain
    # == 1.0 because binary floating point cannot add decimal fractions
    # exactly (0.1 + 0.2 + 0.7 == 0.9999999999999999); 1e-6 is far above that
    # noise and far below the 1e-4 the spin boxes can express.
    _TOTAL_TOLERANCE = 1e-6

    def __init__(self, mat_lib: MaterialsLib, parent=None, material=None):
        super().__init__(parent)
        self._mat_lib = mat_lib
        self._editing = material
        self._rows: list[_CompositionRow] = []
        self._last_gdml: str = ""
        self._last_mat_id: str = ""

        self.setWindowTitle("Edit Local Material" if material else
                            "Add Local Material")
        self.setMinimumSize(520, 400)
        self.resize(560, 480)

        self._build_ui()
        self._apply_theme()

        if material is not None:
            self._save_btn.setText("Save Changes")
            self._load_material(material)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # -- Type selector (QComboBox, same as cad2gdml) --
        cat_layout = QHBoxLayout()
        cat_layout.addWidget(QLabel("Type:"))
        self._cat_combo = QComboBox()
        self._cat_combo.addItem("Compound (atom ratio)", "compound")
        self._cat_combo.addItem("Mixture (mass fraction)", "mixture")
        self._cat_combo.currentIndexChanged.connect(self._on_category_changed)
        cat_layout.addWidget(self._cat_combo)
        cat_layout.addStretch()
        layout.addLayout(cat_layout)

        # -- Basic Info --
        common_group = QGroupBox("Basic Info")
        common_layout = QFormLayout(common_group)
        common_layout.setSpacing(4)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. my_steel, my_water...")
        common_layout.addRow("Name:", self._name_edit)

        self._density_spin = QDoubleSpinBox()
        self._density_spin.setDecimals(4)
        self._density_spin.setRange(0, 1e9)
        self._density_spin.setValue(1.0)
        self._density_spin.setToolTip("Density in g/cm3")
        common_layout.addRow("Density (g/cm3):", self._density_spin)

        # Keep the natural height: as a Preferred box it would take half of any
        # extra height the dialog gets, leaving a blank patch under Density.
        common_group.setSizePolicy(QSizePolicy.Policy.Preferred,
                                   QSizePolicy.Policy.Fixed)
        layout.addWidget(common_group)

        # -- Composition (inline rows, same as cad2gdml) --
        self._comp_group = QGroupBox("Composition")
        comp_layout = QVBoxLayout(self._comp_group)

        # Items container
        self._items_widget = QWidget()
        self._items_layout = QVBoxLayout(self._items_widget)
        self._items_layout.setContentsMargins(0, 0, 0, 0)
        self._items_layout.setSpacing(4)

        # Header row: the Ratio label carries the same fixed width as the spin
        # box below, so the header columns sit over the actual columns. It is
        # part of the scrolled content on purpose -- outside of it the labels
        # would shift sideways by the scrollbar width whenever it appears.
        comp_header = QHBoxLayout()
        comp_header.setSpacing(8)
        comp_header.addWidget(QLabel("Element"), 1)
        ratio_header = QLabel("Ratio")
        ratio_header.setFixedWidth(_RATIO_WIDTH)
        comp_header.addWidget(ratio_header)
        comp_header.addSpacing(8 + _REMOVE_BTN_WIDTH)
        self._items_layout.addLayout(comp_header)

        # The rows are all fixed height, and a box layout with nothing
        # stretchable hands its leftover height to the spacing between items.
        # This trailing spacer absorbs it instead, keeping the rows packed at
        # the top and the Add button at the bottom of the group.
        self._items_layout.addStretch(1)

        # A long element list scrolls here instead of squeezing the rows or
        # stretching the dialog to the screen height.
        self._scroll = QScrollArea()
        self._scroll.setWidget(self._items_widget)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setMinimumHeight(132)
        comp_layout.addWidget(self._scroll, 1)

        # Total proportion label (for mixture validation feedback)
        total_row = QHBoxLayout()
        total_row.addStretch()
        self._total_label = QLabel("")
        total_row.addWidget(self._total_label)
        comp_layout.addLayout(total_row)

        add_item_btn = QPushButton("+ Add Element")
        add_item_btn.clicked.connect(self._add_composition_row)
        comp_layout.addWidget(add_item_btn)

        # Sole owner of the extra height when the dialog is resized.
        layout.addWidget(self._comp_group, 1)

        # -- Buttons --
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._save_btn = QPushButton("Add Material")
        self._save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self._save_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        # Add mode starts with one empty row; edit mode fills its rows from the
        # material instead.
        if self._editing is None:
            self._add_composition_row()

    # -- Composition rows --

    def _load_material(self, mat):
        """Pre-fill every field from an existing material (edit mode).

        The category is set first: the spin decimals of the rows created below
        follow the current category.
        """
        is_mixture = isinstance(mat, MixtureMaterial)
        idx = self._cat_combo.findData("mixture" if is_mixture else "compound")
        if idx >= 0:
            self._cat_combo.setCurrentIndex(idx)
        self._name_edit.setText(mat.mat_name)
        self._density_spin.setValue(mat.density)

        for comp in mat.components:
            self._add_composition_row()
            cr = self._rows[-1]
            pos = cr.combo.findData(comp.symbol)
            if pos >= 0:
                cr.combo.setCurrentIndex(pos)
            cr.spin.setValue(comp.mass_fraction if is_mixture
                             else comp.atom_count)

    def _add_composition_row(self):
        """Add one element composition row (same QHBoxLayout pattern as cad2gdml)."""
        row = QHBoxLayout()
        row.setSpacing(8)

        combo = QComboBox()
        elements = MaterialsLib.get_all_elements()
        sorted_elems = sorted(elements.items(), key=lambda x: x[1][0])
        combo.addItem("Select element...", "")
        for symbol, (z, atom_weight) in sorted_elems:
            combo.addItem(
                f"{symbol} (Z={int(z):d})", symbol)
        row.addWidget(combo)

        is_mixture = self._cat_combo.currentData() == "mixture"
        spin = QDoubleSpinBox()
        spin.setDecimals(4 if is_mixture else 0)
        spin.setRange(0, 1e9)
        spin.setSingleStep(0.0001 if is_mixture else 1.0)
        spin.setValue(1)
        spin.setToolTip(
            "Mass fraction" if is_mixture else "Atom count")
        spin.valueChanged.connect(self._update_total_display)
        spin.setFixedWidth(_RATIO_WIDTH)
        row.addWidget(spin)

        remove_btn = QPushButton("x")
        remove_btn.setFixedWidth(_REMOVE_BTN_WIDTH)
        remove_btn.clicked.connect(
            lambda checked, r=row: self._remove_row(r))
        row.addWidget(remove_btn)

        combo.currentIndexChanged.connect(self._update_total_display)

        # Inserted before the trailing spacer so most-recently-added rows land
        # at the bottom of the list.
        self._items_layout.insertLayout(self._items_layout.count() - 1, row)
        self._rows.append(_CompositionRow(combo, spin))
        self._update_total_display()
        QTimer.singleShot(0, lambda: self._refresh_scroll_area(reveal_last=True))

    def _refresh_scroll_area(self, reveal_last: bool = False):
        """Size the scrolled content to its rows and optionally reveal the last.

        Deferred to the next event loop turn, for two reasons:

        * A nested row layout reports its real minimum size only once the layout
          has been activated; measured any earlier it is a stale 0-ish value.
        * Qt writes a layout's minimum size back to its widget only for
          top-level windows, so this child would otherwise keep a minimum of 0
          and QScrollArea would squeeze a long list into the viewport, letting
          the rows overlap instead of scrolling.

        A fixed height rather than a minimum one: it shrinks the widget again
        when rows are removed, and the resize it forces is what updates the
        scrollbar range.
        """
        self._items_widget.setFixedHeight(
            self._items_widget.minimumSizeHint().height())
        if reveal_last:
            bar = self._scroll.verticalScrollBar()
            bar.setValue(bar.maximum())

    def _remove_row(self, row_layout: QHBoxLayout):
        """Remove one composition row."""
        for i, cr in enumerate(self._rows[:]):
            found = False
            for j in range(row_layout.count()):
                w = row_layout.itemAt(j)
                if w and w.widget() in (cr.combo, cr.spin):
                    found = True
                    break
            if found:
                self._rows.remove(cr)
                break
        while row_layout.count():
            item = row_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        idx = self._items_layout.indexOf(row_layout)
        if idx >= 0:
            self._items_layout.takeAt(idx)
        self._update_total_display()
        QTimer.singleShot(0, self._refresh_scroll_area)

    def _update_total_display(self):
        """Update the total proportion label based on current data."""
        is_mixture = self._cat_combo.currentData() == "mixture"
        if not is_mixture:
            self._total_label.setText("")
            return

        total = 0.0
        has_valid = False
        for cr in self._rows:
            sym = cr.combo.currentData()
            if not sym:
                continue
            has_valid = True
            total += cr.spin.value()

        if not has_valid:
            self._total_label.setText("")
            return

        diff = abs(total - 1.0)
        if diff < self._TOTAL_TOLERANCE:
            self._total_label.setText(
                f"Total: {total:.4f}  (OK)")
            self._total_label.setStyleSheet(
                "color: #2e7d32; font-size: 11px; font-weight: bold;")
        else:
            self._total_label.setText(
                f"Total: {total:.4f}  (must be 1.0)")
            self._total_label.setStyleSheet(
                "color: #c62828; font-size: 11px; font-weight: bold;")

    # -- Category switch --

    def _on_category_changed(self, idx: int):
        """Update spinbox precision when switching Compound/Mixture."""
        is_mixture = self._cat_combo.currentData() == "mixture"
        decimals = 4 if is_mixture else 0
        for cr in self._rows:
            cr.spin.setDecimals(decimals)
            cr.spin.setSingleStep(0.0001 if is_mixture else 1.0)
            if not is_mixture:
                cr.spin.setValue(int(cr.spin.value()))
        self._update_total_display()

    # -- Save --

    def _on_save(self):
        name = self._name_edit.text().strip()
        if not name:
            self._name_edit.setStyleSheet(
                "border: 1px solid #e74c3c; background-color: #fff0f0;")
            return
        else:
            self._name_edit.setStyleSheet(
                "border: 1px solid #d0d0d0; background-color: #ffffff;")

        valid_items = []
        for cr in self._rows:
            sym = cr.combo.currentData()
            if not sym:
                continue
            valid_items.append((cr, sym))

        if not valid_items:
            self._name_edit.setStyleSheet(
                "border: 1px solid #e74c3c; background-color: #fff0f0;")
            return

        cat = self._cat_combo.currentData()

        # For mixture, the mass fractions have to add up to exactly 1.0
        if cat == "mixture":
            total = sum(cr.spin.value() for cr, _ in valid_items)
            if abs(total - 1.0) > self._TOTAL_TOLERANCE:
                self._total_label.setStyleSheet(
                    "color: #c62828; font-size: 11px; font-weight: bold;")
                return
            self._update_total_display()

        # Reuse the existing id when editing so nothing pointing at this
        # material has to be rewritten, otherwise take a fresh one.
        mat_id = (self._editing.mat_id if self._editing
                  else self._mat_lib.generate_id())

        if cat == "compound":
            components = []
            for cr, sym in valid_items:
                components.append(CompoundItem(
                    symbol=sym,
                    atom_count=int(cr.spin.value()),
                ))
            mat = CompoundMaterial(
                mat_id=mat_id,
                mat_name=name,
                density=round(self._density_spin.value(), 4),
                components=components,
            )
        else:
            components = []
            for cr, sym in valid_items:
                components.append(MixtureItem(
                    symbol=sym,
                    mass_fraction=round(cr.spin.value(), 4),
                ))
            mat = MixtureMaterial(
                mat_id=mat_id,
                mat_name=name,
                density=round(self._density_spin.value(), 4),
                components=components,
            )

        if self._editing:
            # In-place: keeps the id and moves the entry if the category
            # switched underneath the user.
            self._mat_lib.update_local_material(mat)
        elif cat == "compound":
            self._mat_lib.add_compound(mat)
        else:
            self._mat_lib.add_mixture(mat)

        self._last_mat_id = mat_id
        self._last_gdml = self._mat_lib.to_gdml_string(mat_id)
        self.accept()

    @property
    def last_gdml(self) -> str:
        return self._last_gdml

    @property
    def last_mat_id(self) -> str:
        return self._last_mat_id

    # -- Theme --

    def _apply_theme(self):
        """Apply light theme matching cad2gdml exactly."""
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
            }
            /* The composition list must stay on the dialog background: a
               QScrollArea paints its viewport with the palette Base colour,
               which is not necessarily white outside of the light theme. */
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
            }
            QLabel {
                color: #2c2c2c;
                font-size: 12px;
            }
            QGroupBox {
                font-size: 13px;
                font-weight: bold;
                color: #555555;
                border: 1px solid #cccccc;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 2px 8px;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox {
                background-color: #ffffff;
                color: #2c2c2c;
                border: 1px solid #d0d0d0;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 12px;
                min-height: 22px;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #0078d4;
                background-color: #f8f9fa;
            }
            QComboBox {
                background-color: #ffffff;
                color: #2c2c2c;
                border: 1px solid #d0d0d0;
                border-radius: 6px;
                padding: 4px 24px 4px 10px;
                font-size: 12px;
                min-height: 22px;
            }
            QComboBox:hover {
                border: 1px solid #0078d4;
                background-color: #f8f9fa;
            }
            QComboBox:on {
                border: 1px solid #0078d4;
                background-color: #f0f4ff;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border: none;
                border-left: 1px solid #e0e0e0;
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
            }
            QComboBox:hover::drop-down {
                border-left: 1px solid #0078d4;
            }
            QComboBox::down-arrow {
                width: 0;
                height: 0;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #666666;
                margin: 2px;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #2c2c2c;
                border: 1px solid #d0d0d0;
                border-radius: 8px;
                padding: 4px;
                outline: none;
                selection-background-color: transparent;
                selection-color: #2c2c2c;
            }
            QComboBox QAbstractItemView::item {
                padding: 6px 10px;
                min-height: 24px;
                border-radius: 4px;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #e8f0fe;
                color: #1a1a1a;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #d2e3fc;
                color: #1a1a1a;
            }
            QPushButton {
                background-color: #f0f0f0;
                color: #2c2c2c;
                border: 1px solid #d0d0d0;
                border-radius: 6px;
                padding: 6px 18px;
                font-size: 12px;
                font-weight: 500;
                min-height: 22px;
            }
            QPushButton:hover {
                background-color: #e4e7eb;
                border: 1px solid #0078d4;
            }
            QPushButton:pressed {
                background-color: #d2d5d9;
            }
        """)
