"""
ProjectTreeWidget - Project Tree Widget

Aligns with cad2gdml's ProjectTreeWidget style:
- QWidget with QLabel header + internal QTreeWidget
- No type prefix labels like [File] [Vol] [Phys]
- Uniform text color (no per-type color coding)
- Clean, minimal look
- Supports checkbox visibility control and selection
"""

from typing import Optional

from PyQt6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QWidget, QVBoxLayout, QLabel
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QFont

from core.gdml_tree import GdmlNode, GdmlNodeType


# Custom data roles
TREE_ITEM_DATA_ROLE = Qt.ItemDataRole.UserRole + 1  # Stores entry_id
TREE_NODE_TYPE_ROLE = Qt.ItemDataRole.UserRole + 2  # Stores GdmlNodeType value


class ProjectTreeWidget(QWidget):
    """Project Tree Widget — matches cad2gdml's appearance."""

    node_selected = pyqtSignal(str)       # Node selected, emits entry_id
    visibility_changed = pyqtSignal(str, bool)  # Visibility changed

    def __init__(self, parent=None):
        super().__init__(parent)
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

        # Geometry root node (matches cad2gdml's "Geometry" root)
        self._geometry_root = QTreeWidgetItem(self._tree, ["Geometry"])
        self._geometry_root.setExpanded(True)

        layout.addWidget(self._tree)

        # Apply dark theme by default
        self.set_dark_theme(True)

        # Connect signals
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemChanged.connect(self._on_item_changed)

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

    def clear_tree(self):
        """Clear the geometry tree (preserves root)."""
        for child in self._geometry_root.takeChildren():
            del child

    def build_from_node_tree(self, root_node: GdmlNode):
        """
        Build QTreeWidget from GdmlNode tree — clean display, no type prefixes.

        Args:
            root_node: GdmlNode root node
        """
        self.clear_tree()

        for file_node in root_node.children:
            if file_node.node_type != GdmlNodeType.GDML_FILE:
                continue
            file_item = self._create_tree_item(file_node)
            self._geometry_root.addChild(file_item)
            self._build_recursive(file_item, file_node)

        self._geometry_root.setExpanded(True)

    def _build_recursive(self, parent_item: QTreeWidgetItem, node: GdmlNode):
        """Recursively build child nodes."""
        for child in node.children:
            child_item = self._create_tree_item(child)
            parent_item.addChild(child_item)
            self._build_recursive(child_item, child)

    def _create_tree_item(self, node: GdmlNode) -> QTreeWidgetItem:
        """Create tree item from node — clean name, no type prefix."""
        item = QTreeWidgetItem()
        # Clean display name: just the name, no [File] [Vol] etc.
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
            params_str = ", ".join(f"{k}={v:.2f}" for k, v in node.solid_params.items())
            lines.append(f"Params: {params_str}")
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
        """Select tree item by entry_id."""
        item = self._find_item_by_entry_id(self._tree.invisibleRootItem(), entry_id)
        if item:
            self._tree.setCurrentItem(item)
            # Expand parents to make selected item visible
            p = item.parent()
            while p:
                p.setExpanded(True)
                p = p.parent()

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
