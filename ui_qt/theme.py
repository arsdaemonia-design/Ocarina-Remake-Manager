"""Hyrule Archive QSS theme and inline SVG vector icon renderer."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtSvg

COLORS = {
    "bg": "#06100b",
    "panel": "#0a1911",
    "panel2": "#0f2318",
    "panel_hover": "#153021",
    "gold": "#d8bb72",
    "gold_bright": "#f2da97",
    "gold_dim": "#998146",
    "text": "#eee8d5",
    "muted": "#a6b0a2",
    "line": "#1c3827",
    "green": "#7cd494",
    "green_bg": "#102a1b",
    "red": "#df8c7f",
    "red_bg": "#3b211e",
    "amber": "#f0c674",
    "amber_bg": "#3d3118",
    "disabled_bg": "#08140e",
    "disabled_fg": "#53695b",
}

_SVG_PATHS = {
    "triforce": (
        '<polygon points="12,3 17,12 7,12" fill="{c}"/>'
        '<polygon points="7,12 12,21 2,21" fill="{c}"/>'
        '<polygon points="17,12 22,21 12,21" fill="{c}"/>'
    ),
    "saves": (
        '<path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1z" '
        'fill="none" stroke="{c}" stroke-width="2" stroke-linejoin="round"/>'
    ),
    "inventory": (
        '<rect x="3" y="3" width="7" height="7" rx="1.5" fill="none" stroke="{c}" stroke-width="2"/>'
        '<rect x="14" y="3" width="7" height="7" rx="1.5" fill="none" stroke="{c}" stroke-width="2"/>'
        '<rect x="3" y="14" width="7" height="7" rx="1.5" fill="none" stroke="{c}" stroke-width="2"/>'
        '<rect x="14" y="14" width="7" height="7" rx="1.5" fill="none" stroke="{c}" stroke-width="2"/>'
    ),
    "mods": (
        '<polygon points="12,2 19,7 19,17 12,22 5,17 5,7" '
        'fill="none" stroke="{c}" stroke-width="2" stroke-linejoin="round"/>'
        '<polygon points="12,7 15.5,12 12,17 8.5,12" fill="{c}"/>'
    ),
    "backups": (
        '<path d="M6 2h12v4l-4 5v2l4 5v4H6v-4l4-5v-2L6 6V2z" '
        'fill="none" stroke="{c}" stroke-width="2" stroke-linejoin="round"/>'
    ),
    "settings": (
        '<circle cx="12" cy="12" r="3" fill="none" stroke="{c}" stroke-width="2"/>'
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 '
        '1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 '
        '1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 '
        '1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 '
        '1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 '
        '1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 '
        '1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 '
        '1.65 0 0 0-.33 1.82V9c.26.6.85 1 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 '
        '1.65 0 0 0-1.51 1z" fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
    ),
    "play": '<polygon points="7,4 20,12 7,20" fill="{c}"/>',
    "folder": (
        '<path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6z" '
        'fill="none" stroke="{c}" stroke-width="2" stroke-linejoin="round"/>'
    ),
    "warning": (
        '<path d="M12 3L2 20h20L12 3z" fill="none" stroke="{c}" stroke-width="2" stroke-linejoin="round"/>'
        '<line x1="12" y1="9" x2="12" y2="14" stroke="{c}" stroke-width="2" stroke-linecap="round"/>'
        '<circle cx="12" cy="17" r="1" fill="{c}"/>'
    ),
}


def make_svg_pixmap(icon_name: str, color: str | None = None, size: int = 20) -> QtGui.QPixmap:
    c = color or COLORS["gold"]
    body = _SVG_PATHS.get(icon_name, _SVG_PATHS["triforce"]).format(c=c)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>'.encode("utf-8")
    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(svg))
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def make_svg_icon(icon_name: str, color: str | None = None, size: int = 18) -> QtGui.QIcon:
    return QtGui.QIcon(make_svg_pixmap(icon_name, color=color, size=size))


def build_stylesheet() -> str:
    c = COLORS
    return f"""
    QMainWindow, QWidget {{
        background-color: {c['bg']};
        color: {c['text']};
        font-family: "Segoe UI", sans-serif;
        font-size: 10pt;
    }}
    QFrame#HeaderBar, QFrame#Sidebar, QFrame#ActivityBar {{
        background-color: {c['panel']};
        border: 1px solid {c['line']};
        border-radius: 10px;
    }}
    QFrame#CardPanel {{
        background-color: {c['panel']};
        border: 1px solid {c['line']};
        border-radius: 10px;
    }}
    QFrame#InnerPanel {{
        background-color: {c['panel2']};
        border: 1px solid {c['line']};
        border-radius: 8px;
    }}
    QFrame#ConflictBanner {{
        background-color: {c['amber_bg']};
        border: 1px solid {c['amber']};
        border-radius: 8px;
    }}
    QFrame#SlotCard {{
        background-color: {c['panel']};
        border: 1px solid {c['line']};
        border-radius: 10px;
    }}
    QFrame#SlotCard:hover {{
        background-color: {c['panel2']};
        border: 1px solid {c['gold_dim']};
    }}
    QFrame#SlotCard[selected="true"] {{
        background-color: {c['panel2']};
        border: 2px solid {c['gold']};
    }}
    QLabel {{
        background-color: transparent;
        color: {c['text']};
    }}
    QLabel#TitleLabel {{
        color: {c['gold']};
        font-size: 15pt;
        font-weight: 700;
        letter-spacing: 0.8px;
    }}
    QLabel#SectionTitle {{
        color: {c['gold']};
        font-size: 11pt;
        font-weight: 700;
        letter-spacing: 0.5px;
    }}
    QLabel#MutedLabel {{
        color: {c['muted']};
        font-size: 9pt;
    }}
    QPushButton {{
        background-color: {c['panel2']};
        color: {c['text']};
        border: 1px solid {c['line']};
        border-radius: 7px;
        padding: 7px 14px;
        font-weight: 600;
        font-size: 9.5pt;
    }}
    QPushButton:hover {{
        background-color: {c['panel_hover']};
        border-color: {c['gold_dim']};
    }}
    QPushButton:pressed {{
        background-color: {c['panel']};
    }}
    QPushButton:disabled {{
        background-color: {c['disabled_bg']};
        color: {c['disabled_fg']};
        border-color: #15291d;
    }}
    QPushButton#GoldButton {{
        background-color: #715f32;
        color: #fff6dc;
        border: 1px solid {c['gold']};
        font-weight: 700;
    }}
    QPushButton#GoldButton:hover {{
        background-color: #8b743f;
    }}
    QPushButton#GoldButton:disabled {{
        background-color: #2d271b;
        color: #796f56;
        border-color: #443b27;
    }}
    QPushButton#DangerButton {{
        background-color: #6b3730;
        color: #ffe6e0;
        border: 1px solid #a45d50;
    }}
    QPushButton#DangerButton:hover {{
        background-color: #88453d;
    }}
    QPushButton#DangerButton:disabled {{
        background-color: #2c1c1a;
        color: #7d5d58;
        border-color: #462a26;
    }}
    QPushButton#NavButton {{
        background-color: transparent;
        color: {c['muted']};
        border: 1px solid transparent;
        border-radius: 8px;
        padding: 10px 12px;
        text-align: left;
        font-weight: 600;
        font-size: 10pt;
    }}
    QPushButton#NavButton:hover {{
        background-color: {c['panel2']};
        color: {c['text']};
    }}
    QPushButton#NavButton[navActive="true"] {{
        background-color: {c['panel2']};
        color: {c['gold_bright']};
        border-left: 3px solid {c['gold']};
        border-top: 1px solid {c['line']};
        border-right: 1px solid {c['line']};
        border-bottom: 1px solid {c['line']};
    }}
    QPushButton#FilterPill {{
        padding: 5px 12px;
        border-radius: 14px;
        font-size: 9pt;
    }}
    QPushButton#FilterPill[pillActive="true"] {{
        background-color: #193b25;
        color: {c['gold_bright']};
        border: 1px solid {c['gold']};
    }}
    QComboBox, QLineEdit {{
        background-color: {c['panel2']};
        color: {c['text']};
        border: 1px solid {c['line']};
        border-radius: 7px;
        padding: 6px 10px;
        min-height: 22px;
    }}
    QComboBox:hover, QLineEdit:focus {{
        border-color: {c['gold_dim']};
    }}
    QComboBox:disabled, QLineEdit:disabled {{
        background-color: {c['disabled_bg']};
        color: {c['disabled_fg']};
        border-color: #15291d;
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {c['panel2']};
        color: {c['text']};
        border: 1px solid {c['gold_dim']};
        selection-background-color: #193c26;
        selection-color: #fff5d8;
    }}
    QCheckBox {{
        color: {c['text']};
        spacing: 8px;
        background: transparent;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid {c['line']};
        background-color: {c['panel2']};
    }}
    QCheckBox::indicator:checked {{
        background-color: {c['gold']};
        border-color: {c['gold_bright']};
    }}
    QTableWidget {{
        background-color: {c['panel']};
        alternate-background-color: #0c1d13;
        color: {c['text']};
        border: 1px solid {c['line']};
        border-radius: 8px;
        gridline-color: #15291d;
        selection-background-color: #193c26;
        selection-color: #fff5d8;
    }}
    QTableWidget::item {{
        padding: 6px 8px;
    }}
    QHeaderView::section {{
        background-color: {c['panel2']};
        color: {c['gold']};
        padding: 8px;
        border: none;
        border-bottom: 1px solid {c['line']};
        font-weight: 700;
        font-size: 9pt;
    }}
    QHeaderView::section:hover {{
        background-color: {c['panel_hover']};
        color: {c['gold_bright']};
        border-bottom: 1px solid {c['gold']};
    }}
    QPlainTextEdit {{
        background-color: #07130c;
        color: {c['text']};
        border: 1px solid {c['line']};
        border-radius: 6px;
        font-family: "Consolas", monospace;
        font-size: 9pt;
        padding: 4px;
    }}
    QProgressBar {{
        background-color: #09160e;
        border: 1px solid {c['line']};
        border-radius: 6px;
        text-align: center;
        color: {c['text']};
        font-size: 8.5pt;
        max-height: 14px;
    }}
    QProgressBar::chunk {{
        background-color: {c['gold']};
        border-radius: 5px;
    }}
    QScrollArea {{
        border: none;
        background-color: transparent;
    }}
    QScrollBar:vertical {{
        background: {c['panel']};
        width: 10px;
        margin: 0px;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical {{
        background: #21442f;
        min-height: 24px;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {c['gold_dim']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QToolTip {{
        background-color: {c['panel2']};
        color: {c['text']};
        border: 1px solid {c['gold']};
        padding: 6px;
        font-size: 9pt;
    }}
    """
