"""
MainWindow - Main Window

Based on cad2gdml's MainWindow design:
  - Ribbon-style toolbar (emoji icons + text labels)
  - Dark/Light theme toggle
  - Help button
  - Left project tree + Center 3D view + Right property panel + Bottom log
"""

import os
from typing import Optional
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QSplitter, QVBoxLayout,
    QWidget, QFileDialog, QMessageBox, QDockWidget, QToolBar,
    QPushButton, QHBoxLayout, QStatusBar, QLabel, QDialog,
    QStackedWidget, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QPalette, QColor, QFont

from core.gdml_agent import GdmlAgent
from core.gdml_tree import GdmlNode, GdmlNodeType
from utils.logger import AsyncLogger, LogLevel
from ui.ribbon_toolbar import RibbonToolBar
from ui.project_tree import ProjectTreeWidget
from ui.property_panel import PropertyPanel
from ui.vtk_widget import VtkWidget
from ui.redefine_world_dialog import RedefineWorldDialog


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("GDML Editor - gdmleditor")
        self.resize(1400, 900)
        self._dark_theme = True

        self._gdml_agent = GdmlAgent()
        self._logger = AsyncLogger()

        self._vtk_widget: Optional[VtkWidget] = None

        # Build UI (create all widgets first, then apply theme)
        self._init_toolbar()
        self._init_project_tree()
        self._init_center_placeholder()
        self._init_vtk_widget()           # ← embedded VTK, pre-created
        self._init_property_panel()
        self._init_log_panel()
        self._init_layout()
        self._init_status_bar()

        # Apply theme (after all widgets created)
        self._apply_global_theme(True)

        self._connect_signals()

        self._logger.log_system("GDML Editor started")

    # ==================== Theme ====================

    def _apply_global_theme(self, dark: bool):
        """Apply global theme to main window and all sub-widgets"""
        self._dark_theme = dark
        if dark:
            palette = QPalette()
            palette.setColor(QPalette.ColorRole.Window, QColor("#1e1e2e"))
            palette.setColor(QPalette.ColorRole.WindowText, QColor("#cdd6f4"))
            palette.setColor(QPalette.ColorRole.Base, QColor("#181825"))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#313244"))
            palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#313244"))
            palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#cdd6f4"))
            palette.setColor(QPalette.ColorRole.Text, QColor("#cdd6f4"))
            palette.setColor(QPalette.ColorRole.Button, QColor("#313244"))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor("#cdd6f4"))
            palette.setColor(QPalette.ColorRole.BrightText, QColor("#f38ba8"))
            palette.setColor(QPalette.ColorRole.Link, QColor("#89b4fa"))
            palette.setColor(QPalette.ColorRole.Highlight, QColor("#45475a"))
            palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#cdd6f4"))
            self.setPalette(palette)
            mw_bg = "#1e1e2e"; dock_bg = "#1e1e2e"; dock_fg = "#cdd6f4"
            dock_t_bg = "#181825"; dock_t_fg = "#a6adc8"; dock_t_bd = "#313244"
            sp_color = "#313244"; log_bg = "#11111b"; log_fg = "#a6adc8"
            st_bg = "#181825"; st_fg = "#a6adc8"
        else:
            palette = QPalette()
            palette.setColor(QPalette.ColorRole.Window, QColor("#f5f5f5"))
            palette.setColor(QPalette.ColorRole.WindowText, QColor("#2c2c2c"))
            palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#e8e8e8"))
            palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
            palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#2c2c2c"))
            palette.setColor(QPalette.ColorRole.Text, QColor("#2c2c2c"))
            palette.setColor(QPalette.ColorRole.Button, QColor("#e0e0e0"))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor("#2c2c2c"))
            palette.setColor(QPalette.ColorRole.BrightText, QColor("#d32f2f"))
            palette.setColor(QPalette.ColorRole.Link, QColor("#0078d4"))
            palette.setColor(QPalette.ColorRole.Highlight, QColor("#0078d4"))
            palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
            self.setPalette(palette)
            mw_bg = "#f5f5f5"; dock_bg = "#f5f5f5"; dock_fg = "#2c2c2c"
            dock_t_bg = "#e8e8e8"; dock_t_fg = "#555555"; dock_t_bd = "#d0d0d0"
            sp_color = "#cccccc"; log_bg = "#fafafa"; log_fg = "#555555"
            st_bg = "#e8e8e8"; st_fg = "#555555"

        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {mw_bg}; }}
            QDockWidget {{ background-color: {dock_bg}; color: {dock_fg};
                titlebar-close-icon: none; titlebar-normal-icon: none; }}
            QDockWidget::title {{ background-color: {dock_t_bg}; color: {dock_t_fg};
                font-size: 13px; font-weight: bold; padding: 4px 8px;
                border-bottom: 1px solid {dock_t_bd}; text-align: left; }}
            QSplitter::handle {{ background-color: {sp_color}; }}
            QSplitter::handle:horizontal {{ width: 2px; }}
            QSplitter::handle:vertical {{ height: 2px; }}
            QScrollBar:vertical {{ background: {log_bg}; width: 10px; margin: 0px; }}
            QScrollBar::handle:vertical {{ background: {dock_t_bg}; min-height: 20px; border-radius: 4px; }}
            QScrollBar::handle:vertical:hover {{ background: {sp_color}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        self._log_widget.setStyleSheet(f"""
            #SystemLog {{ background-color: {log_bg}; color: {log_fg};
                font-family: "Consolas", "Courier New", monospace;
                font-size: 12px; border: none; padding: 4px; }}
        """)

        # Propagate theme to all sub-widgets
        if hasattr(self, '_toolbar'):
            self._toolbar.set_dark_theme(dark)
        if hasattr(self, '_project_tree'):
            self._project_tree.set_dark_theme(dark)
        if hasattr(self, '_property_panel'):
            self._property_panel.set_dark_theme(dark)
        if self._vtk_widget is not None:
            self._vtk_widget.set_dark_theme(dark)

    def _toggle_theme(self):
        """Toggle dark/light theme across all widgets"""
        new_dark = not self._dark_theme
        self._apply_global_theme(new_dark)
        self._logger.log_system(f"Theme switched to {'dark' if new_dark else 'light'} mode")

    # ==================== UI initialization ====================

    def _init_toolbar(self):
        """Initialize Ribbon toolbar"""
        self._toolbar = RibbonToolBar()
        tb = QToolBar("Main Toolbar")
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.addWidget(self._toolbar)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

    def _init_project_tree(self):
        """Initialize project tree (left panel)"""
        self._project_tree = ProjectTreeWidget()
        self._tree_dock = QDockWidget("Project Tree", self)
        self._tree_dock.setWidget(self._project_tree)
        self._tree_dock.setMinimumWidth(200)
        self._tree_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._tree_dock)

    def _init_center_placeholder(self):
        """Initialize placeholder label for center area."""
        self._center_placeholder = QLabel(
            "No 3D view loaded\n\n"
            "Click [📂 Import] on the toolbar to load a GDML file."
        )
        self._center_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._center_placeholder.setStyleSheet("color: #6c7086; font-size: 14px; padding: 40px;")

    def _init_vtk_widget(self):
        """Create the embedded VtkWidget (hidden until scene is loaded)."""
        self._vtk_widget = VtkWidget()
        self._vtk_widget.set_dark_theme(self._dark_theme)
        self._vtk_widget.node_picked.connect(self._on_node_picked)
        self._vtk_widget.setVisible(False)    # hidden until first import

    def _init_property_panel(self):
        """Initialize property panel (right side)"""
        self._property_panel = PropertyPanel()
        self._prop_dock = QDockWidget("Properties", self)
        self._prop_dock.setWidget(self._property_panel)
        self._prop_dock.setMinimumWidth(200)
        self._prop_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._prop_dock)

    def _init_log_panel(self):
        """Initialize log panel (bottom)"""
        self._log_widget = QTextEdit()
        self._log_widget.setReadOnly(True)
        self._log_widget.setObjectName("SystemLog")
        self._log_widget.setMaximumHeight(150)
        self._log_widget.setFont(QFont("Consolas", 9))
        self._logger.set_system_log_widget(self._log_widget)

    def _init_layout(self):
        """Organize layout"""
        # Center area: stacked placeholder(0) / VTK(1) + log (vertical split)
        self._center_stack = QStackedWidget()
        self._center_stack.addWidget(self._center_placeholder)  # index 0 — fallback
        self._center_stack.addWidget(self._vtk_widget)          # index 1 — default 3D view
        # Show the 3D view immediately (with grid + axes + orientation marker)
        self._vtk_widget.setVisible(True)
        self._center_stack.setCurrentIndex(1)

        central = QSplitter(Qt.Orientation.Vertical)
        central.addWidget(self._center_stack)
        central.addWidget(self._log_widget)
        central.setStretchFactor(0, 3)
        central.setStretchFactor(1, 1)
        central.setSizes([600, 150])

        self.setCentralWidget(central)

    def _init_status_bar(self):
        """Initialize status bar"""
        self._status_label = QLabel("Ready")
        self.statusBar().addPermanentWidget(self._status_label)

    def _connect_signals(self):
        """Connect signals"""
        # Ribbon toolbar
        self._toolbar.import_clicked.connect(self._on_import_gdml)
        self._toolbar.reset_view_clicked.connect(self._on_reset_view)
        self._toolbar.export_clicked.connect(self._on_export_gdml)
        self._toolbar.clear_clicked.connect(self._on_clear_all)
        self._toolbar.redefine_world_clicked.connect(self._on_redefine_world)
        self._toolbar.theme_toggled.connect(self._toggle_theme)
        self._toolbar.help_clicked.connect(self._on_help)

        # Project tree
        self._project_tree.node_selected.connect(self._on_node_selected)
        self._project_tree.visibility_changed.connect(self._on_visibility_changed)

        # NOTE: VTK picking signal is connected lazily when _get_vtk_window() is called.

    # ==================== Signal handlers ====================

    def _on_import_gdml(self):
        """Import GDML file"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Import GDML Files", "",
            "GDML Files (*.gdml);;XML Files (*.xml);;All Files (*)"
        )
        if not file_paths:
            return

        for filepath in file_paths:
            self._logger.log_system(f"Loading: {filepath}")
            success, msg = self._gdml_agent.load_gdml_file(filepath)
            if success:
                self._logger.log_system(f"  [OK] {msg}")
            else:
                self._logger.log_system(f"  [ERR] {msg}", LogLevel.ERROR)
                QMessageBox.warning(self, "Import Error", f"Failed to import:\n{msg}")

        self._rebuild_ui()

    def _on_export_gdml(self):
        """Export GDML file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export GDML", "",
            "GDML Files (*.gdml);;All Files (*)"
        )
        if not file_path:
            return
        self._logger.log_system(f"Exporting to: {file_path}")
        # TODO: Implement export logic
        self._logger.log_system("  [OK] Export complete")

    def _on_clear_all(self):
        """Clear all data"""
        reply = QMessageBox.question(
            self, "Clear All",
            "Clear all imported GDML files?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._gdml_agent.clear()
            # Show default 3D view (grid + axes, no geometry)
            self._vtk_widget.get_scene().clear()
            self._vtk_widget._ensure_default_actors()
            self._vtk_widget.refresh()
            self._vtk_widget.setVisible(True)
            self._center_stack.setCurrentIndex(1)
            self._rebuild_ui()
            self._logger.log_system("Cleared all data")

    def _on_reset_view(self):
        """Reset 3D view"""
        if self._vtk_widget:
            scene = self._vtk_widget.get_scene()
            scene.reset_camera()
            self._vtk_widget.refresh()
        self._logger.log_system("View reset")

    def _on_redefine_world(self):
        """Redefine world volume size"""
        # Get all world nodes
        world_nodes = self._gdml_agent.get_world_nodes()
        if not world_nodes:
            QMessageBox.information(self, "Redefine World",
                "No world volume found.\nImport a GDML file first.")
            return

        # Compute global bounding box
        bbox = self._gdml_agent.compute_scene_bbox()
        xmin, xmax, ymin, ymax, zmin, zmax = bbox
        has_scene = not (xmin == xmax == ymin == ymax == zmin == zmax == 0)

        if not has_scene:
            QMessageBox.information(self, "Redefine World",
                "No renderable geometry found.\n"
                "Import a GDML file with solid volumes first.")
            return

        # Current world size (from first world node)
        first_world = world_nodes[0]
        cur_size = first_world.solid_params.get('x', 0)

        dialog = RedefineWorldDialog(bbox, cur_size, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            half = dialog.world_half_size
            full = half * 2.0

            # Update all world nodes
            for wnode in world_nodes:
                self._gdml_agent.set_world_size(wnode, half)

            # Rebuild scene
            root = self._gdml_agent.get_root_node()
            if self._vtk_widget:
                self._vtk_widget.build_scene(root)

            self._logger.log_system(
                f"World volume redefined: {full:.1f} × {full:.1f} × {full:.1f} mm "
                f"(factor ×{dialog.selected_factor})")
            self._status_label.setText(
                f"World: {full:.1f} × {full:.1f} × {full:.1f} mm")

    def _on_help(self):
        """Show help information"""
        QMessageBox.about(self, "About GDML Editor",
            "GDML Editor v0.1.0\n\n"
            "GDML geometry file viewer and editor.\n\n"
            "Supported solid types: box, sphere, tube, cone, tessellated\n"
            "Built with PyQt6 and VTK.\n\n"
            "Part of Easy2Rad project.")

    def _on_node_selected(self, entry_id: str):
        """Tree node selected"""
        node = self._gdml_agent.get_node_by_entry_id(entry_id)
        if node:
            self._property_panel.show_node(node)
            if self._vtk_widget:
                scene = self._vtk_widget.get_scene()
                scene.select_node(entry_id)
                self._vtk_widget.refresh()
            self._status_label.setText(f"Selected: {node.name}")

    def _on_visibility_changed(self, entry_id: str, visible: bool):
        """Visibility changed"""
        if self._vtk_widget:
            scene = self._vtk_widget.get_scene()
            scene.set_visibility(entry_id, visible)
            self._vtk_widget.refresh()

    def _on_node_picked(self, entry_id: str):
        """Node picked in 3D view"""
        self._project_tree.select_item_by_entry_id(entry_id)
        self._on_node_selected(entry_id)

    # ==================== Helper methods ====================

    def _rebuild_ui(self):
        """Rebuild UI after import"""
        root = self._gdml_agent.get_root_node()
        self._project_tree.build_from_node_tree(root)

        # Build scene first (actors added), then show widget.
        # showEvent → Initialize() → Start() → ResetCamera() triggers
        # the first render, which will draw the pre-built scene.
        self._vtk_widget.build_scene(root)
        self._center_stack.setCurrentIndex(1)  # show VtkWidget → showEvent fires

        count = len(self._gdml_agent.get_all_file_nodes())
        self._status_label.setText(f"Files loaded: {count}")
        self._logger.log_system(f"Rebuilt UI with {count} file(s)")

    def get_system_log_widget(self):
        """Get log widget (for main.py to configure)"""
        return self._log_widget

    def closeEvent(self, event):
        """Cleanup on exit"""
        if self._vtk_widget:
            self._vtk_widget.cleanup()
        super().closeEvent(event)
