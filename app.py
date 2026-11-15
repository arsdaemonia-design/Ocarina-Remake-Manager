from __future__ import annotations

import sys

from PySide6 import QtWidgets

from ui_qt.main_window import MainWindow

HookshotManager = MainWindow


def main() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Ocarina Remake Manager")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
