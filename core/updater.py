"""GitHub Releases version check and self-update staging for Ocarina Remake Manager."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
from typing import Any, Callable
import urllib.error
import urllib.request

APP_VERSION = "1.1.0"
GITHUB_REPO = "arsdaemonia-design/Ocarina-Remake-Manager"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"


def parse_version_tuple(version_str: str) -> tuple[int, ...]:
    """Extract numeric version components from a tag or version string."""
    clean = str(version_str or "").strip().lstrip("vV")
    nums = [int(m) for m in re.findall(r"\d+", clean)]
    return tuple(nums) if nums else (0,)


def is_newer_version(latest_tag: str, current_version: str = APP_VERSION) -> bool:
    """Return True when latest_tag represents a strictly newer version."""
    latest = parse_version_tuple(latest_tag)
    current = parse_version_tuple(current_version)
    width = max(len(latest), len(current))
    latest_padded = latest + (0,) * (width - len(latest))
    current_padded = current + (0,) * (width - len(current))
    return latest_padded > current_padded


def select_platform_asset(assets: list[dict[str, Any]], platform: str = sys.platform) -> dict[str, Any] | None:
    """Select the matching release asset dict for the current operating system."""
    valid_assets = [a for a in (assets or []) if isinstance(a, dict) and a.get("name") and a.get("browser_download_url")]
    if not valid_assets:
        return None

    plat = str(platform or "").casefold()
    if plat.startswith("win"):
        for asset in valid_assets:
            if str(asset["name"]).casefold().endswith(".exe"):
                return asset
        return None

    if plat.startswith("linux"):
        for asset in valid_assets:
            name_cf = str(asset["name"]).casefold()
            if "linux" in name_cf and name_cf.endswith(".tar.gz"):
                return asset
        for asset in valid_assets:
            if "linux" in str(asset["name"]).casefold():
                return asset
        return None

    return None


def _github_get_json(url: str, current_version: str, timeout: float) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"OcarinaRemakeManager/{current_version}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_github_update(
    repo: str = GITHUB_REPO,
    current_version: str = APP_VERSION,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Query GitHub Releases API and return version/asset metadata."""
    releases_url = f"https://github.com/{repo}/releases"
    latest_api = f"https://api.github.com/repos/{repo}/releases/latest"
    list_api = f"https://api.github.com/repos/{repo}/releases?per_page=1"

    release_data: dict[str, Any] | None = None
    try:
        payload = _github_get_json(latest_api, current_version, timeout)
        if isinstance(payload, dict) and payload.get("tag_name"):
            release_data = payload
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise

    if release_data is None:
        payload_list = _github_get_json(list_api, current_version, timeout)
        if isinstance(payload_list, list) and payload_list and isinstance(payload_list[0], dict):
            release_data = payload_list[0]

    if not release_data:
        return {
            "current_version": current_version,
            "latest_version": current_version,
            "update_available": False,
            "release_name": "",
            "body": "",
            "html_url": releases_url,
            "asset_name": "",
            "download_url": "",
            "asset_size": 0,
            "no_releases": True,
        }

    tag_name = str(release_data.get("tag_name") or "").strip()
    latest_display = tag_name.lstrip("vV") or current_version
    asset = select_platform_asset(release_data.get("assets") or [])
    return {
        "current_version": current_version,
        "latest_version": tag_name or latest_display,
        "update_available": bool(tag_name and is_newer_version(tag_name, current_version)),
        "release_name": str(release_data.get("name") or tag_name or "").strip(),
        "body": str(release_data.get("body") or "").strip(),
        "html_url": str(release_data.get("html_url") or releases_url).strip(),
        "asset_name": str(asset.get("name") or "") if asset else "",
        "download_url": str(asset.get("browser_download_url") or "") if asset else "",
        "asset_size": int(asset.get("size") or 0) if asset else 0,
        "no_releases": False,
    }


def _extract_linux_binary(archive_path: Path, dest_path: Path) -> Path:
    """Safely extract the Linux executable from a .tar.gz release archive."""
    with tarfile.open(archive_path, "r:gz") as tf:
        file_members = [m for m in tf.getmembers() if m.isfile()]
        if not file_members:
            raise RuntimeError("El archivo de actualización no contiene ningún ejecutable.")
        chosen = None
        for member in file_members:
            if Path(member.name).name == "OcarinaRemakeManager-Linux-x64":
                chosen = member
                break
        if chosen is None:
            for member in file_members:
                if "ocarinaremakemanager" in Path(member.name).name.casefold():
                    chosen = member
                    break
        if chosen is None:
            chosen = max(file_members, key=lambda m: m.size)

        extracted = tf.extractfile(chosen)
        if extracted is None:
            raise RuntimeError(f"No se pudo extraer {chosen.name} del paquete.")
        with extracted, open(dest_path, "wb") as out:
            shutil.copyfileobj(extracted, out)
    return dest_path


def download_and_stage_update(
    download_url: str,
    asset_name: str,
    manager_dir: Path,
    progress_cb: Callable[[float | None, str], None] | None = None,
    is_frozen: bool | None = None,
    current_exe: Path | None = None,
) -> dict[str, Any]:
    """Download a release asset and prepare it for installation/restart."""
    manager_dir = Path(manager_dir)
    updates_dir = manager_dir / "updates"
    updates_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(asset_name or "OcarinaRemakeManager-update").name
    part_path = updates_dir / f"{safe_name}.part"
    saved_path = updates_dir / safe_name

    if progress_cb:
        progress_cb(0.0, f"Descargando {safe_name}…")

    req = urllib.request.Request(
        download_url,
        headers={"User-Agent": f"OcarinaRemakeManager/{APP_VERSION}"},
    )
    with urllib.request.urlopen(req, timeout=60.0) as resp:
        total_raw = resp.headers.get("Content-Length")
        total_bytes = int(total_raw) if total_raw and total_raw.isdigit() else 0
        downloaded = 0
        with open(part_path, "wb") as out:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)
                if progress_cb:
                    frac = (downloaded / total_bytes) if total_bytes > 0 else None
                    mb_done = downloaded / (1024 * 1024)
                    if total_bytes > 0:
                        mb_total = total_bytes / (1024 * 1024)
                        progress_cb(frac, f"Descargando {safe_name} ({mb_done:.1f} / {mb_total:.1f} MB)…")
                    else:
                        progress_cb(None, f"Descargando {safe_name} ({mb_done:.1f} MB)…")

    part_path.replace(saved_path)

    frozen = getattr(sys, "frozen", False) if is_frozen is None else bool(is_frozen)
    if not frozen:
        if progress_cb:
            progress_cb(1.0, f"Paquete descargado en {saved_path}")
        return {
            "mode": "downloaded_only",
            "staged_path": saved_path,
        }

    target_exe = Path(current_exe or sys.executable).resolve()
    name_cf = safe_name.casefold()

    if sys.platform.startswith("win") and name_cf.endswith(".exe"):
        staged_new = target_exe.with_name(target_exe.name + ".new")
        shutil.copy2(saved_path, staged_new)
        script_path = manager_dir / "_apply_orm_update.cmd"
        script_body = "\r\n".join([
            "@echo off",
            "setlocal",
            "ping 127.0.0.1 -n 3 > nul",
            "set RETRIES=0",
            ":retry_move",
            f'move /y "{staged_new}" "{target_exe}" > nul 2>&1',
            "if errorlevel 1 (",
            "  set /a RETRIES+=1",
            "  if %RETRIES% lss 5 (",
            "    ping 127.0.0.1 -n 2 > nul",
            "    goto retry_move",
            "  )",
            "  exit /b 1",
            ")",
            f'start "" "{target_exe}"',
            'del "%~f0"',
            "",
        ])
        script_path.write_text(script_body, encoding="utf-8")
        if progress_cb:
            progress_cb(1.0, f"Actualización lista: {staged_new.name}")
        return {
            "mode": "self_replace_win",
            "target_exe": target_exe,
            "script_path": script_path,
            "staged_path": staged_new,
        }

    if name_cf.endswith(".tar.gz"):
        staged_new = target_exe.with_name(target_exe.name + ".new")
        _extract_linux_binary(saved_path, staged_new)
        os.chmod(staged_new, 0o755)
        os.replace(staged_new, target_exe)
        if progress_cb:
            progress_cb(1.0, f"Actualización instalada en {target_exe}")
        return {
            "mode": "replaced_posix",
            "target_exe": target_exe,
            "staged_path": target_exe,
        }

    staged_new = target_exe.with_name(target_exe.name + ".new")
    shutil.copy2(saved_path, staged_new)
    if not sys.platform.startswith("win"):
        os.chmod(staged_new, 0o755)
    os.replace(staged_new, target_exe)
    return {
        "mode": "replaced_posix",
        "target_exe": target_exe,
        "staged_path": target_exe,
    }


def launch_staged_update(result: dict[str, Any]) -> bool:
    """Trigger the staged updater script or relaunch the replaced binary."""
    mode = str(result.get("mode") or "")
    if mode == "self_replace_win":
        script_path = result.get("script_path")
        if not script_path:
            return False
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(["cmd.exe", "/c", str(script_path)], creationflags=flags)
        return True

    if mode == "replaced_posix":
        target_exe = result.get("target_exe")
        if not target_exe:
            return False
        subprocess.Popen([str(target_exe)], start_new_session=True)
        return True

    return False
