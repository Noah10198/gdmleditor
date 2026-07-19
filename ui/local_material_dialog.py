"""
Add Local Material Dialog — 创建自定义局部材料。

支持两种配方方式：
1. 化合物（Compound）：原子数比例，ex: H₂O
2. 混合物（Mixture）：质量比例，ex: 空气

（从 cad2gdml/ui/local_material_dialog.py 适配而来）
"""

import uuid
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTabWidget,
    QWidget, QLabel, QLineEdit, QDoubleSpinBox, QComboBox, QFormLayout,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QAbstractItemView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from core.materials_lib import (
    MaterialsLib, CompoundItem, MixtureItem,
    CompoundMaterial, MixtureMaterial, CustomElement,
)


class _CompositionItem:
    """在编辑器内部使用的一行组分数据。"""
    def __init__(self, symbol: str, value: float):
        self.symbol = symbol
        self.value = value


class LocalMaterialDialog(QDialog):
    """添加局部材料的对话框（化合物 + 混合物两页）。"""

    def __init__(self, mat_lib: MaterialsLib, parent=None):
        super().__init__(parent)
        self._mat_lib = mat_lib
        self._items: list[_CompositionItem] = []
        self._last_gdml: str = ""

        self.setWindowTitle("Add Local Material")
        self.setMinimumSize(520, 400)
        self.resize(560, 480)

        self._build_ui()
        self._apply_theme()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)

        # 顶部：配方类型（化合物/混合物）
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_compound_tab(), "Compound (atom ratio)")
        self._tabs.addTab(self._build_mixture_tab(), "Mixture (mass ratio)")
        main_layout.addWidget(self._tabs)

        # 材料属性
        prop_group = QGroupBox("Material Properties")
        prop_form = QFormLayout(prop_group)
        self._mat_name_edit = QLineEdit()
        self._mat_name_edit.setPlaceholderText("e.g. my_water, custom_steel")
        prop_form.addRow("Material Name:", self._mat_name_edit)
        self._density_spin = QDoubleSpinBox()
        self._density_spin.setRange(0.0001, 100.0)
        self._density_spin.setDecimals(4)
        self._density_spin.setValue(1.0)
        self._density_spin.setSuffix(" g/cm³")
        prop_form.addRow("Density:", self._density_spin)
        main_layout.addWidget(prop_group)

        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._preview_btn = QPushButton("Preview GDML")
        self._preview_btn.clicked.connect(self._on_preview)
        btn_layout.addWidget(self._preview_btn)
        self._ok_btn = QPushButton("Add Material")
        self._ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(self._ok_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        main_layout.addLayout(btn_layout)

        # 预览区
        self._preview_label = QLabel("")
        self._preview_label.setWordWrap(True)
        self._preview_label.setStyleSheet(
            "background: #2d2d3a; color: #b0b0c0; padding: 8px; "
            "border-radius: 4px; font-family: Consolas, monospace; font-size: 11px;")
        self._preview_label.setMaximumHeight(120)
        self._preview_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        main_layout.addWidget(self._preview_label)

    def _build_compound_tab(self) -> QWidget:
        """化合物选项卡（原子数比例）。"""
        w = QWidget()
        layout = QVBoxLayout(w)
        instr = QLabel("Define compound using atomic ratios (e.g. 2 H + 1 O = H₂O)")
        instr.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(instr)

        # 添加行
        add_row = QHBoxLayout()
        self._comp_elem_combo = QComboBox()
        self._comp_elem_combo.setEditable(True)
        self._comp_atom_spin = QDoubleSpinBox()
        self._comp_atom_spin.setRange(0.01, 1000.0)
        self._comp_atom_spin.setValue(1.0)
        self._comp_atom_spin.setDecimals(2)
        add_btn = QPushButton("Add Element")
        add_btn.clicked.connect(self._on_add_compound_row)

        add_row.addWidget(QLabel(" Element:"))
        add_row.addWidget(self._comp_elem_combo)
        add_row.addWidget(QLabel(" Atoms:"))
        add_row.addWidget(self._comp_atom_spin)
        add_row.addWidget(add_btn)
        add_row.addStretch()
        layout.addLayout(add_row)

        # 表格
        self._comp_table = QTableWidget()
        self._comp_table.setColumnCount(3)
        self._comp_table.setHorizontalHeaderLabels(["Symbol", "Atoms", "Remove"])
        self._comp_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self._comp_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self._comp_table)

        # 填充元素下拉
        self._populate_element_combo(self._comp_elem_combo)

        return w

    def _build_mixture_tab(self) -> QWidget:
        """混合物选项卡（质量比例）。"""
        w = QWidget()
        layout = QVBoxLayout(w)
        instr = QLabel("Define mixture using mass fractions (total = sum of fractions)")
        instr.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(instr)

        # 添加行
        add_row = QHBoxLayout()
        self._mix_elem_combo = QComboBox()
        self._mix_elem_combo.setEditable(True)
        self._mix_frac_spin = QDoubleSpinBox()
        self._mix_frac_spin.setRange(0.001, 1000.0)
        self._mix_frac_spin.setValue(1.0)
        self._mix_frac_spin.setDecimals(3)
        add_btn = QPushButton("Add Element")
        add_btn.clicked.connect(self._on_add_mixture_row)

        add_row.addWidget(QLabel(" Element:"))
        add_row.addWidget(self._mix_elem_combo)
        add_row.addWidget(QLabel(" Mass:"))
        add_row.addWidget(self._mix_frac_spin)
        add_row.addWidget(add_btn)
        add_row.addStretch()
        layout.addLayout(add_row)

        # 表格
        self._mix_table = QTableWidget()
        self._mix_table.setColumnCount(3)
        self._mix_table.setHorizontalHeaderLabels(["Symbol", "Mass Fraction", "Remove"])
        self._mix_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self._mix_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self._mix_table)

        # 填充元素下拉
        self._populate_element_combo(self._mix_elem_combo)

        return w

    def _populate_element_combo(self, combo: QComboBox):
        """用元素周期表填充下拉框。"""
        elements = MaterialsLib.get_all_elements()
        for symbol, (z, weight) in sorted(elements.items(),
                                          key=lambda x: x[1][0]):
            combo.addItem(f"{symbol} (Z={int(z)}, A={weight:.4f})",
                          symbol)

    def _on_add_compound_row(self):
        symbol = self._comp_elem_combo.currentData()
        if not symbol:
            QMessageBox.warning(self, "Warning", "Please select an element.")
            return
        atoms = self._comp_atom_spin.value()
        self._add_table_row(self._comp_table, symbol, atoms)

    def _on_add_mixture_row(self):
        symbol = self._mix_elem_combo.currentData()
        if not symbol:
            QMessageBox.warning(self, "Warning", "Please select an element.")
            return
        mass = self._mix_frac_spin.value()
        self._add_table_row(self._mix_table, symbol, mass)

    def _add_table_row(self, table: QTableWidget, symbol: str, value: float):
        row = table.rowCount()
        table.insertRow(row)

        sym_item = QTableWidgetItem(symbol)
        sym_item.setFlags(sym_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        table.setItem(row, 0, sym_item)

        val_item = QTableWidgetItem(f"{value:.4f}")
        val_item.setFlags(val_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        table.setItem(row, 1, val_item)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(28, 24)
        del_btn.clicked.connect(lambda: self._remove_table_row(table, row))
        table.setCellWidget(row, 2, del_btn)

    def _remove_table_row(self, table: QTableWidget, row: int):
        table.removeRow(row)

    def _on_preview(self):
        """生成并显示 GDML 预览。"""
        name = self._mat_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Warning", "Please enter a material name.")
            return

        density = self._density_spin.value()
        mat_id = f"local_{uuid.uuid4().hex[:8]}"

        # 判断当前选项卡
        current_tab = self._tabs.currentIndex()

        if current_tab == 0:
            # 化合物
            items = self._collect_table_data(self._comp_table)
            if not items:
                QMessageBox.warning(self, "Warning",
                                    "Please add at least one element.")
                return
            mat = CompoundMaterial(mat_id, name, density, [
                CompoundItem(it.symbol, it.value) for it in items
            ])
        else:
            # 混合物
            items = self._collect_table_data(self._mix_table)
            if not items:
                QMessageBox.warning(self, "Warning",
                                    "Please add at least one element.")
                return
            mat = MixtureMaterial(mat_id, name, density, [
                MixtureItem(it.symbol, it.value) for it in items
            ])

        gdml = self._mat_lib.to_gdml_string(mat_id)
        self._last_gdml = gdml
        self._preview_label.setText(gdml)

        # 保存好，以备后续确认
        if current_tab == 0:
            self._pending_mat = mat
        else:
            self._pending_mat = mat
        self._is_compound = (current_tab == 0)

    def _collect_table_data(self, table: QTableWidget) -> list:
        """从表格收集组分数据。"""
        items = []
        for row in range(table.rowCount()):
            sym = table.item(row, 0).text()
            val = float(table.item(row, 1).text())
            items.append(_CompositionItem(sym, val))
        return items

    def _on_ok(self):
        """确认添加材料到库。"""
        if not hasattr(self, '_pending_mat') or self._pending_mat is None:
            QMessageBox.warning(
                self, "Warning",
                "Please click 'Preview GDML' first to validate.")
            return

        if not self._last_gdml:
            QMessageBox.warning(
                self, "Warning",
                "GDML preview is empty. Please check your input.")
            return

        if isinstance(self._pending_mat, CompoundMaterial):
            self._mat_lib.add_compound(self._pending_mat)
        elif isinstance(self._pending_mat, MixtureMaterial):
            self._mat_lib.add_mixture(self._pending_mat)

        QMessageBox.information(
            self, "Success",
            f"Material '{self._pending_mat.mat_name}' has been added.")
        self.accept()

    def _apply_theme(self):
        self.setStyleSheet("""
            QGroupBox { font-size: 12px; font-weight: bold;
                         border: 1px solid #4a4a5a; border-radius: 4px;
                         margin-top: 8px; padding: 12px 8px 8px 8px; }
            QGroupBox::title { subcontrol-origin: margin;
                               left: 10px; padding: 0 4px; }
            QLineEdit, QDoubleSpinBox, QComboBox {
                padding: 3px 6px; font-size: 12px;
                border: 1px solid #4a4a5a; border-radius: 3px;
                background: #2a2a3a; color: #e0e0e0; }
            QPushButton {
                padding: 4px 12px; font-size: 12px;
                border: 1px solid #4a4a5a; border-radius: 3px;
                background: #3a3a4e; color: #e0e0e0; }
            QPushButton:hover { background: #4a4a5e; }
            QTableWidget {
                background: #2a2a3a; color: #e0e0e0;
                gridline-color: #3a3a4a; font-size: 12px; }
            QTableWidget::item { padding: 2px 4px; }
            QHeaderView::section {
                background: #3a3a4e; color: #b0b0c0;
                padding: 4px; border: 1px solid #4a4a5a; }
        """)
