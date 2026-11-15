"""Structured listing and cleanup for Ocarina Remake Manager backups."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

from core.saves import rmtree_force

_STAMP_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})(?:-\d+)?$")


def _format_stamp(name: str, fallback_mtime: float) -> tuple[str, float]:
    match = _STAMP_RE.match(name)
    if match:
        y, m, d, hh, mm, ss = match.groups()
        try:
            dt = datetime(int(y), int(m), int(d), int(hh), int(mm), int(ss))
            return dt.strftime("%Y-%m-%d %H:%M:%S"), dt.timestamp()
        except ValueError:
            pass
    return datetime.fromtimestamp(fallback_mtime).strftime("%Y-%m-%d %H:%M:%S"), fallback_mtime


def _folder_stats(folder: Path) -> tuple[int, float]:
    files = 0
    total_bytes = 0
    try:
        for p in folder.rglob("*"):
            if p.is_file():
                files += 1
                try:
                    total_bytes += p.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return files, total_bytes / 1024.0


def list_backups(backup_dir: Path) -> list[dict]:
    """Return sorted backup records (newest first) from backups/."""
    root = Path(backup_dir)
    if not root.is_dir():
        return []
    entries: list[dict] = []
    try:
        children = list(root.iterdir())
    except OSError:
        return []

    for child in children:
        if not child.is_dir():
            continue
        if child.name in ("nx2navi-config", "removed-mods"):
            try:
                subentries = list(child.iterdir())
            except OSError:
                continue
            for sub in subentries:
                if not sub.exists():
                    continue
                files_count, size_kb = _folder_stats(sub)
                mtime = sub.stat().st_mtime
                ts_label, sort_key = _format_stamp(sub.name, mtime)
                entries.append(
                    {
                        "path": sub,
                        "name": f"{child.name}/{sub.name}",
                        "category": "ini" if child.name == "nx2navi-config" else "mod",
                        "timestamp": ts_label,
                        "sort_key": sort_key,
                        "files_count": files_count,
                        "size_kb": size_kb,
                        "summary": sub.name,
                    }
                )
            continue

        try:
            subnames = sorted(p.name for p in child.iterdir() if p.is_dir())
        except OSError:
            subnames = []
        if "profile-switch" in subnames:
            category = "profile-switch"
        elif "register-profile" in subnames:
            category = "register-profile"
        elif "active" in subnames:
            category = "slot"
        else:
            category = "backup"
        files_count, size_kb = _folder_stats(child)
        mtime = child.stat().st_mtime
        ts_label, sort_key = _format_stamp(child.name, mtime)
        entries.append(
            {
                "path": child,
                "name": child.name,
                "category": category,
                "timestamp": ts_label,
                "sort_key": sort_key,
                "files_count": files_count,
                "size_kb": size_kb,
                "summary": ", ".join(subnames) if subnames else child.name,
            }
        )

    entries.sort(key=lambda item: item["sort_key"], reverse=True)
    return entries


def prune_old_backups(backup_dir: Path, keep_latest: int = 15) -> int:
    """Remove older backups beyond keep_latest (returns number removed)."""
    records = list_backups(backup_dir)
    removed = 0
    for record in records[max(0, keep_latest):]:
        target = Path(record["path"])
        try:
            rmtree_force(target)
            removed += 1
        except OSError:
            pass
    return removed
