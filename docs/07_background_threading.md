# 7. Background Thread Loading

## Problem

Loading large GDML files (e.g. 4.5 MB, 102k lines, ~20k physvols) takes several seconds for XML parsing and node tree construction. Running this on the main thread would freeze the entire UI.

## Solution

### Architecture

```
Main Thread                       Background QThread
───────────                       ─────────────────
MainWindow                           _ImportWorker
  |                                       |
  | QFileDialog (file pick)               |
  |                                       |
  ├── < 500KB? ── sync load ──→ parse    |
  |                                       |
  └── ≥ 500KB ── start QThread ──→ _ImportWorker.run()
       |                                       |
       | QProgressDialog (marquee)             |
       |                                       |
       ├── file_parsed signal ←───────── per-file done
       |     |
       |     └── add_parsed_file_node()
       |
       └── all_done signal ←────────── all files done
             |
             └── _rebuild_ui()
                   ├── Project tree rebuild
                   └── VTK scene rebuild
```

### _ImportWorker

```python
class _ImportWorker(QObject):
    file_parsed = pyqtSignal(object, bool, str, object)  # per-file result
    all_done = pyqtSignal()                               # all files complete

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
```

### Thread Safety Design

- `GdmlAgent.parse_file_only()` is thread-safe (only calls Parser, no UI operations)
- `GdmlAgent.add_parsed_file_node()` is called only from the main thread via signal-slot
- Qt's signal-slot mechanism ensures thread-safe delivery to the main thread

### Concurrency Guard

```python
if self._import_thread and self._import_thread.isRunning():
    QMessageBox.information(self, "Import in Progress", ...)
    return
```

### Graceful Shutdown

```python
def closeEvent(self, event):
    if self._import_worker:
        self._import_worker.stop()
    if self._import_thread and self._import_thread.isRunning():
        self._import_thread.quit()
        self._import_thread.wait(2000)
    ...
```

## Size Threshold

- **< 500KB**: Synchronous load (no thread overhead, faster for small files)
- **≥ 500KB**: Background thread to avoid UI freeze

The threshold is based on empirical testing and can be adjusted.
