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
from PyQt6.QtCore import Qt, QTimer, QThread, QObject, pyqtSignal
from PyQt6.QtGui import QAction, QPalette, QColor, QFont

from core.gdml_agent import GdmlAgent
from core.gdml_tree import GdmlNode, GdmlNodeType
from core.materials_lib import MaterialsLib
from utils.logger import AsyncLogger, LogLevel
from ui.ribbon_toolbar import RibbonToolBar
from ui.project_tree import ProjectTreeWidget
from ui.property_panel import PropertyPanel
from ui.vtk_widget import VtkWidget
from ui.redefine_world_dialog import RedefineWorldDialog
from ui.assign_material_dialog import AssignMaterialDialog
from ui.local_material_dialog import LocalMaterialDialog
from ui.interference_panel import InterferencePanel
from ui.transform_dialog import TransformDialog
from ui.detector_dialog import DetectorDialog
from core.detector_factory import (
    BOX, SPHERE, SHAPES, build_detector_file_node,
    collect_existing_names, format_size_text, make_unique_name,
)
from core.gdml_tree import Placement


class _ImportWorker(QObject):
    """Parses GDML files in a background thread so the UI doesn't freeze."""

    # Emitted per-file: (filepath, success, msg, file_node_or_None)
    file_parsed = pyqtSignal(object, bool, str, object)
    # Emitted when all files are done
    all_done = pyqtSignal()

    def __init__(self, agent: 'GdmlAgent', file_paths: list):
        super().__init__()
        self._agent = agent
        self._file_paths = file_paths
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        for filepath in self._file_paths:
            if self._stop:
                break
            file_node, msg = self._agent.parse_file_only(filepath)
            if file_node is not None:
                self.file_parsed.emit(filepath, True, msg, file_node)
            else:
                self.file_parsed.emit(filepath, False, msg, None)
        self.all_done.emit()


class _TransformSession:
    """State for one open (non-modal) TransformDialog.

    TransformDialog used to run in exec(), so the pre-edit snapshot, the
    debounce timer and the commit/revert branch could all be locals of
    `_on_transform_requested`. Now that the dialog is non-modal that method
    returns as soon as the window is shown, so the very same state has to be
    kept alive out here - including a reference to the dialog, otherwise it is
    garbage collected the moment the event loop comes back.
    """

    #: Live-preview debounce: one repaint per wheel/key burst, not per step.
    PREVIEW_INTERVAL_MS = 60

    def __init__(self, owner, dialog, target_entry_id, refresh_root,
                 is_file_transform, prev_file_transform, prev_override):
        self.owner = owner
        self.dialog = dialog
        self.target_entry_id = target_entry_id
        self.refresh_root = refresh_root
        self.is_file_transform = is_file_transform
        self.prev_file_transform = prev_file_transform
        self.prev_override = prev_override
        self.timer: Optional[QTimer] = None
        #: Set when the application itself closes the dialog (tree rebuild);
        #: the finished handler must then leave the model untouched.
        self.superseded = False

    def start_preview(self):
        """Wire placement_changed -> debounced live preview into the model."""
        self.timer = QTimer(self.owner)
        self.timer.setSingleShot(True)
        self.timer.setInterval(self.PREVIEW_INTERVAL_MS)
        self.timer.timeout.connect(
            lambda: self.apply_placement(self.dialog.current_placement()))
        self.dialog.placement_changed.connect(lambda _p: self.timer.start())

    def stop_preview(self):
        """Drop the debounce timer (a pending tick must not fire afterwards)."""
        if self.timer is not None:
            self.timer.stop()
            self.timer.deleteLater()
            self.timer = None

    def _is_stale(self) -> bool:
        """True when the tree was rebuilt while the dialog was open."""
        return (self.owner._gdml_agent.get_node_by_entry_id(self.target_entry_id)
                is not self.refresh_root)

    def apply_placement(self, p: Placement) -> int:
        """Push `p` into the model and refresh only the affected actors."""
        if self.superseded or self._is_stale():
            return 0
        if self.is_file_transform:
            # File-level transform is stored on the node itself
            self.refresh_root.file_transform = Placement(
                x=p.x, y=p.y, z=p.z,
                rot_x=p.rot_x, rot_y=p.rot_y, rot_z=p.rot_z)
        else:
            # Placement override (lives in agent's _placement_overrides)
            self.owner._gdml_agent.set_placement_override(
                self.target_entry_id, p)
        if self.owner._vtk_widget is None:
            return 0
        return self.owner._vtk_widget.refresh_placement(self.refresh_root)

    def revert(self):
        """Undo whatever the live preview pushed into the model."""
        if self.superseded or self._is_stale():
            return
        if self.is_file_transform:
            self.refresh_root.file_transform = self.prev_file_transform
        elif self.prev_override is not None:
            self.owner._gdml_agent.set_placement_override(
                self.target_entry_id, self.prev_override)
        else:
            self.owner._gdml_agent.clear_placement_override(
                self.target_entry_id)
        if self.owner._vtk_widget:
            self.owner._vtk_widget.refresh_placement(self.refresh_root)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("GDML Editor - gdmleditor")
        self.resize(1400, 900)
        self._dark_theme = False

        self._gdml_agent = GdmlAgent()
        self._logger = AsyncLogger()
        self._mat_lib = MaterialsLib()

        self._vtk_widget: Optional[VtkWidget] = None

        # Background import tracking
        self._import_thread: Optional[QThread] = None
        self._import_worker: Optional[_ImportWorker] = None

        # Open (non-modal) transform dialogs, keyed by target entry id
        self._transform_sessions: dict = {}

        # Open (non-modal) Add Detector dialog, if any.  Registered so a second
        # toolbar click replaces it instead of stacking a second ghost preview
        # (the ghost is one set of actors in the main scene).
        self._detector_dialog: Optional[DetectorDialog] = None

        # Build UI (create all widgets first, then apply theme)
        self._init_toolbar()
        self._init_project_tree()
        self._init_center_placeholder()
        self._init_vtk_widget()           # ← embedded VTK, pre-created
        self._init_property_panel()
        self._init_log_panel()
        self._init_interference_panel()
        self._init_layout()
        self._init_status_bar()

        # Initialize material library (after all widgets created)
        self._init_material_library()

        # Apply theme (after all widgets created)
        self._apply_global_theme(False)

        self._connect_signals()

        self._logger.log_system("GDML Editor started")

    # ==================== Material Library ====================

    def _init_material_library(self):
        """Initialize material library: load elements + NIST materials."""
        data_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
        )
        elem_path = os.path.join(data_dir, "element.xml")
        nist_path = os.path.join(data_dir, "nist.txt")

        if os.path.exists(elem_path):
            cnt = MaterialsLib.load_elements_from_xml(elem_path)
            self._logger.log_system(f"Loaded {cnt} elements from element.xml")
        else:
            self._logger.log_system(f"element.xml not found at {elem_path}",
                                    LogLevel.WARNING)

        if os.path.exists(nist_path):
            cnt = self._mat_lib.load_nist_from_file(nist_path)
            self._logger.log_system(f"Loaded {cnt} NIST materials from nist.txt")
        else:
            self._logger.log_system(f"nist.txt not found at {nist_path}",
                                    LogLevel.WARNING)

        # Load local materials JSON if it exists
        json_path = os.path.join(data_dir, "local_materials.json")
        if os.path.exists(json_path):
            cnt = self._mat_lib.load_local_materials_from_json(json_path)
            self._logger.log_system(f"Loaded {cnt} local materials from JSON")

        # Attach material library to the project tree
        self._project_tree.set_material_lib(self._mat_lib)
        self._project_tree.refresh_materials()

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
        self._tree_dock.setMinimumWidth(280)
        self._tree_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._tree_dock)
        self.resizeDocks([self._tree_dock], [280], Qt.Orientation.Horizontal)

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
        self._prop_dock.setMinimumWidth(280)
        self._prop_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._prop_dock)
        self.resizeDocks([self._prop_dock], [280], Qt.Orientation.Horizontal)

    def _init_interference_panel(self):
        """Initialize interference detection panel (hidden by default)"""
        self._interference_panel = InterferencePanel(self._gdml_agent)
        self._interference_panel.setObjectName("InterferencePanel")
        self._interference_panel.highlight_requested.connect(
            self._on_interference_highlight)
        # Not added to dock area yet — shown on demand

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
        self._toolbar.interference_clicked.connect(self._on_interference)
        self._toolbar.export_clicked.connect(self._on_export_gdml)
        self._toolbar.clear_clicked.connect(self._on_clear_all)
        self._toolbar.redefine_world_clicked.connect(self._on_redefine_world)
        self._toolbar.material_clicked.connect(self._on_material_assignment)
        self._toolbar.add_box_clicked.connect(self._on_add_box_detector)
        self._toolbar.add_sphere_clicked.connect(self._on_add_sphere_detector)
        self._toolbar.theme_toggled.connect(self._toggle_theme)
        self._toolbar.help_clicked.connect(self._on_help)

        # Project tree
        self._project_tree.node_selected.connect(self._on_node_selected)
        self._project_tree.visibility_changed.connect(self._on_visibility_changed)
        self._project_tree.add_local_material_requested.connect(
            self._on_add_local_material)
        self._project_tree.remove_local_material_requested.connect(
            self._on_remove_local_material)
        self._project_tree.edit_local_material_requested.connect(
            self._on_edit_local_material)
        self._project_tree.save_local_materials_requested.connect(
            self._on_save_local_materials)
        self._project_tree.load_local_materials_requested.connect(
            self._on_load_local_materials)
        self._project_tree.solid_preview_requested.connect(
            self._on_solid_preview)
        self._project_tree.delete_geometry_requested.connect(
            self._on_delete_geometry)
        self._project_tree.transform_requested.connect(
            self._on_transform_requested)
        self._project_tree.edit_material_requested.connect(
            self._on_edit_material)

        # Set up placement override provider so scene can resolve overrides
        # during placement accumulation.
        if self._vtk_widget:
            self._vtk_widget.set_override_provider(
                lambda entry_id: self._gdml_agent.get_placement_override(entry_id)
            )

        # NOTE: VTK picking signal is connected lazily when _get_vtk_window() is called.

    # ==================== Signal handlers ====================

    def _on_import_gdml(self):
        """Import GDML file (non-blocking, background parsing)"""
        # Guard against concurrent imports
        if self._import_thread and self._import_thread.isRunning():
            QMessageBox.information(
                self, "Import in Progress",
                "A file import is already in progress. "
                "Please wait for it to finish before importing another file."
            )
            return

        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Import GDML Files", "",
            "GDML Files (*.gdml);;XML Files (*.xml);;All Files (*)"
        )
        if not file_paths:
            return

        # If only one small file, load synchronously (faster, no thread overhead)
        if len(file_paths) == 1 and os.path.getsize(file_paths[0]) < 500_000:
            self._load_files_sync(file_paths)
            return

        # Use background thread for large files
        self._load_files_async(file_paths)

    def _load_files_sync(self, file_paths: list):
        """Synchronous load for small files (no thread overhead)."""
        for filepath in file_paths:
            self._logger.log_system(f"Loading: {filepath}")
            success, msg = self._gdml_agent.load_gdml_file(filepath)
            if success:
                self._logger.log_system(f"  [OK] {msg}")
            else:
                self._logger.log_system(f"  [ERR] {msg}", LogLevel.ERROR)
                QMessageBox.warning(self, "Import Error", f"Failed to import:\n{msg}")

        self._rebuild_ui()
        self._check_unsupported_solids()

    def _load_files_async(self, file_paths: list):
        """Background-thread load for large files."""
        self._logger.log_system(f"Loading {len(file_paths)} file(s) in background...")

        # Show a modal "please wait" dialog (marquee style, no cancel to avoid
        # partial-import state — the thread is fast enough to not need cancel)
        from PyQt6.QtWidgets import QProgressDialog
        progress = QProgressDialog(
            "Parsing GDML file(s)...\nThis may take a moment for large files.",
            None, 0, 0, self  # no cancel button, marquee mode
        )
        progress.setWindowTitle("Importing")
        progress.setModal(True)
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()

        # Create worker + thread
        self._import_worker = _ImportWorker(self._gdml_agent, file_paths)
        self._import_thread = QThread(self)
        self._import_worker.moveToThread(self._import_thread)

        self._import_thread.started.connect(self._import_worker.run)
        self._import_worker.file_parsed.connect(self._on_file_parsed)
        self._import_worker.all_done.connect(
            lambda: self._on_import_all_done(progress))
        self._import_thread.finished.connect(self._import_worker.deleteLater)
        self._import_thread.finished.connect(self._import_thread.deleteLater)

        self._import_thread.start()

    def _on_file_parsed(self, filepath: str, success: bool, msg: str,
                        file_node: object):
        """Called on main thread when one file finishes parsing."""
        if success and file_node is not None:
            self._gdml_agent.add_parsed_file_node(file_node)
            self._logger.log_system(f"  [OK] {msg}")
        elif not success:
            self._logger.log_system(f"  [ERR] {msg}", LogLevel.ERROR)
            QMessageBox.warning(self, "Import Error",
                                f"Failed to import:\n{msg}")

    def _on_import_all_done(self, progress_dialog):
        """Called on main thread when ALL files are parsed.

        The progress dialog is kept open until the project tree AND the
        3D scene are fully rebuilt — otherwise large geometries leave the
        UI frozen-looking during rebuild with no progress feedback.
        """
        # Clean up thread references (dialog stays open during rebuild)
        if self._import_thread:
            self._import_thread.quit()
            self._import_thread.wait()
        self._import_thread = None
        self._import_worker = None

        self._logger.log_system("All files parsed, building UI...")
        try:
            self._rebuild_ui(progress_dialog)
        finally:
            progress_dialog.close()
        self._check_unsupported_solids()

    def _check_unsupported_solids(self):
        """Show warning about unparseable solid types."""
        unsupported = self._gdml_agent.get_unsupported_solids()
        if not unsupported:
            return

        from collections import Counter
        tag_counts = Counter(s["tag"] for s in unsupported)
        detail_lines = []
        for tag, count in tag_counts.most_common():
            names = [s["name"] for s in unsupported if s["tag"] == tag]
            detail_lines.append(f"  • {tag} ({count}): {', '.join(names)}")

        warning_msg = (
            "The following solid types were found but cannot be fully parsed:\n\n"
            + "\n".join(detail_lines) + "\n\n"
            "These solids will be preserved for GDML export but will NOT "
            "be rendered in the 3D view."
        )
        QMessageBox.warning(self, "Incomplete Geometry Parsing", warning_msg)

    def _on_interference(self):
        """Show interference detection dialog."""
        # Set up override provider and scene (same as VTK)
        self._interference_panel.set_override_provider(
            lambda entry_id: self._gdml_agent.get_placement_override(entry_id)
        )
        if self._vtk_widget:
            self._interference_panel.set_vtk_scene(
                self._vtk_widget.get_scene()
            )

        # Refresh tree with current volumes
        self._interference_panel._populate_tree()

        self._interference_panel.show()
        self._interference_panel.raise_()
        self._interference_panel.activateWindow()

    def _on_interference_highlight(self, entry_id_a: str, entry_id_b: str):
        """Highlight colliding volumes in 3D scene."""
        if not self._vtk_widget:
            return
        scene = self._vtk_widget.get_scene()
        # Highlight single volume if only one provided
        if entry_id_b:
            scene.highlight_volumes([entry_id_a, entry_id_b])
        elif entry_id_a:
            scene.highlight_volumes([entry_id_a])
        self._vtk_widget.refresh()

    def _on_export_gdml(self):
        """Export GDML file with all placement overrides applied."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export GDML", "",
            "GDML Files (*.gdml);;All Files (*)"
        )
        if not file_path:
            return
        self._logger.log_system(f"Exporting to: {file_path}")

        try:
            from core.gdml_writer import GdmlWriter
            root = self._gdml_agent.get_root_node()
            overrides = self._gdml_agent.get_all_placement_overrides()

            # Check world material consistency (multi-file merge)
            world_mats = self._gdml_agent.get_world_materials()
            if len(world_mats) > 1:
                QMessageBox.information(
                    self, "World Material",
                    "Detected multiple worlds with different materials.\n"
                    "The system will use G4_AIR instead.")

            writer = GdmlWriter()
            writer.write(root, overrides, file_path, mat_lib=self._mat_lib)
            self._logger.log_system("  [OK] Export complete")
        except Exception as e:
            self._logger.log_system(
                f"  [ERR] Export failed: {e}",
                level=LogLevel.ERROR)
            QMessageBox.warning(
                self, "Export Error",
                f"Failed to export GDML:\n{e}")

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
            self._vtk_widget._update_cube_axes_bounds()
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

    def _refresh_world_selection(self, world_nodes) -> None:
        """Re-show the selected node so the panel reflects the new world size."""
        cur = self._property_panel.get_current_node()
        if cur is None:
            return
        affected = set()
        for w in world_nodes:
            affected.add(w.entry_id)
            for d in w.get_all_descendants():
                affected.add(d.entry_id)
        if cur.entry_id in affected:
            self._property_panel.show_node(cur)

    def _on_redefine_world(self):
        """Redefine world volume size (with live 3D preview in the dialog)."""
        # Get all world nodes
        world_nodes = self._gdml_agent.get_world_nodes()
        if not world_nodes:
            QMessageBox.information(self, "Redefine World",
                "No world volume found.\nImport a GDML file first.")
            return

        # Bounding box of what is actually rendered: VTK already baked in
        # physvol placements, rotations, file transforms and every solid type
        # (box / tube / tessellated / ...). The world boxes themselves are
        # excluded so they don't measure themselves. Fall back to the
        # analytical estimate when the scene is empty.
        scene = self._vtk_widget.get_scene() if self._vtk_widget else None
        world_ids = {w.entry_id for w in world_nodes}
        bbox = (scene.get_geometry_bounds(exclude_entry_ids=world_ids)
                if scene is not None else None)
        if bbox is None:
            bbox = self._gdml_agent.compute_scene_bbox()
        xmin, xmax, ymin, ymax, zmin, zmax = bbox
        has_scene = not (xmin == xmax == ymin == ymax == zmin == zmax == 0)

        if not has_scene:
            QMessageBox.information(self, "Redefine World",
                "No renderable geometry found.\n"
                "Import a GDML file with solid volumes first.")
            return

        # Current world size(s): one entry per world node, so the dialog can
        # flag a mismatch (multi-file mode where files were resized apart)
        world_sizes = [w.solid_params.get('x', 0.0) for w in world_nodes]
        cur_size = world_sizes[0] if world_sizes else 0.0

        root = self._gdml_agent.get_root_node()
        dialog = RedefineWorldDialog(
            bbox, cur_size, root_node=root, parent=self,
            world_count=len(world_nodes), current_world_sizes=world_sizes,
            dark_theme=self._dark_theme,
            # Same overrides as the main view, so the preview geometry lines up
            # with the bbox measured above (which already includes them).
            override_provider=(
                lambda entry_id: self._gdml_agent.get_placement_override(entry_id)))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            half = dialog.world_half_size
            full = half * 2.0

            # Update all world nodes
            for wnode in world_nodes:
                self._gdml_agent.set_world_size(wnode, half)

            # ── Linked updates: 3D view, property panel, status bar ──
            if self._vtk_widget:
                self._vtk_widget.build_scene(root)
            self._refresh_world_selection(world_nodes)

            # Multi-file mode resizes every file's world at once - say so
            worlds_note = (f", {len(world_nodes)} world volumes"
                           if len(world_nodes) > 1 else "")
            self._logger.log_system(
                f"World volume redefined: {full:.1f} × {full:.1f} × {full:.1f} mm "
                f"(factor ×{dialog.selected_factor}{worlds_note})")
            self._status_label.setText(
                f"World: {full:.1f} × {full:.1f} × {full:.1f} mm"
                + (f"  ({len(world_nodes)} files)" if len(world_nodes) > 1 else ""))

    # ==================== Add detector (box / sphere) ====================

    def _on_add_box_detector(self):
        self._on_add_detector(BOX)

    def _on_add_sphere_detector(self):
        self._on_add_detector(SPHERE)

    def _on_add_detector(self, shape: str):
        """Add a box / sphere detector as its own GDML file, next to the imports."""
        # The ghost preview is a single set of actors in the main scene, so only
        # one Add Detector dialog can be open at a time: reject any pending one
        # (which drops its ghost) before opening the requested shape.
        if self._detector_dialog is not None:
            self._detector_dialog.reject()

        root = self._gdml_agent.get_root_node()
        existing = collect_existing_names(root)

        # Inherit the project's world size when there is one: the detector then
        # shares the world box the main view already draws (identical world
        # sizes keep VtkScene's unified-world mode, instead of adding a second
        # differently sized wireframe box).
        world_size = None
        for wnode in self._gdml_agent.get_world_nodes():
            params = wnode.solid_params or {}
            if all(k in params for k in ("x", "y", "z")):
                world_size = (params["x"], params["y"], params["z"])
                break

        dialog = DetectorDialog(
            shape=shape,
            default_name=make_unique_name(existing, shape),
            existing_names=existing,
            world_size=world_size,
            parent=self,
        )
        self._detector_dialog = dialog
        dialog.preview_changed.connect(self._on_detector_preview)
        dialog.finished.connect(self._on_detector_finished)
        dialog.show()
        # The form was filled before the signal was connected, so seed the ghost
        # explicitly - otherwise the main view stays empty until the first edit.
        self._on_detector_preview(dialog.preview())

    def _on_detector_preview(self, spec: dict):
        """Mirror the Add Detector dialog's current sizes into the main 3D view."""
        if self._vtk_widget is None:
            return
        self._vtk_widget.get_scene().show_detector_preview(
            spec["shape"], spec["params_mm"], spec["world_size"])

    def _on_detector_finished(self, result: int):
        """Dialog closed: always drop the ghost; on Add, commit the real file."""
        dialog = self._detector_dialog
        if dialog is None:
            return
        self._detector_dialog = None

        # The ghost is only a preview either way - on Add the actual geometry is
        # drawn by the rebuild below.  (A rebuild that happened while the dialog
        # was open has already dropped it, so this is a no-op then.)
        if self._vtk_widget is not None:
            self._vtk_widget.get_scene().clear_detector_preview()

        if result == QDialog.DialogCode.Accepted:
            file_node = build_detector_file_node(
                shape=dialog.shape,
                name=dialog.detector_name,
                params_mm=dialog.params_mm,
                world_size=dialog.world_size,
            )

            self._gdml_agent.add_parsed_file_node(file_node)
            self._rebuild_ui()
            # Put the new file in focus so it is obvious what was just created.
            self._project_tree.select_item_by_entry_id(file_node.entry_id)

            size_text = format_size_text(dialog.shape, dialog.params_mm)
            self._logger.log_system(
                f"Added {SHAPES[dialog.shape]['label'].lower()} detector: "
                f"{file_node.name} ({size_text})")
            self._status_label.setText(f"Added {file_node.name} — {size_text}")

        dialog.deleteLater()

    def _on_help(self):
        """Show help information"""
        QMessageBox.about(self, "About GDML Editor",
            "GDML Editor v0.1.0\n\n"
            "GDML geometry file viewer and editor.\n\n"
            "Supported solid types: box, sphere, tube, cone, tessellated\n"
            "Built with PyQt6 and VTK.\n\n"
            "Part of Easy2Rad project.")

    # ==================== Material handlers ====================

    def _on_material_assignment(self):
        """Open the batch material assignment dialog."""
        self._open_material_dialog()

    def _on_edit_material(self, entry_id: str):
        """Right-click a volume -> open the material dialog focused on it."""
        self._open_material_dialog(focus_entry_id=entry_id)

    def _open_material_dialog(self, focus_entry_id: Optional[str] = None):
        """Open the batch material assignment dialog.

        Args:
            focus_entry_id: when given, the dialog scrolls to and selects the
                row of this volume, so the user lands on what they clicked.
        """
        file_nodes = self._gdml_agent.get_all_file_nodes()
        if not file_nodes:
            QMessageBox.information(
                self, "Assign Materials",
                "No GDML files loaded.\nImport a GDML file first.")
            return

        dialog = AssignMaterialDialog(self._gdml_agent, self._mat_lib, self,
                                      focus_entry_id=focus_entry_id)
        dialog.materials_saved.connect(self._on_materials_saved)
        dialog.exec()

    def _on_materials_saved(self, assigned: int, total: int):
        """Rebuild 3D scene after material assignment (update colors)."""
        self._logger.log_system(
            f"Materials assigned: {assigned}/{total} volumes have materials")
        # Refresh 3D scene (material colors changed)
        root = self._gdml_agent.get_root_node()
        if self._vtk_widget:
            self._vtk_widget.build_scene(root)
        self._status_label.setText(
            f"Materials: {assigned}/{total} assigned")

    def _log_local_material_gdml(self, gdml: str):
        """Echo a local material's generated GDML, as cad2gdml does."""
        self._logger.log_system("━━ GDML Material Definition ━━━━")
        for line in gdml.strip().splitlines():
            self._logger.log_system(line)
        self._logger.log_system("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    def _on_add_local_material(self):
        """Open local material dialog and auto-select the new material."""
        from core.materials_lib import CustomElement

        dialog = LocalMaterialDialog(self._mat_lib, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._project_tree.populate_local_materials(self._mat_lib)
            new_mat_id = dialog.last_mat_id
            if new_mat_id:
                self._project_tree.select_local_material(new_mat_id)
                mat = self._mat_lib.get_local_material_by_id(new_mat_id)
                if mat:
                    self._property_panel.show_local_material_info(mat)
            if self._mat_lib.GDML_OUTPUT_ENABLED and dialog.last_gdml:
                self._log_local_material_gdml(dialog.last_gdml)
            else:
                self._logger.log_system(
                    f"Local material added. Total: "
                    f"{len(self._mat_lib.get_local_material_names())}")

    def _on_edit_local_material(self, mat_id: str):
        """Re-open a saved local material for editing, in place."""
        from core.materials_lib import CustomElement

        mat = self._mat_lib.get_local_material_by_id(mat_id)
        if mat is None or isinstance(mat, CustomElement):
            # Custom elements have no editor of their own yet.
            self._logger.log_system(
                "Only compound and mixture materials can be edited.",
                LogLevel.ERROR)
            return

        dialog = LocalMaterialDialog(self._mat_lib, self, material=mat)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._project_tree.populate_local_materials(self._mat_lib)
        self._project_tree.select_local_material(dialog.last_mat_id)
        # The edit writes a fresh object under the same id, so re-read it
        # instead of showing the one the dialog was opened with.
        updated = self._mat_lib.get_local_material_by_id(dialog.last_mat_id)
        if updated:
            self._property_panel.show_local_material_info(updated)
        if self._mat_lib.GDML_OUTPUT_ENABLED and dialog.last_gdml:
            self._log_local_material_gdml(dialog.last_gdml)
        else:
            self._logger.log_system(f"Local material '{mat.mat_name}' updated.")

    def _on_remove_local_material(self, display_name: str):
        """Remove a local material by tree display name (matches cad2gdml)."""
        from core.materials_lib import CustomElement

        for mat in self._mat_lib.get_all_local_materials():
            # Custom elements: compare by symbol (matches tree display)
            if isinstance(mat, CustomElement):
                if mat.symbol == display_name:
                    if self._mat_lib.delete_material(mat.mat_id):
                        self._project_tree.populate_local_materials(self._mat_lib)
                        self._logger.log_system(
                            f"Deleted local material: {display_name}")
                    return
            else:
                name = getattr(mat, 'mat_name', getattr(mat, 'name', ''))
                if name == display_name:
                    if self._mat_lib.delete_material(mat.mat_id):
                        self._project_tree.populate_local_materials(self._mat_lib)
                        self._logger.log_system(
                            f"Deleted local material: {display_name}")
                    return

    def _on_save_local_materials(self):
        """Save local materials to JSON file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Local Materials", "",
            "JSON Files (*.json);;All Files (*)")
        if not file_path:
            return
        if self._mat_lib.save_local_materials_to_json(file_path):
            self._logger.log_system(
                f"Saved {len(self._mat_lib.get_local_material_names())} "
                f"local materials to {file_path}")
        else:
            self._logger.log_system("Failed to save local materials",
                                    LogLevel.ERROR)

    def _on_load_local_materials(self):
        """Load local materials from JSON file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Local Materials", "",
            "JSON Files (*.json);;All Files (*)")
        if not file_path:
            return
        cnt = self._mat_lib.load_local_materials_from_json(file_path)
        if cnt > 0:
            self._project_tree.populate_local_materials(self._mat_lib)
            self._logger.log_system(
                f"Loaded {cnt} local materials from {file_path}")
        else:
            self._logger.log_system(
                "No local materials loaded (file may be empty)",
                LogLevel.WARNING)

    def _on_node_selected(self, entry_id: str):
        """Tree node selected (handles geometry + material items, matching cad2gdml)."""
        # ── NIST material item clicked ──
        if entry_id.startswith("__mat__:"):
            mat_name = entry_id[8:]
            density = self._mat_lib.get_nist_density(mat_name)
            self._property_panel.show_material_reference(mat_name, density)
            self._status_label.setText(f"Material: {mat_name}")
            return

        # ── Local material item clicked ──
        if entry_id.startswith("__local__:"):
            mat_id = entry_id[10:]
            mat = self._mat_lib.get_local_material_by_id(mat_id)
            if mat:
                from core.materials_lib import CustomElement
                self._property_panel.show_local_material_info(mat)
                if isinstance(mat, CustomElement):
                    display = mat.symbol
                else:
                    display = getattr(mat, 'mat_name', mat_id)
                self._status_label.setText(
                    f"Local Material: {display}")
            else:
                self._property_panel.show_node(None)
                self._status_label.setText(f"Local material (id={mat_id}) not found")
            return

        # ── Geometry node clicked ──
        node = self._gdml_agent.get_node_by_entry_id(entry_id)
        if node:
            self._property_panel.show_node(node)
            if self._vtk_widget:
                scene = self._vtk_widget.get_scene()
                scene.select_node(entry_id)
                self._vtk_widget.refresh()
            self._status_label.setText(f"Selected: {node.name}")
        else:
            self._property_panel.show_node(None)
            self._status_label.setText("No node selected")



    def _on_visibility_changed(self, entry_id: str, visible: bool):
        """Visibility changed"""
        if self._vtk_widget:
            scene = self._vtk_widget.get_scene()
            scene.set_visibility(entry_id, visible)
            self._vtk_widget.refresh()

    def _on_solid_preview(self, entry_id: str):
        """Preview a single solid in a VTK popup window."""
        from ui.vtk_view_window import VtkViewWindow
        from core.gdml_tree import GdmlNode, GdmlNodeType

        # Find the SOLID_DEF node
        node = self._gdml_agent.get_node_by_entry_id(entry_id)
        if not node or node.node_type != GdmlNodeType.SOLID_DEF:
            self._logger.log_system(
                f"Cannot preview: solid not found (id={entry_id})",
                LogLevel.WARNING)
            return

        # Create a minimal tree: ROOT -> GDML_FILE -> VOLUME (with solid's params)
        temp_root = GdmlNode(GdmlNodeType.ROOT_NODE, "preview")
        temp_file = GdmlNode(GdmlNodeType.GDML_FILE, "preview.gdml")
        temp_vol = GdmlNode(GdmlNodeType.VOLUME_NODE, node.name)
        if node.solid_params:
            temp_vol.solid_params = dict(node.solid_params)
        temp_vol.gdml_tag = node.gdml_tag
        temp_vol.material_name = node.material_name or "G4_WATER"
        temp_file.add_child(temp_vol)
        temp_root.add_child(temp_file)

        # Show in a preview window (minimal: no toolbar, transparent by default)
        preview = VtkViewWindow(preview_mode=True)
        preview.setWindowTitle(f"Solid Preview: {node.name}")
        # Use build_scene instead of get_scene().build_from_tree so CubeAxes is preserved
        preview.build_scene(temp_root, render_all_volumes=True)
        preview.set_all_opacity(0.45)
        preview.resize(600, 500)

        # Hold a reference so the window isn't garbage-collected
        if not hasattr(self, '_preview_windows'):
            self._preview_windows = []
        self._preview_windows.append(preview)
        preview.destroyed.connect(
            lambda: self._preview_windows.remove(preview)
            if preview in self._preview_windows else None)
        preview.show()

    def _on_delete_geometry(self, entry_id: str):
        """Delete a GDML file and rebuild the UI."""
        self._gdml_agent.remove_file_node(entry_id)
        self._rebuild_ui()

    def _on_transform_requested(self, entry_id: str):
        """Open TransformDialog for a volume instance or file node."""
        node = self._gdml_agent.get_node_by_entry_id(entry_id)
        if node is None:
            self._logger.log_warning(
                "Transform: cannot find node for entry: " + entry_id)
            return

        # Determine transform target: for VOLUME_NODE instances under a PHYVOL,
        # the actual placement lives on the parent PHYVOL_NODE.
        is_file_transform = (node.node_type == GdmlNodeType.GDML_FILE)
        if (node.node_type == GdmlNodeType.VOLUME_NODE
                and node.parent
                and node.parent.node_type == GdmlNodeType.PHYVOL_NODE):
            # Edit the parent physvol's placement
            physvol = node.parent
            target_entry_id = physvol.entry_id
            # Subtree to refresh for the live preview: the PHYVOL_NODE, since
            # every actor below it accumulates this placement.
            refresh_root = physvol
            # Show current (possibly overridden) value in the dialog
            override = self._gdml_agent.get_placement_override(target_entry_id)
            placement = override if override else (physvol.placement or Placement())
            title = "Edit Physvol Transform"
            target_label = "{} -> {}".format(physvol.name, physvol.ref_name)

        elif node.node_type == GdmlNodeType.GDML_FILE:
            # Edit file-level transform
            target_entry_id = node.entry_id
            # The whole file subtree moves, except the world box itself
            refresh_root = node
            placement = node.file_transform or Placement()
            title = "Edit File Transform"
            target_label = "File: " + (node.name if node.name else "unnamed")

        elif node.node_type == GdmlNodeType.WORLD_NODE:
            self._logger.log_info(
                "World transform is not editable via this dialog.")
            return
        else:
            self._logger.log_info(
                "Transform is not applicable for this node type: "
                + node.node_type.name)
            return

        # Non-modal: the user can pan / zoom / rotate the 3D view, or browse the
        # tree, while tuning the spinboxes. One editor per target - re-selecting
        # the same node raises the open dialog instead of stacking a second one
        # with its own revert snapshot.
        existing = self._transform_sessions.get(target_entry_id)
        if existing is not None:
            existing.dialog.show()
            existing.dialog.raise_()
            existing.dialog.activateWindow()
            return

        dialog = TransformDialog(title, target_label, placement, self)

        # ── Live preview ──
        # Only the affected subtree is refreshed (VtkWidget.refresh_placement):
        # geometry, mapper, selection highlight and the camera are all
        # preserved, i.e. no full scene rebuild. Whatever the preview pushed
        # into the model is reverted when the dialog is not accepted, so the
        # model is never left half-edited (Cancel / Esc / closing the window all
        # land in _on_transform_finished).
        session = _TransformSession(
            owner=self,
            dialog=dialog,
            target_entry_id=target_entry_id,
            refresh_root=refresh_root,
            is_file_transform=is_file_transform,
            prev_file_transform=(refresh_root.file_transform
                                 if is_file_transform else None),
            prev_override=self._gdml_agent.get_placement_override(
                target_entry_id),
        )
        # Debounce: one spinbox step with the wheel or holding a key must not
        # trigger one repaint each - only the last value of the burst matters.
        session.start_preview()

        self._transform_sessions[target_entry_id] = session
        dialog.finished.connect(
            lambda result: self._on_transform_finished(session, result))
        dialog.show()
        dialog.raise_()

    def _on_transform_finished(self, session: _TransformSession, result: int):
        """Commit or revert a non-modal transform dialog once it closes."""
        self._transform_sessions.pop(session.target_entry_id, None)
        session.stop_preview()

        if session.superseded:
            # The tree was rebuilt underneath the dialog: its target node is
            # gone, so there is nothing left to commit or roll back.
            session.dialog.deleteLater()
            return

        if result == QDialog.DialogCode.Accepted:
            # Commit the spinbox values as they are now. This is also the only
            # apply for "opened the dialog and pressed OK without editing",
            # where placement_changed never fired.
            updated = session.apply_placement(session.dialog.get_placement())
            self._logger.log_system(
                f"Transform applied: {updated} actor(s) updated")
        else:
            # Cancel / Esc / window close: undo the live preview
            session.revert()

        session.dialog.deleteLater()

    def _close_transform_sessions(self):
        """Tear down every open transform dialog after the tree was rebuilt.

        Their target nodes no longer exist, so any pending preview must be
        dropped instead of written back (see _TransformSession.superseded).
        """
        for session in list(self._transform_sessions.values()):
            session.superseded = True
            session.dialog.close()      # -> finished -> _on_transform_finished
        self._transform_sessions.clear()

    def _on_node_picked(self, entry_id: str):
        """Node picked in 3D view"""
        self._project_tree.select_item_by_entry_id(entry_id)
        self._on_node_selected(entry_id)

    # ==================== Helper methods ====================

    def _rebuild_ui(self, progress=None):
        """Rebuild UI after import.

        When `progress` (a QProgressDialog) is given — the large-file async
        import path — the tree/scene build loops periodically refresh the
        dialog text and pump the event loop, keeping the UI responsive while
        large geometry is being rebuilt.
        """
        # Non-modal transform dialogs survive an import/delete, but their
        # target nodes do not: close them before the tree is replaced, so no
        # preview is written back onto a stale node.
        self._close_transform_sessions()

        root = self._gdml_agent.get_root_node()
        scene = self._vtk_widget.get_scene()

        tree_cb = None
        if progress is not None:
            if scene is not None:
                scene.set_build_progress_callback(
                    self._make_rebuild_flusher(progress, "3D scene"))
            tree_cb = self._make_rebuild_flusher(progress, "project tree")

        try:
            self._project_tree.build_from_node_tree(root, progress_cb=tree_cb)

            # Build scene first (actors added), then show widget.
            # showEvent → Initialize() → Start() → ResetCamera() triggers
            # the first render, which will draw the pre-built scene.
            self._vtk_widget.build_scene(root)
        finally:
            if scene is not None:
                scene.set_build_progress_callback(None)

        self._center_stack.setCurrentIndex(1)  # show VtkWidget → showEvent fires
        count = len(self._gdml_agent.get_all_file_nodes())
        self._status_label.setText(f"Files loaded: {count}")
        self._logger.log_system(f"Rebuilt UI with {count} file(s)")

    def _make_rebuild_flusher(self, progress: object, what: str):
        """Build progress callback: throttled dialog refresh + event pumping."""
        import time
        state = {"last": 0.0}

        def flush(done: int):
            now = time.monotonic()
            if now - state["last"] >= 0.1:
                state["last"] = now
                progress.setLabelText(
                    f"Building {what}... ({done} nodes processed)")
                QApplication.processEvents()

        return flush

    def get_system_log_widget(self):
        """Get log widget (for main.py to configure)"""
        return self._log_widget

    def closeEvent(self, event):
        """Cleanup on exit"""
        # Gracefully shut down background import if running
        if self._import_worker:
            self._import_worker.stop()
        if self._import_thread and self._import_thread.isRunning():
            self._import_thread.quit()
            self._import_thread.wait(2000)
        if self._vtk_widget:
            self._vtk_widget.cleanup()
        super().closeEvent(event)
