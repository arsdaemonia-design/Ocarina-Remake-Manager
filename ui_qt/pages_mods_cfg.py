"""PySide6 pages for Mods (unified profile link + conflict banner), Backups, and Settings."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ui_qt.theme import COLORS, make_svg_pixmap

_SORT_KEY_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1


class SortableTableWidgetItem(QtWidgets.QTableWidgetItem):
    """Table item that sorts by an explicit structured key stored in UserRole + 1."""

    def __lt__(self, other: QtWidgets.QTableWidgetItem) -> bool:
        left_key = self.data(_SORT_KEY_ROLE)
        right_key = other.data(_SORT_KEY_ROLE)
        if left_key is not None and right_key is not None:
            return left_key < right_key
        return self.text().casefold() < other.text().casefold()


class ModsPage(QtWidgets.QWidget):
    """Central mod library, port compatibility matrix, profile link, and RomFS conflict banner."""

    filter_changed = QtCore.Signal(str)
    search_changed = QtCore.Signal(str)
    link_toggled = QtCore.Signal(bool)
    apply_mod_profile_requested = QtCore.Signal()
    save_mod_profile_requested = QtCore.Signal()
    resolve_conflicts_requested = QtCore.Signal()
    install_requested = QtCore.Signal()
    gamebanana_requested = QtCore.Signal()
    toggle_requested = QtCore.Signal()
    remove_requested = QtCore.Signal()
    mod_selected = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # Intro + profile link card
        top_card = QtWidgets.QFrame()
        top_card.setObjectName("CardPanel")
        top_layout = QtWidgets.QVBoxLayout(top_card)
        top_layout.setContentsMargins(14, 12, 14, 12)
        top_layout.setSpacing(8)

        self.intro_title = QtWidgets.QLabel("BIBLIOTECA DE MODS")
        self.intro_title.setObjectName("SectionTitle")
        top_layout.addWidget(self.intro_title)

        self.intro_desc = QtWidgets.QLabel("")
        self.intro_desc.setObjectName("MutedLabel")
        self.intro_desc.setWordWrap(True)
        top_layout.addWidget(self.intro_desc)

        link_row = QtWidgets.QHBoxLayout()
        link_row.setSpacing(10)
        self.link_checkbox = QtWidgets.QCheckBox("Vincular mods al perfil global")
        self.link_checkbox.setChecked(True)
        link_row.addWidget(self.link_checkbox)

        self.mod_profile_label = QtWidgets.QLabel("Perfil de mods:")
        self.mod_profile_label.setObjectName("MutedLabel")
        link_row.addWidget(self.mod_profile_label)

        self.mod_profile_combo = QtWidgets.QComboBox()
        self.mod_profile_combo.setMinimumWidth(160)
        link_row.addWidget(self.mod_profile_combo)

        self.apply_profile_btn = QtWidgets.QPushButton("Aplicar perfil")
        link_row.addWidget(self.apply_profile_btn)

        link_row.addStretch(1)
        self.save_profile_btn = QtWidgets.QPushButton("Guardar selección en perfil…")
        link_row.addWidget(self.save_profile_btn)
        top_layout.addLayout(link_row)
        root.addWidget(top_card)

        # RomFS Conflict warning banner (hidden unless conflicts exist)
        self.conflict_banner = QtWidgets.QFrame()
        self.conflict_banner.setObjectName("ConflictBanner")
        cb_layout = QtWidgets.QHBoxLayout(self.conflict_banner)
        cb_layout.setContentsMargins(12, 10, 12, 10)
        cb_layout.setSpacing(10)
        warn_icon = QtWidgets.QLabel()
        warn_icon.setPixmap(make_svg_pixmap("warning", COLORS["amber"], 22))
        cb_layout.addWidget(warn_icon)
        self.conflict_label = QtWidgets.QLabel("")
        self.conflict_label.setWordWrap(True)
        self.conflict_label.setStyleSheet(f"color: {COLORS['amber']}; font-weight: 600; font-size: 9.5pt;")
        cb_layout.addWidget(self.conflict_label, 1)
        self.resolve_conflicts_btn = QtWidgets.QPushButton("Resolver conflictos")
        self.resolve_conflicts_btn.setObjectName("GoldButton")
        cb_layout.addWidget(self.resolve_conflicts_btn)
        self.conflict_banner.hide()
        root.addWidget(self.conflict_banner)

        # Search + actions bar (column sorting handles Active / Type / Status)
        ctrl_row = QtWidgets.QHBoxLayout()
        ctrl_row.setSpacing(8)

        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("Buscar mod…")
        self.search_edit.setMinimumWidth(260)
        self.search_edit.setMaximumWidth(380)
        self.search_edit.setClearButtonEnabled(True)
        ctrl_row.addWidget(self.search_edit)
        ctrl_row.addStretch(1)

        self.install_btn = QtWidgets.QPushButton("Importar ZIP…")
        self.install_btn.setObjectName("GoldButton")
        self.gb_btn = QtWidgets.QPushButton("GameBanana URL…")
        self.toggle_btn = QtWidgets.QPushButton("Activar / desactivar")
        self.remove_btn = QtWidgets.QPushButton("Desinstalar…")
        self.remove_btn.setObjectName("DangerButton")
        ctrl_row.addWidget(self.install_btn)
        ctrl_row.addWidget(self.gb_btn)
        ctrl_row.addWidget(self.toggle_btn)
        ctrl_row.addWidget(self.remove_btn)
        root.addLayout(ctrl_row)

        # Sortable Mods Table
        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setSortIndicator(0, QtCore.Qt.SortOrder.AscendingOrder)
        self.table.setSortingEnabled(True)
        self.table.setHorizontalHeaderLabels(["Mod", "Tipo", "Estado"])
        root.addWidget(self.table, 1)

        # Detail panel + legend
        detail_box = QtWidgets.QFrame()
        detail_box.setObjectName("InnerPanel")
        db_layout = QtWidgets.QVBoxLayout(detail_box)
        db_layout.setContentsMargins(12, 8, 12, 8)
        self.detail_label = QtWidgets.QLabel("")
        self.detail_label.setWordWrap(True)
        db_layout.addWidget(self.detail_label)
        root.addWidget(detail_box)

        self.legend_label = QtWidgets.QLabel("")
        self.legend_label.setObjectName("MutedLabel")
        self.legend_label.setWordWrap(True)
        self.legend_label.setContentsMargins(2, 2, 2, 6)
        self.legend_label.setMinimumHeight(22)
        root.addWidget(self.legend_label)

        self.link_checkbox.toggled.connect(self.link_toggled.emit)
        self.apply_profile_btn.clicked.connect(self.apply_mod_profile_requested.emit)
        self.save_profile_btn.clicked.connect(self.save_mod_profile_requested.emit)
        self.resolve_conflicts_btn.clicked.connect(self.resolve_conflicts_requested.emit)
        self.search_edit.textChanged.connect(self.search_changed.emit)
        self.install_btn.clicked.connect(self.install_requested.emit)
        self.gb_btn.clicked.connect(self.gamebanana_requested.emit)
        self.toggle_btn.clicked.connect(self.toggle_requested.emit)
        self.remove_btn.clicked.connect(self.remove_requested.emit)
        self.table.itemSelectionChanged.connect(self.mod_selected.emit)
        self.table.itemDoubleClicked.connect(lambda _item: self.toggle_requested.emit())

    def current_filter(self) -> str:
        return "all"

    def set_link_mode(self, linked: bool, active_user: str, tx) -> None:
        self.link_checkbox.blockSignals(True)
        self.link_checkbox.setChecked(linked)
        self.link_checkbox.blockSignals(False)
        user_disp = active_user or "Default"
        self.link_checkbox.setText(tx(
            f"Vincular mods al perfil global («{user_disp}»)",
            f"Link mods to global profile ('{user_disp}')",
        ))
        self.mod_profile_label.setVisible(not linked)
        self.mod_profile_combo.setVisible(not linked)
        self.apply_profile_btn.setVisible(not linked)
        self.save_profile_btn.setVisible(not linked)

    def show_conflicts(self, conflicts: list[dict], tx) -> None:
        if not conflicts:
            self.conflict_banner.hide()
            return
        pairs = [
            f"{c['mods'][0]} ↔ {c['mods'][1]} ({c['overlap_count']})"
            for c in conflicts[:4]
        ]
        if len(conflicts) > 4:
            pairs.append(tx(f"y {len(conflicts) - 4} más", f"and {len(conflicts) - 4} more"))
        self.conflict_label.setText(tx(
            f"Conflicto RomFS detectado entre mods activos: {' · '.join(pairs)}. Estos mods sobrescriben los mismos archivos al cargarse juntos.",
            f"RomFS conflict detected among enabled mods: {' · '.join(pairs)}. These mods overwrite the same files when loaded together.",
        ))
        self.resolve_conflicts_btn.setText(tx("Dejar sin conflictos", "Resolve conflicts"))
        self.conflict_banner.show()

    def populate_mods(self, rows: list[dict], selected_mod_path: str = "") -> None:
        tag_colors = {
            "enabled": COLORS["green"],
            "disabled": COLORS["muted"],
            "library_only": COLORS["gold"],
            "review": COLORS["amber"],
            "incompatible": COLORS["red"],
        }
        tag_rank = {
            "enabled": 0,
            "disabled": 1,
            "library_only": 2,
            "review": 3,
            "incompatible": 4,
        }
        header = self.table.horizontalHeader()
        sort_col = header.sortIndicatorSection()
        if sort_col < 0 or sort_col >= self.table.columnCount():
            sort_col = 0
        sort_order = header.sortIndicatorOrder()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for idx, row in enumerate(rows):
            self.table.insertRow(idx)
            color = QtGui.QColor(tag_colors.get(row["tag"], COLORS["text"]))
            name_cf = row["name"].casefold()

            name_item = SortableTableWidgetItem(f"{row['symbol']}{row['name']}")
            name_item.setData(QtCore.Qt.ItemDataRole.UserRole, str(row["path"]))
            name_item.setData(_SORT_KEY_ROLE, (name_cf,))
            name_item.setForeground(color)

            kind_item = SortableTableWidgetItem(row["kind_text"])
            kind_item.setData(_SORT_KEY_ROLE, (row["kind_text"].casefold(), name_cf))
            kind_item.setForeground(color)

            state_item = SortableTableWidgetItem(row["state_text"])
            state_item.setData(_SORT_KEY_ROLE, (tag_rank.get(row["tag"], 9), row["state_text"].casefold(), name_cf))
            state_item.setForeground(color)

            self.table.setItem(idx, 0, name_item)
            self.table.setItem(idx, 1, kind_item)
            self.table.setItem(idx, 2, state_item)

        self.table.setSortingEnabled(True)
        self.table.sortItems(sort_col, sort_order)

        if selected_mod_path:
            for row_idx in range(self.table.rowCount()):
                item0 = self.table.item(row_idx, 0)
                if item0 and str(item0.data(QtCore.Qt.ItemDataRole.UserRole) or "") == selected_mod_path:
                    self.table.selectRow(row_idx)
                    break

    def selected_mod_path(self) -> str:
        items = self.table.selectedItems()
        if not items:
            return ""
        row_idx = items[0].row()
        first = self.table.item(row_idx, 0)
        return str(first.data(QtCore.Qt.ItemDataRole.UserRole) or "") if first else ""

    def retranslate(self, tx) -> None:
        self.intro_title.setText(tx("BIBLIOTECA DE MODS", "MOD LIBRARY"))
        self.intro_desc.setText(tx(
            "Hookshot y Longshot cargan RomFS. NX2NAVI reconoce ExeFS, pero puede marcar algunos mods como Not Usable.",
            "Hookshot and Longshot load RomFS. NX2NAVI recognizes ExeFS, but may mark some mods Not Usable.",
        ))
        self.mod_profile_label.setText(tx("Perfil de mods:", "Mod profile:"))
        self.apply_profile_btn.setText(tx("Aplicar perfil de mods", "Apply mod profile"))
        self.save_profile_btn.setText(tx("Guardar selección en perfil…", "Save selection to profile…"))
        self.search_edit.setPlaceholderText(tx("Buscar mod…", "Filter mods…"))
        self.install_btn.setText(tx("Importar ZIP a biblioteca…", "Import ZIP to library…"))
        self.gb_btn.setText(tx("GameBanana URL…", "GameBanana URL…"))
        self.remove_btn.setText(tx("Desinstalar mod…", "Uninstall mod…"))
        self.table.setHorizontalHeaderLabels([tx("Mod", "Mod"), tx("Tipo", "Type"), tx("Estado", "Status")])
        self.table.horizontalHeader().setToolTip(tx(
            "Haz clic en cualquier encabezado (Mod, Tipo, Estado) para ordenar las filas.",
            "Click any column header (Mod, Type, Status) to sort the table.",
        ))
        self.legend_label.setText(tx(
            "● Activo en port · ○ Desactivado · ◇ Solo biblioteca · ▲ ExeFS revisar · ✕ Incompatible  |  Clic en encabezados para ordenar",
            "● Enabled · ○ Disabled · ◇ Library only · ▲ Check ExeFS · ✕ Incompatible  |  Click column headers to sort",
        ))
        self.install_btn.setToolTip(tx("Extrae un ZIP a Mods/ sin activarlo aún.", "Extracts a ZIP into central Mods/ without enabling yet."))
        self.gb_btn.setToolTip(tx(
            "Descarga o actualiza un mod directamente desde la API de GameBanana (URL o ID).",
            "Download or update a mod directly from the GameBanana API (URL or ID).",
        ))
        self.toggle_btn.setToolTip(tx("Despliega el mod al port si hace falta y lo activa o desactiva (o doble clic en la fila).", "Deploys mod to the port if needed and toggles it (or double-click row)."))
        self.remove_btn.setToolTip(tx("Respalda y elimina el mod de la biblioteca y del port.", "Backs up and removes mod from central library and port."))


class BackupsPage(QtWidgets.QWidget):
    """Backup browser and cleanup table."""

    refresh_requested = QtCore.Signal()
    open_selected_requested = QtCore.Signal(str)
    open_root_requested = QtCore.Signal()
    prune_requested = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        top = QtWidgets.QFrame()
        top.setObjectName("CardPanel")
        tl = QtWidgets.QHBoxLayout(top)
        tl.setContentsMargins(14, 12, 14, 12)
        tl.setSpacing(8)
        self.title_lbl = QtWidgets.QLabel("HISTORIAL DE RESPALDOS")
        self.title_lbl.setObjectName("SectionTitle")
        tl.addWidget(self.title_lbl, 1)
        self.refresh_btn = QtWidgets.QPushButton("Actualizar")
        self.open_sel_btn = QtWidgets.QPushButton("Abrir seleccionado")
        self.open_root_btn = QtWidgets.QPushButton("Abrir backups/")
        self.prune_btn = QtWidgets.QPushButton("Limpiar antiguos (dejar 15)")
        self.prune_btn.setObjectName("DangerButton")
        tl.addWidget(self.refresh_btn)
        tl.addWidget(self.open_sel_btn)
        tl.addWidget(self.open_root_btn)
        tl.addWidget(self.prune_btn)
        root.addWidget(top)

        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setSortIndicator(0, QtCore.Qt.SortOrder.DescendingOrder)
        self.table.setSortingEnabled(True)
        root.addWidget(self.table, 1)

        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        self.open_sel_btn.clicked.connect(self._on_open_selected)
        self.open_root_btn.clicked.connect(self.open_root_requested.emit)
        self.prune_btn.clicked.connect(self.prune_requested.emit)

    def _on_open_selected(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        first = self.table.item(items[0].row(), 0)
        if first:
            path_str = str(first.data(QtCore.Qt.ItemDataRole.UserRole) or "")
            if path_str:
                self.open_selected_requested.emit(path_str)

    def populate_backups(self, records: list[dict], tx) -> None:
        cat_labels = {
            "profile-switch": tx("Cambio de perfil", "Profile switch"),
            "register-profile": tx("Registro de perfil", "Profile snapshot"),
            "slot": tx("Slot individual", "Slot backup"),
            "ini": tx("nx2navi.ini", "nx2navi.ini"),
            "mod": tx("Mod desinstalado", "Uninstalled mod"),
            "backup": tx("Respaldo", "Backup"),
        }
        header = self.table.horizontalHeader()
        sort_col = header.sortIndicatorSection()
        if sort_col < 0 or sort_col >= self.table.columnCount():
            sort_col = 0
        sort_order = header.sortIndicatorOrder()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for idx, rec in enumerate(records):
            self.table.insertRow(idx)
            ts_item = SortableTableWidgetItem(rec["timestamp"])
            ts_item.setData(QtCore.Qt.ItemDataRole.UserRole, str(rec["path"]))
            ts_item.setData(_SORT_KEY_ROLE, rec["timestamp"])
            cat_text = cat_labels.get(rec["category"], rec["category"])
            cat_item = SortableTableWidgetItem(cat_text)
            cat_item.setData(_SORT_KEY_ROLE, cat_text.casefold())
            sum_item = SortableTableWidgetItem(rec["summary"])
            sum_item.setData(_SORT_KEY_ROLE, rec["summary"].casefold())
            cnt_item = SortableTableWidgetItem(str(rec["files_count"]))
            cnt_item.setData(_SORT_KEY_ROLE, int(rec["files_count"]))
            sz_item = SortableTableWidgetItem(f"{rec['size_kb']:.1f} KB")
            sz_item.setData(_SORT_KEY_ROLE, float(rec["size_kb"]))
            self.table.setItem(idx, 0, ts_item)
            self.table.setItem(idx, 1, cat_item)
            self.table.setItem(idx, 2, sum_item)
            self.table.setItem(idx, 3, cnt_item)
            self.table.setItem(idx, 4, sz_item)
        self.table.setSortingEnabled(True)
        self.table.sortItems(sort_col, sort_order)

    def retranslate(self, tx) -> None:
        self.title_lbl.setText(tx("HISTORIAL DE RESPALDOS", "BACKUP HISTORY"))
        self.refresh_btn.setText(tx("Actualizar", "Refresh"))
        self.open_sel_btn.setText(tx("Abrir seleccionado", "Open selected"))
        self.open_root_btn.setText(tx("Abrir backups/", "Open backups/"))
        self.prune_btn.setText(tx("Limpiar antiguos (dejar 15)", "Prune old (keep 15)"))
        self.table.setHorizontalHeaderLabels([
            tx("Fecha", "Date"),
            tx("Tipo", "Type"),
            tx("Contenido", "Contents"),
            tx("Archivos", "Files"),
            tx("Tamaño", "Size"),
        ])


class SettingsPage(QtWidgets.QWidget):
    """Port directory selector, save account picker, global profile toggle, and language."""

    port_chosen = QtCore.Signal(str)
    manual_path_submitted = QtCore.Signal(str)
    browse_requested = QtCore.Signal()
    account_changed = QtCore.Signal(str)
    language_changed = QtCore.Signal(str)
    link_changed = QtCore.Signal(bool)
    check_updates_requested = QtCore.Signal()
    auto_update_toggled = QtCore.Signal(bool)
    browse_launch_exe_requested = QtCore.Signal()
    reset_launch_exe_requested = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        # Ports & Path card
        ports_card = QtWidgets.QFrame()
        ports_card.setObjectName("CardPanel")
        pl = QtWidgets.QVBoxLayout(ports_card)
        pl.setContentsMargins(14, 12, 14, 12)
        pl.setSpacing(8)
        self.ports_title = QtWidgets.QLabel("PORTS INSTALADOS Y RUTA")
        self.ports_title.setObjectName("SectionTitle")
        pl.addWidget(self.ports_title)

        self.ports_table = QtWidgets.QTableWidget(0, 3)
        self.ports_table.setMaximumHeight(160)
        self.ports_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.ports_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.ports_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.ports_table.verticalHeader().setVisible(False)
        hdr = self.ports_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        pl.addWidget(self.ports_table)

        path_row = QtWidgets.QHBoxLayout()
        self.path_edit = QtWidgets.QLineEdit()
        self.use_path_btn = QtWidgets.QPushButton("Usar ruta")
        self.browse_btn = QtWidgets.QPushButton("Cambiar carpeta…")
        self.switch_sel_port_btn = QtWidgets.QPushButton("Activar port de la tabla")
        self.switch_sel_port_btn.setObjectName("GoldButton")
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(self.use_path_btn)
        path_row.addWidget(self.browse_btn)
        path_row.addWidget(self.switch_sel_port_btn)
        pl.addLayout(path_row)

        exe_row = QtWidgets.QHBoxLayout()
        self.launch_exe_lbl = QtWidgets.QLabel("Ejecutable al pulsar Jugar:")
        self.launch_exe_edit = QtWidgets.QLineEdit()
        self.launch_exe_edit.setReadOnly(True)
        self.browse_launch_exe_btn = QtWidgets.QPushButton("Elegir .exe…")
        self.reset_launch_exe_btn = QtWidgets.QPushButton("Auto")
        exe_row.addWidget(self.launch_exe_lbl)
        exe_row.addWidget(self.launch_exe_edit, 1)
        exe_row.addWidget(self.browse_launch_exe_btn)
        exe_row.addWidget(self.reset_launch_exe_btn)
        pl.addLayout(exe_row)

        self.launch_exe_note = QtWidgets.QLabel("")
        self.launch_exe_note.setObjectName("MutedLabel")
        self.launch_exe_note.setWordWrap(True)
        pl.addWidget(self.launch_exe_note)
        root.addWidget(ports_card)

        # Account & Profile settings card
        acct_card = QtWidgets.QFrame()
        acct_card.setObjectName("CardPanel")
        al = QtWidgets.QVBoxLayout(acct_card)
        al.setContentsMargins(14, 12, 14, 12)
        al.setSpacing(8)
        self.acct_title = QtWidgets.QLabel("CUENTA DE GUARDADO Y PERFIL GLOBAL")
        self.acct_title.setObjectName("SectionTitle")
        al.addWidget(self.acct_title)

        acct_row = QtWidgets.QHBoxLayout()
        self.acct_lbl = QtWidgets.QLabel("Cuenta del port:")
        self.account_combo = QtWidgets.QComboBox()
        self.account_combo.setMinimumWidth(280)
        acct_row.addWidget(self.acct_lbl)
        acct_row.addWidget(self.account_combo)
        acct_row.addStretch(1)
        al.addLayout(acct_row)

        self.global_link_check = QtWidgets.QCheckBox("Modo unificado: cambiar de usuario cambia partidas y mods a la vez")
        self.global_link_check.setChecked(True)
        al.addWidget(self.global_link_check)
        root.addWidget(acct_card)

        # Language & Paths info card
        lang_card = QtWidgets.QFrame()
        lang_card.setObjectName("CardPanel")
        ll = QtWidgets.QVBoxLayout(lang_card)
        ll.setContentsMargins(14, 12, 14, 12)
        ll.setSpacing(8)
        self.pref_title = QtWidgets.QLabel("IDIOMA Y RUTAS DEL MANAGER")
        self.pref_title.setObjectName("SectionTitle")
        ll.addWidget(self.pref_title)

        lang_row = QtWidgets.QHBoxLayout()
        self.lang_lbl = QtWidgets.QLabel("Idioma / Language:")
        self.language_combo = QtWidgets.QComboBox()
        self.language_combo.addItems(["Español", "English"])
        lang_row.addWidget(self.lang_lbl)
        lang_row.addWidget(self.language_combo)
        lang_row.addStretch(1)
        ll.addLayout(lang_row)

        update_row = QtWidgets.QHBoxLayout()
        self.version_lbl = QtWidgets.QLabel("")
        self.check_updates_btn = QtWidgets.QPushButton("Buscar actualizaciones en GitHub…")
        update_row.addWidget(self.version_lbl)
        update_row.addStretch(1)
        update_row.addWidget(self.check_updates_btn)
        ll.addLayout(update_row)

        self.auto_update_check = QtWidgets.QCheckBox("Buscar actualizaciones automáticamente al iniciar")
        self.auto_update_check.setChecked(True)
        ll.addWidget(self.auto_update_check)

        self.paths_info = QtWidgets.QLabel("")
        self.paths_info.setObjectName("MutedLabel")
        self.paths_info.setWordWrap(True)
        ll.addWidget(self.paths_info)
        root.addWidget(lang_card)
        root.addStretch(1)

        self.use_path_btn.clicked.connect(lambda: self.manual_path_submitted.emit(self.path_edit.text()))
        self.browse_btn.clicked.connect(self.browse_requested.emit)
        self.switch_sel_port_btn.clicked.connect(self._activate_table_port)
        self.ports_table.itemDoubleClicked.connect(lambda _item: self._activate_table_port())
        self.account_combo.currentTextChanged.connect(self.account_changed.emit)
        self.language_combo.currentTextChanged.connect(self.language_changed.emit)
        self.global_link_check.toggled.connect(self.link_changed.emit)
        self.check_updates_btn.clicked.connect(self.check_updates_requested.emit)
        self.auto_update_check.toggled.connect(self.auto_update_toggled.emit)
        self.browse_launch_exe_btn.clicked.connect(self.browse_launch_exe_requested.emit)
        self.reset_launch_exe_btn.clicked.connect(self.reset_launch_exe_requested.emit)

    def _activate_table_port(self) -> None:
        items = self.ports_table.selectedItems()
        if not items:
            return
        item = self.ports_table.item(items[0].row(), 2)
        if item and item.text():
            self.port_chosen.emit(item.text())

    def populate_ports(self, ports: list[dict], current_root: str) -> None:
        self.ports_table.setRowCount(0)
        for idx, p in enumerate(ports):
            self.ports_table.insertRow(idx)
            self.ports_table.setItem(idx, 0, QtWidgets.QTableWidgetItem(p["name"]))
            self.ports_table.setItem(idx, 1, QtWidgets.QTableWidgetItem(p.get("version", "Detected")))
            self.ports_table.setItem(idx, 2, QtWidgets.QTableWidgetItem(str(p["root"])))
            if str(p["root"]).casefold() == current_root.casefold():
                self.ports_table.selectRow(idx)

    def populate_accounts(self, accounts: list[str], current_account: str) -> None:
        self.account_combo.blockSignals(True)
        self.account_combo.clear()
        self.account_combo.addItems(accounts)
        if current_account in accounts:
            self.account_combo.setCurrentText(current_account)
        self.account_combo.setEnabled(bool(accounts))
        self.account_combo.blockSignals(False)

    def retranslate(self, manager_dir: str, log_path: str, tx, app_version: str = "") -> None:
        self.ports_title.setText(tx("PORTS DETECTADOS Y CARPETA", "DETECTED PORTS & FOLDER"))
        self.ports_table.setHorizontalHeaderLabels([tx("Port", "Port"), tx("Versión", "Version"), tx("Ruta", "Path")])
        self.use_path_btn.setText(tx("Usar ruta", "Use path"))
        self.browse_btn.setText(tx("Cambiar carpeta…", "Change folder…"))
        self.switch_sel_port_btn.setText(tx("Usar port seleccionado", "Switch to selected port"))
        self.launch_exe_lbl.setText(tx("Ejecutable al pulsar Jugar:", "Executable on Play:"))
        self.browse_launch_exe_btn.setText(tx("Elegir .exe…", "Choose .exe…"))
        self.reset_launch_exe_btn.setText(tx("Auto", "Auto"))
        self.launch_exe_note.setText(tx(
            "Nota: En Longshot se recomienda abrir desde el ejecutable del Launcher "
            "(ej. LongshotLauncher-v1.0.0-rc.3-windows-x64-setup.exe o LongshotLauncher.exe) para que reconozca "
            "los saves externos en LongshotLauncher-data\\user\\save. Hookshot y NX2NAVI funcionan con detección automática.",
            "Note: For Longshot, launching via the Launcher executable "
            "(e.g. LongshotLauncher-v1.0.0-rc.3-windows-x64-setup.exe or LongshotLauncher.exe) is recommended so external "
            "saves in LongshotLauncher-data\\user\\save are recognized. Hookshot and NX2NAVI work with auto-detection.",
        ))
        self.acct_title.setText(tx("CUENTA DE GUARDADO Y PERFIL GLOBAL", "SAVE ACCOUNT & GLOBAL PROFILE"))
        self.acct_lbl.setText(tx("Carpeta de cuenta:", "Account folder:"))
        self.global_link_check.setText(tx(
            "Modo unificado: cambiar de usuario cambia partidas y mods a la vez",
            "Unified mode: switching user updates both saves and mods",
        ))
        self.pref_title.setText(tx("IDIOMA Y UBICACIÓN DEL MANAGER", "LANGUAGE & MANAGER PATHS"))
        ver_label = f"v{app_version}" if app_version else "—"
        self.version_lbl.setText(tx(f"Versión instalada: {ver_label}", f"Installed version: {ver_label}"))
        self.check_updates_btn.setText(tx("Buscar actualizaciones en GitHub…", "Check GitHub for updates…"))
        self.auto_update_check.setText(tx(
            "Buscar actualizaciones automáticamente al iniciar",
            "Automatically check for updates on startup",
        ))
        self.paths_info.setText(f"Manager: {manager_dir}\nLog: {log_path}")
