"""Save-profile, slot inspection, backup, and NX2NAVI save-tx services."""

from __future__ import annotations

from datetime import datetime
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import sys
from typing import Callable

ProgressCb = Callable[[float | None, str], None] | None
TxCb = Callable[[str, str], str]

_SCENE_TERMS = (
    "Field", "Forest", "Village", "Temple", "Deku", "Castle", "Market", "Ranch",
    "Cave", "Lake", "River", "Mountain", "Grave", "Kokiri", "Hyrule", "Gerudo",
    "Zora", "Jabu", "Spirit", "Fire", "Water", "Shadow", "Ganon",
)


def _default_tx(es: str, _en: str) -> str:
    return es


def _report(progress_cb: ProgressCb, fraction: float | None, message: str = "") -> None:
    if progress_cb:
        progress_cb(fraction, message)


def rmtree_force(path: Path | str) -> None:
    target = Path(path)
    if not target.exists():
        return

    def onerror(func, p, _exc):
        try:
            os.chmod(p, stat.S_IREAD | stat.S_IWRITE)
            func(p)
        except OSError:
            pass

    if sys.version_info >= (3, 12):
        shutil.rmtree(target, onexc=onerror)
    else:
        shutil.rmtree(target, onerror=onerror)


def contains_slot_folders(folder: Path | str | None) -> bool:
    if not folder:
        return False
    try:
        return any(item.is_dir() and item.name.startswith("slot_") for item in Path(folder).iterdir())
    except OSError:
        return False


def profile_items(folder: Path | str) -> list[Path]:
    return [
        p for p in Path(folder).iterdir()
        if p.name in ("account.sav", "option.sav") or (p.is_dir() and p.name.startswith("slot_"))
    ]


def save_payload_signature(folder: Path | str) -> tuple[tuple[str, int, bytes], ...] | None:
    root = Path(folder)
    signature: list[tuple[str, int, bytes]] = []
    try:
        for item in profile_items(root):
            files = [item] if item.is_file() else (child for child in item.rglob("*") if child.is_file())
            for file in files:
                relative = file.relative_to(root).as_posix()
                data = file.read_bytes()
                signature.append((relative, len(data), hashlib.blake2b(data, digest_size=16).digest()))
    except OSError:
        return None
    return tuple(sorted(signature))


def same_save_payload(left: Path | str, right: Path | str) -> bool:
    left_signature = save_payload_signature(left)
    return bool(left_signature) and left_signature == save_payload_signature(right)


def nx2navi_ready_dir(port: dict | None) -> Path | None:
    if not port or port.get("id") != "nx2navi":
        return None
    tx_dir = Path(port["root"]) / "profile" / "save-tx"
    if not tx_dir.is_dir():
        return None
    ready: list[tuple[int, Path]] = []
    try:
        for entry in tx_dir.iterdir():
            match = re.fullmatch(r"ready-(\d+)", entry.name)
            if match and entry.is_dir() and contains_slot_folders(entry):
                ready.append((int(match.group(1)), entry))
    except OSError:
        return None
    return max(ready, key=lambda item: item[0])[1] if ready else None


def nx2navi_effective_active_dir(port: dict | None, account_folder: Path | None) -> Path | None:
    ready = nx2navi_ready_dir(port)
    if ready is not None:
        return ready
    return account_folder


def nx2navi_settle_and_clean_save_tx(port: dict | None, backup_dir: Path | None = None) -> None:
    if not port or port.get("id") != "nx2navi":
        return
    profile_dir = Path(port["root"]) / "profile"
    tx_dir = profile_dir / "save-tx"
    if tx_dir.is_dir():
        for entry in list(tx_dir.iterdir()):
            if entry.name == "work":
                rmtree_force(entry)
                continue
            if backup_dir is not None and ((entry.is_dir() and any(entry.rglob("*"))) or entry.is_file()):
                tx_backup = Path(backup_dir) / "save-tx"
                tx_backup.mkdir(parents=True, exist_ok=True)
                dst = tx_backup / entry.name
                if not dst.exists():
                    shutil.copytree(entry, dst) if entry.is_dir() else shutil.copy2(entry, dst)
            rmtree_force(entry) if entry.is_dir() else entry.unlink(missing_ok=True)
    for pending_name in ("save-import", "save-import.part"):
        pending = profile_dir / pending_name
        if pending.exists():
            if backup_dir is not None:
                imp_backup = Path(backup_dir) / "save-import"
                imp_backup.mkdir(parents=True, exist_ok=True)
                dst = imp_backup / pending.name
                if not dst.exists():
                    shutil.copytree(pending, dst) if pending.is_dir() else shutil.copy2(pending, dst)
            rmtree_force(pending) if pending.is_dir() else pending.unlink(missing_ok=True)


def read_active_marker(folder: Path | None) -> str:
    if not folder:
        return ""
    marker = Path(folder) / ".orm-active-profile"
    try:
        if marker.is_file():
            return marker.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        pass
    return ""


def write_active_marker(folder: Path | None, name: str) -> None:
    if not folder or not name:
        return
    marker = Path(folder) / ".orm-active-profile"
    try:
        marker.write_text(name, encoding="utf-8")
    except OSError:
        pass


def detect_active_profile(
    port: dict | None,
    account_folder: Path | None,
    profile_paths: dict[str, Path],
    saved_name: str,
) -> tuple[str, bool]:
    """Return (detected_profile_name, should_persist_settings)."""
    if not account_folder:
        return "", False
    effective = nx2navi_effective_active_dir(port, account_folder) if (port and port.get("id") == "nx2navi") else account_folder
    if not effective or not contains_slot_folders(effective):
        return "", False
    matches = [name for name, folder in profile_paths.items() if same_save_payload(effective, folder)]
    if len(matches) == 1:
        detected = matches[0]
        write_active_marker(account_folder, detected)
        return detected, saved_name != detected
    if len(matches) > 1:
        detected = saved_name if saved_name in matches else matches[0]
        write_active_marker(account_folder, detected)
        return detected, saved_name != detected
    marker_name = read_active_marker(account_folder)
    if marker_name and marker_name in profile_paths:
        return marker_name, saved_name != marker_name
    if saved_name and saved_name in profile_paths:
        return saved_name, False
    return "", False


def extract_jpeg_bytes(caption_path: Path) -> bytes | None:
    if not caption_path.is_file():
        return None
    try:
        data = caption_path.read_bytes()
        start = data.find(b"\xff\xd8")
        end = data.find(b"\xff\xd9", start + 2) if start >= 0 else -1
        if start < 0 or end < 0:
            return None
        return data[start:end + 2]
    except OSError:
        return None


def read_scene(caption_path: Path) -> str:
    try:
        data = caption_path.read_bytes()
        strings = [
            s.decode("ascii", "replace")
            for s in re.findall(rb"[A-Za-z][A-Za-z0-9_]*(?:/[A-Za-z][A-Za-z0-9_]*)+", data)
        ]
        for value in strings:
            key = value.split("/", 1)[0]
            if any(term.lower() in key.lower() for term in _SCENE_TERMS):
                return value
    except OSError:
        pass
    return ""


def scene_label(scene: str, tx: TxCb = _default_tx) -> str:
    labels = {
        "InsideTheDekuTree": tx("Interior del Gran Árbol Deku", "Inside the Great Deku Tree"),
        "HyruleField": tx("Campo de Hyrule", "Hyrule Field"),
        "KokiriForest": tx("Bosque Kokiri", "Kokiri Forest"),
        "KakarikoVillage": tx("Aldea Kakariko", "Kakariko Village"),
        "Market": tx("Mercado", "Market"),
        "TempleOfTime": tx("Templo del Tiempo", "Temple of Time"),
    }
    key = scene.split("/")[0] if scene else ""
    if key in labels:
        return labels[key]
    return key.replace("_", " ") if key else tx("Escena no identificada", "Unknown scene")


def parse_caption_stats(caption_path: Path) -> dict:
    """Decode real gameplay vitals, timestamp, coordinates, and summary flags from caption.sav."""
    if not caption_path.is_file():
        return {}
    try:
        data = caption_path.read_bytes()
    except OSError:
        return {}
    if len(data) < 0x32C or struct.unpack_from("<I", data, 0)[0] != 0x01020304:
        return {}

    kv: dict[int, int] = {}
    quest_vals: list[int] = []
    is_autosave = False
    for off in range(0x028, 0x2A0, 8):
        key_hash, val = struct.unpack_from("<II", data, off)
        if key_hash != 0:
            kv[key_hash] = val
        if off < 0x100:
            if key_hash == 0x1EDA08D5:
                is_autosave = bool(val)
            elif key_hash != 0:
                quest_vals.append(1 if val != 0 else 0)

    hearts_cur_q = kv.get(0x1E55ECC5)
    hearts_max_q = kv.get(0x74BD05D0)
    hearts_current = (hearts_cur_q / 4.0) if hearts_cur_q is not None else None
    hearts_max = int(hearts_max_q // 4) if (hearts_max_q is not None and hearts_max_q > 0) else None

    year = kv.get(0x9811A3F7, 0)
    month = kv.get(0xDFD840D3, 0)
    day = kv.get(0xBD46F485, 0)
    hour = kv.get(0x23F3D75E, 0)
    minute = kv.get(0x5EE50BED, 0)
    second = kv.get(0x27853BF7, 0)
    ingame_datetime = (
        f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
        if (year and month and day)
        else ""
    )

    x, y, z = struct.unpack_from("<fff", data, 0x2A0)
    meta_parts = [
        p.decode("latin1", errors="ignore")
        for p in data[0x2EC:0x32C].split(b"\x00")
        if p
    ]
    joined_meta = " / ".join(meta_parts).casefold()
    if "adult" in joined_meta:
        age = "adult"
    elif "child" in joined_meta:
        age = "child"
    else:
        age = ""

    return {
        "hearts_current_quarters": hearts_cur_q,
        "hearts_max_quarters": hearts_max_q,
        "hearts_current": hearts_current,
        "hearts_max": hearts_max,
        "rupees": kv.get(0xA9557547),
        "magic_current": kv.get(0x19F26B6A),
        "magic_max": kv.get(0x943F8EC3),
        "skulltulas": kv.get(0xDC941483),
        "ingame_datetime": ingame_datetime,
        "quest_flags_done": sum(quest_vals),
        "quest_flags_total": len(quest_vals),
        "is_autosave": is_autosave,
        "coords": (round(x, 1), round(y, 1), round(z, 1)),
        "age": age,
    }


def parse_progress_inventory(progress_path: Path, tx: TxCb = _default_tx) -> dict:
    """Decode owned equipment, stones, medallions, items, bottles, upgrades, and ammo from progress.sav."""
    if not progress_path.is_file():
        return {}
    try:
        data = progress_path.read_bytes()
    except OSError:
        return {}
    if (
        len(data) < 0x175D8
        or struct.unpack_from("<I", data, 0)[0] != 0x01020304
        or struct.unpack_from("<I", data, 4)[0] != 0x002D80EB
        or struct.unpack_from("<I", data, 8)[0] != 0x175D8
    ):
        return {}

    kv: dict[int, int] = {}
    for off in range(40, 0x175D8, 8):
        key_hash, val = struct.unpack_from("<Ii", data, off)
        if key_hash:
            kv[key_hash] = val

    def has(key_hash: int) -> bool:
        return kv.get(key_hash, 0) > 0

    swords = [
        label
        for key_hash, label in (
            (0xEEB495B9, tx("Espada Kokiri", "Kokiri Sword")),
            (0xF1C45294, tx("Espada Maestra", "Master Sword")),
            (0xB0B3E399, tx("Espada Biggoron", "Biggoron Sword")),
            (0x396A5C02, tx("Daga Gigante", "Giant's Knife")),
            (0x8D02F5EA, tx("Daga Gigante Rota", "Broken Giant's Knife")),
        )
        if has(key_hash)
    ]
    shields = [
        label
        for key_hash, label in (
            (0x7CA64F23, tx("Escudo Deku", "Deku Shield")),
            (0x08BEFD3A, tx("Escudo Hyliano", "Hylian Shield")),
            (0xF58E0E2F, tx("Escudo Espejo", "Mirror Shield")),
        )
        if has(key_hash)
    ]
    tunics = [
        label
        for key_hash, label in (
            (0x84BA0D24, tx("Túnica Kokiri", "Kokiri Tunic")),
            (0x6F631388, tx("Ropa del Héroe", "Hero's Clothes")),
            (0x21ECBD19, tx("Túnica Goron", "Goron Tunic")),
            (0xB816AF94, tx("Túnica Zora", "Zora Tunic")),
        )
        if has(key_hash)
    ]
    boots = [
        label
        for key_hash, label in (
            (0x2BAD189A, tx("Botas de Hierro", "Iron Boots")),
            (0xC9220366, tx("Botas Flotadoras", "Hover Boots")),
        )
        if has(key_hash)
    ]
    stones = [
        label
        for key_hash, label in (
            (0xCBD1E58C, tx("Esmeralda Kokiri", "Kokiri Emerald")),
            (0x7D69AD47, tx("Rubí Goron", "Goron Ruby")),
            (0xB8E3BF45, tx("Zafiro Zora", "Zora Sapphire")),
        )
        if has(key_hash)
    ]
    medallions = [
        label
        for key_hash, label in (
            (0x235C7D9A, tx("Luz", "Light")),
            (0x692D57CB, tx("Bosque", "Forest")),
            (0x5CE254A6, tx("Fuego", "Fire")),
            (0x0151A68F, tx("Agua", "Water")),
            (0x204D2063, tx("Sombra", "Shadow")),
            (0x0C7A5FD0, tx("Espíritu", "Spirit")),
        )
        if has(key_hash)
    ]
    items = [
        label
        for key_hash, label in (
            (0xB7DF60F1, tx("Ocarina de las Hadas", "Fairy Ocarina")),
            (0x54E2A3D1, tx("Ocarina del Tiempo", "Ocarina of Time")),
            (0x80D34CE9, tx("Tirachinas", "Slingshot")),
            (0xA1D76D31, tx("Bumerán", "Boomerang")),
            (0x938D56BF, tx("Arco de las Hadas", "Fairy Bow")),
            (0x8573D2CD, "Hookshot"),
            (0x8499EA34, "Longshot"),
            (0x1AAFDB66, tx("Martillo Megatón", "Megaton Hammer")),
            (0x49D1C374, tx("Lupa de la Verdad", "Lens of Truth")),
            (0x5E529AB9, tx("Flecha de Fuego", "Fire Arrow")),
            (0x40735A8D, tx("Flecha de Hielo", "Ice Arrow")),
            (0xBFB285C8, tx("Flecha de Luz", "Light Arrow")),
            (0xB796C16D, tx("Fuego de Din", "Din's Fire")),
            (0x47F2CA87, tx("Viento de Farore", "Farore's Wind")),
            (0xF0828CD0, tx("Amor de Nayru", "Nayru's Love")),
        )
        if has(key_hash)
    ]
    upgrades = [
        label
        for key_hash, label in (
            (0xD1317941, tx("Brazalete Goron", "Goron Bracelet")),
            (0x0012B8C0, tx("Guanteletes de Plata", "Silver Gauntlets")),
            (0x40AE1183, tx("Guanteletes de Oro", "Golden Gauntlets")),
            (0x1240044B, tx("Escama de Plata", "Silver Scale")),
            (0x4AEB140A, tx("Escama de Oro", "Golden Scale")),
            (0xAFA4BB52, tx("Bolsa Gigante (1000)", "Giant's Wallet (1000)")),
            (0x2D2C874B, tx("Bolsa de Adulto (500)", "Adult's Wallet (500)")),
            (0x1D74617E, tx("Bolsa Kokiri (200)", "Kokiri Wallet (200)")),
            (0xF3B14CE2, tx("Piedra de la Agonía", "Stone of Agony")),
            (0xFEB4D56B, tx("Pase Gerudo", "Gerudo Pass")),
            (0x9A826FAB, tx("Doble Defensa", "Double Defense")),
            (0x5F043856, tx("Doble Magia", "Double Magic")),
        )
        if has(key_hash)
    ]

    bottle_contents_map = {
        0xBE69DE49: tx("Vacía", "Empty"),
        0xEABA6067: tx("Poción roja", "Red potion"),
        0x049D37C1: tx("Poción verde", "Green potion"),
        0xF383D6E5: tx("Poción azul", "Blue potion"),
        0x6F49E357: tx("Hada", "Fairy"),
        0x1E834EF8: tx("Pez", "Fish"),
        0x73356827: tx("Leche", "Milk"),
        0xEEF6E4B0: tx("Media leche", "Half milk"),
        0x1C293517: tx("Fuego azul", "Blue fire"),
        0x74D62ECB: tx("Bicho", "Bug"),
        0x0F24E808: tx("Carta", "Letter"),
        0x02084F9E: "Poe",
        0xCDC21471: tx("Gran Poe", "Big Poe"),
    }
    bottles: list[str] = []
    for stock_h, content_h in (
        (0xD53CE3A7, 0x7D48DF76),
        (0xFCA29A04, 0x1EDD164A),
        (0x893216A1, 0xB80C70A8),
        (0x5324F9D3, 0xE4C1B1FC),
        (0xC92B16BE, 0x365E1953),
    ):
        if has(stock_h):
            content_u32 = kv.get(content_h, 0xBE69DE49) & 0xFFFFFFFF
            bottles.append(bottle_contents_map.get(content_u32, tx("Objeto especial", "Special item")))

    ammo = {
        "sticks": max(0, kv.get(0xB9494411, 0)),
        "nuts": max(0, kv.get(0xF30D9F54, 0)),
        "bombs": max(0, kv.get(0xDB1BCD4F, 0)),
        "arrows": max(0, kv.get(0x518EC74B, 0)),
        "seeds": max(0, kv.get(0x5FADF7FC, 0)),
        "bombchus": max(0, kv.get(0xDF7C517A, 0)),
        "beans": max(0, kv.get(0xB003124D, 0)),
        "heart_pieces": max(0, kv.get(0x51EC97B3, 0)),
        "skulltulas": max(0, kv.get(0x04735978, 0)),
        "rupees": max(0, kv.get(0xA77921D7, 0)),
    }

    return {
        "swords": swords,
        "shields": shields,
        "tunics": tunics,
        "boots": boots,
        "stones": stones,
        "medallions": medallions,
        "items": items,
        "upgrades": upgrades,
        "bottles": bottles,
        "ammo": ammo,
    }


def inspect_slot(slot_dir: Path, tx: TxCb = _default_tx) -> dict:
    """Return real metadata, thumbnail bytes, scene, decoded stats, and inventory for a save slot."""
    slot = Path(slot_dir)
    files = [p for p in slot.rglob("*") if p.is_file()]
    size_bytes = sum(p.stat().st_size for p in files)
    mtimes = [p.stat().st_mtime for p in files]
    mtime_str = datetime.fromtimestamp(max(mtimes)).strftime("%Y-%m-%d %H:%M") if mtimes else "—"
    caption = slot / "caption.sav"
    progress = slot / "progress.sav"
    raw_scene = read_scene(caption)
    progress_size = progress.stat().st_size if progress.is_file() else 0
    caption_size = caption.stat().st_size if caption.is_file() else 0
    progress_hash = "—"
    if progress.is_file():
        try:
            progress_hash = hashlib.blake2b(progress.read_bytes(), digest_size=8).hexdigest().upper()
        except OSError:
            progress_hash = "—"

    return {
        "path": slot,
        "name": slot.name,
        "title": slot.name.replace("_", " ").upper(),
        "files_count": len(files),
        "size_bytes": size_bytes,
        "size_kb": size_bytes / 1024.0,
        "mtime_str": mtime_str,
        "raw_scene": raw_scene,
        "scene_display": scene_label(raw_scene, tx),
        "jpeg_bytes": extract_jpeg_bytes(caption),
        "progress_size": progress_size,
        "caption_size": caption_size,
        "progress_hash": progress_hash,
        "stats": parse_caption_stats(caption),
        "inventory": parse_progress_inventory(progress, tx),
    }


def make_backup_slot(src: Path, backup_dir: Path) -> Path:
    dest = Path(backup_dir) / datetime.now().strftime("%Y%m%d-%H%M%S-%f") / "active" / Path(src).name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest)
    return dest


def export_slot_files(
    src: Path,
    target: Path,
    *,
    progress_cb: ProgressCb = None,
    tx: TxCb = _default_tx,
) -> Path:
    _report(progress_cb, 0.3, tx(f"Exportando {src.name}…", f"Exporting {src.name}…"))
    shutil.copytree(src, target)
    _report(progress_cb, 1.0, tx("Exportación completa", "Export complete"))
    return target


def activate_profile_files(
    port: dict | None,
    active_root: Path,
    profile_paths: dict[str, Path],
    active_name: str,
    target_name: str,
    backup_dir: Path,
    *,
    progress_cb: ProgressCb = None,
    tx: TxCb = _default_tx,
) -> Path:
    """Safely swap active save files to target_name, backing up live and previous profiles."""
    target = profile_paths[target_name]
    is_nx2navi = bool(port and port.get("id") == "nx2navi")
    effective_active = nx2navi_effective_active_dir(port, active_root) if is_nx2navi else active_root
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = Path(backup_dir) / stamp / "profile-switch"
    backup.mkdir(parents=True, exist_ok=True)
    active_items = profile_items(effective_active)
    root_items = profile_items(active_root)
    target_items = profile_items(target)

    try:
        _report(progress_cb, 0.15, tx("Respaldando partidas actuales…", "Backing up current saves…"))
        live_backup = backup / "active-before"
        target_backup = backup / f"{target_name}-before"
        live_backup.mkdir()
        target_backup.mkdir()
        for item in active_items:
            dst = live_backup / item.name
            shutil.copytree(item, dst) if item.is_dir() else shutil.copy2(item, dst)
        if effective_active != active_root and root_items:
            account_root_backup = backup / "account-root-before"
            account_root_backup.mkdir()
            for item in root_items:
                dst = account_root_backup / item.name
                shutil.copytree(item, dst) if item.is_dir() else shutil.copy2(item, dst)
        for item in target_items:
            dst = target_backup / item.name
            shutil.copytree(item, dst) if item.is_dir() else shutil.copy2(item, dst)

        other_matches = [
            prof_name for prof_name, prof_dir in profile_paths.items()
            if prof_name != active_name and same_save_payload(effective_active, prof_dir)
        ] if active_items else []

        if active_name and active_name != target_name and active_name in profile_paths and active_items and not other_matches:
            _report(progress_cb, 0.4, tx(
                f"Guardando progreso actual en «{active_name}»…",
                f"Saving current progress back to '{active_name}'…",
            ))
            old_profile = profile_paths[active_name]
            old_profile_backup = backup / "previous-profile-before"
            old_profile_backup.mkdir()
            for item in profile_items(old_profile):
                dst = old_profile_backup / item.name
                shutil.copytree(item, dst) if item.is_dir() else shutil.copy2(item, dst)
            for item in profile_items(old_profile):
                item.unlink() if item.is_file() else rmtree_force(item)
            for item in active_items:
                dst = old_profile / item.name
                shutil.copytree(item, dst) if item.is_dir() else shutil.copy2(item, dst)

        _report(progress_cb, 0.65, tx(
            f"Copiando «{target_name}» a la raíz activa…",
            f"Copying '{target_name}' into active root…",
        ))
        for item in profile_items(active_root):
            item.unlink() if item.is_file() else rmtree_force(item)
        if is_nx2navi:
            nx2navi_settle_and_clean_save_tx(port, backup_dir=backup)
        for item in target_backup.iterdir():
            dst = active_root / item.name
            shutil.copytree(item, dst) if item.is_dir() else shutil.copy2(item, dst)

        write_active_marker(active_root, target_name)
        _report(progress_cb, 0.95, tx(f"Perfil «{target_name}» activado", f"Profile '{target_name}' activated"))
        return backup
    except OSError as exc:
        try:
            for item in profile_items(active_root):
                item.unlink() if item.is_file() else rmtree_force(item)
            restore_dir = backup / "account-root-before"
            if not restore_dir.exists():
                restore_dir = backup / "active-before"
            if restore_dir.exists():
                for item in restore_dir.iterdir():
                    dst = active_root / item.name
                    shutil.copytree(item, dst) if item.is_dir() else shutil.copy2(item, dst)
        except OSError:
            pass
        raise RuntimeError(tx(
            f"Hubo un error. Hay copias previas en:\n{backup}\n\nDetalle: {exc}",
            f"An error occurred. Previous copies are at:\n{backup}\n\nDetails: {exc}",
        )) from exc


def save_active_as_profile_files(
    port: dict | None,
    active_root: Path,
    name: str,
    backup_dir: Path,
    *,
    progress_cb: ProgressCb = None,
    tx: TxCb = _default_tx,
) -> Path:
    effective_active = nx2navi_effective_active_dir(port, active_root) if (port and port.get("id") == "nx2navi") else active_root
    items = profile_items(effective_active)
    target = active_root / name
    backup = Path(backup_dir) / datetime.now().strftime("%Y%m%d-%H%M%S-%f") / "register-profile"
    try:
        _report(progress_cb, 0.25, tx(f"Respaldando «{name}»…", f"Backing up '{name}'…"))
        if target.exists():
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copytree(target, backup / name)
            rmtree_force(target)
        _report(progress_cb, 0.65, tx(f"Copiando partidas activas a «{name}»…", f"Copying active saves to '{name}'…"))
        target.mkdir()
        for item in items:
            dst = target / item.name
            shutil.copytree(item, dst) if item.is_dir() else shutil.copy2(item, dst)
        write_active_marker(active_root, name)
        _report(progress_cb, 1.0, tx(f"Perfil «{name}» guardado", f"Profile '{name}' saved"))
        return backup
    except OSError:
        if backup.exists() and (backup / name).exists():
            rmtree_force(target)
            shutil.copytree(backup / name, target)
        else:
            rmtree_force(target)
        raise


def import_slot_files(
    port: dict | None,
    active_root: Path | None,
    target: Path,
    source: Path,
    backup_dir: Path,
    *,
    active_profile_name: str = "",
    profile_paths: dict[str, Path] | None = None,
    progress_cb: ProgressCb = None,
    tx: TxCb = _default_tx,
) -> tuple[Path, bool]:
    """Restore an exported slot. Also keeps active profile folder synced when importing to live root."""
    actual_target = Path(target)
    _report(progress_cb, 0.2, tx(f"Respaldando {actual_target.name}…", f"Backing up {actual_target.name}…"))
    if (
        port
        and port.get("id") == "nx2navi"
        and active_root
        and actual_target.parent != active_root
        and actual_target.parent.parent.name == "save-tx"
    ):
        actual_target = active_root / target.name

    backup = make_backup_slot(actual_target, backup_dir) if actual_target.exists() else make_backup_slot(target, backup_dir)
    staged = actual_target.with_name(actual_target.name + ".importing")
    synced_profile = False

    try:
        _report(progress_cb, 0.55, tx("Copiando slot restaurado…", "Copying restored slot…"))
        if staged.exists():
            rmtree_force(staged)
        shutil.copytree(source, staged)
        if actual_target.exists():
            rmtree_force(actual_target)
        staged.rename(actual_target)

        if port and port.get("id") == "nx2navi" and active_root and actual_target.parent == active_root:
            _report(progress_cb, 0.75, tx("Limpiando diario save-tx de NX2NAVI…", "Settling NX2NAVI save-tx journal…"))
            nx2navi_settle_and_clean_save_tx(port, backup_dir=backup.parent.parent)

        # Audit fix #4: keep identified active profile folder synchronized when restoring live slot.
        if (
            active_root
            and actual_target.parent == active_root
            and active_profile_name
            and profile_paths
            and active_profile_name in profile_paths
        ):
            profile_slot = profile_paths[active_profile_name] / actual_target.name
            if profile_slot != actual_target:
                _report(progress_cb, 0.9, tx(
                    f"Sincronizando copia del perfil «{active_profile_name}»…",
                    f"Syncing profile '{active_profile_name}' copy…",
                ))
                if profile_slot.exists():
                    prof_backup = backup.parent.parent / "profile-before" / profile_slot.name
                    prof_backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(profile_slot, prof_backup)
                    rmtree_force(profile_slot)
                shutil.copytree(actual_target, profile_slot)
                synced_profile = True

        _report(progress_cb, 1.0, tx("Restauración completa", "Restore complete"))
        return backup, synced_profile
    except OSError:
        rmtree_force(staged)
        if backup.exists() and not actual_target.exists():
            shutil.copytree(backup, actual_target)
        raise


def import_external_save_as_profile(
    active_root: Path,
    source_dir: Path,
    profile_name: str,
    backup_dir: Path,
    *,
    progress_cb: ProgressCb = None,
    tx: TxCb = _default_tx,
) -> tuple[Path, int]:
    """Import an emulator save folder or standalone slot folder into active_root / profile_name."""
    source = Path(source_dir)
    if not source.is_dir():
        raise FileNotFoundError(source)

    resolved_root: Path | None = None
    single_slot = False
    if contains_slot_folders(source):
        resolved_root = source
    elif (source / "progress.sav").is_file() and (source / "caption.sav").is_file():
        single_slot = True
        resolved_root = source
    else:
        for child in sorted(source.iterdir(), key=lambda p: p.name.casefold()):
            if not child.is_dir():
                continue
            if contains_slot_folders(child):
                resolved_root = child
                break
            for grandchild in sorted(child.iterdir(), key=lambda p: p.name.casefold()):
                if grandchild.is_dir() and contains_slot_folders(grandchild):
                    resolved_root = grandchild
                    break
            if resolved_root is not None:
                break

    if resolved_root is None:
        raise ValueError(tx(
            "No se encontraron carpetas slot_00..slot_05 ni archivos progress.sav + caption.sav en la carpeta elegida.",
            "No slot_00..slot_05 folders or progress.sav + caption.sav files were found in the selected folder.",
        ))

    target = Path(active_root) / profile_name
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = Path(backup_dir) / stamp / "import-profile"
    if target.exists():
        _report(progress_cb, 0.25, tx(f"Respaldando «{profile_name}»…", f"Backing up '{profile_name}'…"))
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copytree(target, backup / profile_name)
        rmtree_force(target)

    _report(progress_cb, 0.55, tx(f"Importando save en «{profile_name}»…", f"Importing save into '{profile_name}'…"))
    target.mkdir(parents=True, exist_ok=True)
    imported_slots = 0
    if single_slot:
        slot0 = target / "slot_00"
        slot0.mkdir(parents=True, exist_ok=True)
        for fname in ("progress.sav", "caption.sav"):
            src_file = resolved_root / fname
            if src_file.is_file():
                shutil.copy2(src_file, slot0 / fname)
        imported_slots = 1
    else:
        for item in profile_items(resolved_root):
            dst = target / item.name
            if item.is_dir():
                shutil.copytree(item, dst)
                if item.name.startswith("slot_"):
                    imported_slots += 1
            else:
                shutil.copy2(item, dst)

    _report(progress_cb, 1.0, tx(f"Perfil «{profile_name}» importado", f"Imported profile '{profile_name}'"))
    return target, imported_slots
