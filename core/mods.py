"""Mod library inspection, selective deployment, NX2NAVI INI control, and RomFS conflict detection."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import Callable
import urllib.error
import urllib.request
import zipfile

from core.saves import rmtree_force
from nx2navi_ini import disabled_mods, update_disabled_mods

ProgressCb = Callable[[float | None, str], None] | None
TxCb = Callable[[str, str], str]
TrCb = Callable[[str], str]

_MAX_ROMFS_FILES_PER_MOD = 5000


def _default_tx(es: str, _en: str) -> str:
    return es


def _default_tr(text: str) -> str:
    return text


def _report(progress_cb: ProgressCb, fraction: float | None, message: str = "") -> None:
    if progress_cb:
        progress_cb(fraction, message)


def inspect_mod(mod: Path | str, cache: dict | None = None) -> dict:
    mod_path = Path(mod)
    try:
        cache_key = (str(mod_path.resolve()), mod_path.stat().st_mtime_ns)
    except OSError:
        cache_key = (str(mod_path), None)
    if cache is not None and cache_key in cache:
        return dict(cache[cache_key])

    exefs = False
    romfs = False
    for _current, dirs, files in os.walk(mod_path):
        marker_dirs = {name.casefold() for name in dirs}
        if "romfs" in marker_dirs or "romfslite" in marker_dirs:
            romfs = True
        if "exefs" in marker_dirs:
            exefs = True
        if any(Path(name).suffix.casefold() in (".pchtxt", ".ips") for name in files):
            exefs = True
        dirs[:] = [name for name in dirs if name.casefold() not in ("romfs", "romfslite", "exefs")]
        if romfs and exefs:
            break
    kind = "Mixto" if romfs and exefs else "RomFS" if romfs else "ExeFS" if exefs else "Sin detectar"
    result = {"exefs": exefs, "romfs": romfs, "kind": kind}
    if cache is not None:
        cache[cache_key] = result
    return dict(result)


def list_mod_romfs_files(mod: Path | str, romfs_cache: dict | None = None) -> tuple[str, ...]:
    """Return relative lowercase POSIX paths inside romfs/ or romfslite/, cached per mod mtime."""
    mod_path = Path(mod)
    try:
        cache_key = (str(mod_path.resolve()), mod_path.stat().st_mtime_ns)
    except OSError:
        cache_key = (str(mod_path), None)
    if romfs_cache is not None and cache_key in romfs_cache:
        return romfs_cache[cache_key]

    collected: list[str] = []
    for current, dirs, files in os.walk(mod_path):
        current_path = Path(current)
        if current_path.name.casefold() in ("romfs", "romfslite"):
            base_root = current_path
            for sub_cur, _sub_dirs, sub_files in os.walk(base_root):
                sub_path = Path(sub_cur)
                for fname in sub_files:
                    rel = (sub_path / fname).relative_to(base_root).as_posix().casefold()
                    collected.append(rel)
                    if len(collected) >= _MAX_ROMFS_FILES_PER_MOD:
                        break
                if len(collected) >= _MAX_ROMFS_FILES_PER_MOD:
                    break
            dirs[:] = [d for d in dirs if d.casefold() not in ("romfs", "romfslite")]
            if len(collected) >= _MAX_ROMFS_FILES_PER_MOD:
                break
    result = tuple(sorted(set(collected)))
    if romfs_cache is not None:
        romfs_cache[cache_key] = result
    return result


def detect_mod_conflicts(
    mod_library_dir: Path,
    enabled_names: list[str] | set[str],
    *,
    inspect_cache: dict | None = None,
    romfs_cache: dict | None = None,
    ignore_rsizetable: bool = True,
) -> list[dict]:
    """Detect overlapping RomFS asset paths among currently enabled mods."""
    candidates = sorted(
        (mod_library_dir / name for name in set(enabled_names) if (mod_library_dir / name).is_dir()),
        key=lambda p: p.name.casefold(),
    )
    romfs_sets: dict[str, set[str]] = {}
    for mod_dir in candidates:
        kind = inspect_mod(mod_dir, cache=inspect_cache)
        if not kind["romfs"]:
            continue
        files = list_mod_romfs_files(mod_dir, romfs_cache=romfs_cache)
        if ignore_rsizetable:
            # ResourceSizeTable manifests are bundled by most standalone RomFS mods and are not content asset collisions.
            files = tuple(f for f in files if not f.startswith("system/resource/resourcesizetable"))
        if files:
            romfs_sets[mod_dir.name] = set(files)

    conflicts: list[dict] = []
    names = sorted(romfs_sets, key=str.casefold)
    for i, left_name in enumerate(names):
        left_files = romfs_sets[left_name]
        for right_name in names[i + 1:]:
            overlap = sorted(left_files & romfs_sets[right_name])
            if overlap:
                conflicts.append(
                    {
                        "mods": (left_name, right_name),
                        "overlap_count": len(overlap),
                        "sample_paths": overlap[:5],
                    }
                )
    return conflicts


def deployed_mod(port: dict | None, name: str) -> Path | None:
    if not port:
        return None
    folder = Path(port["mods_dir"])
    if not folder.is_dir():
        return None
    if port.get("id") == "nx2navi":
        target = folder / name
        return target if target.is_dir() else None
    for candidate in (name, "_" + name, "-" + name):
        target = folder / candidate
        if target.is_dir():
            return target
    return None


def mod_status(
    port: dict | None,
    mod: Path,
    *,
    inspect_cache: dict | None = None,
    nx_mod_log_status: dict | None = None,
) -> dict:
    kind = inspect_mod(mod, cache=inspect_cache)
    deployed = deployed_mod(port, mod.name)
    if not port:
        return {**kind, "deployed": False, "enabled": False, "incompatible": True, "state": "No compatible con este port"}
    if port.get("id") in ("hookshot", "longshot") and kind["exefs"]:
        if kind["romfs"]:
            state = "No instalado" if not deployed else "Parcial · ExeFS ignorado"
            return {
                **kind,
                "deployed": bool(deployed),
                "enabled": bool(deployed and not deployed.name.startswith(("_", "-"))),
                "incompatible": False,
                "state": state,
            }
        return {**kind, "deployed": bool(deployed), "enabled": False, "incompatible": True, "state": "No compatible · ExeFS"}

    if not deployed:
        review = port.get("id") == "nx2navi" and kind["exefs"]
        state = "No instalado · ExeFS, validar en NX2NAVI" if review else "No instalado"
        return {
            **kind,
            "deployed": False,
            "enabled": False,
            "incompatible": not (kind["romfs"] or (port.get("id") == "nx2navi" and kind["exefs"])),
            "review_required": review,
            "state": state,
        }

    if port.get("id") == "nx2navi":
        try:
            disabled = mod.name in disabled_mods(port["ini_path"])
        except OSError:
            return {**kind, "deployed": True, "enabled": False, "incompatible": True, "state": "No se pudo leer la lista de mods desactivados de NX2NAVI."}
    else:
        disabled = deployed.name.startswith(("_", "-"))

    enabled = not disabled
    if port.get("id") == "nx2navi" and kind["exefs"]:
        log_result = (nx_mod_log_status or {}).get(mod.name.casefold())
        if log_result and log_result.get("not_usable"):
            state = "Not Usable · ExeFS" if enabled else "Desactivado · ExeFS (Not Usable)"
            return {
                **kind,
                "deployed": True,
                "enabled": enabled,
                "incompatible": True,
                "known_not_usable": True,
                "review_required": False,
                "log_detail": log_result.get("detail", ""),
                "state": state,
            }
        if log_result and log_result.get("validated"):
            state = "Activo · ExeFS validado" if enabled else "Desactivado · ExeFS validado"
            return {
                **kind,
                "deployed": True,
                "enabled": enabled,
                "incompatible": False,
                "known_not_usable": False,
                "review_required": False,
                "state": state,
            }
        state = "ExeFS · verificar en NX2NAVI" if enabled else "Desactivado · ExeFS"
        return {
            **kind,
            "deployed": True,
            "enabled": enabled,
            "incompatible": False,
            "known_not_usable": False,
            "review_required": True,
            "state": state,
        }
    if kind["exefs"] and kind["romfs"]:
        state = "Parcial · ExeFS ignorado" if enabled else "Desactivado · ExeFS ignorado"
    else:
        state = "Activo" if enabled else "Desactivado"
    return {**kind, "deployed": True, "enabled": enabled, "incompatible": False, "review_required": False, "state": state}


def backup_nx2navi_ini(port: dict, backup_dir: Path) -> Path:
    ini = Path(port["ini_path"])
    if not ini.is_file():
        raise FileNotFoundError(ini)
    backup = Path(backup_dir) / "nx2navi-config" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup.mkdir(parents=True, exist_ok=True)
    dst = backup / ini.name
    shutil.copy2(ini, dst)
    return dst


def deploy_library_mod(
    port: dict,
    mod: Path,
    *,
    progress_cb: ProgressCb = None,
    tx: TxCb = _default_tx,
) -> Path:
    mods_dir = Path(port["mods_dir"])
    target = mods_dir / mod.name
    existing = deployed_mod(port, mod.name)
    if existing:
        return existing
    _report(progress_cb, None, tx(f"Desplegando «{mod.name}» al port…", f"Deploying '{mod.name}' to port…"))
    mods_dir.mkdir(parents=True, exist_ok=True)
    staging = mods_dir / (".orm-installing-" + re.sub(r"[^A-Za-z0-9_-]", "_", mod.name)[:48])
    if staging.exists():
        rmtree_force(staging)
    shutil.copytree(mod, staging)
    try:
        staging.rename(target)
    except Exception:
        rmtree_force(staging)
        raise
    return target


def set_mod_state(
    port: dict | None,
    mod: Path,
    enabled: bool,
    backup_dir: Path,
    *,
    inspect_cache: dict | None = None,
    progress_cb: ProgressCb = None,
    tx: TxCb = _default_tx,
) -> Path | None:
    if not port:
        raise RuntimeError(tx("Elige un port compatible primero.", "Select a supported port first."))
    kind = inspect_mod(mod, cache=inspect_cache)
    if port.get("id") in ("hookshot", "longshot") and kind["exefs"] and not kind["romfs"]:
        raise RuntimeError(tx(
            "Hookshot y Longshot no pueden activar un mod solo ExeFS.",
            "Hookshot and Longshot cannot enable an ExeFS-only mod.",
        ))
    deployed = deploy_library_mod(port, mod, progress_cb=progress_cb, tx=tx)
    if port.get("id") == "nx2navi":
        disabled = disabled_mods(port["ini_path"])
        if enabled:
            disabled.discard(mod.name)
        else:
            disabled.add(mod.name)
        ini_backup = backup_nx2navi_ini(port, backup_dir)
        update_disabled_mods(port["ini_path"], disabled)
        return ini_backup

    desired_name = mod.name if enabled else "_" + mod.name
    target = deployed.with_name(desired_name)
    if deployed.name != desired_name:
        if target.exists():
            raise FileExistsError(target)
        deployed.rename(target)
    return None


def apply_mod_profile_files(
    port: dict,
    mod_library_dir: Path,
    enabled_names: set[str],
    backup_dir: Path,
    *,
    inspect_cache: dict | None = None,
    progress_cb: ProgressCb = None,
    tx: TxCb = _default_tx,
) -> Path | None:
    """Audit fix #2: deploy only enabled compatible mods; avoid copying disabled/incompatible mods."""
    library_mods = sorted((m for m in Path(mod_library_dir).iterdir() if m.is_dir()), key=lambda p: p.name.casefold())
    total = max(1, len(library_mods))
    ini_backup: Path | None = None

    if port.get("id") == "nx2navi":
        for idx, mod in enumerate(library_mods, start=1):
            kind = inspect_mod(mod, cache=inspect_cache)
            if mod.name in enabled_names and (kind["romfs"] or kind["exefs"]):
                _report(progress_cb, 0.1 + 0.55 * (idx / total), tx(
                    f"Desplegando {mod.name} ({idx}/{total})…",
                    f"Deploying {mod.name} ({idx}/{total})…",
                ))
                deploy_library_mod(port, mod)

        _report(progress_cb, 0.75, tx("Actualizando nx2navi.ini…", "Updating nx2navi.ini…"))
        disabled = disabled_mods(port["ini_path"])
        managed = {m.name for m in library_mods}
        disabled.difference_update(managed)
        mods_dir = Path(port["mods_dir"])
        if mods_dir.is_dir():
            for entry in mods_dir.iterdir():
                if entry.is_dir() and entry.name in managed and entry.name not in enabled_names:
                    disabled.add(entry.name)
        ini_backup = backup_nx2navi_ini(port, backup_dir)
        update_disabled_mods(port["ini_path"], disabled)
        _report(progress_cb, 1.0, tx("Perfil de mods aplicado", "Mod profile applied"))
        return ini_backup

    # Hookshot / Longshot: deploy enabled RomFS mods, disable unneeded deployed mods, clean redundant ExeFS-only folders.
    for idx, mod in enumerate(library_mods, start=1):
        kind = inspect_mod(mod, cache=inspect_cache)
        deployed = deployed_mod(port, mod.name)
        _report(progress_cb, 0.1 + 0.85 * (idx / total), tx(
            f"Ajustando {mod.name} ({idx}/{total})…",
            f"Updating {mod.name} ({idx}/{total})…",
        ))
        if kind["exefs"] and not kind["romfs"]:
            if deployed:
                rmtree_force(deployed)
            continue
        if not kind["romfs"]:
            continue
        want_enabled = mod.name in enabled_names
        if want_enabled:
            set_mod_state(port, mod, True, backup_dir, inspect_cache=inspect_cache, tx=tx)
        elif deployed:
            set_mod_state(port, mod, False, backup_dir, inspect_cache=inspect_cache, tx=tx)

    _report(progress_cb, 1.0, tx("Perfil de mods aplicado", "Mod profile applied"))
    return ini_backup


def install_mod_archive(
    archive: str | Path,
    mod_library_dir: Path,
    *,
    overwrite: bool = False,
    backup_dir: Path | None = None,
    progress_cb: ProgressCb = None,
    tx: TxCb = _default_tx,
    tr: TrCb = _default_tr,
) -> Path:
    archive_path = Path(archive)
    with zipfile.ZipFile(archive_path) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        markers = ("romfs/", "romfslite/", "exefs/", "cheats/")
        marker_entries = []
        for name in names:
            offsets = [name.lower().find(marker) for marker in markers if marker in name.lower()]
            if offsets:
                marker_entries.append((name, min(offsets)))
        marker_entries = [(name, offset) for name, offset in marker_entries if offset >= 0]
        if not marker_entries:
            raise ValueError(tr("No se encontró una carpeta RomFS, ExeFS o cheats en el ZIP; no se importó."))
        prefix = min((name[:offset] for name, offset in marker_entries), key=len)
        selected = [name for name, _offset in marker_entries if name.startswith(prefix)]
        if not selected:
            raise ValueError(tr("No pude localizar archivos bajo romfs/."))
        seen_rel = set()
        for name in selected:
            rel = name[len(prefix):].replace("\\", "/").casefold()
            if rel in seen_rel:
                raise ValueError(tx("El ZIP contiene entradas duplicadas.", "The ZIP contains duplicate entries."))
            seen_rel.add(rel)

        total_size = sum(zf.getinfo(name).file_size for name in selected)
        if total_size > 2 * 1024 * 1024 * 1024:
            raise ValueError(tx("El ZIP supera el límite de 2 GB descomprimidos.", "The ZIP exceeds the 2 GB uncompressed size limit."))

        mod_name = archive_path.stem
        if any(ch in mod_name for ch in '<>:"/\\|?*') or mod_name.endswith((".", " ")):
            raise ValueError(tr("El nombre del archivo ZIP no se puede usar como nombre de mod."))
        dest = Path(mod_library_dir) / mod_name
        if dest.exists() and not overwrite:
            raise FileExistsError(tx(f"Ya hay un mod llamado {mod_name} en la biblioteca.", f"A mod named {mod_name} is already in the library."))

        staging = dest.with_name(dest.name + ".installing")
        if staging.exists():
            rmtree_force(staging)
        staging.mkdir(parents=True)
        try:
            total_files = max(1, len(selected))
            step = max(1, total_files // 40)
            _report(progress_cb, 0.05, tx(
                f"Extrayendo {mod_name} (0/{total_files})…",
                f"Extracting {mod_name} (0/{total_files})…",
            ))
            for index, name in enumerate(selected, start=1):
                relative = name[len(prefix):].replace("\\", "/")
                parts = PurePosixPath(relative).parts
                if not parts or any(p in ("..", "", ".") for p in parts) or (parts and ":" in parts[0]):
                    raise ValueError(tx("Ruta insegura dentro del ZIP", "Unsafe path inside ZIP"))
                target = staging.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as inp, target.open("wb") as out:
                    shutil.copyfileobj(inp, out)
                if index == total_files or index % step == 0:
                    _report(progress_cb, 0.05 + 0.9 * (index / total_files), tx(
                        f"Extrayendo {mod_name} ({index}/{total_files})…",
                        f"Extracting {mod_name} ({index}/{total_files})…",
                    ))
            if dest.exists() and overwrite:
                if backup_dir is not None:
                    bk = Path(backup_dir) / "updated-mods" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                    bk.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(dest, bk / dest.name)
                rmtree_force(dest)
            staging.rename(dest)
            _report(progress_cb, 1.0, tx(f"Mod «{mod_name}» importado", f"Imported mod '{mod_name}'"))
            return dest
        except Exception:
            rmtree_force(staging)
            raise


def parse_gamebanana_mod_id(url_or_id: str) -> int:
    raw = str(url_or_id).strip()
    if re.fullmatch(r"\d+", raw):
        return int(raw)
    match = re.search(r"gamebanana\.com/(?:mods|dl)/(\d+)", raw, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    raise ValueError("URL o ID de GameBanana no reconocido (usa gamebanana.com/mods/<id> o el ID numérico).")


def fetch_gamebanana_mod_info(url_or_id: str) -> dict:
    mod_id = parse_gamebanana_mod_id(url_or_id)
    api_url = f"https://gamebanana.com/apiv11/Mod/{mod_id}?_csvProperties=_sName,_aFiles,_tsDateUpdated"
    req = urllib.request.Request(api_url, headers={"User-Agent": "OcarinaRemakeManager/2.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"No se pudo consultar GameBanana (mod {mod_id}): {exc}") from exc

    raw_files = data.get("_aFiles") or []
    if isinstance(raw_files, dict):
        file_list = list(raw_files.values())
    else:
        file_list = list(raw_files)
    zip_files = [
        f for f in file_list
        if isinstance(f, dict) and f.get("_sDownloadUrl") and str(f.get("_sFile", "")).lower().endswith(".zip")
    ]
    return {
        "mod_id": mod_id,
        "name": str(data.get("_sName") or f"GameBanana-{mod_id}").strip(),
        "updated_ts": int(data.get("_tsDateUpdated") or 0),
        "files": zip_files or [f for f in file_list if isinstance(f, dict) and f.get("_sDownloadUrl")],
    }


def download_and_install_gamebanana_mod(
    url_or_id: str,
    mod_library_dir: Path,
    *,
    file_entry: dict | None = None,
    backup_dir: Path | None = None,
    progress_cb: ProgressCb = None,
    tx: TxCb = _default_tx,
    tr: TrCb = _default_tr,
) -> tuple[Path, dict]:
    _report(progress_cb, 0.05, tx("Consultando API de GameBanana…", "Querying GameBanana API…"))
    info = fetch_gamebanana_mod_info(url_or_id)
    chosen = file_entry
    if chosen is None:
        zip_files = [f for f in info["files"] if str(f.get("_sFile", "")).lower().endswith(".zip")]
        if not zip_files:
            raise ValueError(tx(
                "El mod en GameBanana no tiene descargas en formato .zip disponibles.",
                "This GameBanana mod has no .zip downloads available.",
            ))
        chosen = sorted(
            zip_files,
            key=lambda item: int(item.get("_tsDateAdded") or 0),
            reverse=True,
        )[0]

    dl_url = str(chosen.get("_sDownloadUrl") or "")
    if not dl_url:
        raise ValueError(tx("Falta URL de descarga en GameBanana.", "Missing GameBanana download URL."))

    raw_fname = str(chosen.get("_sFile") or f"{info['name']}.zip")
    safe_stem = re.sub(r'[<>:"/\\|?*]', "_", Path(raw_fname).stem).strip(" .") or f"gb_mod_{info['mod_id']}"
    with tempfile.TemporaryDirectory(prefix="orm_gb_") as tmpdir:
        zip_path = Path(tmpdir) / f"{safe_stem}.zip"
        req = urllib.request.Request(dl_url, headers={"User-Agent": "OcarinaRemakeManager/2.0"})
        _report(progress_cb, 0.12, tx(f"Descargando {zip_path.name}…", f"Downloading {zip_path.name}…"))
        with urllib.request.urlopen(req, timeout=60) as resp, zip_path.open("wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            downloaded = 0
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    _report(
                        progress_cb,
                        0.12 + 0.48 * min(1.0, downloaded / total),
                        tx(f"Descargando {zip_path.name}…", f"Downloading {zip_path.name}…"),
                    )

        def sub_progress(frac: float | None, msg: str) -> None:
            if frac is None:
                _report(progress_cb, None, msg)
            else:
                _report(progress_cb, 0.6 + 0.4 * frac, msg)

        dest = install_mod_archive(
            zip_path,
            mod_library_dir,
            overwrite=True,
            backup_dir=backup_dir,
            progress_cb=sub_progress,
            tx=tx,
            tr=tr,
        )

    meta = {
        "mod_id": info["mod_id"],
        "name": info["name"],
        "file_id": chosen.get("_idRow"),
        "file_name": raw_fname,
        "updated_ts": info["updated_ts"],
        "url": f"https://gamebanana.com/mods/{info['mod_id']}",
    }
    try:
        (dest / ".gamebanana.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return dest, meta


def remove_mod_files(
    port: dict | None,
    mod: Path,
    backup_dir: Path,
    settings: dict,
    *,
    progress_cb: ProgressCb = None,
    tx: TxCb = _default_tx,
) -> tuple[Path, Path | None]:
    deployed = deployed_mod(port, mod.name) if port else None
    backup = Path(backup_dir) / "removed-mods" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup.mkdir(parents=True, exist_ok=True)
    ini_backup: Path | None = None

    _report(progress_cb, 0.2, tx(f"Respaldando «{mod.name}»…", f"Backing up '{mod.name}'…"))
    (backup / "library").mkdir(parents=True, exist_ok=True)
    shutil.copytree(mod, backup / "library" / mod.name)
    if deployed and port:
        _report(progress_cb, 0.5, tx(f"Quitando «{mod.name}» del port…", f"Removing '{mod.name}' from port…"))
        (backup / "port").mkdir(parents=True, exist_ok=True)
        shutil.copytree(deployed, backup / "port" / deployed.name)
        rmtree_force(deployed)
        if port.get("id") == "nx2navi":
            disabled = disabled_mods(port["ini_path"])
            disabled.discard(mod.name)
            ini_backup = backup_nx2navi_ini(port, backup_dir)
            update_disabled_mods(port["ini_path"], disabled)

    _report(progress_cb, 0.8, tx("Borrando de la biblioteca central…", "Removing from central library…"))
    rmtree_force(mod)
    for profiles in settings.get("mod_profiles", {}).values():
        for profile, names in list(profiles.items()):
            profiles[profile] = [name for name in names if name != mod.name]
    _report(progress_cb, 1.0, tx(f"Mod «{mod.name}» desinstalado", f"Uninstalled mod '{mod.name}'"))
    return backup, ini_backup
