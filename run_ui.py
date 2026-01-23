#!/usr/bin/env python
"""UI startup script for ScreenControlAgent."""

import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from screen_agent.ui import MainWindow


def main():
    """Main entry point for the UI."""
    # Enable high DPI scaling
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Consistent cross-platform appearance

    # Create and show main window
    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
