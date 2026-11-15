"""PySide6 pages for Saves (slot cards + preview inspector) and Inventory & Progress (real slot metadata)."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ui_qt.slot_card import SlotCard, format_hearts, pixmap_from_jpeg
from ui_qt.theme import COLORS, make_svg_pixmap


class SavesPage(QtWidgets.QWidget):
    """Save slots visual card grid paired with a large screenshot & action inspector."""

    slot_selected = QtCore.Signal(object)
    refresh_requested = QtCore.Signal()
    backup_requested = QtCore.Signal()
    export_requested = QtCore.Signal()
    import_requested = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cards: dict[str, SlotCard] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        status_card = QtWidgets.QFrame()
        status_card.setObjectName("CardPanel")
        sc_layout = QtWidgets.QVBoxLayout(status_card)
        sc_layout.setContentsMargins(14, 10, 14, 10)
        sc_layout.setSpacing(6)

        top_row = QtWidgets.QHBoxLayout()
        self.slots_heading_label = QtWidgets.QLabel("ESPACIOS DE GUARDADO")
        self.slots_heading_label.setObjectName("SectionTitle")
        top_row.addWidget(self.slots_heading_label, 1)

        self.profile_mode_badge = QtWidgets.QLabel("—")
        self.profile_mode_badge.setStyleSheet(
            f"background-color: {COLORS['panel2']}; color: {COLORS['muted']}; "
            "border-radius: 6px; padding: 4px 10px; font-weight: 700; font-size: 9pt;"
        )
        top_row.addWidget(self.profile_mode_badge, 0)
        sc_layout.addLayout(top_row)

        self.save_status_label = QtWidgets.QLabel("")
        self.save_status_label.setObjectName("MutedLabel")
        self.save_status_label.setWordWrap(True)
        sc_layout.addWidget(self.save_status_label)
        root.addWidget(status_card)

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(12)
        root.addLayout(body, 1)

        # Left scrollable card grid
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_container = QtWidgets.QWidget()
        self.scroll_container.setStyleSheet("background: transparent;")
        self.grid_wrapper = QtWidgets.QVBoxLayout(self.scroll_container)
        self.grid_wrapper.setContentsMargins(0, 0, 4, 0)
        self.grid_wrapper.setSpacing(10)

        self.cards_grid = QtWidgets.QGridLayout()
        self.cards_grid.setSpacing(10)
        self.grid_wrapper.addLayout(self.cards_grid)

        self.empty_label = QtWidgets.QLabel("")
        self.empty_label.setObjectName("MutedLabel")
        self.empty_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.hide()
        self.grid_wrapper.addWidget(self.empty_label)
        self.grid_wrapper.addStretch(1)

        self.scroll.setWidget(self.scroll_container)
        body.addWidget(self.scroll, 3)

        # Right inspector panel
        inspector = QtWidgets.QFrame()
        inspector.setObjectName("CardPanel")
        inspector.setMinimumWidth(330)
        inspector.setMaximumWidth(420)
        insp_layout = QtWidgets.QVBoxLayout(inspector)
        insp_layout.setContentsMargins(14, 14, 14, 14)
        insp_layout.setSpacing(10)

        self.preview_heading = QtWidgets.QLabel("VISTA PREVIA")
        self.preview_heading.setObjectName("SectionTitle")
        insp_layout.addWidget(self.preview_heading)

        self.preview_image = QtWidgets.QLabel()
        self.preview_image.setFixedHeight(194)
        self.preview_image.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setStyleSheet(
            f"background-color: #0e1611; border: 1px solid {COLORS['line']}; border-radius: 8px; color: {COLORS['muted']};"
        )
        insp_layout.addWidget(self.preview_image)

        self.preview_title = QtWidgets.QLabel("Selecciona un slot")
        self.preview_title.setStyleSheet(f"color: {COLORS['gold']}; font-size: 13pt; font-weight: 700;")
        insp_layout.addWidget(self.preview_title)

        self.preview_scene = QtWidgets.QLabel("La escena aparecerá aquí")
        self.preview_scene.setWordWrap(True)
        self.preview_scene.setStyleSheet(f"color: {COLORS['text']}; font-size: 10.5pt; font-weight: 600;")
        insp_layout.addWidget(self.preview_scene)

        stats_box = QtWidgets.QFrame()
        stats_box.setObjectName("InnerPanel")
        stats_layout = QtWidgets.QVBoxLayout(stats_box)
        stats_layout.setContentsMargins(10, 8, 10, 8)
        self.preview_stats = QtWidgets.QLabel("—")
        self.preview_stats.setObjectName("MutedLabel")
        self.preview_stats.setWordWrap(True)
        stats_layout.addWidget(self.preview_stats)
        insp_layout.addWidget(stats_box)

        insp_layout.addStretch(1)

        btn_grid = QtWidgets.QGridLayout()
        btn_grid.setSpacing(8)
        self.refresh_btn = QtWidgets.QPushButton("Actualizar")
        self.backup_btn = QtWidgets.QPushButton("Respaldar slot")
        self.export_btn = QtWidgets.QPushButton("Exportar…")
        self.import_btn = QtWidgets.QPushButton("Importar / restaurar…")
        self.import_btn.setObjectName("GoldButton")

        btn_grid.addWidget(self.refresh_btn, 0, 0)
        btn_grid.addWidget(self.backup_btn, 0, 1)
        btn_grid.addWidget(self.export_btn, 1, 0)
        btn_grid.addWidget(self.import_btn, 1, 1)
        insp_layout.addLayout(btn_grid)
        body.addWidget(inspector, 2)

        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        self.backup_btn.clicked.connect(self.backup_requested.emit)
        self.export_btn.clicked.connect(self.export_requested.emit)
        self.import_btn.clicked.connect(self.import_requested.emit)

    def clear_slots(self, tx, no_port: bool = False) -> None:
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._cards.clear()
        if no_port:
            self.empty_label.setText(tx(
                "Bienvenido a Ocarina Remake Manager.\n\n"
                "Aún no has seleccionado ningún port (Hookshot, Longshot o NX2NAVI).\n"
                "• Pulsa el botón de carpeta 📁 en «PORT ACTIVO» (abajo a la izquierda), o\n"
                "• Ve a «Configuración» → «Explorar…» para elegir la carpeta de tu juego.",
                "Welcome to Ocarina Remake Manager.\n\n"
                "No game port has been selected yet (Hookshot, Longshot, or NX2NAVI).\n"
                "• Click the folder button 📁 under 'ACTIVE PORT' (bottom-left), or\n"
                "• Open 'Settings' → 'Browse…' to select your game folder.",
            ))
            self.empty_label.show()
        self.update_preview(None, tx)

    def populate_slots(self, slot_infos: list[dict], selected_path, tx) -> None:
        self.clear_slots(tx)
        if not slot_infos:
            self.empty_label.setText(tx(
                "No hay slots en esta vista. Elige o activa un perfil con partidas.",
                "No save slots in this view. Select or activate a profile with saves.",
            ))
            self.empty_label.show()
            return
        self.empty_label.hide()
        files_word = tx("archivos", "files")
        no_thumb = tx("Sin captura", "No capture")
        for idx, info in enumerate(slot_infos):
            card = SlotCard(info, files_word=files_word, no_thumb_text=no_thumb)
            card.clicked.connect(self.slot_selected.emit)
            self._cards[str(info["path"])] = card
            self.cards_grid.addWidget(card, idx // 2, idx % 2)
        self.cards_grid.setColumnStretch(0, 1)
        self.cards_grid.setColumnStretch(1, 1)
        self.mark_selected(selected_path)

    def mark_selected(self, selected_path) -> None:
        selected_key = str(selected_path) if selected_path else ""
        for key, card in self._cards.items():
            card.set_selected(key == selected_key)

    def update_preview(self, slot_info: dict | None, tx) -> None:
        if not slot_info:
            self.preview_image.setPixmap(QtGui.QPixmap())
            self.preview_image.setText(tx("Sin captura disponible", "No screenshot available"))
            self.preview_title.setText(tx("Selecciona un slot", "Select a slot"))
            self.preview_scene.setText(tx("La escena aparecerá aquí", "The scene will appear here"))
            self.preview_stats.setText(tx(
                "Selecciona un port y una partida para ver su captura, corazones, rupias y escena.",
                "Select a port and a save slot to view its screenshot, hearts, rupees, and scene.",
            ))
            return

        pixmap = pixmap_from_jpeg(slot_info.get("jpeg_bytes"), 344, 186)
        if pixmap is not None:
            self.preview_image.setPixmap(pixmap)
            self.preview_image.setText("")
        else:
            self.preview_image.setPixmap(QtGui.QPixmap())
            self.preview_image.setText(tx("Sin captura disponible", "No screenshot available"))

        self.preview_title.setText(slot_info["title"])
        self.preview_scene.setText(slot_info["scene_display"])
        stats_data = slot_info.get("stats") or {}
        lines: list[str] = []
        if stats_data.get("hearts_max") is not None and stats_data.get("rupees") is not None:
            h_cur = format_hearts(stats_data.get("hearts_current"))
            h_max = stats_data["hearts_max"]
            rupees = stats_data["rupees"]
            skulls = stats_data.get("skulltulas", 0)
            m_cur = stats_data.get("magic_current", 0)
            m_max = stats_data.get("magic_max", 0)
            q_done = stats_data.get("quest_flags_done", 0)
            q_tot = stats_data.get("quest_flags_total", 0)
            lines.append(
                f"♥ {tx('Corazones', 'Hearts')}: {h_cur}/{h_max}   ·   "
                f"{tx('Rupias', 'Rupees')}: {rupees}   ·   "
                f"Skulltulas: {skulls}/100"
            )
            lines.append(
                f"{tx('Magia', 'Magic')}: {m_cur}/{m_max}   ·   "
                f"{tx('Hitos', 'Milestones')}: {q_done}/{q_tot}"
            )
            if stats_data.get("ingame_datetime"):
                lines.append(f"{tx('Guardado en juego', 'In-game save')}: {stats_data['ingame_datetime']}")
        lines.extend([
            f"{tx('Archivos', 'Files')}: {slot_info['files_count']}   ·   {tx('Tamaño', 'Size')}: {slot_info['size_kb']:.1f} KB",
            f"{tx('Escena interna', 'Internal scene')}: {slot_info['raw_scene'] or '—'}",
            f"progress.sav Hash: {slot_info['progress_hash']}",
        ])
        self.preview_stats.setText("\n".join(lines))

    def set_actions_enabled(self, has_actions: bool, busy: bool = False) -> None:
        self.refresh_btn.setEnabled(not busy)
        enabled = has_actions and not busy
        self.backup_btn.setEnabled(enabled)
        self.export_btn.setEnabled(enabled)
        self.import_btn.setEnabled(enabled)

    def retranslate(self, tx) -> None:
        self.preview_heading.setText(tx("VISTA PREVIA", "PREVIEW"))
        self.refresh_btn.setText(tx("Actualizar", "Refresh"))
        self.backup_btn.setText(tx("Respaldar slot", "Back up slot"))
        self.export_btn.setText(tx("Exportar…", "Export…"))
        self.import_btn.setText(tx("Importar / restaurar…", "Import / restore…"))
        self.refresh_btn.setToolTip(tx("Recarga perfiles, slots y mods desde el disco.", "Reload profiles, slots, and mods from disk."))
        self.backup_btn.setToolTip(tx("Crea un respaldo rápido del slot seleccionado en backups/.", "Create a quick backup of the selected slot in backups/."))
        self.export_btn.setToolTip(tx("Copia el slot seleccionado a una carpeta externa.", "Copy the selected slot to an external folder."))
        self.import_btn.setToolTip(tx("Reemplaza el slot seleccionado desde una carpeta exportada (respalda antes).", "Replace the selected slot from an exported folder (backs up first)."))


class InventoryPage(QtWidgets.QWidget):
    """Hyrule Archive real slot inspector showing verified slot files and decoding scope."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._last_info: dict | None = None
        self._last_port_label: str = ""
        self._last_profile: str = ""
        self._build_ui()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        hero = QtWidgets.QFrame()
        hero.setObjectName("CardPanel")
        hero_layout = QtWidgets.QHBoxLayout(hero)
        hero_layout.setContentsMargins(16, 16, 16, 16)
        hero_layout.setSpacing(16)

        self.hero_image = QtWidgets.QLabel()
        self.hero_image.setFixedSize(320, 180)
        self.hero_image.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.hero_image.setStyleSheet(
            f"background-color: #0e1611; border: 1px solid {COLORS['gold_dim']}; border-radius: 8px; color: {COLORS['muted']};"
        )
        hero_layout.addWidget(self.hero_image)

        meta_col = QtWidgets.QVBoxLayout()
        meta_col.setSpacing(6)
        self.hero_kicker = QtWidgets.QLabel("FICHA DE AVENTURA · INSPECTOR DE SLOT")
        self.hero_kicker.setObjectName("SectionTitle")
        meta_col.addWidget(self.hero_kicker)

        self.slot_title = QtWidgets.QLabel("—")
        self.slot_title.setStyleSheet(f"color: {COLORS['text']}; font-size: 16pt; font-weight: 700;")
        meta_col.addWidget(self.slot_title)

        self.scene_label = QtWidgets.QLabel("—")
        self.scene_label.setStyleSheet(f"color: {COLORS['gold']}; font-size: 11.5pt; font-weight: 600;")
        meta_col.addWidget(self.scene_label)

        self.file_meta = QtWidgets.QLabel("")
        self.file_meta.setObjectName("MutedLabel")
        self.file_meta.setWordWrap(True)
        meta_col.addWidget(self.file_meta)
        meta_col.addStretch(1)
        hero_layout.addLayout(meta_col, 1)
        root.addWidget(hero)

        note_banner = QtWidgets.QFrame()
        note_banner.setObjectName("InnerPanel")
        nb_layout = QtWidgets.QHBoxLayout(note_banner)
        nb_layout.setContentsMargins(12, 10, 12, 10)
        nb_layout.setSpacing(10)
        icon_lbl = QtWidgets.QLabel()
        icon_lbl.setPixmap(make_svg_pixmap("inventory", COLORS["gold"], 20))
        nb_layout.addWidget(icon_lbl)
        self.scope_note = QtWidgets.QLabel("")
        self.scope_note.setObjectName("MutedLabel")
        self.scope_note.setWordWrap(True)
        nb_layout.addWidget(self.scope_note, 1)
        root.addWidget(note_banner)

        cards_grid = QtWidgets.QGridLayout()
        cards_grid.setSpacing(10)
        self._category_cards: list[tuple[QtWidgets.QLabel, QtWidgets.QLabel, str, str, str, str]] = []
        specs = [
            ("Equipamiento · Espadas, Escudos, Túnicas y Botas", "Equipment · Swords, Shields, Tunics & Boots", "Esperando datos de progress.sav…", "Waiting for progress.sav data…"),
            ("Piedras Espirituales y Medallones", "Spiritual Stones & Medallions", "Esperando datos de progress.sav…", "Waiting for progress.sav data…"),
            ("Objetos, Magias, Mejoras y Botellas", "Items, Spells, Upgrades & Bottles", "Esperando datos de progress.sav…", "Waiting for progress.sav data…"),
            ("Estado Vital, Munición y Coordenadas", "Vitals, Ammo & Coordinates", "Esperando datos de caption.sav y progress.sav…", "Waiting for caption.sav & progress.sav data…"),
        ]
        for idx, (title_es, title_en, desc_es, desc_en) in enumerate(specs):
            box = QtWidgets.QFrame()
            box.setObjectName("CardPanel")
            bl = QtWidgets.QVBoxLayout(box)
            bl.setContentsMargins(14, 12, 14, 12)
            bl.setSpacing(6)
            title_lbl = QtWidgets.QLabel(title_es)
            title_lbl.setObjectName("SectionTitle")
            bl.addWidget(title_lbl)
            desc_lbl = QtWidgets.QLabel(desc_es)
            desc_lbl.setStyleSheet(f"color: {COLORS['text']}; font-size: 9.5pt;")
            desc_lbl.setWordWrap(True)
            bl.addWidget(desc_lbl)
            self._category_cards.append((title_lbl, desc_lbl, title_es, title_en, desc_es, desc_en))
            cards_grid.addWidget(box, idx // 2, idx % 2)
        root.addLayout(cards_grid)
        root.addStretch(1)

    def update_slot(self, slot_info: dict | None, port_label: str, profile_name: str, tx) -> None:
        self._last_info = slot_info
        self._last_port_label = port_label
        self._last_profile = profile_name
        self.hero_kicker.setText(tx(
            f"FICHA DE AVENTURA · {port_label} · PERFIL «{profile_name or '—'}»",
            f"ADVENTURE LOG · {port_label} · PROFILE '{profile_name or '—'}'",
        ))
        self.scope_note.setText(tx(
            "Inventario completo decodificado desde progress.sav (catálogo Traiver/OOT-SW2SE) junto con corazones, rupias, magia, Skulltulas, fecha y coordenadas reales de caption.sav.",
            "Full inventory decoded from progress.sav (Traiver/OOT-SW2SE catalog) together with hearts, rupees, magic, Gold Skulltulas, timestamp, and coordinates from caption.sav.",
        ))

        if not slot_info:
            for title_lbl, desc_lbl, t_es, t_en, d_es, d_en in self._category_cards:
                title_lbl.setText(tx(t_es, t_en))
                desc_lbl.setText(tx(d_es, d_en))
            self.hero_image.setPixmap(QtGui.QPixmap())
            self.hero_image.setText(tx("Selecciona un slot en Partidas", "Select a slot in Saves"))
            self.slot_title.setText(tx("Sin slot seleccionado", "No slot selected"))
            self.scene_label.setText("—")
            self.file_meta.setText("")
            return

        pixmap = pixmap_from_jpeg(slot_info.get("jpeg_bytes"), 312, 174)
        if pixmap is not None:
            self.hero_image.setPixmap(pixmap)
            self.hero_image.setText("")
        else:
            self.hero_image.setPixmap(QtGui.QPixmap())
            self.hero_image.setText(tx("Sin captura disponible", "No screenshot available"))

        self.slot_title.setText(slot_info["title"])
        self.scene_label.setText(
            f"{slot_info['scene_display']}   ({slot_info['raw_scene'] or tx('sin escena interna', 'no internal id')})"
        )
        self.file_meta.setText(
            f"{tx('Modificado', 'Modified')}: {slot_info['mtime_str']}   ·   "
            f"{tx('Archivos', 'Files')}: {slot_info['files_count']} ({slot_info['size_kb']:.1f} KB)\n"
            f"progress.sav: {slot_info['progress_size']:,} bytes  ·  BLAKE2b: {slot_info['progress_hash']}\n"
            f"caption.sav: {slot_info['caption_size']:,} bytes  ·  {tx('Ruta', 'Path')}: {slot_info['path']}"
        )

        def fmt_list(values: list[str]) -> str:
            return ", ".join(values) if values else tx("Ninguno", "None")

        st = slot_info.get("stats") or {}
        inv = slot_info.get("inventory") or {}
        if inv:
            stones = inv.get("stones", [])
            meds = inv.get("medallions", [])
            bottles = inv.get("bottles", [])
            bottles_txt = ", ".join(f"#{i + 1}: {b}" for i, b in enumerate(bottles)) if bottles else tx("Ninguna", "None")
            card_0 = tx(
                f"Espadas: {fmt_list(inv.get('swords', []))}\n"
                f"Escudos: {fmt_list(inv.get('shields', []))}\n"
                f"Túnicas: {fmt_list(inv.get('tunics', []))}\n"
                f"Botas: {fmt_list(inv.get('boots', []))}",
                f"Swords: {fmt_list(inv.get('swords', []))}\n"
                f"Shields: {fmt_list(inv.get('shields', []))}\n"
                f"Tunics: {fmt_list(inv.get('tunics', []))}\n"
                f"Boots: {fmt_list(inv.get('boots', []))}",
            )
            card_1 = tx(
                f"Piedras ({len(stones)}/3): {fmt_list(stones)}\n"
                f"Medallones ({len(meds)}/6): {fmt_list(meds)}",
                f"Stones ({len(stones)}/3): {fmt_list(stones)}\n"
                f"Medallions ({len(meds)}/6): {fmt_list(meds)}",
            )
            card_2 = tx(
                f"Objetos / Magias: {fmt_list(inv.get('items', []))}\n"
                f"Mejoras: {fmt_list(inv.get('upgrades', []))}\n"
                f"Botellas ({len(bottles)}): {bottles_txt}",
                f"Items / Spells: {fmt_list(inv.get('items', []))}\n"
                f"Upgrades: {fmt_list(inv.get('upgrades', []))}\n"
                f"Bottles ({len(bottles)}): {bottles_txt}",
            )
        else:
            no_prog = tx(
                "Este slot no contiene progress.sav legible o usa otro formato.",
                "This slot does not contain a readable progress.sav.",
            )
            card_0 = card_1 = card_2 = no_prog

        ammo = inv.get("ammo") or {}
        vitals_lines: list[str] = []
        if st.get("hearts_max") is not None and st.get("rupees") is not None:
            h_cur = format_hearts(st.get("hearts_current"))
            h_max = st["hearts_max"]
            rupees = st["rupees"]
            m_cur = st.get("magic_current", 0)
            m_max = st.get("magic_max", 0)
            skulls = st.get("skulltulas", 0)
            hp_cnt = ammo.get("heart_pieces", 0)
            age_raw = st.get("age", "")
            age_disp = (
                tx("Adulto", "Adult") if age_raw == "adult"
                else (tx("Niño", "Child") if age_raw == "child" else tx("No especificado", "Unspecified"))
            )
            cx, cy, cz = st.get("coords", (0.0, 0.0, 0.0))
            dt_str = st.get("ingame_datetime") or "—"
            vitals_lines.append(tx(
                f"♥ {h_cur}/{h_max} corazones ({hp_cnt}/4 piezas) · Rupias: {rupees} · Magia: {m_cur}/{m_max}",
                f"♥ {h_cur}/{h_max} hearts ({hp_cnt}/4 pieces) · Rupees: {rupees} · Magic: {m_cur}/{m_max}",
            ))
            vitals_lines.append(tx(
                f"Skulltulas: {skulls}/100 · Edad: {age_disp} · Guardado: {dt_str}",
                f"Skulltulas: {skulls}/100 · Age: {age_disp} · Saved: {dt_str}",
            ))
            vitals_lines.append(tx(
                f"Coordenadas: X={cx:.1f}, Y={cy:.1f}, Z={cz:.1f}",
                f"Coordinates: X={cx:.1f}, Y={cy:.1f}, Z={cz:.1f}",
            ))
        elif ammo:
            vitals_lines.append(tx(
                f"Rupias: {ammo.get('rupees', 0)} · Skulltulas: {ammo.get('skulltulas', 0)} · Piezas corazón: {ammo.get('heart_pieces', 0)}/4",
                f"Rupees: {ammo.get('rupees', 0)} · Skulltulas: {ammo.get('skulltulas', 0)} · Heart pieces: {ammo.get('heart_pieces', 0)}/4",
            ))

        if ammo:
            vitals_lines.append(tx(
                f"Munición — Bombas: {ammo.get('bombs', 0)} · Flechas: {ammo.get('arrows', 0)} · "
                f"Palos: {ammo.get('sticks', 0)} · Nueces: {ammo.get('nuts', 0)} · "
                f"Semillas: {ammo.get('seeds', 0)} · Bombchus: {ammo.get('bombchus', 0)} · Frijoles: {ammo.get('beans', 0)}",
                f"Ammo — Bombs: {ammo.get('bombs', 0)} · Arrows: {ammo.get('arrows', 0)} · "
                f"Sticks: {ammo.get('sticks', 0)} · Nuts: {ammo.get('nuts', 0)} · "
                f"Seeds: {ammo.get('seeds', 0)} · Bombchus: {ammo.get('bombchus', 0)} · Beans: {ammo.get('beans', 0)}",
            ))

        card_3 = "\n".join(vitals_lines) if vitals_lines else tx(
            "Este slot no contiene cabecera legible en caption.sav ni en progress.sav.",
            "This slot does not contain a readable caption.sav or progress.sav.",
        )
        card_texts = [card_0, card_1, card_2, card_3]

        for idx, (title_lbl, desc_lbl, t_es, t_en, _d_es, _d_en) in enumerate(self._category_cards):
            title_lbl.setText(tx(t_es, t_en))
            desc_lbl.setText(card_texts[idx])
