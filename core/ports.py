"""Port discovery, resolution, and save-account selection services."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from port_adapters import detect_port


def port_display_label(port: dict | None, unidentified_text: str = "Port no identificado") -> str:
    if not port:
        return unidentified_text
    version = port.get("version", "Detected")
    return f"{port['name']}  ·  {version}" if version and version != "Detected" else port["name"]


def _norm_root(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def discover_known_ports(settings: dict, default_root: Path | None = None) -> list[dict]:
    """Find configured Hookshot, Longshot, and NX2NAVI installations."""
    candidates: list[Path] = []
    raw_game_path = str(settings.get("game_path") or "").strip()
    if raw_game_path:
        candidates.append(Path(raw_game_path).expanduser())
    for raw in settings.get("known_ports", []):
        raw_str = str(raw).strip()
        if raw_str:
            candidates.append(Path(raw_str).expanduser())
    if default_root is not None:
        candidates.append(default_root)

    discovered: dict[str, dict] = {}
    for candidate in candidates:
        try:
            if not candidate.is_dir():
                continue
            port = detect_port(candidate)
        except OSError:
            continue
        if not port:
            continue
        key = _norm_root(port["root"])
        if key not in discovered:
            discovered[key] = port

    order = {"hookshot": 0, "longshot": 1, "nx2navi": 2}
    return sorted(
        discovered.values(),
        key=lambda item: (order.get(item["id"], 99), str(item["root"]).casefold()),
    )


def list_save_accounts(port: dict | None, contains_slot_folders_fn: Callable[[Path], bool]) -> list[Path]:
    """Return candidate save account directories inside the port's saves_dir."""
    if not port:
        return []
    save_root = port.get("saves_dir")
    if not save_root or not Path(save_root).is_dir():
        return []
    try:
        candidates = sorted((p for p in Path(save_root).iterdir() if p.is_dir()), key=lambda p: p.name.casefold())
    except OSError:
        return []

    matched = [
        p for p in candidates
        if contains_slot_folders_fn(p)
        or any(q.is_dir() and contains_slot_folders_fn(q) for q in _safe_iterdir(p))
    ]
    if matched:
        return matched
    return candidates if port.get("id") == "nx2navi" else []


def select_save_account(
    port: dict | None,
    settings: dict,
    contains_slot_folders_fn: Callable[[Path], bool],
) -> tuple[Path | None, list[Path]]:
    """Select the active account directory honoring explicit user preference."""
    accounts = list_save_accounts(port, contains_slot_folders_fn)
    if not accounts or not port:
        return None, accounts
    chosen_name = str(settings.get("selected_accounts", {}).get(port["id"], "")).strip()
    if chosen_name:
        for account in accounts:
            if account.name == chosen_name:
                return account, accounts
    return accounts[0], accounts


def _safe_iterdir(folder: Path) -> list[Path]:
    try:
        return list(folder.iterdir())
    except OSError:
        return []
