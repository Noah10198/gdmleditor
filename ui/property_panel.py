"""
PropertyPanel - Property Panel

Displays properties of the selected node, similar to cad2gdml's GeoParamWidget.
Supports:
  - Node basic info display
  - Solid parameters display
  - Placement info display
"""

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLabel,
    QGroupBox, QScrollArea
)

from core.gdml_tree import GdmlNode, Placement


class PropertyPanel(QWidget):
    """Property Panel"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_node: Optional[GdmlNode] = None
        self._dark_theme = True
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        title = QLabel("Properties")
        title.setObjectName("PropertyHeader")
        layout.addWidget(title)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)

        # Basic info
        self._info_group = QGroupBox("Info")
        info_layout = QFormLayout()
        self._name_label = QLabel("-")
        self._type_label = QLabel("-")
        self._entry_label = QLabel("-")
        self._mat_label = QLabel("-")
        info_layout.addRow("Name:", self._name_label)
        info_layout.addRow("Type:", self._type_label)
        info_layout.addRow("Entry ID:", self._entry_label)
        info_layout.addRow("Material:", self._mat_label)
        self._info_group.setLayout(info_layout)
        self._content_layout.addWidget(self._info_group)

        # Solid parameters
        self._solid_group = QGroupBox("Solid Parameters")
        self._solid_layout = QFormLayout()
        self._solid_group.setLayout(self._solid_layout)
        self._content_layout.addWidget(self._solid_group)

        # Placement
        self._placement_group = QGroupBox("Placement")
        self._placement_layout = QFormLayout()
        self._pos_x_label = QLabel("-")
        self._pos_y_label = QLabel("-")
        self._pos_z_label = QLabel("-")
        self._rot_x_label = QLabel("-")
        self._rot_y_label = QLabel("-")
        self._rot_z_label = QLabel("-")
        self._placement_layout.addRow("Pos X:", self._pos_x_label)
        self._placement_layout.addRow("Pos Y:", self._pos_y_label)
        self._placement_layout.addRow("Pos Z:", self._pos_z_label)
        self._placement_layout.addRow("Rot X:", self._rot_x_label)
        self._placement_layout.addRow("Rot Y:", self._rot_y_label)
        self._placement_layout.addRow("Rot Z:", self._rot_z_label)
        self._placement_group.setLayout(self._placement_layout)
        self._content_layout.addWidget(self._placement_group)

        self._content_layout.addStretch()
        self._scroll.setWidget(content)
        layout.addWidget(self._scroll)

    def set_dark_theme(self, is_dark: bool):
        """Switch between dark and light appearance."""
        self._dark_theme = is_dark
        if is_dark:
            bg = "#1e1e2e"
            hdr_fg = "#cdd6f4"
            grp_fg = "#a6adc8"
            grp_border = "#313244"
            lbl_fg = "#cdd6f4"
        else:
            bg = "#f5f5f5"
            hdr_fg = "#2c2c2c"
            grp_fg = "#555555"
            grp_border = "#d0d0d0"
            lbl_fg = "#2c2c2c"

        self.setStyleSheet(f"""
            PropertyPanel {{
                background-color: {bg};
            }}
            QLabel {{
                color: {lbl_fg};
                font-size: 12px;
            }}
            QLabel#PropertyHeader {{
                font-size: 14px;
                font-weight: bold;
                color: {hdr_fg};
                padding: 4px 0px;
            }}
            QGroupBox {{
                font-size: 13px;
                font-weight: bold;
                color: {grp_fg};
                border: 1px solid {grp_border};
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 16px;
                background-color: transparent;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 2px 8px;
                color: {grp_fg};
            }}
            QScrollArea {{
                background-color: {bg};
                border: none;
            }}
        """)
        # Also set scroll area viewport background
        if hasattr(self, '_scroll') and self._scroll:
            self._scroll.viewport().setStyleSheet(f"background-color: {bg};")

    def show_node(self, node: Optional[GdmlNode]):
        """Display node properties"""
        self._current_node = node
        if node is None:
            self._name_label.setText("-")
            self._type_label.setText("-")
            self._entry_label.setText("-")
            self._mat_label.setText("-")
            self._clear_form(self._solid_layout)
            self._update_placement(None)
            return

        self._name_label.setText(node.name)
        self._type_label.setText(f"{node.node_type.name} ({node.gdml_tag})")
        self._entry_label.setText(node.entry_id)
        self._mat_label.setText(node.material_name)

        # Solid parameters
        self._clear_form(self._solid_layout)
        if node.solid_params:
            for key, value in node.solid_params.items():
                label = QLabel(f"{key}:")
                value_label = QLabel(f"{value:.4f}")
                self._solid_layout.addRow(label, value_label)

        # Placement
        self._update_placement(node.placement)

        self._solid_group.setVisible(bool(node.solid_params))
        self._placement_group.setVisible(node.placement is not None)

    def _update_placement(self, placement: Optional[Placement]):
        """Update placement display"""
        if placement is None:
            self._pos_x_label.setText("-")
            self._pos_y_label.setText("-")
            self._pos_z_label.setText("-")
            self._rot_x_label.setText("-")
            self._rot_y_label.setText("-")
            self._rot_z_label.setText("-")
        else:
            self._pos_x_label.setText(f"{placement.x:.4f}")
            self._pos_y_label.setText(f"{placement.y:.4f}")
            self._pos_z_label.setText(f"{placement.z:.4f}")
            self._rot_x_label.setText(f"{placement.rot_x:.2f}\u00b0")
            self._rot_y_label.setText(f"{placement.rot_y:.2f}\u00b0")
            self._rot_z_label.setText(f"{placement.rot_z:.2f}\u00b0")

    def _clear_form(self, form_layout: QFormLayout):
        """Clear form"""
        while form_layout.rowCount() > 0:
            form_layout.removeRow(0)
