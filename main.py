"""
GDML Editor - GDML Geometry Editor

Entry point following cad2gdml's application design.
Supports importing, parsing, displaying and editing GDML geometry files.

MVP supported solid types:
  - box
  - sphere
  - tube
  - tessellated (triangular mesh)
"""

import sys
import os

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Suppress Qt warnings
os.environ["QT_LOGGING_RULES"] = ("qt.qpa.windows.warning=false;"
                                  "qt.qpa.gl.warning=false;"
                                  "qt.qpa.eglfs.warning=false")

try:
    import ctypes
    ctypes.windll.user32.DisableProcessWindowsGhosting()
except Exception:
    pass

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import qInstallMessageHandler, QtMsgType, QMessageLogContext

from app.main_window import MainWindow
from utils.logger import AsyncLogger


def _qt_message_filter(_msg_type: QtMsgType, _context: QMessageLogContext,
                       message: str) -> None:
    """Silence benign Qt platform noise on Windows.

    Qt tries to give native title bars a dark border when a window's
    background is dark (3D preview windows / dark theme). On Windows builds
    where DwmSetWindowAttribute is unavailable or called before the native
    window exists it prints, per window/attempt:
      QWindowsWindow::setDarkBorderToWindow: Unable to set dark window border.
    It is cosmetic noise - the OS simply falls back to the normal border -
    so the line is dropped. Everything else is forwarded to stderr.
    """
    text = str(message)
    if "setDarkBorderToWindow" in text:
        return
    print(f"Qt: {text}", file=sys.stderr)


def main():
    """
    Application entry point

    1. Create QApplication instance
    2. Create and show main window
    3. Configure logging system
    4. Enter Qt event loop
    """
    app = QApplication(sys.argv)
    app.setApplicationName("GDML Editor")
    app.setApplicationVersion("0.1.0")
    _ = qInstallMessageHandler(_qt_message_filter)

    # Create main window
    main_window = MainWindow()

    # Configure logger
    logger = AsyncLogger()
    logger.set_system_log_widget(main_window.get_system_log_widget())

    logger.log_system("GDML Editor started")
    logger.log_system(f"Python version: {sys.version}")

    # Show main window
    main_window.show()

    # Enter event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
