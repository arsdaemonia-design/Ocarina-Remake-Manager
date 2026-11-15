"""Background worker thread for long-running disk operations in PySide6."""

from __future__ import annotations

from typing import Any, Callable
from PySide6 import QtCore


class OperationWorker(QtCore.QThread):
    """Runs a blocking disk operation and emits Qt signals for progress and completion."""

    progress_changed = QtCore.Signal(object, str)
    finished_ok = QtCore.Signal(object)
    failed_err = QtCore.Signal(object)

    def __init__(self, fn: Callable[[Callable[[float | None, str], None]], Any], parent=None) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        def report(fraction: float | None, message: str = "") -> None:
            self.progress_changed.emit(fraction, message)

        try:
            result = self._fn(report)
        except Exception as exc:
            self.failed_err.emit(exc)
            return
        self.finished_ok.emit(result)
