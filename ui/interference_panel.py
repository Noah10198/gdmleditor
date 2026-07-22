"""Interference Panel — dockable widget for collision detection.

Modes:
  Sampling — random 5% (≤50 pairs) auto-checked each Run
  Full     — all volumes auto-checked
  Custom   — user manually checks volumes

Each row is a volume with:
  ☐ name       [status]   [View]
"""

import random
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, pyqtSlot, QTimer
)
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QTreeWidget, QTreeWidgetItem, QPushButton, QRadioButton,
    QButtonGroup, QLabel, QHeaderView, QMessageBox,
    QFormLayout, QGroupBox,
)

from core.collision_detector import (
    compute_world_transform, compute_half_size,
    generate_full_pairs, generate_sampled_pairs,
)
from core.gdml_tree import GdmlNode, GdmlNodeType


# ── Helpers ──────────────────────────────────────────────────────

def _collect_instance_volumes(agent) -> List[Tuple[GdmlNode, str, str]]:
    """Get volumes that are actually rendered in the 3D scene.
    Returns list of (volume_node, file_path, display_path).
    Matches VtkScene._build_node_recursive logic — only instance volumes
    under PHYVOL_NODE in world subtrees.
    """
    results = []
    for file_node in agent.get_all_file_nodes():
        fname = file_node.name or "?"
        # Walk world subtree
        for node in file_node.get_all_descendants():
            if node.node_type != GdmlNodeType.VOLUME_NODE:
                continue
            if not node.solid_params:
                continue
            # Must be an instance: under PHYVOL_NODE under WORLD
            parent = node.parent
            if parent and parent.node_type == GdmlNodeType.PHYVOL_NODE:
                grand = parent.parent
                while grand:
                    if grand.node_type == GdmlNodeType.WORLD_NODE:
                        break
                    grand = grand.parent
                if grand:
                    dp = _build_path(node)
                    results.append((node, fname, dp))
    return results


def _build_path(vol: GdmlNode) -> str:
    """Build display path like 'World → Chamber'."""
    parts = []
    n = vol
    while n:
        if n.node_type == GdmlNodeType.WORLD_NODE:
            parts.insert(0, "World")
        elif n.node_type == GdmlNodeType.VOLUME_NODE:
            dn = n.gdml_attrs.get("name", n.entry_id or "?")
            parts.insert(0, str(dn))
        elif n.node_type == GdmlNodeType.PHYVOL_NODE:
            dn = n.gdml_attrs.get("name", n.entry_id or "?")
            if dn and dn != "?":  # skip empty physvol names
                parts.insert(0, str(dn))
        elif n.node_type == GdmlNodeType.GDML_FILE:
            break
        n = n.parent
    return " → ".join(parts)





# ── Worker Thread ───────────────────────────────────────────────

class _CollisionWorker(QThread):
    """Background worker: AABB coarse-check → mesh-level precise check."""
    progress = pyqtSignal(int, int)          # checked, total
    result   = pyqtSignal(int, int, str, float, float, float)  # idx_a, idx_b, other_name, ox, oy, oz (AABB overlap)
    finished = pyqtSignal()
    no_collision = pyqtSignal(int)           # idx → ✅

    def __init__(self, volumes: List[GdmlNode], pairs: List[Tuple[int, int]],
                 polydatas: List, override_provider=None):
        super().__init__()
        self._volumes = volumes
        self._pairs = pairs
        self._polydatas = polydatas      # list of vtkPolyData or None
        self._override = override_provider
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        total = len(self._pairs)

        # Suppress VTK warnings during intersection
        from vtkmodules.vtkCommonCore import vtkLogger
        vtkLogger.SetStderrVerbosity(vtkLogger.VERBOSITY_OFF)

        from vtkmodules.vtkFiltersGeneral import vtkIntersectionPolyDataFilter
        from vtkmodules.vtkFiltersCore import vtkTriangleFilter

        # Preprocess polydata: convert triangle strips → clean triangles
        clean_pds = []
        for pd in self._polydatas:
            if pd is None:
                clean_pds.append(None)
                continue
            from vtkmodules.vtkCommonDataModel import vtkPolyData
            tri = vtkTriangleFilter()
            tri.SetInputData(pd)
            tri.Update()
            # Deep copy so each output is independent
            out = vtkPolyData()
            out.DeepCopy(tri.GetOutput())
            clean_pds.append(out)

        # Precompute AABBs from actual mesh vertices (exact, no approximation)
        aabbs = []
        for cpd in clean_pds:
            if cpd is None:
                aabbs.append((0.0, 0.0, 0.0, 0.0, 0.0, 0.0))
            else:
                aabbs.append(cpd.GetBounds())  # (xmin,xmax,ymin,ymax,zmin,zmax)

        collided: Dict[int, set] = {}
        done = 0

        for idx_a, idx_b in self._pairs:
            if self._stop:
                return

            cpd_a = clean_pds[idx_a]
            cpd_b = clean_pds[idx_b]
            if cpd_a is None or cpd_b is None:
                done += 1
                self.progress.emit(done, total)
                continue

            # Stage 1: AABB quick rejection
            ba = aabbs[idx_a]
            bb = aabbs[idx_b]
            ox = min(ba[1], bb[1]) - max(ba[0], bb[0])
            oy = min(ba[3], bb[3]) - max(ba[2], bb[2])
            oz = min(ba[5], bb[5]) - max(ba[4], bb[4])

            if ox > 0 and oy > 0 and oz > 0:
                # Stage 2: Mesh-level precise intersection
                try:
                    intersect = vtkIntersectionPolyDataFilter()
                    intersect.SetInputData(0, cpd_a)
                    intersect.SetInputData(1, cpd_b)
                    intersect.Update()
                    result_mesh = intersect.GetOutput()
                    n_cells = result_mesh.GetNumberOfCells()
                except Exception:
                    n_cells = 0

                if n_cells > 0:
                    # Real collision confirmed
                    other = self._volumes[idx_b]
                    dn = other.gdml_attrs.get("name", other.entry_id or "?")
                    collided.setdefault(idx_a, set()).add(dn)
                    collided.setdefault(idx_b, set()).add(
                        self._volumes[idx_a].gdml_attrs.get("name", "?")
                    )
                    self.result.emit(idx_a, idx_b, str(dn),
                                     float(ox), float(oy), float(oz))

            done += 1
            self.progress.emit(done, total)

        # Restore VTK warnings
        vtkLogger.SetStderrVerbosity(vtkLogger.VERBOSITY_WARNING)

        # Emit ✅ for volumes with no collisions at all
        all_indices = set(range(len(self._volumes)))
        collided_indices = set(collided.keys())
        for idx in all_indices - collided_indices:
            self.no_collision.emit(idx)

        self.finished.emit()


# ── View Detail Dialog ─────────────────────────────────────────

class _InterferenceDetail(QDialog):
    """Show collision pair with side-by-side 3D render."""

    def __init__(self, vol_a: GdmlNode, vol_b: GdmlNode, entry_a: str, entry_b: str,
                 vtk_scene=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Interference View")
        self.resize(900, 600)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        main_layout = QHBoxLayout(self)

        # ── Left panel: info ──
        left = QVBoxLayout()
        pairs = [("Volume A", vol_a, entry_a)]
        if vol_b is not None:
            pairs.append(("Volume B", vol_b, entry_b))
        for label, vol, eid in pairs:
            name = vol.gdml_attrs.get("name", "?")
            path = _build_path(vol)
            gb = QGroupBox(f"{label}: {name}")
            form = QFormLayout(gb)
            form.addRow("Path:", QLabel(path))
            tx, ty, tz, rx, ry, rz = compute_world_transform(vol)
            form.addRow("Position:", QLabel(f"({tx:.1f}, {ty:.1f}, {tz:.1f})"))
            form.addRow("Rotation:", QLabel(f"({rx:.1f}°, {ry:.1f}°, {rz:.1f}°)"))
            hx, hy, hz = compute_half_size(vol)
            form.addRow("Half-size:", QLabel(f"{hx:.1f} × {hy:.1f} × {hz:.1f}"))
            left.addWidget(gb)

        left.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        left.addWidget(close_btn)
        main_layout.addLayout(left, 1)

        # ── Right panel: 3D render ──
        from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
        from vtkmodules.vtkRenderingCore import (
            vtkRenderer, vtkPolyDataMapper, vtkActor,
        )
        from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
        from vtkmodules.vtkRenderingOpenGL2 import vtkOpenGLPolyDataMapper  # noqa

        self._vtk_widget = QVTKRenderWindowInteractor(self)
        self._renderer = vtkRenderer()
        self._renderer.SetBackground(0.12, 0.12, 0.15)
        self._vtk_widget.GetRenderWindow().AddRenderer(self._renderer)
        main_layout.addWidget(self._vtk_widget, 2)

        # Use TrackballCamera style (same as main 3D view)
        self._interactor_style = vtkInteractorStyleTrackballCamera()

        # Add volumes with distinct colors
        entries = [(entry_a, (0.2, 0.6, 1.0))]  # blue for first
        if entry_b:
            entries.append((entry_b, (1.0, 0.3, 0.3)))  # red for second
        for eid, color in entries:
            if not eid or not vtk_scene:
                continue
            pd = vtk_scene.get_world_polydata(eid)
            if pd is None:
                continue
            mapper = vtkPolyDataMapper()
            mapper.SetInputData(pd)
            actor = vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetColor(*color)
            actor.GetProperty().SetOpacity(0.8)
            actor.GetProperty().SetEdgeColor(0, 0, 0)
            actor.GetProperty().SetEdgeVisibility(True)
            self._renderer.AddActor(actor)

        # Auto center camera
        self._renderer.ResetCamera()
        self._renderer.GetActiveCamera().Zoom(1.2)

        # Start interactor after widget is visible
        QTimer.singleShot(100, self._init_vtk)

    def _init_vtk(self):
        self._vtk_widget.Initialize()
        self._vtk_widget.GetRenderWindow().GetInteractor().SetInteractorStyle(self._interactor_style)
        self._vtk_widget.Start()
        self._vtk_widget.Render()


# ── Main Panel ──────────────────────────────────────────────────

class InterferencePanel(QDialog):
    """Interference detection dialog — triggered from toolbar button."""

    highlight_requested = pyqtSignal(str, str)   # entry_id_a, entry_id_b
    """Request main 3D view to highlight these two volumes."""

    STATUS_NOT_RUN = "—"
    STATUS_OK      = "✅"
    STATUS_COL     = "🔴"

    def __init__(self, agent, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Interference Detection")
        self.resize(680, 520)
        self.setModal(False)  # non-modal — user can still interact with 3D view
        self._agent = agent
        self._override_provider = None
        self._worker: Optional[_CollisionWorker] = None

        # Volume lookup: entry_id → tree_item
        self._vol_to_item: Dict[str, QTreeWidgetItem] = {}
        self._collision_map: Dict[str, List[Tuple[GdmlNode, Tuple]]] = {}  # entry_id → [(other_vol, overlap), ...]

        self._build_ui()

    def set_override_provider(self, provider):
        self._override_provider = provider

    def set_vtk_scene(self, scene):
        """Pass VtkScene reference for mesh-level verification."""
        self._vtk_scene = scene

    # ── UI build ──────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(6, 6, 6, 6)

        # Mode row
        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(2)
        self._mode_group = QButtonGroup(self)
        self._rb_sampling = QRadioButton("Sampling (5%)")
        self._rb_full    = QRadioButton("Full")
        self._rb_custom  = QRadioButton("Custom")
        self._mode_group.addButton(self._rb_sampling, 0)
        self._mode_group.addButton(self._rb_full, 1)
        self._mode_group.addButton(self._rb_custom, 2)
        self._rb_sampling.setChecked(True)
        mode_layout.addWidget(self._rb_sampling)
        mode_layout.addWidget(self._rb_full)
        mode_layout.addWidget(self._rb_custom)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)

        # Action buttons
        action_layout = QHBoxLayout()
        self._run_btn = QPushButton("▶ Run")
        self._run_btn.clicked.connect(self._on_run)
        self._stop_btn = QPushButton("⏹ Stop")
        self._stop_btn.clicked.connect(self._on_stop)
        self._stop_btn.setEnabled(False)
        self._clear_btn = QPushButton("🗑 Clear")
        self._clear_btn.clicked.connect(self._on_clear)
        action_layout.addWidget(self._run_btn)
        action_layout.addWidget(self._stop_btn)
        action_layout.addWidget(self._clear_btn)
        action_layout.addStretch()
        layout.addLayout(action_layout)

        # Progress
        self._progress_label = QLabel("Status: Idle")
        layout.addWidget(self._progress_label)

        # Tree
        self._tree = QTreeWidget()
        self._tree.setColumnCount(3)
        self._tree.setHeaderLabels(["Volume", "Status", "View"])
        self._tree.header().setStretchLastSection(False)
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self._tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self._tree.header().resizeSection(0, 250)
        self._tree.header().resizeSection(1, 200)
        self._tree.header().resizeSection(2, 60)
        self._tree.header().setMinimumSectionSize(50)
        self._tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._tree, 1)

        # Bottom bar
        bottom = QHBoxLayout()
        self._checked_label = QLabel("Checked: 0")
        bottom.addWidget(self._checked_label)
        bottom.addStretch()

        csv_btn = QPushButton("💾 CSV")
        csv_btn.clicked.connect(self._on_export_csv)
        bottom.addWidget(csv_btn)

        hl_btn = QPushButton("🔦 Highlight Checked")
        hl_btn.clicked.connect(self._on_highlight)
        bottom.addWidget(hl_btn)

        layout.addLayout(bottom)

        # Connect mode changes
        self._mode_group.buttonClicked.connect(self._on_mode_changed)

        # Populate tree
        self._populate_tree()

    # ── Tree population ──────────────────────────────────────

    def _populate_tree(self):
        self._tree.clear()
        self._vol_to_item.clear()
        self._collision_map.clear()

        volumes = _collect_instance_volumes(self._agent)
        # Group by file
        file_groups: Dict[str, list] = {}
        for v, fname, dpath in volumes:
            file_groups.setdefault(fname, []).append((v, dpath))

        for fname in sorted(file_groups.keys()):
            file_item = QTreeWidgetItem(self._tree, [f"📁 {fname}"])
            file_item.setFlags(file_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            file_item.setChildIndicatorPolicy(
                QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
            )

            for v, dpath in file_groups[fname]:
                dn = v.gdml_attrs.get("name", v.entry_id or "?")
                item = QTreeWidgetItem(file_item)
                item.setText(0, dn)
                item.setToolTip(0, dpath)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Unchecked)
                item.setText(1, self.STATUS_NOT_RUN)
                item.setData(0, Qt.ItemDataRole.UserRole, v)

                self._vol_to_item[v.entry_id] = item

                # View button
                view_btn = QPushButton("View")
                view_btn.clicked.connect(
                    lambda checked, it=item: self._on_view(it)
                )
                self._tree.setItemWidget(item, 2, view_btn)

        self._tree.expandAll()
        self._update_checked_count()



    # ── Mode handling ────────────────────────────────────────

    def _get_all_vol_items(self) -> list:
        """Collect all tree items that store a volume reference."""
        items = []
        for i in range(self._tree.topLevelItemCount()):
            file_item = self._tree.topLevelItem(i)
            for j in range(file_item.childCount()):
                items.append(file_item.child(j))
        return items

    def _on_mode_changed(self):
        mode = self._mode_group.checkedId()
        all_items = self._get_all_vol_items()

        if mode == 1:  # Full — check all
            for item in all_items:
                item.setCheckState(0, Qt.CheckState.Checked)
        elif mode == 0:  # Sampling
            total = len(all_items)
            n_sample = min(max(2, int(total * 0.05)), 50) if total > 1 else total
            # Filter items by file for cross-file guarantee
            file_groups: Dict[str, list] = {}
            for item in all_items:
                v = item.data(0, Qt.ItemDataRole.UserRole)
                n = v
                fn = "?"
                while n:
                    if n.node_type == GdmlNodeType.GDML_FILE:
                        fn = n.name or "?"
                        break
                    n = n.parent
                file_groups.setdefault(fn, []).append(item)

            sampled_ids = set()
            # If multiple files, ensure at least one from each
            file_list = list(file_groups.values())
            if len(file_list) > 1:
                for g in file_list:
                    sampled_ids.add(id(random.choice(g)))
            # Fill remaining from all items
            remaining = [it for it in all_items if id(it) not in sampled_ids]
            needed = n_sample - len(sampled_ids)
            if needed > 0 and remaining:
                more = random.sample(remaining, min(needed, len(remaining)))
                for m in more:
                    sampled_ids.add(id(m))

            for item in all_items:
                item.setCheckState(0,
                    Qt.CheckState.Checked if id(item) in sampled_ids else Qt.CheckState.Unchecked)
        else:  # Custom — do nothing, user picks manually
            pass

        self._update_checked_count()

    def _on_item_changed(self, item, column):
        if column == 0:
            self._update_checked_count()

    def _update_checked_count(self):
        n = sum(1 for item in self._get_all_vol_items()
                if item.checkState(0) == Qt.CheckState.Checked)
        self._checked_label.setText(f"Checked: {n}")

    # ── Run / Stop / Clear ───────────────────────────────────

    def _on_run(self):
        if self._worker:
            if self._worker.isRunning():
                return
            # Stale reference — clean up
            try:
                self._worker.quit()
            except Exception:
                pass
            self._worker = None

        all_items = self._get_all_vol_items()
        mode = self._mode_group.checkedId()

        if mode == 1:  # Full — check all
            for item in all_items:
                item.setCheckState(0, Qt.CheckState.Checked)
        elif mode == 0:  # Sampling — randomly select 5% (2–50)
            for item in all_items:
                item.setCheckState(0, Qt.CheckState.Unchecked)
            total = len(all_items)
            if total < 2:
                QMessageBox.information(self, "Interference",
                                        "Need at least 2 volumes.")
                return
            n_sel = min(max(2, int(total * 0.05)), 50)
            # Cross-file guarantee
            file_groups = {}
            for item in all_items:
                v = item.data(0, Qt.ItemDataRole.UserRole)
                n = v
                fn = "?"
                while n:
                    if n.node_type == GdmlNodeType.GDML_FILE:
                        fn = n.name or "?"
                        break
                    n = n.parent
                file_groups.setdefault(fn, []).append(item)
            selected_ids = set()
            if len(file_groups) > 1:
                for g in file_groups.values():
                    selected_ids.add(id(random.choice(g)))
            remaining = [it for it in all_items if id(it) not in selected_ids]
            needed = n_sel - len(selected_ids)
            if needed > 0 and remaining:
                more = random.sample(remaining, min(needed, len(remaining)))
                for m in more:
                    selected_ids.add(id(m))
            for item in all_items:
                if id(item) in selected_ids:
                    item.setCheckState(0, Qt.CheckState.Checked)

        # Gather checked volumes
        checked = [item for item in all_items
                   if item.checkState(0) == Qt.CheckState.Checked]
        if len(checked) < 2:
            QMessageBox.information(self, "Interference",
                                    "Select at least 2 volumes to check.")
            return

        volumes = [item.data(0, Qt.ItemDataRole.UserRole) for item in checked]

        # Reset status
        self._collision_map.clear()
        for item in checked:
            item.setText(1, "")
        for item in all_items:
            if item.checkState(0) != Qt.CheckState.Checked:
                item.setText(1, self.STATUS_NOT_RUN)

        # Generate pairs
        indices = list(range(len(volumes)))
        if mode == 1:  # Full
            pairs = generate_full_pairs(indices)
        elif mode == 0:  # Sampling
            file_ids = {}
            for i, v in enumerate(volumes):
                n = v
                while n:
                    if n.node_type == GdmlNodeType.GDML_FILE:
                        file_ids[i] = n.name or "?"
                        break
                    n = n.parent
            pairs = generate_sampled_pairs(indices, file_ids)
        else:  # Custom
            pairs = generate_full_pairs(indices)

        # Precompute world polydata for each volume (main thread, safe)
        vtk_scene = getattr(self, '_vtk_scene', None)
        polydatas = []
        for v in volumes:
            if vtk_scene:
                try:
                    pd = vtk_scene.get_world_polydata(v.entry_id)
                    polydatas.append(pd)
                except Exception:
                    polydatas.append(None)
            else:
                polydatas.append(None)

        self._progress_label.setText(f"Status: Running (0/{len(pairs)})…")
        self._run_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)

        self._worker = _CollisionWorker(volumes, pairs, polydatas, self._override_provider)
        self._worker.progress.connect(self._on_progress)
        self._worker.result.connect(self._on_collision)
        self._worker.no_collision.connect(self._on_no_collision)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_stop(self):
        if self._worker:
            self._worker.stop()
            self._stop_btn.setEnabled(False)
            self._progress_label.setText("Status: Stopped")

    def _on_clear(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
        self._collision_map.clear()
        for item in self._get_all_vol_items():
            item.setText(1, self.STATUS_NOT_RUN)
        self._progress_label.setText("Status: Idle")
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

    # ── Worker callbacks ─────────────────────────────────────

    @pyqtSlot(int, int)
    def _on_progress(self, done, total):
        self._progress_label.setText(f"Status: Running ({done}/{total})…")

    @pyqtSlot(int, int, str, float, float, float)
    def _on_collision(self, idx_a, idx_b, other_name, ox, oy, oz):
        w = self._worker
        if w is None:
            return
        try:
            vol_a = w._volumes[idx_a]
            vol_b = w._volumes[idx_b]
        except (IndexError, AttributeError):
            return
        self._collision_map.setdefault(vol_a.entry_id, []).append((vol_b, (ox, oy, oz)))
        self._collision_map.setdefault(vol_b.entry_id, []).append((vol_a, (ox, oy, oz)))
        item_a = self._vol_to_item.get(vol_a.entry_id)
        if item_a and item_a.checkState(0) == Qt.CheckState.Checked:
            item_a.setText(1, f"{self.STATUS_COL} {other_name}")

    @pyqtSlot(int)
    def _on_no_collision(self, idx):
        w = self._worker
        if w is None:
            return
        try:
            v = w._volumes[idx]
        except (IndexError, AttributeError):
            return
        item = self._vol_to_item.get(v.entry_id)
        if item:
            item.setText(1, self.STATUS_OK)

    @pyqtSlot()
    def _on_worker_finished(self):
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        # Clear worker reference to prevent stale signal access
        self._worker = None
        n = len(self._collision_map)
        col_count = sum(1 for item in self._get_all_vol_items()
                        if item.text(1).startswith(self.STATUS_COL))
        self._progress_label.setText(
            f"Status: Done — {col_count} collisions "
            f"({n} volumes involved)"
        )

    # ── View detail ──────────────────────────────────────────

    def _on_view(self, item: QTreeWidgetItem):
        vol = item.data(0, Qt.ItemDataRole.UserRole)
        if not vol:
            return
        status = item.text(1)

        if status == self.STATUS_NOT_RUN:
            QMessageBox.information(self, "Info",
                                    "Volume was not checked.\n"
                                    "Check it and click Run first.")
            return

        # Show detail dialog with 3D view of selected volume(s)
        collisions = self._collision_map.get(vol.entry_id, [])
        vtk_scene = getattr(self, '_vtk_scene', None)
        if collisions:
            other_vol = collisions[0][0]
            dlg = _InterferenceDetail(vol, other_vol,
                                      vol.entry_id, other_vol.entry_id,
                                      vtk_scene, self)
        else:
            dlg = _InterferenceDetail(vol, None,
                                      vol.entry_id, None,
                                      vtk_scene, self)
        dlg.show()  # non-modal

    # ── Export CSV ───────────────────────────────────────────

    def _on_export_csv(self):
        if not self._collision_map:
            QMessageBox.information(self, "Info", "No results to export. Run first.")
            return

        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "", "CSV Files (*.csv)")
        if not path:
            return

        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write("volume_a,volume_b,overlap_x_mm,overlap_y_mm,overlap_z_mm\n")
                for vol_id, collist in self._collision_map.items():
                    vol_a = self._vol_to_item.get(vol_id)
                    name_a = vol_a.text(0) if vol_a else vol_id
                    for other_vol, (ox, oy, oz) in collist:
                        name_b = other_vol.gdml_attrs.get("name", other_vol.entry_id or "?")
                        f.write(f"{name_a},{name_b},{ox:.1f},{oy:.1f},{oz:.1f}\n")
            QMessageBox.information(self, "Exported", f"Saved to {path}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"CSV export failed: {e}")

    # ── Highlight ────────────────────────────────────────────

    def _on_highlight(self):
        """Highlight all colliding volumes in 3D scene."""
        # Find volumes with collision status
        for item in self._get_all_vol_items():
            if item.text(1).startswith(self.STATUS_COL):
                vol = item.data(0, Qt.ItemDataRole.UserRole)
                if vol and vol.entry_id:
                    self.highlight_requested.emit(vol.entry_id, "")
