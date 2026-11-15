"""Visual save slot card widget displaying thumbnail, scene, size, and timestamp."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ui_qt.theme import COLORS


def format_hearts(value: float | None) -> str:
    if value is None:
        return "—"
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def pixmap_from_jpeg(jpeg_bytes: bytes | None, width: int, height: int) -> QtGui.QPixmap | None:
    if not jpeg_bytes:
        return None
    pixmap = QtGui.QPixmap()
    if not pixmap.loadFromData(jpeg_bytes, "JPG"):
        return None
    return pixmap.scaled(
        width,
        height,
        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        QtCore.Qt.TransformationMode.SmoothTransformation,
    )


class SlotCard(QtWidgets.QFrame):
    """Selectable Hyrule Archive card representing a single save slot."""

    clicked = QtCore.Signal(object)

    def __init__(self, slot_info: dict, files_word: str = "archivos", no_thumb_text: str = "Sin captura", parent=None) -> None:
        super().__init__(parent)
        self.slot_info = slot_info
        self.slot_path = slot_info["path"]
        self.setObjectName("SlotCard")
        self.setProperty("selected", False)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        thumb = QtWidgets.QLabel()
        thumb.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        thumb.setFixedHeight(124)
        thumb.setStyleSheet(
            f"background-color: #0e1611; border: 1px solid {COLORS['line']}; border-radius: 6px; color: {COLORS['muted']}; font-size: 9pt;"
        )
        pixmap = pixmap_from_jpeg(slot_info.get("jpeg_bytes"), 220, 122)
        if pixmap is not None:
            thumb.setPixmap(pixmap)
        else:
            thumb.setText(no_thumb_text)
        layout.addWidget(thumb)

        top_row = QtWidgets.QHBoxLayout()
        top_row.setSpacing(6)
        title_lbl = QtWidgets.QLabel(slot_info["title"])
        title_lbl.setStyleSheet(f"color: {COLORS['gold']}; font-weight: 700; font-size: 9.5pt;")
        top_row.addWidget(title_lbl)
        top_row.addStretch(1)
        size_lbl = QtWidgets.QLabel(f"{slot_info['size_kb']:.1f} KB")
        size_lbl.setStyleSheet(
            f"background-color: {COLORS['panel2']}; color: {COLORS['muted']}; border: 1px solid {COLORS['line']}; "
            "border-radius: 4px; padding: 1px 6px; font-size: 8pt;"
        )
        top_row.addWidget(size_lbl)
        layout.addLayout(top_row)

        scene_lbl = QtWidgets.QLabel(slot_info["scene_display"])
        scene_lbl.setWordWrap(True)
        scene_lbl.setStyleSheet(f"color: {COLORS['text']}; font-weight: 600; font-size: 10pt;")
        layout.addWidget(scene_lbl)

        stats = slot_info.get("stats") or {}
        if stats.get("hearts_max") is not None and stats.get("rupees") is not None:
            hearts_cur = format_hearts(stats.get("hearts_current"))
            hearts_max = stats.get("hearts_max")
            rupees = stats.get("rupees")
            skulls = stats.get("skulltulas", 0)
            vitals_lbl = QtWidgets.QLabel(f"♥ {hearts_cur}/{hearts_max}   ·   💎 {rupees}   ·   🕷 {skulls}")
            vitals_lbl.setStyleSheet(f"color: {COLORS['green']}; font-size: 8.5pt; font-weight: 600;")
            layout.addWidget(vitals_lbl)

        meta_lbl = QtWidgets.QLabel(f"{slot_info['files_count']} {files_word}  ·  {slot_info['mtime_str']}")
        meta_lbl.setObjectName("MutedLabel")
        layout.addWidget(meta_lbl)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit(self.slot_path)
        super().mousePressEvent(event)
