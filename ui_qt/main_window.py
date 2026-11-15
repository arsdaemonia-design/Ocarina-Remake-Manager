"""PySide6 MainWindow for Ocarina Remake Manager (Hyrule Archive Edition)."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Callable

from PySide6 import QtCore, QtGui, QtWidgets

from core.backups import list_backups, prune_old_backups
from core.i18n import Translator
from core.mods import (
    apply_mod_profile_files,
    deployed_mod,
    detect_mod_conflicts,
    download_and_install_gamebanana_mod,
    inspect_mod,
    install_mod_archive,
    mod_status,
    remove_mod_files,
    set_mod_state,
)
from core.ports import discover_known_ports, port_display_label, select_save_account
from core.process_guard import game_is_running, game_running_message
from core.saves import (
    activate_profile_files,
    contains_slot_folders,
    detect_active_profile,
    export_slot_files,
    import_external_save_as_profile,
    import_slot_files,
    inspect_slot,
    make_backup_slot,
    nx2navi_effective_active_dir,
    profile_items,
    save_active_as_profile_files,
    write_active_marker,
)
from nx2navi_ini import read_mod_log_status
from port_adapters import detect_port
from ui_qt.pages_mods_cfg import BackupsPage, ModsPage, SettingsPage
from ui_qt.pages_saves_inv import InventoryPage, SavesPage
from ui_qt.theme import COLORS, build_stylesheet, make_svg_icon, make_svg_pixmap
from ui_qt.workers import OperationWorker


def resolve_manager_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


class MainWindow(QtWidgets.QMainWindow):
    """Unified PySide6 application window with Quick Port Switcher and Global Profile."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.manager_dir = resolve_manager_dir()
        self.settings_path = self.manager_dir / "settings.json"
        try:
            self.settings: dict = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            self.settings = {}
        self.settings.setdefault("link_mod_profile_to_user", True)

        self.i18n = Translator(language=self.settings.get("language", "es"))
        self.default_game_dir = self.manager_dir
        self.backup_dir = self.manager_dir / "backups"
        self.mod_library_dir = self.manager_dir / "Mods"
        self.mod_library_dir.mkdir(exist_ok=True)
        self.log_file_path = self.manager_dir / "operations.log"

        self.known_ports = discover_known_ports(self.settings, self.manager_dir)
        raw_game_path = str(self.settings.get("game_path") or "").strip()
        configured = Path(raw_game_path).expanduser() if raw_game_path else None
        self.port = detect_port(configured) if (configured and configured.is_dir()) else None
        if not self.port and self.known_ports:
            self.port = self.known_ports[0]
        self.game_dir = Path(self.port["root"]) if self.port else (configured if (configured and configured.is_dir()) else self.manager_dir)

        self.active_root: Path | None = None
        self.account_candidates: list[Path] = []
        self.profile_paths: dict[str, Path] = {}
        self.slot_infos: dict[str, dict] = {}
        self.selected_slot_path: Path | None = None
        self.nx_mod_log_status: dict = {}
        self._mod_inspection_cache: dict = {}
        self._romfs_files_cache: dict = {}
        self._current_conflicts: list[dict] = []
        self._mod_operation_active = False
        self._active_worker: OperationWorker | None = None
        self._log_visible = True
        self.operation_logs: list[str] = []
        self.last_game_check_issue = False
        self.last_port_backup: Path | None = None
        self._nav_buttons: list[tuple[QtWidgets.QPushButton, str, str, str]] = []

        self.setWindowTitle("Ocarina Remake Manager · Hyrule Archive")
        self.setWindowIcon(make_svg_icon("triforce", COLORS["gold"], 32))
        self.resize(1260, 840)
        self.setMinimumSize(980, 680)
        self.setStyleSheet(build_stylesheet())

        self._build_ui()
        self._apply_translations()
        self.refresh()
        if self.port:
            active_name = self.active_profile_name() or self.tx("ninguno", "none")
            self.log_operation(self.tx(
                f"Port detectado: {self.port_label()} (perfil activo: {active_name})",
                f"Port detected: {self.port_label()} (active profile: {active_name})",
            ))
        else:
            self.select_page(4)
            self.report_progress(0.0, self.tx(
                "Bienvenido · Elige la carpeta de Hookshot, Longshot o NX2NAVI para comenzar",
                "Welcome · Select your Hookshot, Longshot, or NX2NAVI folder to begin",
            ))

    # --- i18n helpers ---
    def tr(self, text: str) -> str:
        return self.i18n.tr(text)

    def tx(self, spanish: str, english: str) -> str:
        return self.i18n.tx(spanish, english)

    def port_label(self, port: dict | None = None) -> str:
        target = self.port if port is None else port
        return port_display_label(target, self.tr("Port no identificado"))

    # --- settings / profile helpers ---
    def persist_settings(self) -> None:
        # Audit fix #5: remove stale top-level active_profile key when persisting settings.
        self.settings.pop("active_profile", None)
        temporary = self.settings_path.with_name(self.settings_path.name + ".tmp")
        temporary.write_text(json.dumps(self.settings, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.settings_path)

    def active_profile_name(self) -> str:
        port_id = self.port["id"] if self.port else ""
        port_profiles = self.settings.get("active_profiles", {})
        if port_id and port_id in port_profiles:
            return port_profiles[port_id]
        return ""

    def set_active_profile_name(self, name: str) -> None:
        port_id = self.port["id"] if self.port else "hookshot"
        self.settings.setdefault("active_profiles", {})[port_id] = name

    def is_mod_profile_linked(self) -> bool:
        return bool(self.settings.get("link_mod_profile_to_user", True))

    def selected_user_profile(self) -> str:
        return self.user_combo.currentText().strip()

    def selected_mod_profile(self) -> str:
        if self.is_mod_profile_linked() and self.selected_user_profile():
            return self.selected_user_profile()
        return self.mods_page.mod_profile_combo.currentText().strip() or self.selected_user_profile() or "Default"

    # --- UI construction ---
    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        outer = QtWidgets.QVBoxLayout(central)
        outer.setContentsMargins(14, 14, 14, 12)
        outer.setSpacing(10)

        # Top Header Bar
        header = QtWidgets.QFrame()
        header.setObjectName("HeaderBar")
        hl = QtWidgets.QHBoxLayout(header)
        hl.setContentsMargins(14, 10, 14, 10)
        hl.setSpacing(12)

        emblem = QtWidgets.QLabel()
        emblem.setPixmap(make_svg_pixmap("triforce", COLORS["gold"], 34))
        hl.addWidget(emblem)

        brand_col = QtWidgets.QVBoxLayout()
        brand_col.setSpacing(1)
        self.brand_title = QtWidgets.QLabel("OCARINA REMAKE MANAGER")
        self.brand_title.setObjectName("TitleLabel")
        brand_col.addWidget(self.brand_title)
        self.brand_sub = QtWidgets.QLabel("HYRULE ARCHIVE EDITION")
        self.brand_sub.setObjectName("MutedLabel")
        brand_col.addWidget(self.brand_sub)
        hl.addLayout(brand_col)

        hl.addSpacing(8)

        # Global User Profile Selector
        self.header_bar = header
        prof_col = QtWidgets.QVBoxLayout()
        prof_col.setSpacing(3)
        self.hdr_prof_lbl = QtWidgets.QLabel("PERFIL GLOBAL")
        self.hdr_prof_lbl.setObjectName("MutedLabel")
        prof_col.addWidget(self.hdr_prof_lbl)
        prof_row = QtWidgets.QHBoxLayout()
        prof_row.setSpacing(6)
        self.user_combo = QtWidgets.QComboBox()
        self.user_combo.setMinimumWidth(145)
        self.activate_profile_btn = QtWidgets.QPushButton("Activar perfil")
        self.activate_profile_btn.setObjectName("GoldButton")
        self.save_profile_btn = QtWidgets.QPushButton("+ Guardar…")
        self.import_profile_btn = QtWidgets.QPushButton("Importar save…")
        prof_row.addWidget(self.user_combo)
        prof_row.addWidget(self.activate_profile_btn)
        prof_row.addWidget(self.save_profile_btn)
        prof_row.addWidget(self.import_profile_btn)
        prof_col.addLayout(prof_row)
        hl.addLayout(prof_col)

        hl.addStretch(1)

        self.play_btn = QtWidgets.QPushButton("Jugar")
        self.play_btn.setObjectName("GoldButton")
        self.play_btn.setIcon(make_svg_icon("play", "#fff6dc", 16))
        self.play_btn.setMinimumHeight(40)
        self.play_btn.setMinimumWidth(118)
        hl.addWidget(self.play_btn)
        outer.addWidget(header)

        # Middle Area: Sidebar + Content Stack
        middle = QtWidgets.QHBoxLayout()
        middle.setSpacing(12)
        outer.addLayout(middle, 1)

        sidebar = QtWidgets.QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(252)
        self.sidebar_panel = sidebar
        sb_layout = QtWidgets.QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(10, 12, 10, 12)
        sb_layout.setSpacing(6)

        nav_specs = [
            ("saves", "nav.saves", "Partidas", "Saves"),
            ("inventory", "nav.inventory", "Inventario y Progreso", "Inventory & Progress"),
            ("mods", "nav.mods", "Mods", "Mods"),
            ("backups", "nav.backups", "Respaldos", "Backups"),
            ("settings", "nav.settings", "Configuración", "Settings"),
        ]
        for idx, (icon_name, _key, es_txt, en_txt) in enumerate(nav_specs):
            btn = QtWidgets.QPushButton(es_txt)
            btn.setObjectName("NavButton")
            btn.setIcon(make_svg_icon(icon_name, COLORS["gold"], 18))
            btn.setIconSize(QtCore.QSize(18, 18))
            btn.setProperty("navActive", idx == 0)
            btn.clicked.connect(lambda _checked=False, page_idx=idx: self.select_page(page_idx))
            sb_layout.addWidget(btn)
            self._nav_buttons.append((btn, icon_name, es_txt, en_txt))

        sb_layout.addStretch(1)

        # Single Port Selector + Active Profile Status Panel in Sidebar
        port_footer = QtWidgets.QFrame()
        port_footer.setObjectName("InnerPanel")
        self.port_footer = port_footer
        pfl = QtWidgets.QVBoxLayout(port_footer)
        pfl.setContentsMargins(10, 10, 10, 10)
        pfl.setSpacing(6)

        self.hdr_port_lbl = QtWidgets.QLabel("PORT ACTIVO")
        self.hdr_port_lbl.setObjectName("MutedLabel")
        pfl.addWidget(self.hdr_port_lbl)

        port_row = QtWidgets.QHBoxLayout()
        port_row.setSpacing(6)
        self.port_combo = QtWidgets.QComboBox()
        self.port_combo.setMinimumWidth(0)
        self.port_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.browse_port_btn = QtWidgets.QPushButton()
        self.browse_port_btn.setIcon(make_svg_icon("folder", COLORS["gold"], 16))
        self.browse_port_btn.setFixedWidth(34)
        port_row.addWidget(self.port_combo, 1)
        port_row.addWidget(self.browse_port_btn)
        pfl.addLayout(port_row)

        self.active_profile_lbl = QtWidgets.QLabel("—")
        self.active_profile_lbl.setWordWrap(True)
        pfl.addWidget(self.active_profile_lbl)

        self.active_profile_badge = QtWidgets.QLabel("—")
        self.active_profile_badge.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.active_profile_badge.setStyleSheet(
            f"background-color: {COLORS['panel']}; color: {COLORS['muted']}; "
            "border-radius: 5px; padding: 3px 6px; font-weight: 700; font-size: 8pt;"
        )
        pfl.addWidget(self.active_profile_badge)
        sb_layout.addWidget(port_footer)
        middle.addWidget(sidebar)

        self.stack = QtWidgets.QStackedWidget()
        self.saves_page = SavesPage()
        self.inventory_page = InventoryPage()
        self.mods_page = ModsPage()
        self.backups_page = BackupsPage()
        self.settings_page = SettingsPage()
        for page in (self.saves_page, self.inventory_page, self.mods_page, self.backups_page, self.settings_page):
            self.stack.addWidget(page)
        middle.addWidget(self.stack, 1)

        # Bottom Activity & Log Bar
        activity = QtWidgets.QFrame()
        activity.setObjectName("ActivityBar")
        act_layout = QtWidgets.QVBoxLayout(activity)
        act_layout.setContentsMargins(12, 8, 12, 8)
        act_layout.setSpacing(6)

        status_row = QtWidgets.QHBoxLayout()
        status_row.setSpacing(10)
        self.operation_status_label = QtWidgets.QLabel("Listo")
        self.operation_status_label.setStyleSheet(f"color: {COLORS['text']}; font-weight: 600; font-size: 9pt;")
        status_row.addWidget(self.operation_status_label, 1)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setFixedWidth(250)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        status_row.addWidget(self.progress_bar)

        self.toggle_log_btn = QtWidgets.QPushButton("Registro (0) ▼")
        status_row.addWidget(self.toggle_log_btn)
        act_layout.addLayout(status_row)

        self.log_container = QtWidgets.QWidget()
        log_row = QtWidgets.QHBoxLayout(self.log_container)
        log_row.setContentsMargins(0, 0, 0, 0)
        log_row.setSpacing(8)
        self.log_text = QtWidgets.QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFixedHeight(86)
        log_row.addWidget(self.log_text, 1)
        self.clear_log_btn = QtWidgets.QPushButton("Limpiar")
        log_row.addWidget(self.clear_log_btn, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        act_layout.addWidget(self.log_container)
        outer.addWidget(activity)

        # Connect signals
        self.port_combo.currentIndexChanged.connect(self._on_quick_port_changed)
        self.browse_port_btn.clicked.connect(self.choose_game)
        self.user_combo.currentIndexChanged.connect(self._on_user_profile_selected)
        self.activate_profile_btn.clicked.connect(self.activate_profile)
        self.save_profile_btn.clicked.connect(self.save_active_as_profile)
        self.import_profile_btn.clicked.connect(self.import_save_as_new_profile)
        self.play_btn.clicked.connect(self.launch_game)

        self.saves_page.slot_selected.connect(self._on_slot_selected)
        self.saves_page.refresh_requested.connect(self.refresh)
        self.saves_page.backup_requested.connect(self.backup_slot)
        self.saves_page.export_requested.connect(self.export_slot)
        self.saves_page.import_requested.connect(self.import_slot)

        self.mods_page.filter_changed.connect(lambda _mode: self.refresh_mods())
        self.mods_page.search_changed.connect(lambda _txt: self.refresh_mods())
        self.mods_page.link_toggled.connect(self._on_link_mode_changed)
        self.mods_page.apply_mod_profile_requested.connect(self.apply_selected_mod_profile)
        self.mods_page.save_mod_profile_requested.connect(self.save_mod_profile_as)
        self.mods_page.resolve_conflicts_requested.connect(self.resolve_romfs_conflicts)
        self.mods_page.install_requested.connect(self.install_mod)
        self.mods_page.gamebanana_requested.connect(self.install_from_gamebanana)
        self.mods_page.toggle_requested.connect(self.toggle_mod)
        self.mods_page.remove_requested.connect(self.remove_mod)
        self.mods_page.mod_selected.connect(self.update_mod_action_buttons)

        self.backups_page.refresh_requested.connect(self.refresh_backups)
        self.backups_page.open_selected_requested.connect(self._open_folder_in_explorer)
        self.backups_page.open_root_requested.connect(lambda: self._open_folder_in_explorer(str(self.backup_dir)))
        self.backups_page.prune_requested.connect(self.prune_backups)

        self.settings_page.port_chosen.connect(self.switch_port_path)
        self.settings_page.manual_path_submitted.connect(self.switch_port_path)
        self.settings_page.browse_requested.connect(self.choose_game)
        self.settings_page.account_changed.connect(self._on_account_changed)
        self.settings_page.language_changed.connect(self._on_language_changed)
        self.settings_page.link_changed.connect(self._on_link_mode_changed)

        self.toggle_log_btn.clicked.connect(self.toggle_log_panel)
        self.clear_log_btn.clicked.connect(self.clear_operation_logs)

    def select_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for idx, (btn, _icon, _es, _en) in enumerate(self._nav_buttons):
            btn.setProperty("navActive", idx == index)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        if index == 1:
            self._update_inventory_view()
        elif index == 3:
            self.refresh_backups()

    def _apply_translations(self) -> None:
        self.brand_sub.setText(self.tx(
            "HYRULE ARCHIVE EDITION · PARTIDAS, PERFILES Y MODS",
            "HYRULE ARCHIVE EDITION · SAVES, PROFILES & MODS",
        ))
        self.hdr_port_lbl.setText(self.tx("PORT ACTIVO", "ACTIVE PORT"))
        self.hdr_prof_lbl.setText(self.tx("PERFIL GLOBAL", "GLOBAL PROFILE"))
        self.save_profile_btn.setText(self.tx("+ Guardar perfil…", "+ Save profile…"))
        self.import_profile_btn.setText(self.tx("Importar save…", "Import save…"))
        self.play_btn.setText(self.tx("Jugar", "Play"))
        self.browse_port_btn.setToolTip(self.tx(
            "Elegir manualmente la carpeta de Hookshot, Longshot o NX2NAVI.",
            "Browse for a Hookshot, Longshot, or NX2NAVI folder.",
        ))
        self.play_btn.setToolTip(self.tx(
            "Aplica el perfil seleccionado (saves y mods) y abre el juego.",
            "Applies the selected profile (saves and mods) and launches the game.",
        ))
        self.save_profile_btn.setToolTip(self.tx(
            "Crea o actualiza un perfil con las partidas activas y la selección actual de mods.",
            "Creates or updates a profile with the active saves and current mod selection.",
        ))
        self.import_profile_btn.setToolTip(self.tx(
            "Importa una carpeta de emulador (slot_00..05) o slot individual como nuevo perfil global.",
            "Import an emulator save folder (slot_00..05) or standalone slot as a new global profile.",
        ))
        for btn, _icon, es_txt, en_txt in self._nav_buttons:
            btn.setText(self.tx(es_txt, en_txt))
        self.clear_log_btn.setText(self.tx("Limpiar", "Clear"))
        self._update_log_toggle_label()
        self.saves_page.retranslate(self.tx)
        self.mods_page.retranslate(self.tx)
        self.backups_page.retranslate(self.tx)
        self.settings_page.retranslate(str(self.manager_dir), str(self.log_file_path), self.tx)
        self.settings_page.language_combo.blockSignals(True)
        self.settings_page.language_combo.setCurrentText("English" if self.i18n.language == "en" else "Español")
        self.settings_page.language_combo.blockSignals(False)

    # --- Logging and Progress ---
    def toggle_log_panel(self) -> None:
        self._log_visible = not self._log_visible
        self.log_container.setVisible(self._log_visible)
        self._update_log_toggle_label()

    def _update_log_toggle_label(self) -> None:
        arrow = "▼" if self._log_visible else "▲"
        self.toggle_log_btn.setText(self.tx(
            f"Registro ({len(self.operation_logs)}) {arrow}",
            f"Log ({len(self.operation_logs)}) {arrow}",
        ))

    def clear_operation_logs(self) -> None:
        self.operation_logs.clear()
        self.log_text.clear()
        self._update_log_toggle_label()

    def log_operation(self, message: str, level: str = "INFO") -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        prefix = f"[{stamp}] " if level == "INFO" else f"[{stamp} · {level}] "
        entry = prefix + str(message)
        self.operation_logs.append(entry)
        if len(self.operation_logs) > 300:
            self.operation_logs = self.operation_logs[-300:]
        self.log_text.appendPlainText(entry)
        self._update_log_toggle_label()
        try:
            with open(self.log_file_path, "a", encoding="utf-8") as stream:
                stream.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [{level}] {message}\n")
        except OSError:
            pass

    def report_progress(self, fraction: float | None, text: str = "") -> None:
        if text:
            self.operation_status_label.setText(text)
        if fraction is None:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(max(0, min(100, int(fraction * 100))))

    # --- Port & Account Switching ---
    def _populate_port_selector(self) -> None:
        self.port_combo.blockSignals(True)
        self.port_combo.clear()
        current_root = str(self.port["root"]).casefold() if self.port else ""
        selected_idx = -1
        for idx, p in enumerate(self.known_ports):
            self.port_combo.addItem(self.port_label(p), str(p["root"]))
            if str(p["root"]).casefold() == current_root:
                selected_idx = idx
        if self.port and selected_idx < 0:
            self.port_combo.addItem(self.port_label(self.port), str(self.port["root"]))
            selected_idx = self.port_combo.count() - 1
        if self.port_combo.count() == 0:
            self.port_combo.addItem(self.tx("— Seleccionar carpeta de port (📁) —", "— Select port folder (📁) —"), "")
            selected_idx = 0
        if selected_idx >= 0:
            self.port_combo.setCurrentIndex(selected_idx)
        self.port_combo.blockSignals(False)

    def _on_quick_port_changed(self, idx: int) -> None:
        if self._mod_operation_active or idx < 0:
            return
        root_str = self.port_combo.itemData(idx)
        if root_str and (not self.port or str(root_str).casefold() != str(self.port["root"]).casefold()):
            self.switch_port_path(str(root_str))

    def choose_game(self) -> None:
        if self._mod_operation_active:
            return
        start_dir = str(self.default_game_dir if self.default_game_dir.is_dir() else self.game_dir)
        chosen = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tx("Selecciona la carpeta del port", "Select the port folder"),
            start_dir,
        )
        if chosen:
            self.switch_port_path(chosen)

    def switch_port_path(self, raw_path: str) -> None:
        if self._mod_operation_active:
            return
        raw = str(raw_path).strip().strip('"')
        if raw.lower().startswith("file://"):
            from urllib.parse import unquote, urlparse
            raw = unquote(urlparse(raw).path)
            if len(raw) > 2 and raw[0] == "/" and raw[2] == ":":
                raw = raw[1:]
        if raw.lower().startswith(("http://", "https://")):
            QtWidgets.QMessageBox.critical(
                self,
                self.tx("Ruta no válida", "Invalid path"),
                self.tx("Pega una ruta local de Windows, no una URL web.", "Paste a local Windows path, not a web URL."),
            )
            return
        path = Path(raw).expanduser()
        if not path.is_dir():
            QtWidgets.QMessageBox.critical(self, self.tx("Carpeta no encontrada", "Folder not found"), str(path))
            return

        resolved = path.resolve()
        self.port = detect_port(resolved)
        self.game_dir = Path(self.port["root"]) if self.port else resolved
        self.settings["game_path"] = str(self.game_dir)
        if self.port:
            known = list(self.settings.get("known_ports", []))
            norm = str(self.port["root"])
            if norm not in known:
                known.append(norm)
                self.settings["known_ports"] = known
        self.persist_settings()
        self.known_ports = discover_known_ports(self.settings, self.default_game_dir)

        self.user_combo.blockSignals(True)
        self.user_combo.clear()
        self.user_combo.blockSignals(False)
        self.selected_slot_path = None

        if not self.port:
            self.log_operation(self.tx(f"Carpeta sin port compatible: {self.game_dir}", f"Unsupported folder: {self.game_dir}"), level="WARN")
            QtWidgets.QMessageBox.warning(
                self,
                self.tx("No se detectó un port compatible", "No supported port detected"),
                self.tx(
                    "Esta carpeta no parece ser Hookshot, NX2NAVI o Longshot. Se guardó la ruta, pero las acciones quedan desactivadas.",
                    "This folder does not look like Hookshot, NX2NAVI, or Longshot. The path was saved, but game actions are disabled.",
                ),
            )
        self.refresh()
        if self.port:
            active_name = self.active_profile_name() or self.tx("sin identificar", "unidentified")
            self.log_operation(self.tx(
                f"Port cambiado a {self.port_label()} (perfil activo: {active_name})",
                f"Switched port to {self.port_label()} (active profile: {active_name})",
            ))

    def _on_account_changed(self, account_name: str) -> None:
        if not self.port or not account_name or self._mod_operation_active:
            return
        self.settings.setdefault("selected_accounts", {})[self.port["id"]] = account_name
        self.persist_settings()
        self.refresh()

    def _on_language_changed(self, text: str) -> None:
        lang = "en" if text == "English" else "es"
        if lang == self.i18n.language:
            return
        self.i18n.set_language(lang)
        self.settings["language"] = lang
        self.persist_settings()
        self._apply_translations()
        self.refresh()

    def _on_link_mode_changed(self, checked: bool) -> None:
        self.settings["link_mod_profile_to_user"] = bool(checked)
        self.persist_settings()
        self.mods_page.set_link_mode(checked, self.selected_user_profile(), self.tx)
        self.settings_page.global_link_check.blockSignals(True)
        self.settings_page.global_link_check.setChecked(checked)
        self.settings_page.global_link_check.blockSignals(False)
        self.refresh_mod_profile_choices()

    # --- Main Refresh Pipeline ---
    def refresh(self) -> None:
        self._populate_port_selector()
        self.settings_page.populate_ports(self.known_ports, str(self.port["root"]) if self.port else "")
        self.settings_page.path_edit.setText(str(self.game_dir))
        self.settings_page.global_link_check.blockSignals(True)
        self.settings_page.global_link_check.setChecked(self.is_mod_profile_linked())
        self.settings_page.global_link_check.blockSignals(False)

        if not self.port:
            self.settings_page.path_edit.setText("")
            self.settings_page.path_edit.setPlaceholderText(self.tx(
                "Elige la carpeta de Hookshot, Longshot o NX2NAVI…",
                "Select your Hookshot, Longshot, or NX2NAVI folder…",
            ))
            self.active_profile_lbl.setText("—")
            self.active_profile_badge.setText(self.tx("○ SIN PORT", "○ NO PORT"))
            self.active_profile_badge.setStyleSheet(
                f"background-color: {COLORS['panel']}; color: {COLORS['muted']}; border-radius: 5px; padding: 3px 6px; font-weight: 700; font-size: 8pt;"
            )
            self.active_root = None
            self.account_candidates = []
            self.profile_paths = {}
            self.settings_page.populate_accounts([], "")
            self.user_combo.blockSignals(True)
            self.user_combo.clear()
            self.user_combo.setEnabled(False)
            self.user_combo.blockSignals(False)
            self.activate_profile_btn.setEnabled(False)
            self.save_profile_btn.setEnabled(False)
            self.import_profile_btn.setEnabled(False)
            self.play_btn.setEnabled(False)
            self.saves_page.set_actions_enabled(False, self._mod_operation_active)
            self.saves_page.clear_slots(self.tx, no_port=True)
            self._update_profile_mode_ui("", "", False)
            self.refresh_mods()
            return

        account, accounts = select_save_account(self.port, self.settings, contains_slot_folders)
        self.active_root = account
        self.account_candidates = accounts
        self.settings_page.populate_accounts([a.name for a in accounts], account.name if account else "")

        self.profile_paths = {
            p.name: p
            for p in sorted(account.iterdir(), key=lambda item: item.name.casefold())
            if p.is_dir() and contains_slot_folders(p)
        } if account else {}

        effective_active = nx2navi_effective_active_dir(self.port, account) if self.port["id"] == "nx2navi" else account
        has_active_saves = bool(effective_active and contains_slot_folders(effective_active))
        active_name, changed = (
            detect_active_profile(self.port, account, self.profile_paths, self.active_profile_name())
            if has_active_saves
            else ("", False)
        )
        if active_name and changed:
            self.set_active_profile_name(active_name)
            self.persist_settings()

        if active_name and active_name in self.profile_paths and has_active_saves:
            self.active_profile_lbl.setText(self.tx(f"En uso: {active_name}", f"Active: {active_name}"))
            self.active_profile_badge.setText(self.tx("● ACTIVO EN EL JUEGO", "● ACTIVE IN GAME"))
            self.active_profile_badge.setStyleSheet(
                f"background-color: {COLORS['green_bg']}; color: {COLORS['green']}; border-radius: 5px; padding: 3px 6px; font-weight: 700; font-size: 8pt;"
            )
        elif has_active_saves:
            self.active_profile_lbl.setText(self.tx("Sin identificar (hay saves)", "Unidentified (saves exist)"))
            self.active_profile_badge.setText(self.tx("● PARTIDA ACTIVA", "● ACTIVE SAVE"))
            self.active_profile_badge.setStyleSheet(
                f"background-color: {COLORS['amber_bg']}; color: {COLORS['amber']}; border-radius: 5px; padding: 3px 6px; font-weight: 700; font-size: 8pt;"
            )
        else:
            self.active_profile_lbl.setText(self.tx("Sin partidas en la raíz", "No saves in root"))
            self.active_profile_badge.setText(self.tx("○ SIN PARTIDA ACTIVA", "○ NO ACTIVE SAVE"))
            self.active_profile_badge.setStyleSheet(
                f"background-color: {COLORS['panel']}; color: {COLORS['muted']}; border-radius: 5px; padding: 3px 6px; font-weight: 700; font-size: 8pt;"
            )

        previous_user = self.user_combo.currentText()
        names = list(self.profile_paths)
        self.user_combo.blockSignals(True)
        self.user_combo.clear()
        self.user_combo.addItems(names)
        if names:
            if previous_user in names:
                self.user_combo.setCurrentText(previous_user)
            elif active_name and active_name in names:
                self.user_combo.setCurrentText(active_name)
            elif "Nico" in names:
                self.user_combo.setCurrentText("Nico")
            else:
                self.user_combo.setCurrentIndex(0)
            self.user_combo.setEnabled(not self._mod_operation_active)
        else:
            self.user_combo.setEnabled(False)
        self.user_combo.blockSignals(False)

        self.save_profile_btn.setEnabled(has_active_saves and not self._mod_operation_active)
        self.import_profile_btn.setEnabled(bool(self.active_root) and not self._mod_operation_active)
        self.saves_page.set_actions_enabled(bool(has_active_saves or self.profile_paths), self._mod_operation_active)
        self.play_btn.setEnabled(Path(self.port.get("launch_exe", "")).is_file() and not self._mod_operation_active)

        self.refresh_mod_profile_choices()
        self.refresh_slots()
        self.refresh_mods()

    def _on_user_profile_selected(self) -> None:
        self.refresh_slots()
        self.refresh_mod_profile_choices()

    def _update_profile_mode_ui(self, selected_profile: str, active_profile: str, viewing_active: bool) -> None:
        if not self.port:
            self.saves_page.profile_mode_badge.setText("—")
            self.saves_page.slots_heading_label.setText(self.tx("ESPACIOS DE GUARDADO", "SAVE SLOTS"))
            self.activate_profile_btn.setEnabled(False)
            self.activate_profile_btn.setText(self.tx("Activar perfil…", "Activate profile…"))
            return
        if not selected_profile or selected_profile not in self.profile_paths:
            self.saves_page.profile_mode_badge.setText(self.tx("Sin perfiles guardados", "No saved profiles"))
            self.saves_page.profile_mode_badge.setStyleSheet(
                f"background-color: {COLORS['panel2']}; color: {COLORS['muted']}; border-radius: 6px; padding: 4px 10px; font-weight: 700; font-size: 9pt;"
            )
            self.saves_page.slots_heading_label.setText(self.tx("ESPACIOS DE GUARDADO", "SAVE SLOTS"))
            self.activate_profile_btn.setEnabled(False)
            self.activate_profile_btn.setText(self.tx("Activar perfil…", "Activate profile…"))
            return

        effective_active = nx2navi_effective_active_dir(self.port, self.active_root) if self.port["id"] == "nx2navi" else self.active_root
        has_active_slots = bool(effective_active and contains_slot_folders(effective_active))
        if viewing_active and selected_profile == active_profile and has_active_slots:
            self.saves_page.profile_mode_badge.setText(self.tx("● VIENDO PERFIL ACTIVO", "● VIEWING ACTIVE PROFILE"))
            self.saves_page.profile_mode_badge.setStyleSheet(
                f"background-color: {COLORS['green_bg']}; color: {COLORS['green']}; border-radius: 6px; padding: 4px 10px; font-weight: 700; font-size: 9pt;"
            )
            self.saves_page.slots_heading_label.setText(self.tx(
                f"ESPACIOS DE GUARDADO  ·  ACTIVO EN EL JUEGO («{active_profile}»)",
                f"SAVE SLOTS  ·  ACTIVE IN GAME ('{active_profile}')",
            ))
            # Allow activating if linked mod profile differs from currently enabled mods, else mark active
            self.activate_profile_btn.setEnabled(False)
            self.activate_profile_btn.setText(self.tx("Perfil activo", "Active profile"))
        elif viewing_active:
            self.saves_page.profile_mode_badge.setText(self.tx("● VIENDO PARTIDA ACTIVA", "● VIEWING ACTIVE SAVE"))
            self.saves_page.profile_mode_badge.setStyleSheet(
                f"background-color: {COLORS['green_bg']}; color: {COLORS['green']}; border-radius: 6px; padding: 4px 10px; font-weight: 700; font-size: 9pt;"
            )
            self.saves_page.slots_heading_label.setText(self.tx("ESPACIOS DE GUARDADO  ·  ACTIVO EN EL JUEGO", "SAVE SLOTS  ·  ACTIVE IN GAME"))
            self.activate_profile_btn.setEnabled(not self._mod_operation_active)
            self.activate_profile_btn.setText(self.tx(f"Activar «{selected_profile}»", f"Activate '{selected_profile}'"))
        else:
            self.saves_page.profile_mode_badge.setText(self.tx(
                "👁 VISTA PREVIA (NO ACTIVO) — Pulsa «Activar» para cargarlo",
                "👁 PREVIEW ONLY (NOT ACTIVE) — Click 'Activate' to load",
            ))
            self.saves_page.profile_mode_badge.setStyleSheet(
                f"background-color: {COLORS['amber_bg']}; color: {COLORS['amber']}; border-radius: 6px; padding: 4px 10px; font-weight: 700; font-size: 9pt;"
            )
            self.saves_page.slots_heading_label.setText(self.tx(
                f"ESPACIOS DE GUARDADO  ·  VISTA PREVIA DE «{selected_profile}»",
                f"SAVE SLOTS  ·  PREVIEW OF '{selected_profile}'",
            ))
            self.activate_profile_btn.setEnabled(not self._mod_operation_active)
            self.activate_profile_btn.setText(self.tx(f"Activar «{selected_profile}»", f"Activate '{selected_profile}'"))

    def refresh_slots(self) -> None:
        self.slot_infos.clear()
        if not self.port:
            self._update_profile_mode_ui("", "", False)
            self.saves_page.clear_slots(self.tx)
            self._update_inventory_view()
            return

        selected_profile = self.selected_user_profile()
        active_profile = self.active_profile_name()
        effective_active = nx2navi_effective_active_dir(self.port, self.active_root) if self.port["id"] == "nx2navi" else self.active_root
        has_active_slots = bool(effective_active and contains_slot_folders(effective_active))

        if selected_profile in self.profile_paths and selected_profile != active_profile:
            folder = self.profile_paths[selected_profile]
            viewing_active = False
            self.saves_page.save_status_label.setText(self.tx(
                f"Mostrando la copia guardada del perfil «{selected_profile}». Pulsa «Activar «{selected_profile}»» para cargar saves y mods en {self.port['name']}.",
                f"Showing the saved copy of profile '{selected_profile}'. Click 'Activate '{selected_profile}'' to load saves and mods into {self.port['name']}.",
            ))
        elif has_active_slots:
            folder = effective_active
            viewing_active = True
            self.saves_page.save_status_label.setText(self.tx(
                f"Mostrando los slots activos que {self.port['name']} carga al iniciar.",
                f"Showing the active slots {self.port['name']} loads at startup.",
            ))
        elif selected_profile in self.profile_paths:
            folder = self.profile_paths[selected_profile]
            viewing_active = False
            self.saves_page.save_status_label.setText(self.tx(
                f"No hay slots en la raíz activa. Pulsa «Activar «{selected_profile}»» para cargar este perfil.",
                f"No slots in the active root folder. Click 'Activate '{selected_profile}'' to load this profile.",
            ))
        else:
            folder = None
            viewing_active = False
            self.saves_page.save_status_label.setText(self.tx("No se encontraron carpetas de slots.", "No save slot folders were found."))

        self._update_profile_mode_ui(selected_profile, active_profile, viewing_active)
        if not folder:
            self.selected_slot_path = None
            self.saves_page.clear_slots(self.tx)
            self._update_inventory_view()
            return

        infos: list[dict] = []
        for slot in sorted(folder.glob("slot_*")):
            if slot.is_dir():
                info = inspect_slot(slot, self.tx)
                self.slot_infos[str(slot)] = info
                infos.append(info)

        if self.selected_slot_path and str(self.selected_slot_path) in self.slot_infos:
            selected = self.selected_slot_path
        elif infos:
            selected = infos[0]["path"]
        else:
            selected = None
        self.selected_slot_path = selected
        self.saves_page.populate_slots(infos, selected, self.tx)
        self.saves_page.update_preview(self.slot_infos.get(str(selected)) if selected else None, self.tx)
        self._update_inventory_view()

    def _on_slot_selected(self, slot_path: Path) -> None:
        self.selected_slot_path = Path(slot_path)
        self.saves_page.mark_selected(self.selected_slot_path)
        self.saves_page.update_preview(self.slot_infos.get(str(self.selected_slot_path)), self.tx)
        self._update_inventory_view()

    def _update_inventory_view(self) -> None:
        info = self.slot_infos.get(str(self.selected_slot_path)) if self.selected_slot_path else None
        prof = self.selected_user_profile() or self.active_profile_name() or "—"
        self.inventory_page.update_slot(info, self.port_label(), prof, self.tx)

    # --- Mod profiles & Mod list ---
    def refresh_mod_profile_choices(self) -> None:
        linked = self.is_mod_profile_linked()
        active_user = self.selected_user_profile()
        self.mods_page.set_link_mode(linked, active_user, self.tx)

        # Audit fix #3: treat NX2NAVI identically to Hookshot and Longshot for profile names.
        profiles = self.settings.get("mod_profiles", {}).get(self.port["id"], {}) if self.port else {}
        names = list(profiles)
        if active_user:
            names.append(active_user)
        names.append("Default")
        values = list(dict.fromkeys(names))

        combo = self.mods_page.mod_profile_combo
        current = combo.currentText().strip()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(values)
        if linked and active_user and active_user in values:
            combo.setCurrentText(active_user)
        elif current in values:
            combo.setCurrentText(current)
        elif active_user in values:
            combo.setCurrentText(active_user)
        elif values:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _save_mod_profile_state(self, profile_name: str | None = None, changed_mod: str | None = None, changed_enabled: bool | None = None) -> None:
        if not self.port:
            return
        name = profile_name or self.selected_mod_profile()
        port_profiles = self.settings.setdefault("mod_profiles", {}).setdefault(self.port["id"], {})
        if name in port_profiles and changed_mod is not None:
            enabled = set(port_profiles[name])
            if changed_enabled:
                enabled.add(changed_mod)
            else:
                enabled.discard(changed_mod)
        else:
            enabled = {
                mod.name for mod in self.mod_library_dir.iterdir()
                if mod.is_dir() and mod_status(self.port, mod, inspect_cache=self._mod_inspection_cache, nx_mod_log_status=self.nx_mod_log_status)["enabled"]
            }
            if changed_mod is not None:
                if changed_enabled:
                    enabled.add(changed_mod)
                else:
                    enabled.discard(changed_mod)
        port_profiles[name] = sorted(enabled, key=str.casefold)
        self.persist_settings()

    def refresh_mods(self) -> None:
        selected_before = self.mods_page.selected_mod_path()
        self.refresh_mod_profile_choices()
        if not self.port:
            self.mods_page.populate_mods([])
            self.mods_page.show_conflicts([], self.tx)
            self.update_mod_action_buttons()
            return

        self.nx_mod_log_status = (
            read_mod_log_status(self.port["root"] / "logs", game_root=self.port["root"], library_dir=self.mod_library_dir)
            if self.port["id"] == "nx2navi"
            else {}
        )

        search_text = self.mods_page.search_edit.text().strip().casefold()
        rows: list[dict] = []
        enabled_names: list[str] = []

        for mod in sorted(self.mod_library_dir.iterdir(), key=lambda p: p.name.casefold()):
            if not mod.is_dir():
                continue
            info = mod_status(self.port, mod, inspect_cache=self._mod_inspection_cache, nx_mod_log_status=self.nx_mod_log_status)
            if info["enabled"]:
                enabled_names.append(mod.name)
            if search_text and search_text not in mod.name.casefold():
                continue

            if info["incompatible"]:
                tag, symbol = "incompatible", "✕ "
            elif info.get("review_required"):
                tag, symbol = "review", "▲ "
            elif not info["deployed"]:
                tag, symbol = "library_only", "◇ "
            elif info["enabled"]:
                tag, symbol = "enabled", "● "
            else:
                tag, symbol = "disabled", "○ "

            rows.append(
                {
                    "path": mod,
                    "name": mod.name,
                    "kind_text": self.tr(info["kind"]),
                    "state_text": self.tr(info["state"]),
                    "tag": tag,
                    "symbol": symbol,
                }
            )

        self.mods_page.populate_mods(rows, selected_before)
        self._current_conflicts = detect_mod_conflicts(
            self.mod_library_dir,
            enabled_names,
            inspect_cache=self._mod_inspection_cache,
            romfs_cache=self._romfs_files_cache,
        )
        self.mods_page.show_conflicts(self._current_conflicts, self.tx)
        self.update_mod_action_buttons()

    def update_mod_action_buttons(self) -> None:
        if self._mod_operation_active:
            self.mods_page.toggle_btn.setEnabled(False)
            self.mods_page.remove_btn.setEnabled(False)
            return
        sel = self.mods_page.selected_mod_path()
        if not sel:
            self.mods_page.detail_label.setText(self.tx(
                "Selecciona un mod para ver detalles y su estado en el port.",
                "Select a mod to see details and its status in the port.",
            ))
            self.mods_page.toggle_btn.setEnabled(bool(self.port))
            self.mods_page.toggle_btn.setText(self.tx("Activar / desactivar", "Enable / disable"))
            self.mods_page.remove_btn.setEnabled(False)
            self.mods_page.remove_btn.setText(self.tx("Desinstalar mod…", "Uninstall mod…"))
            return

        mod = Path(sel)
        info = mod_status(self.port, mod, inspect_cache=self._mod_inspection_cache, nx_mod_log_status=self.nx_mod_log_status)
        if info.get("log_detail"):
            detail = info["log_detail"]
        elif info.get("review_required"):
            detail = self.tx(
                "NX2NAVI aún no ha informado si este ExeFS se puede aplicar. Revisa el estado en su launcher después de iniciar.",
                "NX2NAVI has not reported whether this ExeFS patch can be applied yet. Check its launcher status after starting.",
            )
        elif self.port and self.port["id"] in ("hookshot", "longshot") and info["exefs"] and not info["romfs"]:
            detail = self.tx(
                "Este paquete contiene solo ExeFS; Hookshot y Longshot no lo cargarán.",
                "This package contains only ExeFS; Hookshot and Longshot will not load it.",
            )
        else:
            detail = self.tx(
                f"Biblioteca: {self.mod_library_dir.name} · Port: {self.port['name'] if self.port else '—'} · {'desplegado' if info['deployed'] else 'solo biblioteca'}",
                f"Library: {self.mod_library_dir.name} · Port: {self.port['name'] if self.port else '—'} · {'deployed' if info['deployed'] else 'library only'}",
            )
        self.mods_page.detail_label.setText(detail)

        if info["incompatible"] and not info.get("known_not_usable"):
            self.mods_page.toggle_btn.setText(self.tx("No compatible", "Incompatible"))
            self.mods_page.toggle_btn.setEnabled(False)
        elif info.get("known_not_usable"):
            if info["enabled"]:
                self.mods_page.toggle_btn.setText(self.tx("Desactivar mod", "Disable mod"))
                self.mods_page.toggle_btn.setEnabled(True)
            else:
                self.mods_page.toggle_btn.setText(self.tx("Not Usable en NX2NAVI", "Not Usable in NX2NAVI"))
                self.mods_page.toggle_btn.setEnabled(False)
        else:
            self.mods_page.toggle_btn.setEnabled(True)
            self.mods_page.toggle_btn.setText(
                self.tx("Activar mod", "Enable mod") if not info["enabled"] else self.tx("Desactivar mod", "Disable mod")
            )
        self.mods_page.remove_btn.setEnabled(True)
        self.mods_page.remove_btn.setText(self.tx("Desinstalar seleccionado…", "Uninstall selected…"))

    # --- Backups Browser ---
    def refresh_backups(self) -> None:
        records = list_backups(self.backup_dir)
        self.backups_page.populate_backups(records, self.tx)

    def prune_backups(self) -> None:
        if self._mod_operation_active:
            return
        records = list_backups(self.backup_dir)
        if len(records) <= 15:
            QtWidgets.QMessageBox.information(
                self,
                self.tx("Respaldos", "Backups"),
                self.tx(f"Solo hay {len(records)} respaldos guardados (el mínimo conservado es 15).", f"Only {len(records)} backups exist (latest 15 are always kept)."),
            )
            return
        reply = QtWidgets.QMessageBox.question(
            self,
            self.tx("Limpiar respaldos antiguos", "Prune old backups"),
            self.tx(
                f"Se conservarán los 15 respaldos más recientes y se eliminarán {len(records) - 15} antiguos. ¿Continuar?",
                f"The 15 newest backups will be kept and {len(records) - 15} older backups will be deleted. Continue?",
            ),
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        removed = prune_old_backups(self.backup_dir, keep_latest=15)
        self.log_operation(self.tx(f"Eliminados {removed} respaldos antiguos", f"Removed {removed} old backups"))
        self.refresh_backups()

    def _open_folder_in_explorer(self, path_str: str) -> None:
        target = Path(path_str)
        if not target.exists():
            return
        if os.name == "nt":
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])

    # --- Background Worker Orchestration ---
    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self.port_combo,
            self.browse_port_btn,
            self.user_combo,
            self.activate_profile_btn,
            self.save_profile_btn,
            self.import_profile_btn,
            self.play_btn,
            self.mods_page.install_btn,
            self.mods_page.gb_btn,
            self.mods_page.toggle_btn,
            self.mods_page.remove_btn,
            self.mods_page.apply_profile_btn,
            self.mods_page.save_profile_btn,
            self.mods_page.resolve_conflicts_btn,
            self.mods_page.link_checkbox,
            self.settings_page.use_path_btn,
            self.settings_page.browse_btn,
            self.settings_page.switch_sel_port_btn,
            self.settings_page.account_combo,
            self.settings_page.language_combo,
        ):
            widget.setEnabled(enabled)
        self.saves_page.set_actions_enabled(enabled, busy=not enabled)

    def _explain_error(self, exc: Exception) -> str:
        if isinstance(exc, PermissionError) or getattr(exc, "winerror", None) == 5:
            backup_note = f"\n\nRespaldo previo: {self.last_port_backup}" if self.last_port_backup and self.last_port_backup.exists() else ""
            return self.tx(
                f"Windows negó permiso para escribir en el port. Cierra el juego y su launcher.{backup_note}",
                f"Windows denied permission to write to the port. Close the game and its launcher.{backup_note}",
            )
        return str(exc)

    def _run_background_operation(
        self,
        work: Callable[[Callable[[float | None, str], None]], object],
        *,
        status_text: str = "",
        on_success: Callable[[object], None] | None = None,
        error_title: str | None = None,
    ) -> bool:
        if self._mod_operation_active:
            return False
        self._mod_operation_active = True
        self._set_controls_enabled(False)
        self.report_progress(None, status_text or self.tx("Procesando operación…", "Running operation…"))

        worker = OperationWorker(work, self)
        self._active_worker = worker
        worker.progress_changed.connect(self.report_progress)

        def handle_ok(result: object) -> None:
            self._mod_operation_active = False
            self._active_worker = None
            self._set_controls_enabled(True)
            self.report_progress(1.0, self.tx("Operación completada", "Operation complete"))
            self.refresh()
            if on_success:
                on_success(result)

        def handle_err(exc: Exception) -> None:
            self._mod_operation_active = False
            self._active_worker = None
            self._set_controls_enabled(True)
            msg = self._explain_error(exc)
            self.report_progress(0.0, self.tx("Error en la operación", "Operation failed"))
            self.log_operation(msg, level="ERROR")
            self.refresh()
            QtWidgets.QMessageBox.critical(self, error_title or self.tx("Error", "Error"), msg)

        worker.finished_ok.connect(handle_ok)
        worker.failed_err.connect(handle_err)
        worker.start()
        return True

    def _ensure_game_closed(self) -> bool:
        if not self.port:
            return True
        running, issue = game_is_running(self.port)
        self.last_game_check_issue = issue
        if running:
            QtWidgets.QMessageBox.critical(
                self,
                self.tx("El juego está abierto", "The game is running"),
                game_running_message(issue, self.tr),
            )
            return False
        return True

    # --- Save Operations ---
    def _selected_slot_dir(self) -> Path | None:
        if self.selected_slot_path and self.selected_slot_path.exists():
            return self.selected_slot_path
        QtWidgets.QMessageBox.information(
            self,
            self.tx("Partidas", "Saves"),
            self.tx("Selecciona un slot primero.", "Select a save slot first."),
        )
        return None

    def activate_profile(self) -> None:
        if self._mod_operation_active:
            return
        name = self.selected_user_profile()
        target = self.profile_paths.get(name)
        if not target or not self.active_root:
            QtWidgets.QMessageBox.information(
                self,
                self.tx("Perfiles", "Profiles"),
                self.tx("No se encontró el perfil seleccionado.", "The selected profile was not found."),
            )
            return
        if not self._ensure_game_closed():
            return

        active_name = self.active_profile_name()
        effective_active = nx2navi_effective_active_dir(self.port, self.active_root) if self.port["id"] == "nx2navi" else self.active_root
        linked = self.is_mod_profile_linked()
        port_mod_profiles = self.settings.get("mod_profiles", {}).get(self.port["id"], {})

        if active_name == name and effective_active and contains_slot_folders(effective_active) and not (linked and name in port_mod_profiles):
            QtWidgets.QMessageBox.information(
                self,
                self.tx("Perfil activo", "Active profile"),
                self.tx(f"'{name}' ya está activado.", f"'{name}' is already active."),
            )
            return

        mod_note = (
            self.tx(
                f"\nTambién se aplicará la selección de mods de «{name}» en {self.port['name']}.",
                f"\nThe mod selection for '{name}' will also be applied to {self.port['name']}.",
            )
            if (linked and name in port_mod_profiles)
            else ""
        )
        reply = QtWidgets.QMessageBox.question(
            self,
            self.tx("Activar perfil global", "Activate global profile"),
            self.tx(
                f"Se respaldará el contenido activo y se cargará «{name}» en {self.port['name']}.{mod_note}\n\n¿Continuar?",
                f"The active saves will be backed up and '{name}' will be loaded into {self.port['name']}.{mod_note}\n\nContinue?",
            ),
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        def work(report):
            backup = activate_profile_files(
                self.port,
                self.active_root,
                self.profile_paths,
                active_name,
                name,
                self.backup_dir,
                progress_cb=report,
                tx=self.tx,
            )
            if linked and name in port_mod_profiles:
                ini_bk = apply_mod_profile_files(
                    self.port,
                    self.mod_library_dir,
                    set(port_mod_profiles[name]),
                    self.backup_dir,
                    inspect_cache=self._mod_inspection_cache,
                    progress_cb=report,
                    tx=self.tx,
                )
                if ini_bk:
                    self.last_port_backup = ini_bk
            self.set_active_profile_name(name)
            self.persist_settings()
            return backup

        def done(backup):
            self.user_combo.setCurrentText(name)
            self.log_operation(self.tx(
                f"Perfil global activado: «{name}» en {self.port['name']} · Respaldo: {backup}",
                f"Activated global profile '{name}' on {self.port['name']} · Backup: {backup}",
            ))
            QtWidgets.QMessageBox.information(
                self,
                self.tx("Perfil activado", "Profile activated"),
                self.tx(f"«{name}» ya está activo en {self.port['name']}.\n\nRespaldo:\n{backup}", f"'{name}' is now active in {self.port['name']}.\n\nBackup:\n{backup}"),
            )

        self._run_background_operation(
            work,
            status_text=self.tx(f"Activando perfil «{name}»…", f"Activating profile '{name}'…"),
            on_success=done,
            error_title=self.tx("Cambio incompleto", "Switch incomplete"),
        )

    def save_active_as_profile(self) -> None:
        if self._mod_operation_active or not self._ensure_game_closed():
            return
        if not self.active_root or not self.port:
            return
        effective = nx2navi_effective_active_dir(self.port, self.active_root) if self.port["id"] == "nx2navi" else self.active_root
        items = profile_items(effective)
        if not any(p.is_dir() and p.name.startswith("slot_") for p in items):
            QtWidgets.QMessageBox.information(
                self,
                self.tx("Perfiles", "Profiles"),
                self.tx("No hay slots activos en la raíz para guardar como perfil.", "No active slots found to save as a profile."),
            )
            return

        name, ok = QtWidgets.QInputDialog.getText(
            self,
            self.tx("Guardar perfil global", "Save global profile"),
            self.tx("Nombre para este perfil (partidas + mods):", "Name for this profile (saves + mods):"),
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in (".", "..") or any(ch in name for ch in '<>:/\\|?*'):
            QtWidgets.QMessageBox.critical(
                self,
                self.tx("Nombre no válido", "Invalid name"),
                self.tx("El nombre contiene caracteres no permitidos.", "The name contains invalid characters."),
            )
            return

        target = self.active_root / name
        if target.exists():
            reply = QtWidgets.QMessageBox.question(
                self,
                self.tx("Actualizar perfil existente", "Update existing profile"),
                self.tx(
                    f"Ya existe «{name}». Se respaldará antes de actualizarlo con las partidas activas. ¿Continuar?",
                    f"'{name}' already exists. It will be backed up before updating with the active saves. Continue?",
                ),
            )
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return

        def work(report):
            backup = save_active_as_profile_files(
                self.port,
                self.active_root,
                name,
                self.backup_dir,
                progress_cb=report,
                tx=self.tx,
            )
            self.set_active_profile_name(name)
            if self.is_mod_profile_linked():
                self._save_mod_profile_state(name)
            else:
                self.persist_settings()
            return backup

        def done(_backup):
            self.user_combo.setCurrentText(name)
            self.log_operation(self.tx(f"Partidas activas guardadas en «{name}»", f"Saved active saves as profile '{name}'"))
            QtWidgets.QMessageBox.information(
                self,
                self.tx("Perfil guardado", "Profile saved"),
                self.tx(f"El perfil «{name}» quedó guardado.", f"Profile '{name}' was saved."),
            )

        self._run_background_operation(
            work,
            status_text=self.tx(f"Guardando perfil «{name}»…", f"Saving profile '{name}'…"),
            on_success=done,
            error_title=self.tx("No se guardó", "Profile not saved"),
        )

    def import_save_as_new_profile(self) -> None:
        if self._mod_operation_active or not self.port or not self.active_root:
            return
        source = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tx(
                "Selecciona carpeta de emulador (slot_00..05) o carpeta de un slot (progress.sav)",
                "Select emulator save folder (slot_00..05) or a single slot folder (progress.sav)",
            ),
        )
        if not source:
            return
        source_dir = Path(source)
        default_name = source_dir.name if source_dir.name and not source_dir.name.startswith("slot_") else "ImportedSave"
        name, ok = QtWidgets.QInputDialog.getText(
            self,
            self.tx("Importar save a nuevo perfil", "Import save as new profile"),
            self.tx("Nombre para el nuevo perfil global (partidas + mods):", "Name for the new global profile (saves + mods):"),
            text=default_name,
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in (".", "..") or any(ch in name for ch in '<>:/\\|?*'):
            QtWidgets.QMessageBox.critical(
                self,
                self.tx("Nombre no válido", "Invalid name"),
                self.tx("El nombre contiene caracteres no permitidos.", "The name contains invalid characters."),
            )
            return

        target = self.active_root / name
        if target.exists():
            reply = QtWidgets.QMessageBox.question(
                self,
                self.tx("Reemplazar perfil existente", "Replace existing profile"),
                self.tx(
                    f"Ya existe el perfil «{name}». Se respaldará antes de importar. ¿Continuar?",
                    f"Profile '{name}' already exists. It will be backed up before importing. Continue?",
                ),
            )
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return

        def work(report):
            imported_dir, count = import_external_save_as_profile(
                self.active_root,
                source_dir,
                name,
                self.backup_dir,
                progress_cb=report,
                tx=self.tx,
            )
            port_profiles = self.settings.setdefault("mod_profiles", {}).setdefault(self.port["id"], {})
            if name not in port_profiles:
                self._save_mod_profile_state(name)
            else:
                self.persist_settings()
            return imported_dir, count

        def done(result):
            _imported_dir, count = result
            self.user_combo.setCurrentText(name)
            self.log_operation(self.tx(
                f"Save importado como nuevo perfil «{name}» ({count} slot(s))",
                f"Imported save as new profile '{name}' ({count} slot(s))",
            ))
            QtWidgets.QMessageBox.information(
                self,
                self.tx("Perfil importado", "Profile imported"),
                self.tx(
                    f"Se importaron {count} slot(s) en el nuevo perfil «{name}». Pulsa «Activar perfil» cuando quieras cargarlo al juego.",
                    f"Imported {count} slot(s) into new profile '{name}'. Click 'Activate profile' when ready to load it into the game.",
                ),
            )

        self._run_background_operation(
            work,
            status_text=self.tx(f"Importando save a «{name}»…", f"Importing save into '{name}'…"),
            on_success=done,
            error_title=self.tx("Error al importar save", "Save import failed"),
        )

    def backup_slot(self) -> None:
        if self._mod_operation_active or not self._ensure_game_closed():
            return
        src = self._selected_slot_dir()
        if not src:
            return

        def work(report):
            report(0.3, self.tx(f"Respaldando {src.name}…", f"Backing up {src.name}…"))
            backup = make_backup_slot(src, self.backup_dir)
            report(1.0, self.tx("Respaldo completado", "Backup complete"))
            return backup

        def done(backup):
            self.log_operation(self.tx(f"Respaldo de {src.name} en {backup}", f"Backed up {src.name} to {backup}"))
            QtWidgets.QMessageBox.information(
                self,
                self.tx("Respaldo creado", "Backup created"),
                self.tx(f"Se guardó una copia en:\n{backup}", f"Backup created at:\n{backup}"),
            )

        self._run_background_operation(work, status_text=self.tx("Creando respaldo…", "Creating backup…"), on_success=done)

    def export_slot(self) -> None:
        if self._mod_operation_active or not self._ensure_game_closed():
            return
        src = self._selected_slot_dir()
        if not src:
            return
        dest = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tx("Elige carpeta para exportar la partida", "Choose a folder to export the save"),
        )
        if not dest:
            return
        prefix = self.selected_user_profile() or self.active_profile_name() or "active"
        target = Path(dest) / f"{prefix}_{src.name}"
        if target.exists():
            QtWidgets.QMessageBox.critical(
                self,
                self.tx("Exportación", "Export"),
                self.tx(f"Ya existe: {target}", f"Already exists: {target}"),
            )
            return

        def work(report):
            return export_slot_files(src, target, progress_cb=report, tx=self.tx)

        def done(_res):
            self.log_operation(self.tx(f"Slot {src.name} exportado a {target}", f"Exported {src.name} to {target}"))
            QtWidgets.QMessageBox.information(self, self.tx("Exportación completa", "Export complete"), str(target))

        self._run_background_operation(work, status_text=self.tx("Exportando slot…", "Exporting slot…"), on_success=done)

    def import_slot(self) -> None:
        if self._mod_operation_active or not self._ensure_game_closed():
            return
        target = self._selected_slot_dir()
        if not target:
            return
        source_str = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tx("Selecciona la carpeta de un slot exportado", "Select an exported save slot folder"),
        )
        if not source_str:
            return
        source = Path(source_str)
        if not (source / "progress.sav").is_file() or not (source / "caption.sav").is_file():
            QtWidgets.QMessageBox.critical(
                self,
                self.tx("Partida no válida", "Invalid save"),
                self.tx("La carpeta debe contener progress.sav y caption.sav.", "The folder must contain progress.sav and caption.sav."),
            )
            return

        # Audit fix #4: explicitly clarify active root vs preview profile before restoring
        is_live = bool(self.active_root and (target.parent == self.active_root or target.parent.parent.name == "save-tx"))
        active_name = self.active_profile_name()
        target_desc = (
            self.tx(
                f"la partida ACTIVA en el juego ({target.name}" + (f" · sincronizando perfil «{active_name}»)" if active_name in self.profile_paths else ")"),
                f"the ACTIVE save in game ({target.name}" + (f" · syncing profile '{active_name}')" if active_name in self.profile_paths else ")"),
            )
            if is_live
            else self.tx(f"la copia guardada del perfil «{target.parent.name}» ({target.name})", f"the saved copy of profile '{target.parent.name}' ({target.name})")
        )
        reply = QtWidgets.QMessageBox.question(
            self,
            self.tx("Confirmar restauración", "Confirm restore"),
            self.tx(
                f"Se reemplazará {target_desc}.\nSe creará un respaldo automático antes. ¿Continuar?",
                f"This will replace {target_desc}.\nAn automatic backup will be created first. Continue?",
            ),
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        def work(report):
            return import_slot_files(
                self.port,
                self.active_root,
                target,
                source,
                self.backup_dir,
                active_profile_name=active_name,
                profile_paths=self.profile_paths,
                progress_cb=report,
                tx=self.tx,
            )

        def done(res):
            backup, synced = res
            self.log_operation(self.tx(
                f"Slot {target.name} restaurado (perfil sincronizado={synced}) · Respaldo: {backup}",
                f"Restored {target.name} (synced_profile={synced}) · Backup: {backup}",
            ))
            QtWidgets.QMessageBox.information(
                self,
                self.tx("Partida restaurada", "Save restored"),
                self.tx(f"Slot actualizado. Respaldo previo:\n{backup}", f"Slot updated. Previous backup:\n{backup}"),
            )

        self._run_background_operation(work, status_text=self.tx("Restaurando slot…", "Restoring save slot…"), on_success=done)

    # --- Mod Operations ---
    def install_mod(self) -> None:
        if self._mod_operation_active:
            return
        archive, _filter = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tx("Selecciona el ZIP del mod", "Select the mod ZIP"),
            "",
            "ZIP (*.zip)",
        )
        if not archive:
            return

        def work(report):
            return install_mod_archive(archive, self.mod_library_dir, progress_cb=report, tx=self.tx, tr=self.tr)

        def done(dest):
            self.log_operation(self.tx(f"Mod «{dest.name}» importado a la biblioteca", f"Imported mod '{dest.name}' into library"))
            QtWidgets.QMessageBox.information(
                self,
                self.tx("Mod guardado", "Mod saved"),
                self.tx("El paquete se guardó en la biblioteca central. Actívalo para copiarlo al port.", "The package was saved in the central library. Enable it to deploy to the port."),
            )

        self._run_background_operation(
            work,
            status_text=self.tx("Importando mod a biblioteca…", "Importing mod into library…"),
            on_success=done,
            error_title=self.tx("No se instaló", "Install failed"),
        )

    def install_from_gamebanana(self) -> None:
        if self._mod_operation_active:
            return
        prefill = ""
        sel = self.mods_page.selected_mod_path()
        if sel:
            meta_file = Path(sel) / ".gamebanana.json"
            if meta_file.is_file():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    prefill = str(meta.get("url") or meta.get("mod_id") or "")
                except (OSError, ValueError):
                    prefill = ""

        url_or_id, ok = QtWidgets.QInputDialog.getText(
            self,
            self.tx("Instalar / actualizar desde GameBanana", "Install / update from GameBanana"),
            self.tx(
                "Pega la URL del mod en GameBanana (p. ej. https://gamebanana.com/mods/123456) o su ID numérico:",
                "Paste the GameBanana mod URL (e.g. https://gamebanana.com/mods/123456) or numeric mod ID:",
            ),
            text=prefill,
        )
        if not ok or not url_or_id.strip():
            return
        raw_input = url_or_id.strip()

        def work(report):
            return download_and_install_gamebanana_mod(
                raw_input,
                self.mod_library_dir,
                backup_dir=self.backup_dir,
                progress_cb=report,
                tx=self.tx,
                tr=self.tr,
            )

        def done(result):
            dest, meta = result
            self.log_operation(self.tx(
                f"GameBanana: mod «{dest.name}» descargado/actualizado (#{meta['mod_id']})",
                f"GameBanana: downloaded/updated mod '{dest.name}' (#{meta['mod_id']})",
            ))
            QtWidgets.QMessageBox.information(
                self,
                self.tx("Mod descargado desde GameBanana", "Downloaded from GameBanana"),
                self.tx(
                    f"«{dest.name}» quedó guardado en Mods/ ({meta.get('file_name', '')}). Actívalo cuando quieras.",
                    f"'{dest.name}' was saved into Mods/ ({meta.get('file_name', '')}). Enable it whenever you are ready.",
                ),
            )

        self._run_background_operation(
            work,
            status_text=self.tx("Consultando API de GameBanana…", "Querying GameBanana API…"),
            on_success=done,
            error_title=self.tx("Error de GameBanana", "GameBanana error"),
        )

    def toggle_mod(self) -> None:
        if self._mod_operation_active or not self.port:
            return
        sel = self.mods_page.selected_mod_path()
        if not sel:
            QtWidgets.QMessageBox.information(self, "Mods", self.tx("Selecciona un mod primero.", "Select a mod first."))
            return
        if not self._ensure_game_closed():
            return
        mod = Path(sel)
        info = mod_status(self.port, mod, inspect_cache=self._mod_inspection_cache, nx_mod_log_status=self.nx_mod_log_status)
        if info["incompatible"] and not info.get("known_not_usable"):
            QtWidgets.QMessageBox.critical(
                self,
                self.tx("No compatible", "Incompatible"),
                self.tx("Este mod no se puede activar en el port seleccionado.", "This mod cannot be enabled on the selected port."),
            )
            return
        if info.get("known_not_usable") and not info["enabled"]:
            QtWidgets.QMessageBox.information(self, self.tx("Not Usable en NX2NAVI", "Not Usable in NX2NAVI"), info.get("log_detail", ""))
            return
        if self.port["id"] == "nx2navi" and info.get("review_required") and not info["enabled"]:
            reply = QtWidgets.QMessageBox.question(
                self,
                self.tx("Compatibilidad por validar", "Compatibility needs review"),
                self.tx(
                    "Revisión necesaria: NX2NAVI puede marcar este ExeFS como Not Usable. ¿Activarlo de todos modos?",
                    "Review needed: NX2NAVI may mark this ExeFS mod Not Usable. Enable it anyway?",
                ),
            )
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return

        enabled = not info["enabled"]
        profile_name = self.selected_mod_profile()

        def work(report):
            report(0.25, self.tx(f"Cambiando «{mod.name}»…", f"Updating '{mod.name}'…"))
            ini_bk = set_mod_state(
                self.port,
                mod,
                enabled,
                self.backup_dir,
                inspect_cache=self._mod_inspection_cache,
                progress_cb=report,
                tx=self.tx,
            )
            if ini_bk:
                self.last_port_backup = ini_bk
            self._save_mod_profile_state(profile_name, changed_mod=mod.name, changed_enabled=enabled)
            report(1.0, self.tx(f"Mod «{mod.name}» actualizado", f"Mod '{mod.name}' updated"))

        def done(_res):
            self.log_operation(self.tx(
                f"Mod «{mod.name}» {'activado' if enabled else 'desactivado'} en {self.port['name']} (perfil «{profile_name}»)",
                f"{'Enabled' if enabled else 'Disabled'} mod '{mod.name}' on {self.port['name']} (profile '{profile_name}')",
            ))

        self._run_background_operation(work, status_text=self.tx("Aplicando cambio al mod…", "Applying mod change…"), on_success=done)

    def remove_mod(self) -> None:
        if self._mod_operation_active:
            return
        sel = self.mods_page.selected_mod_path()
        if not sel:
            return
        mod = Path(sel)
        reply = QtWidgets.QMessageBox.question(
            self,
            self.tx("Desinstalar mod", "Uninstall mod"),
            self.tx(
                f"Esto quita «{mod.name}» de la biblioteca central y del port actual con respaldo previo. ¿Continuar?",
                f"This removes '{mod.name}' from the central library and current port after creating a backup. Continue?",
            ),
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes or not self._ensure_game_closed():
            return

        def work(report):
            backup, ini_bk = remove_mod_files(
                self.port,
                mod,
                self.backup_dir,
                self.settings,
                progress_cb=report,
                tx=self.tx,
            )
            if ini_bk:
                self.last_port_backup = ini_bk
            self.persist_settings()
            return backup

        def done(backup):
            self.log_operation(self.tx(f"Mod «{mod.name}» desinstalado · Respaldo: {backup}", f"Uninstalled mod '{mod.name}' · Backup: {backup}"))
            QtWidgets.QMessageBox.information(
                self,
                self.tx("Mod desinstalado", "Mod uninstalled"),
                self.tx(f"El mod se eliminó con respaldo en:\n{backup}", f"The mod was removed with backup at:\n{backup}"),
            )

        self._run_background_operation(work, status_text=self.tx("Desinstalando mod…", "Uninstalling mod…"), on_success=done)

    def save_mod_profile_as(self) -> None:
        if self._mod_operation_active or not self.port:
            return
        default_name = self.selected_mod_profile()
        name, ok = QtWidgets.QInputDialog.getText(
            self,
            self.tx("Guardar perfil de mods", "Save mod profile"),
            self.tx("Nombre del perfil de mods:", "Mod profile name:"),
            text=default_name,
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        existing = self.settings.get("mod_profiles", {}).get(self.port["id"], {}).get(name)
        if existing is not None:
            reply = QtWidgets.QMessageBox.question(
                self,
                self.tx("Actualizar perfil de mods", "Update mod profile"),
                self.tx(f"El perfil «{name}» ya existe. ¿Reemplazar su selección de mods?", f"Profile '{name}' already exists. Replace its mod list?"),
            )
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return

        self._save_mod_profile_state(name)
        self.refresh_mod_profile_choices()
        if not self.is_mod_profile_linked():
            self.mods_page.mod_profile_combo.setCurrentText(name)
        self.log_operation(self.tx(f"Perfil de mods «{name}» guardado para {self.port['name']}", f"Saved mod profile '{name}' for {self.port['name']}"))

    def apply_selected_mod_profile(self) -> None:
        if self._mod_operation_active or not self.port or not self._ensure_game_closed():
            return
        profile_name = self.selected_mod_profile()
        port_profiles = self.settings.setdefault("mod_profiles", {}).setdefault(self.port["id"], {})
        if profile_name not in port_profiles:
            enabled = [
                m.name for m in self.mod_library_dir.iterdir()
                if m.is_dir() and mod_status(self.port, m, inspect_cache=self._mod_inspection_cache, nx_mod_log_status=self.nx_mod_log_status)["enabled"]
            ]
            port_profiles[profile_name] = sorted(enabled, key=str.casefold)
            self.persist_settings()
        enabled_names = set(port_profiles[profile_name])

        def work(report):
            ini_bk = apply_mod_profile_files(
                self.port,
                self.mod_library_dir,
                enabled_names,
                self.backup_dir,
                inspect_cache=self._mod_inspection_cache,
                progress_cb=report,
                tx=self.tx,
            )
            if ini_bk:
                self.last_port_backup = ini_bk
            self.persist_settings()

        self._run_background_operation(
            work,
            status_text=self.tx(f"Aplicando perfil de mods «{profile_name}»…", f"Applying mod profile '{profile_name}'…"),
            on_success=lambda _r: self.log_operation(self.tx(
                f"Perfil de mods «{profile_name}» aplicado en {self.port['name']}",
                f"Applied mod profile '{profile_name}' on {self.port['name']}",
            )),
        )

    def resolve_romfs_conflicts(self) -> None:
        if self._mod_operation_active or not self.port or not self._ensure_game_closed():
            return
        # Recommended clean pair when available; otherwise keep non-conflicting priority order.
        recommended = {"Blood and Horror Restoration - Darker ReDead Mask", "PlayableZelda"}
        currently_enabled = {
            m.name for m in self.mod_library_dir.iterdir()
            if m.is_dir() and mod_status(self.port, m, inspect_cache=self._mod_inspection_cache, nx_mod_log_status=self.nx_mod_log_status)["enabled"]
        }
        keep = currently_enabled & recommended
        if not keep:
            # Greedy conflict-free keep set
            keep = set()
            for candidate in sorted(currently_enabled, key=str.casefold):
                if not detect_mod_conflicts(self.mod_library_dir, keep | {candidate}, inspect_cache=self._mod_inspection_cache, romfs_cache=self._romfs_files_cache):
                    keep.add(candidate)

        turn_off = sorted(currently_enabled - keep, key=str.casefold)
        if not turn_off:
            return
        reply = QtWidgets.QMessageBox.question(
            self,
            self.tx("Resolver conflictos RomFS", "Resolve RomFS conflicts"),
            self.tx(
                f"Se mantendrán activos:\n• " + "\n• ".join(sorted(keep)) + f"\n\nSe desactivarán para evitar colisiones:\n• " + "\n• ".join(turn_off) + "\n\n¿Aplicar?",
                f"Keep enabled:\n• " + "\n• ".join(sorted(keep)) + f"\n\nDisable to remove file collisions:\n• " + "\n• ".join(turn_off) + "\n\nApply?",
            ),
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        profile_name = self.selected_mod_profile()
        self.settings.setdefault("mod_profiles", {}).setdefault(self.port["id"], {})[profile_name] = sorted(keep, key=str.casefold)

        def work(report):
            ini_bk = apply_mod_profile_files(
                self.port,
                self.mod_library_dir,
                keep,
                self.backup_dir,
                inspect_cache=self._mod_inspection_cache,
                progress_cb=report,
                tx=self.tx,
            )
            if ini_bk:
                self.last_port_backup = ini_bk
            self.persist_settings()

        self._run_background_operation(
            work,
            status_text=self.tx("Resolviendo conflictos de mods…", "Resolving mod conflicts…"),
            on_success=lambda _r: self.log_operation(self.tx(
                f"Conflictos resueltos en {self.port['name']}: activos={sorted(keep)}",
                f"Resolved conflicts on {self.port['name']}: enabled={sorted(keep)}",
            )),
        )

    # --- Launch ---
    def launch_game(self) -> None:
        if self._mod_operation_active or not self.port:
            return
        if not self._ensure_game_closed():
            return
        executable = Path(self.port["launch_exe"])
        if not executable.is_file():
            QtWidgets.QMessageBox.critical(self, self.tx("Ejecutable no encontrado", "Executable not found"), str(executable))
            return

        save_profile = self.selected_user_profile()
        mod_profile = self.selected_mod_profile()
        effective_active = nx2navi_effective_active_dir(self.port, self.active_root) if (self.port["id"] == "nx2navi" and self.active_root) else self.active_root
        has_active_slots = bool(effective_active and contains_slot_folders(effective_active))
        switch_save = bool(save_profile and save_profile in self.profile_paths and (save_profile != self.active_profile_name() or not has_active_slots))

        if switch_save:
            prompt = self.tx(
                f"Se activará la partida «{save_profile}» y se aplicará el perfil de mods «{mod_profile}» antes de abrir {self.port['name']}. ¿Continuar?",
                f"Save profile '{save_profile}' and mod profile '{mod_profile}' will be applied before launching {self.port['name']}. Continue?",
            )
        else:
            prompt = self.tx(
                f"Antes de iniciar, se aplicará el perfil de mods «{mod_profile}» en {self.port['name']}. ¿Continuar?",
                f"Before launch, mod profile '{mod_profile}' will be applied on {self.port['name']}. Continue?",
            )

        reply = QtWidgets.QMessageBox.question(self, self.tx("Jugar", "Play"), prompt)
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        port_profiles = self.settings.setdefault("mod_profiles", {}).setdefault(self.port["id"], {})
        if mod_profile not in port_profiles:
            port_profiles[mod_profile] = sorted(
                (
                    m.name for m in self.mod_library_dir.iterdir()
                    if m.is_dir() and mod_status(self.port, m, inspect_cache=self._mod_inspection_cache, nx_mod_log_status=self.nx_mod_log_status)["enabled"]
                ),
                key=str.casefold,
            )
        enabled_names = set(port_profiles[mod_profile])

        def work(report):
            if switch_save and self.active_root:
                activate_profile_files(
                    self.port,
                    self.active_root,
                    self.profile_paths,
                    self.active_profile_name(),
                    save_profile,
                    self.backup_dir,
                    progress_cb=report,
                    tx=self.tx,
                )
                self.set_active_profile_name(save_profile)
            ini_bk = apply_mod_profile_files(
                self.port,
                self.mod_library_dir,
                enabled_names,
                self.backup_dir,
                inspect_cache=self._mod_inspection_cache,
                progress_cb=report,
                tx=self.tx,
            )
            if ini_bk:
                self.last_port_backup = ini_bk
            self.persist_settings()
            report(0.95, self.tx(f"Iniciando {self.port['name']}…", f"Launching {self.port['name']}…"))
            cmd = [str(executable), *self.port.get("launch_args", [])]
            if os.name != "nt" and executable.suffix.lower() == ".exe":
                wine_bin = shutil.which("wine")
                if not wine_bin:
                    raise RuntimeError(self.tx(
                        "Este port usa un binario de Windows (.exe) y no se encontró Wine en el sistema Linux.",
                        "This port uses a Windows binary (.exe) and Wine was not found on Linux.",
                    ))
                cmd = [wine_bin, *cmd]
            subprocess.Popen(cmd, cwd=str(self.port["root"]))
            report(1.0, self.tx(f"{self.port['name']} iniciado", f"Launched {self.port['name']}"))
            return save_profile if switch_save else ""

        def done(activated):
            if activated:
                self.user_combo.setCurrentText(activated)
            save_note = f", partida: «{activated}»" if activated else ""
            save_note_en = f", save: '{activated}'" if activated else ""
            self.log_operation(self.tx(
                f"Iniciado {self.port['name']} (mods: «{mod_profile}»{save_note})",
                f"Launched {self.port['name']} (mods: '{mod_profile}'{save_note_en})",
            ))

        self._run_background_operation(
            work,
            status_text=self.tx("Preparando perfil y abriendo el port…", "Preparing profile and launching port…"),
            on_success=done,
            error_title=self.tx("No se pudo iniciar", "Could not launch"),
        )
