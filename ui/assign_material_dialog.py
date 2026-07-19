"""
AssignMaterialDialog — 批量材料分配对话框。

与 cad2gdml 一致：
- 右键 → 子菜单内嵌 QComboBox（不是展开 flat 菜单项，也不是弹新窗口）
- 支持多选批量分配
- 纯亮色主题
"""

from typing import Optional, List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QAbstractItemView, QMenu, QWidget,
    QComboBox, QDialogButtonBox, QLabel, QWidgetAction,
)
from PyQt6.QtCore import Qt, QTimer, QEvent, QObject, pyqtSignal

from core.gdml_tree import GdmlNode, GdmlNodeType
from core.gdml_agent import GdmlAgent
from core.materials_lib import MaterialsLib


# ---- Column indices ----
COL_NODE_NAME = 0
COL_SOURCE_FILE = 1
COL_STATUS = 2
COL_MATERIAL = 3

HEADERS = ["Volume", "Source File", "Status", "Material"]

MAT_ASSIGNED = "✅"
MAT_UNASSIGNED = "❌"


class _ComboHoverWatcher(QObject):
    """Opens the combo popup on mouse hover for a better UX."""

    def __init__(self, combo: QComboBox, parent=None):
        super().__init__(parent)
        self._combo = combo
        combo.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self._combo and event.type() == QEvent.Type.Enter:
            QTimer.singleShot(0, self._combo.showPopup)
        return super().eventFilter(obj, event)


class AssignMaterialDialog(QDialog):
    """表格批量分配材料对话框。

    右键 assignable 行 → 子菜单 → 内嵌 QComboBox 选择 NIST/局部材料。
    支持多选批量分配（同 cad2gdml）。
    """

    materials_saved = pyqtSignal(int, int)  # assigned, total

    def __init__(self, gdml_agent: GdmlAgent, material_lib: MaterialsLib,
                 parent=None):
        super().__init__(parent)
        self._gdml_agent = gdml_agent
        self._mat_lib = material_lib

        # Flat list: (node, assignable)
        self._all_rows: List[tuple] = []
        self._solid_nodes: List[GdmlNode] = []

        self.setWindowTitle("Assign Materials")
        self.setMinimumSize(750, 500)
        self.resize(850, 600)

        self._build_ui()
        self._populate_table()
        self._apply_theme()

    # ---- UI Construction ----

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        header = QLabel("Select assignable rows, right-click to set material.")
        header.setObjectName("MatDlgHeader")
        layout.addWidget(header)

        self._table = QTableWidget()
        self._table.setColumnCount(len(HEADERS))
        self._table.setHorizontalHeaderLabels(HEADERS)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(False)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._table.verticalHeader().setVisible(False)
        self._table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(
            self._on_table_context_menu)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(COL_NODE_NAME,
                                  QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_SOURCE_FILE,
                                  QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_STATUS,
                                  QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_MATERIAL,
                                  QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table)

        # Bottom bar
        summary_layout = QHBoxLayout()
        self._summary_label = QLabel("0 nodes selected")
        self._summary_label.setObjectName("MatDlgSummary")
        summary_layout.addWidget(self._summary_label)
        summary_layout.addStretch()

        btn_box = QDialogButtonBox()
        save_btn = btn_box.addButton(
            "Save && Close", QDialogButtonBox.ButtonRole.AcceptRole)
        save_btn.clicked.connect(self._on_save)
        cancel_btn = btn_box.addButton(
            "Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        cancel_btn.clicked.connect(self.reject)
        summary_layout.addWidget(btn_box)
        layout.addLayout(summary_layout)

        self._table.itemSelectionChanged.connect(self._on_selection_changed)

    # ---- Data Population ----

    def _populate_table(self):
        """递归填充表格——只包含 assignable 的节点（VOLUME_NODE / WORLD_NODE）。"""
        self._all_rows = []
        self._solid_nodes = []
        self._table.setRowCount(0)

        for file_node in self._gdml_agent.get_all_file_nodes():
            self._append_node_rows(file_node)

        self._table.setRowCount(len(self._all_rows))

        for row, (node, assignable) in enumerate(self._all_rows):
            if assignable:
                self._solid_nodes.append(node)

            # Node name
            name_item = QTableWidgetItem(node.name)
            name_item.setToolTip(node.name)
            self._table.setItem(row, COL_NODE_NAME, name_item)

            # Source file
            src = self._get_source_file_name(node) if assignable else ""
            self._table.setItem(row, COL_SOURCE_FILE, QTableWidgetItem(src))

            # Status + Material
            if assignable:
                self._update_row_status(row, node)
            else:
                self._table.setItem(row, COL_STATUS, QTableWidgetItem(""))
                self._table.setItem(row, COL_MATERIAL, QTableWidgetItem(""))

    def _append_node_rows(self, node: GdmlNode):
        """递归展平树到 _all_rows。"""
        assignable = node.node_type in (GdmlNodeType.VOLUME_NODE,
                                         GdmlNodeType.WORLD_NODE)
        self._all_rows.append((node, assignable))
        for child in node.children:
            self._append_node_rows(child)

    def _get_source_file_name(self, node: GdmlNode) -> str:
        """回溯找到节点所属的 GDML 文件名。"""
        cur = node.parent
        while cur is not None and cur.node_type != GdmlNodeType.GDML_FILE:
            cur = cur.parent
        return cur.name if cur else ""

    def _update_row_status(self, row: int, node: GdmlNode):
        """刷新 ✅/❌ 和材料名为 assignable 行。"""
        mat = (node.material_name or "").strip()
        status_item = QTableWidgetItem(MAT_ASSIGNED if mat else MAT_UNASSIGNED)
        status_item.setToolTip("Assigned" if mat else "Not assigned")
        self._table.setItem(row, COL_STATUS, status_item)
        mat_item = QTableWidgetItem(mat)
        mat_item.setToolTip(mat)
        self._table.setItem(row, COL_MATERIAL, mat_item)

    # ---- Right-click Context Menu (embedded QComboBox, same as cad2gdml) ----

    def _on_table_context_menu(self, pos):
        """右键菜单——只有 assignable 行才弹出。"""
        # Collect selected assignable rows
        selected_rows = set()
        for item in self._table.selectedItems():
            selected_rows.add(item.row())
        if not selected_rows:
            return

        assignable_rows = {r for r in selected_rows
                           if self._all_rows[r][1]}
        if not assignable_rows:
            return

        menu = QMenu(self)

        # ---- Global Material submenu with embedded QComboBox ----
        global_menu = menu.addMenu("Global Material")
        global_names = self._mat_lib.get_nist_left_list()
        global_combo = QComboBox()
        global_combo.setPlaceholderText("Select global material...")
        global_combo.addItem("")  # empty = clear
        for name in global_names:
            global_combo.addItem(name)
        global_combo.currentTextChanged.connect(
            lambda txt, m=menu: (
                self._on_global_selected(txt, assignable_rows,
                                         global_combo),
                m.close()))
        wa = QWidgetAction(menu)
        wa.setDefaultWidget(global_combo)
        global_menu.addAction(wa)
        _ComboHoverWatcher(global_combo, self)

        # ---- Local Material submenu with embedded QComboBox ----
        local_menu = menu.addMenu("Local Material")
        local_names = self._mat_lib.get_local_material_names()
        local_combo = QComboBox()
        local_combo.setPlaceholderText("Select local material...")
        local_combo.addItem("")  # empty = clear
        for name in sorted(local_names):
            local_combo.addItem(name)
        local_combo.currentTextChanged.connect(
            lambda txt, m=menu: (
                self._on_local_selected(txt, assignable_rows,
                                        local_combo),
                m.close()))
        wa2 = QWidgetAction(menu)
        wa2.setDefaultWidget(local_combo)
        local_menu.addAction(wa2)
        _ComboHoverWatcher(local_combo, self)

        menu.addSeparator()
        clear_action = menu.addAction("❌ Clear Material")
        clear_action.triggered.connect(
            lambda: (self._clear_material(assignable_rows), menu.close()))

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _on_global_selected(self, text: str, rows: set,
                            global_cb: QComboBox):
        if not text:
            return
        self._apply_material_to_rows(text, rows)
        global_cb.blockSignals(True)
        global_cb.setCurrentIndex(0)
        global_cb.blockSignals(False)

    def _on_local_selected(self, text: str, rows: set,
                           local_cb: QComboBox):
        if not text:
            return
        self._apply_material_to_rows(text, rows)
        local_cb.blockSignals(True)
        local_cb.setCurrentIndex(0)
        local_cb.blockSignals(False)

    def _apply_material_to_rows(self, material_name: str, rows: set):
        for row in rows:
            node, assignable = self._all_rows[row]
            if not assignable:
                continue
            node.material_name = material_name
            self._update_row_status(row, node)

    def _clear_material(self, rows: set):
        for row in rows:
            node, assignable = self._all_rows[row]
            if not assignable:
                continue
            node.material_name = ""
            self._update_row_status(row, node)

    # ---- Selection Tracking ----

    def _on_selection_changed(self):
        rows = set()
        for item in self._table.selectedItems():
            rows.add(item.row())
        assignable = sum(1 for r in rows if self._all_rows[r][1])
        total = sum(1 for _, a in self._all_rows if a)
        self._summary_label.setText(
            f"{assignable}/{total} assignable node(s) selected")

    # ---- Save ----

    def _on_save(self):
        assigned = sum(1 for n in self._solid_nodes
                       if (n.material_name or "").strip())
        self.materials_saved.emit(assigned, len(self._solid_nodes))
        self.accept()

    # ---- Light Only Theme ----

    def _apply_theme(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
            }
            #MatDlgHeader {
                color: #2c2c2c;
                font-size: 13px;
                padding: 4px 0px;
            }
            #MatDlgSummary {
                color: #666666;
                font-size: 12px;
            }
            QTableWidget {
                background-color: #ffffff;
                color: #2c2c2c;
                gridline-color: #e0e0e0;
                border: 1px solid #cccccc;
                border-radius: 4px;
                font-size: 12px;
            }
            QTableWidget::item {
                padding: 4px 8px;
                background-color: transparent;
            }
            QTableWidget::item:selected {
                background-color: #0078d4;
                color: #ffffff;
            }
            QTableWidget:focus {
                outline: none;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                color: #333333;
                padding: 6px 8px;
                border: none;
                border-bottom: 1px solid #cccccc;
                font-weight: bold;
                font-size: 12px;
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
            QLabel {
                color: #2c2c2c;
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
            QMenu {
                background-color: #ffffff;
                color: #2c2c2c;
                border: 1px solid #d0d0d0;
                border-radius: 8px;
                padding: 4px;
                font-size: 12px;
            }
            QMenu::item {
                padding: 6px 24px 6px 12px;
                border-radius: 4px;
                min-height: 22px;
            }
            QMenu::item:selected {
                background-color: #e8f0fe;
                color: #1a1a1a;
            }
            QMenu::item:disabled {
                color: #aaaaaa;
            }
            QMenu::separator {
                height: 1px;
                background-color: #e0e0e0;
                margin: 4px 8px;
            }
        """)
