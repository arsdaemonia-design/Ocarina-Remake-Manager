"""Process and Windows lock checks to prevent writes while a port is running."""

from __future__ import annotations

import csv
import ctypes
from ctypes import wintypes
import os
import subprocess
from pathlib import Path
from typing import Callable


def nx2navi_launcher_running() -> bool | None:
    local_data = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    lock_path = local_data / "Programs" / "NX2navi" / "data" / "launcher.lock"
    if not lock_path.is_file():
        return False
    try:
        import msvcrt

        with lock_path.open("r+b") as lock_file:
            lock_file.seek(0)
            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                return True
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            return False
    except OSError:
        return None


def nx2navi_instance_locked(port: dict | None) -> bool:
    """Check NX2NAVI's exclusive instance.lock and running ocarina.exe via CreateFileW."""
    if not port or port.get("id") != "nx2navi" or os.name != "nt":
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    invalid_handle = ctypes.c_void_p(-1).value
    error_sharing_violation = 32
    open_existing = 3
    normal_attr = 0x80

    def is_locked(path: Path, access: int, share_mode: int) -> bool:
        if not path.is_file():
            return False
        handle = create_file(str(path), access, share_mode, None, open_existing, normal_attr, None)
        if handle not in (None, 0, invalid_handle):
            close_handle(handle)
            return False
        return ctypes.get_last_error() == error_sharing_violation

    instance_lock = Path(port["root"]) / "profile" / "instance.lock"
    if is_locked(instance_lock, 0xC0000000, 0):
        return True
    game_exe = Path(port.get("game_exe", ""))
    return is_locked(game_exe, 0x40000000, 7)


def game_is_running(port: dict | None) -> tuple[bool, bool]:
    """Return (is_running, verification_issue). Excludes pythonw.exe false positives for NX2NAVI."""
    if not port:
        return False, False
    if os.name == "nt" and port.get("id") == "nx2navi":
        launcher_running = nx2navi_launcher_running()
        if launcher_running is not False:
            return True, launcher_running is None
        if nx2navi_instance_locked(port):
            return True, False

    if os.name != "nt":
        targets = {"ocarina", "nx2navi"} if port.get("id") == "nx2navi" else {
            Path(port.get("game_exe", port.get("launch_exe", ""))).stem.casefold(),
            Path(port.get("launch_exe", "")).stem.casefold(),
        }
        targets.discard("")
        for pat in targets:
            try:
                res = subprocess.run(["pgrep", "-fi", pat], capture_output=True, text=True, check=False, timeout=4)
                if res.returncode == 0 and res.stdout.strip():
                    return True, False
            except OSError:
                return False, False
        return False, False

    try:
        result = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            check=False,
            timeout=4,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            return True, True
        rows = [row for row in csv.reader(result.stdout.splitlines()) if row]
        process_names = {row[0].casefold() for row in rows}
        if port.get("id") == "nx2navi":
            # Audit fix #1: ignore generic pythonw.exe; check only ocarina.exe and nx2navi.exe.
            targets = {"ocarina.exe", "nx2navi.exe"}
            game_exe = port.get("game_exe")
            if game_exe:
                targets.add(Path(game_exe).name.casefold())
        else:
            game_name = Path(port.get("game_exe", port["launch_exe"])).name.casefold()
            launch_name = Path(port.get("launch_exe", "")).name.casefold()
            targets = {name for name in (game_name, launch_name) if name}
        return bool(process_names & targets), False
    except (OSError, csv.Error, subprocess.TimeoutExpired):
        return True, True


def game_running_message(issue: bool, tr: Callable[[str], str]) -> str:
    if issue:
        return tr(
            "No pude confirmar que el juego y el launcher estén cerrados. Cierra ambos y vuelve a intentarlo. Si ya están cerrados, ejecuta el manager fuera de un entorno restringido."
        )
    return tr("Cierra el juego y el launcher del port antes de modificar mods o iniciar otro perfil.")
