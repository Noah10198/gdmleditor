"""
ProjectTreeWidget - Project Tree Widget

Aligns with cad2gdml's ProjectTreeWidget style:
- QWidget with QLabel header + internal QTreeWidget
- No type prefix labels like [File] [Vol] [Phys]
- Uniform text color (no per-type color coding)
- Clean, minimal look
- Supports checkbox visibility control and selection
- Global/Local Materials nodes (reuse from cad2gdml)
"""

from typing import Optional, List

from PyQt6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QWidget, QVBoxLayout, QLabel, QMenu, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QFont

from core.gdml_tree import GdmlNode, GdmlNodeType
from core.materials_lib import MaterialsLib


# Custom data roles
TREE_ITEM_DATA_ROLE = Qt.ItemDataRole.UserRole + 1  # Stores entry_id
TREE_NODE_TYPE_ROLE = Qt.ItemDataRole.UserRole + 2  # Stores GdmlNodeType value


class ProjectTreeWidget(QWidget):
    """Project Tree Widget — matches cad2gdml's appearance."""

    node_selected = pyqtSignal(str)       # Node selected, emits entry_id
    visibility_changed = pyqtSignal(str, bool)  # Visibility changed
    solid_preview_requested = pyqtSignal(str)   # Right-click solid -> preview in 3D
    delete_geometry_requested = pyqtSignal(str) # Delete GDML file by entry_id
    transform_requested = pyqtSignal(str)       # Right-click volume/file -> edit transform

    # Material signals (matches cad2gdml)
    assign_material_requested = pyqtSignal()
    add_local_material_requested = pyqtSignal()
    remove_local_material_requested = pyqtSignal(str)   # material name
    save_local_materials_requested = pyqtSignal()
    load_local_materials_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mat_lib: Optional[MaterialsLib] = None
        self._global_mat_root: Optional[QTreeWidgetItem] = None
        self._local_mat_root: Optional[QTreeWidgetItem] = None
        self._setup_ui()

    def _setup_ui(self):
        """Build the tree and header label — same pattern as cad2gdml."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel("  Project Tree")
        header.setObjectName("TreeHeader")
        header.setFixedHeight(28)
        layout.addWidget(header)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setColumnCount(1)
        self._tree.setMinimumWidth(180)
        self._tree.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        self._tree.setSelectionBehavior(QTreeWidget.SelectionBehavior.SelectRows)
        self._tree.setAnimated(True)
        self._tree.setIndentation(16)

        # Material nodes first (matches cad2gdml: Global → Local → Geometry)
        self._global_mat_root = QTreeWidgetItem(self._tree, ["Global Materials"])
        self._global_mat_root.setExpanded(False)  # 278 items, keep collapsed
        self._global_mat_root.setFlags(self._global_mat_root.flags()
                                        & ~Qt.ItemFlag.ItemIsUserCheckable)

        self._local_mat_root = QTreeWidgetItem(self._tree, ["Local Materials"])
        self._local_mat_root.setExpanded(True)
        self._local_mat_root.setFlags(self._local_mat_root.flags()
                                       & ~Qt.ItemFlag.ItemIsUserCheckable)

        # Geometry root node (after materials, matching cad2gdml)
        self._geometry_root = QTreeWidgetItem(self._tree, ["Geometry"])
        self._geometry_root.setExpanded(True)

        layout.addWidget(self._tree)

        # Apply dark theme by default
        self.set_dark_theme(True)

        # Connect signals
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def set_dark_theme(self, is_dark: bool):
        """Switch between dark and light appearance — matches cad2gdml's palette."""
        if is_dark:
            hdr_bg = "#181825"
            hdr_fg = "#a6adc8"
            hdr_border = "#313244"
            tree_bg = "#1e1e2e"
            tree_fg = "#cdd6f4"
            sel_bg = "#313244"
            sel_fg = "#cdd6f4"
            hover_bg = "#282840"
        else:
            hdr_bg = "#e8e8e8"
            hdr_fg = "#555555"
            hdr_border = "#d0d0d0"
            tree_bg = "#ffffff"
            tree_fg = "#2c2c2c"
            sel_bg = "#d0e4f6"
            sel_fg = "#2c2c2c"
            hover_bg = "#e8f0fe"

        self.setStyleSheet(f"""
            #TreeHeader {{
                background-color: {hdr_bg};
                color: {hdr_fg};
                font-size: 13px;
                font-weight: bold;
                padding: 4px 8px;
                border-bottom: 1px solid {hdr_border};
            }}
            QTreeWidget {{
                background-color: {tree_bg};
                color: {tree_fg};
                border: none;
                font-size: 13px;
                outline: none;
            }}
            QTreeWidget::item {{
                padding: 4px 2px;
                border: none;
            }}
            QTreeWidget::item:selected {{
                background-color: {sel_bg};
                color: {sel_fg};
            }}
            QTreeWidget::item:hover {{
                background-color: {hover_bg};
            }}
        """)

    # ==================== Material Library ====================

    def set_material_lib(self, mat_lib: MaterialsLib):
        """Set MaterialsLib reference."""
        self._mat_lib = mat_lib

    def populate_global_materials(self, mat_names: List[str]):
        """Populate the Global Materials tree node (matches cad2gdml)."""
        self._global_mat_root.takeChildren()
        for name in mat_names:
            item = QTreeWidgetItem(self._global_mat_root, [name])
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(0, Qt.ItemDataRole.UserRole, f"__mat__:{name}")

    def populate_local_materials(self, mat_lib: Optional[MaterialsLib] = None):
        """Populate the Local Materials tree node (matches cad2gdml)."""
        from core.materials_lib import CustomElement
        lib = mat_lib or self._mat_lib
        if lib is None:
            return
        self._local_mat_root.takeChildren()
        for mat in lib.get_all_local_materials():
            # Custom element: display symbol only (matches cad2gdml)
            if isinstance(mat, CustomElement):
                name = mat.symbol
            else:
                name = getattr(mat, 'mat_name',
                               getattr(mat, 'name', 'unnamed'))
            mat_id = getattr(mat, 'mat_id', '')
            item = QTreeWidgetItem(self._local_mat_root, [name])
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(0, Qt.ItemDataRole.UserRole, f"__local__:{mat_id}")

    def refresh_materials(self):
        """Refresh all material tree nodes from library."""
        if self._mat_lib:
            self.populate_global_materials(self._mat_lib.get_nist_list())
            self.populate_local_materials(self._mat_lib)

    # ==================== Context Menu ====================

    def _on_context_menu(self, pos):
        """Handle right-click context menu."""
        item = self._tree.itemAt(pos)
        if item is None:
            return

        # Local Materials root (matches cad2gdml emoji icons)
        if item is self._local_mat_root:
            menu = QMenu(self)
            add_act = menu.addAction("➕ Add Material...")
            add_act.triggered.connect(self.add_local_material_requested.emit)
            menu.addSeparator()
            save_act = menu.addAction("💾 Save Materials...")
            save_act.triggered.connect(self.save_local_materials_requested.emit)
            load_act = menu.addAction("📂 Load Materials...")
            load_act.triggered.connect(self.load_local_materials_requested.emit)
            menu.exec(self._tree.viewport().mapToGlobal(pos))
            return

        # Local Material item (delete, matches cad2gdml emoji)
        if item.parent() is self._local_mat_root:
            menu = QMenu(self)
            del_act = menu.addAction("❌ Delete Material")
            action = menu.exec(self._tree.viewport().mapToGlobal(pos))
            if action == del_act:
                mat_name = item.text(0)
                self.remove_local_material_requested.emit(mat_name)
            return

        # Solid under Solids group: preview in 3D
        node_type_val = item.data(0, TREE_NODE_TYPE_ROLE)
        if node_type_val == GdmlNodeType.SOLID_DEF.value:
            menu = QMenu(self)
            preview_act = menu.addAction("🔍 Preview in 3D")
            action = menu.exec(self._tree.viewport().mapToGlobal(pos))
            if action == preview_act:
                entry_id = item.data(0, TREE_ITEM_DATA_ROLE)
                if entry_id:
                    self.solid_preview_requested.emit(entry_id)
            return

        # GDML file node: delete + file-level transform
        if node_type_val == GdmlNodeType.GDML_FILE.value:
            menu = QMenu(self)
            edit_act = menu.addAction("Edit Transform...")
            menu.addSeparator()
            del_act = menu.addAction("❌ Delete File")
            action = menu.exec(self._tree.viewport().mapToGlobal(pos))
            entry_id = item.data(0, TREE_ITEM_DATA_ROLE)
            if entry_id:
                if action == edit_act:
                    self.transform_requested.emit(entry_id)
                elif action == del_act:
                    self.delete_geometry_requested.emit(entry_id)
            return

        # Volume instance under World: edit physvol placement
        if node_type_val == GdmlNodeType.VOLUME_NODE.value:
            menu = QMenu(self)
            edit_act = menu.addAction("Edit Transform...")
            action = menu.exec(self._tree.viewport().mapToGlobal(pos))
            if action == edit_act:
                entry_id = item.data(0, TREE_ITEM_DATA_ROLE)
                if entry_id:
                    self.transform_requested.emit(entry_id)
            return

    # ==================== Geometry Tree ====================

    def clear_tree(self):
        """Clear the geometry tree (preserves root)."""
        for child in self._geometry_root.takeChildren():
            del child

    def build_from_node_tree(self, root_node: GdmlNode):
        """
        Build QTreeWidget from GdmlNode tree.

        Structure:
          filename.gdml
            +-- Solids (all solid definitions, no checkbox)
            |   +-- solid1
            |   +-- ...
            +-- World (volume hierarchy, no SOLID_DEF children)
                +-- world_vol
                    +-- ...
        """
        self.clear_tree()

        for file_node in root_node.children:
            if file_node.node_type != GdmlNodeType.GDML_FILE:
                continue
            file_item = self._create_tree_item(file_node)
            self._geometry_root.addChild(file_item)
            self._build_file_tree(file_item, file_node)

        self._geometry_root.setExpanded(True)

    def _build_file_tree(self, file_item: QTreeWidgetItem, file_node: GdmlNode):
        """Build Solids + World groups under a file node."""
        # Collect all SOLID_DEF nodes from the entire subtree
        solid_nodes: List[GdmlNode] = []
        self._collect_solid_nodes(file_node, solid_nodes)

        # Create "Solids" group (only if there are solids)
        if solid_nodes:
            solids_item = QTreeWidgetItem(file_item, ["Solids"])
            solids_item.setFlags(solids_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)

            for solid_node in solid_nodes:
                solid_item = self._create_tree_item(solid_node)
                # No checkbox for solids (info-only nodes)
                solid_item.setFlags(solid_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                solids_item.addChild(solid_item)

        # Create "World" group — only show the physical hierarchy starting from
        # WORLD_NODE. Other VOLUME_NODEs under file_node are logical definitions
        # (Geant4 LogicalVolumeStore) and are not shown in the hierarchy.
        world_node = next(
            (c for c in file_node.children if c.node_type == GdmlNodeType.WORLD_NODE),
            None
        )
        if world_node:
            world_item = QTreeWidgetItem(file_item, ["World"])
            world_item.setFlags(world_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            self._build_world_tree(world_item, world_node)

    @staticmethod
    def _collect_solid_nodes(node: GdmlNode, result: List[GdmlNode]):
        """Recursively collect all SOLID_DEF nodes (avoid duplicates)."""
        if node.node_type == GdmlNodeType.SOLID_DEF and node not in result:
            result.append(node)
        for child in node.children:
            ProjectTreeWidget._collect_solid_nodes(child, result)

    def _build_world_tree(self, parent_item: QTreeWidgetItem, node: GdmlNode):
        """Build world hierarchy — show only logical physical bodies.

        - SOLID_DEF: skipped (shown in "Solids" group only)
        - PHYVOL_NODE: skipped (wrapper node; its instance children appear
          directly under the parent, showing the clean physical hierarchy)
        - instance VOLUME_NODE: shown as a direct child of its logical parent
        """
        if node.node_type in (GdmlNodeType.SOLID_DEF, GdmlNodeType.PHYVOL_NODE):
            for child in node.children:
                self._build_world_tree(parent_item, child)
            return
        child_item = self._create_tree_item(node)
        parent_item.addChild(child_item)
        for child in node.children:
            self._build_world_tree(child_item, child)

    def _create_tree_item(self, node: GdmlNode) -> QTreeWidgetItem:
        """Create tree item from node — clean name, no type prefix."""
        item = QTreeWidgetItem()
        display_name = node.name if node.name else "(unnamed)"
        item.setText(0, display_name)
        item.setData(0, TREE_ITEM_DATA_ROLE, node.entry_id)
        item.setData(0, TREE_NODE_TYPE_ROLE, node.node_type.value)
        item.setData(0, Qt.ItemDataRole.ToolTipRole, self._get_tooltip(node))

        # Checkbox
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Checked if node.visible else Qt.CheckState.Unchecked)

        return item

    def _get_tooltip(self, node: GdmlNode) -> str:
        """Get tooltip text."""
        lines = [f"Name: {node.name}",
                 f"Type: {node.node_type.name}",
                 f"GDML Tag: {node.gdml_tag}",
                 f"Material: {node.material_name}",
                 f"Entry ID: {node.entry_id}"]
        if node.solid_params:
            parts = []
            for k, v in node.solid_params.items():
                if isinstance(v, (int, float)):
                    parts.append(f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v}")
                elif isinstance(v, str):
                    parts.append(f"{k}={v}")
                elif isinstance(v, dict):
                    parts.append(f"{k}={len(v)} items")
                elif isinstance(v, (list, tuple)):
                    parts.append(f"{k}={len(v)} items")
            if parts:
                lines.append(f"Params: {', '.join(parts)}")
        if node.placement:
            p = node.placement
            lines.append(f"Position: ({p.x:.2f}, {p.y:.2f}, {p.z:.2f})")
        return "\n".join(lines)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle click event — emit node selection only.

        NOTE: Checkbox toggling is handled by _on_item_changed, NOT here.
        The itemClicked signal fires BEFORE Qt updates the check state,
        so reading checkState() here would return the stale old value.
        """
        if item is self._geometry_root:
            return

        # Material items (matches cad2gdml: emit __mat__:xxx / __local__:xxx)
        user_data = item.data(0, Qt.ItemDataRole.UserRole) or ""
        if user_data.startswith("__mat__:") or user_data.startswith("__local__:"):
            self.node_selected.emit(user_data)
            return

        # Geometry items
        entry_id = item.data(0, TREE_ITEM_DATA_ROLE)
        if entry_id:
            self.node_selected.emit(entry_id)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        """Handle checkbox state cascade (matches cad2gdml's behavior)."""
        if column != 0 or item is self._geometry_root:
            return
        if item.data(0, TREE_ITEM_DATA_ROLE) is None:
            return

        state = item.checkState(0)
        if state == Qt.CheckState.PartiallyChecked:
            return

        # Cascade to children
        if item.childCount() > 0:
            self._tree.blockSignals(True)
            self._cascade_check_state(item, state)
            self._tree.blockSignals(False)

        # Emit visibility for all leaves under this item
        self._emit_visibility_for_leaves(item, state)

    def _cascade_check_state(self, parent_item: QTreeWidgetItem, state: Qt.CheckState):
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            child.setCheckState(0, state)
            self._cascade_check_state(child, state)

    def _emit_visibility_for_leaves(self, item: QTreeWidgetItem, state: Qt.CheckState):
        """Emit visibility signals for ALL items that have 3D actors.

        A node like VOLUME_NODE has an actor even if it also has children
        (SOLID_DEF sub-items). So we check EVERY item for actor type,
        not just leaf items.
        """
        # 1) Emit for this item if it has a 3D actor
        eid = item.data(0, TREE_ITEM_DATA_ROLE)
        if eid and self._has_actor_type(item):
            self.visibility_changed.emit(
                eid, state == Qt.CheckState.Checked
            )

        # 2) Recurse into children
        for i in range(item.childCount()):
            self._emit_visibility_for_leaves(item.child(i), state)

    def _has_actor_type(self, item: QTreeWidgetItem) -> bool:
        """Check if this tree item's node type has a 3D actor in the scene."""
        nt = item.data(0, TREE_NODE_TYPE_ROLE)
        # Only VOLUME_NODE (6) and WORLD_NODE (9) create actors
        return nt in (6, 9)

    def select_item_by_entry_id(self, entry_id: str):
        """Select tree item by entry_id (geometry nodes)."""
        item = self._find_item_by_entry_id(self._tree.invisibleRootItem(), entry_id)
        if item:
            self._tree.setCurrentItem(item)
            # Expand parents to make selected item visible
            p = item.parent()
            while p:
                p.setExpanded(True)
                p = p.parent()

    def select_local_material(self, mat_id: str):
        """Select a local material item by its mat_id."""
        target_data = f"__local__:{mat_id}"
        for i in range(self._local_mat_root.childCount()):
            child = self._local_mat_root.child(i)
            if child.data(0, Qt.ItemDataRole.UserRole) == target_data:
                self._tree.setCurrentItem(child)
                self._local_mat_root.setExpanded(True)
                return

    def _find_item_by_entry_id(self, parent: QTreeWidgetItem, entry_id: str) -> Optional[QTreeWidgetItem]:
        """Recursively search for item with given entry_id."""
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.data(0, TREE_ITEM_DATA_ROLE) == entry_id:
                return child
            result = self._find_item_by_entry_id(child, entry_id)
            if result:
                return result
        return None
