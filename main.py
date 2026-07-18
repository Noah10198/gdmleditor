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

from app.main_window import MainWindow
from utils.logger import AsyncLogger


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
