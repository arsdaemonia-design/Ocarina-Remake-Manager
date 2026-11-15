"""Small, file-system based adapters for supported Ocarina ports."""

from pathlib import Path
import json
import os


def _is_nx2navi_dir(path):
    return (path / "nx2navi.ini").is_file() and any(
        (path / marker).is_file()
        for marker in ("ocarina.exe", "nx2navi_xlate.exe", "nx2navi_xlate.id")
    )


def _is_direct_port_dir(path):
    return _is_nx2navi_dir(path) or (path / "hookshot.exe").is_file() or (path / "longshot.exe").is_file()


def _resolve_port_root(root):
    if _is_direct_port_dir(root):
        return root

    nx2_sub = root / "NX2navi"
    if (nx2_sub / "nx2navi.ini").is_file() and (
        _is_nx2navi_dir(nx2_sub) or (nx2_sub / "logs").is_dir() or (nx2_sub / "profile").is_dir()
    ):
        return nx2_sub.resolve()

    for builds_json in (root / "LongshotLauncher-data" / "builds.json", root / "builds.json"):
        if not builds_json.is_file():
            continue
        try:
            data = json.loads(builds_json.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        builds = data.get("builds") if isinstance(data, dict) else None
        if not isinstance(builds, list):
            continue
        ordered = sorted(
            (b for b in builds if isinstance(b, dict)),
            key=lambda b: not bool(b.get("default")),
        )
        for entry in ordered:
            candidates = []
            folder_val = str(entry.get("folder") or "").strip()
            if folder_val:
                candidates.append(Path(folder_val))
            name_val = str(entry.get("name") or "").strip()
            if name_val:
                candidates.append(builds_json.parent / "builds" / name_val)
            for candidate in candidates:
                try:
                    if candidate.is_dir() and (candidate / "longshot.exe").is_file():
                        return candidate.resolve()
                except OSError:
                    continue

    for builds_dir in (root / "LongshotLauncher-data" / "builds", root / "builds"):
        if not builds_dir.is_dir():
            continue
        try:
            subdirs = sorted(
                (d for d in builds_dir.iterdir() if d.is_dir() and (d / "longshot.exe").is_file()),
                key=lambda d: d.stat().st_mtime,
                reverse=True,
            )
            if subdirs:
                return subdirs[0].resolve()
        except OSError:
            continue

    try:
        for child in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
            if child.is_dir() and _is_direct_port_dir(child):
                return child.resolve()
    except OSError:
        pass

    return root


def _read_version_file(file_path, default="Detected"):
    if file_path.is_file():
        try:
            for line in file_path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.lower().startswith("version="):
                    return line.split("=", 1)[1].strip() or default
        except OSError:
            pass
    return default


def _resolve_longshot_user_dir(selected_root, build_root):
    """Return the shared Longshot user directory when managed by LongshotLauncher."""
    candidates = [
        selected_root / "LongshotLauncher-data",
        selected_root,
        build_root.parent.parent if build_root.parent.name.casefold() == "builds" else None,
    ]
    seen = set()
    for base in candidates:
        if base is None:
            continue
        try:
            resolved = base.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        is_launcher_data = resolved.name.casefold() == "longshotlauncher-data" or (
            (resolved / "builds.json").is_file() and (resolved / "user").is_dir()
        )
        if not is_launcher_data:
            continue
        user_dir = resolved / "user"
        if (user_dir / "save").is_dir():
            return user_dir
        if user_dir.is_dir() and not (build_root / "user" / "save").is_dir():
            return user_dir

    appdata_raw = os.environ.get("APPDATA")
    appdata = Path(appdata_raw) if appdata_raw else (Path.home() / "AppData" / "Roaming")
    installed_user = appdata / "Longshot"
    if (installed_user / "save").is_dir():
        return installed_user

    return None


def detect_port(root):
    selected_root = Path(root).expanduser().resolve()
    if not selected_root.is_dir():
        return None
    root = _resolve_port_root(selected_root)

    if _is_nx2navi_dir(root):
        local_data = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        local_app = local_data / "Programs" / "NX2navi"
        game_exe = root / "ocarina.exe"
        launcher_exe = game_exe
        launcher_args = []
        version = "Detected"
        try:
            launcher_settings = json.loads((local_app / "data" / "launcher.json").read_text(encoding="utf-8"))
            configured_game = Path(launcher_settings.get("game_dir", "")).resolve()
            current_version = (local_app / "app" / "current.txt").read_text(encoding="utf-8-sig").strip()
            launcher_python = local_app / "python" / "pythonw.exe"
            launcher_start = local_app / "app" / current_version / "launcher" / "start.pyw"
            same_game = os.path.normcase(os.path.normpath(str(configured_game))) == os.path.normcase(os.path.normpath(str(root)))
            if same_game and launcher_python.is_file() and launcher_start.is_file():
                launcher_exe = launcher_python
                launcher_args = [str(launcher_start), "--play"]
                version = current_version or version
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        return {
            "id": "nx2navi",
            "name": "NX2NAVI",
            "version": version,
            "root": root,
            "mods_dir": root / "mods",
            "ini_path": root / "nx2navi.ini",
            "saves_dir": root / "profile" / "save",
            "launch_exe": launcher_exe,
            "launch_args": launcher_args,
            "game_exe": game_exe,
            "mod_backend": "nx2navi_ini",
        }

    if (root / "hookshot.exe").is_file():
        version = _read_version_file(root / "hookshot_version.txt")
        return {
            "id": "hookshot",
            "name": "HOOKSHOT",
            "version": version,
            "root": root,
            "mods_dir": root / "mods",
            "ini_path": None,
            "saves_dir": root / "user" / "save",
            "launch_exe": root / "hookshot.exe",
            "launch_args": [],
            "game_exe": root / "hookshot.exe",
            "mod_backend": "folder_prefix",
        }

    if (root / "longshot.exe").is_file():
        version = _read_version_file(root / "longshot_version.txt")
        shared_user = _resolve_longshot_user_dir(selected_root, root)
        saves_dir = (shared_user / "save") if shared_user else (root / "user" / "save")
        launch_args = ["--user", str(shared_user)] if shared_user else []
        return {
            "id": "longshot",
            "name": "LONGSHOT",
            "version": version,
            "root": root,
            "mods_dir": root / "mods",
            "ini_path": None,
            "saves_dir": saves_dir,
            "launch_exe": root / "longshot.exe",
            "launch_args": launch_args,
            "game_exe": root / "longshot.exe",
            "mod_backend": "folder_prefix",
        }

    return None
