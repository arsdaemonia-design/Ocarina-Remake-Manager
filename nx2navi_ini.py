"""Read and update NX2navi's native mod switches without losing other settings."""

import json
import os
import re
from pathlib import Path


def _fnv1a_32(text):
    h = 0x811C9DC5
    for b in text.encode("utf-8"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return f"{h:08X}"


def disabled_mods(ini_path):
    text = _read(ini_path)
    section = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip().lower()
        elif section == "mods" and not stripped.startswith(("#", ";")):
            match = re.match(r"\s*mods_disabled\s*=\s*(.*?)\s*$", line, re.IGNORECASE)
            if match:
                return {name.strip() for name in match.group(1).split("|") if name.strip()}
    return set()


def update_disabled_mods(ini_path, disabled):
    """Update only mods_disabled, preserving every other line and setting."""
    path = Path(ini_path)
    text = _read(path)
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    section = None
    mods_section_seen = False
    key_seen = False
    rendered = "|".join(sorted(set(disabled), key=str.casefold))
    output = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if section == "mods" and not key_seen:
                output.append(f"mods_disabled = {rendered}" if rendered else "# mods_disabled =")
                key_seen = True
            section = stripped[1:-1].strip().lower()
            if section == "mods":
                mods_section_seen = True
            output.append(line)
            continue
        if section == "mods" and not stripped.startswith(("#", ";")) and re.match(r"\s*mods_disabled\s*=", line, re.IGNORECASE):
            if not key_seen:
                output.append(f"mods_disabled = {rendered}" if rendered else "# mods_disabled =")
                key_seen = True
            continue
        output.append(line)

    if section == "mods" and not key_seen:
        output.append(f"mods_disabled = {rendered}" if rendered else "# mods_disabled =")
        key_seen = True
    if not mods_section_seen:
        if output and output[-1] != "":
            output.append("")
        output.extend(("[mods]", f"mods_disabled = {rendered}" if rendered else "# mods_disabled ="))

    updated = newline.join(output) + (newline if text.endswith(("\n", "\r")) else "")
    temporary = path.with_name(path.name + ".manager-tmp")
    try:
        temporary.write_text(updated, encoding="utf-8", newline="")
        os.replace(temporary, path)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _find_exefs_patches(mod_dir):
    patches = []
    for current, dirs, files in os.walk(mod_dir):
        dirs[:] = [d for d in dirs if d.casefold() not in ("romfs", "romfslite")]
        current_path = Path(current)
        if current_path.name.casefold() == "exefs":
            for fname in files:
                if Path(fname).suffix.casefold() in (".pchtxt", ".ips"):
                    patches.append(current_path / fname)
    return patches


def _read_build_cache_exefs(game_root):
    cache_dir = Path(game_root) / "build-cache"
    exefs_status = {}
    status_file = cache_dir / "exefs.status"
    if status_file.is_file():
        try:
            for line in status_file.read_text(encoding="utf-8", errors="replace").splitlines():
                fields = line.split("\t")
                if len(fields) >= 5:
                    exefs_status[fields[0].strip().upper()] = (
                        fields[2].strip().casefold(),
                        fields[4].strip(),
                    )
        except OSError:
            pass

    mod_code = {}
    code_file = cache_dir / "mod-code.json"
    if code_file.is_file():
        try:
            loaded = json.loads(code_file.read_text(encoding="utf-8", errors="replace"))
            if isinstance(loaded, dict):
                mod_code = loaded
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    return exefs_status, mod_code


def read_mod_log_status(log_dir, game_root=None, library_dir=None):
    """Read NX2navi mod results from rotating logs and build-cache/exefs.status."""
    directory = Path(log_dir)
    result = {}
    if directory.is_dir():
        logs = sorted(directory.glob("nx2navi*.log"), key=lambda path: path.stat().st_mtime)
        pattern = re.compile(r"^\[host\] mods: (.+?): (on|off), (romfs|exefs), (.*)$", re.IGNORECASE)
        for log in logs:
            try:
                for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
                    match = pattern.match(line.strip())
                    if not match:
                        continue
                    name, requested, kind, detail = match.groups()
                    lowered = detail.casefold()
                    result[name.casefold()] = {
                        "requested": requested.casefold() == "on",
                        "kind": kind.casefold(),
                        "detail": detail.strip(),
                        "not_usable": "whole mod stays off" in lowered or "cannot be applied" in lowered,
                        "validated": lowered == "ok",
                    }
            except OSError:
                continue

    root = Path(game_root) if game_root else (directory.parent if directory.name.casefold() == "logs" else None)
    if root and root.is_dir():
        exefs_status, mod_code = _read_build_cache_exefs(root)
        if exefs_status or mod_code:
            scan_roots = [root / "mods"]
            if library_dir:
                scan_roots.append(Path(library_dir))
            seen_mods = {}
            for mods_root in scan_roots:
                if not mods_root.is_dir():
                    continue
                try:
                    for mod_dir in mods_root.iterdir():
                        if mod_dir.is_dir() and mod_dir.name.casefold() not in seen_mods:
                            seen_mods[mod_dir.name.casefold()] = mod_dir
                except OSError:
                    continue

            for mod_key, mod_dir in seen_mods.items():
                patches = _find_exefs_patches(mod_dir)
                if not patches:
                    continue
                has_unsupported = False
                has_supported = False
                has_built = False
                unsupported_detail = ""
                for patch_file in patches:
                    rel = patch_file.relative_to(mod_dir).as_posix()
                    lookup_id = f"{mod_dir.name}/{rel}"
                    fnv_key = _fnv1a_32(lookup_id)
                    if fnv_key in exefs_status:
                        status_kind, note = exefs_status[fnv_key]
                        if status_kind == "unsupported":
                            has_unsupported = True
                            if not unsupported_detail:
                                unsupported_detail = f"{patch_file.name}: {note}" if note else patch_file.name
                        elif status_kind in ("ok", "applied", "supported"):
                            has_supported = True
                    if lookup_id in mod_code:
                        has_built = True

                entry = result.setdefault(
                    mod_key,
                    {
                        "requested": True,
                        "kind": "exefs",
                        "detail": "",
                        "not_usable": False,
                        "validated": False,
                        "built": False,
                    },
                )
                if has_unsupported:
                    entry["kind"] = "exefs"
                    entry["not_usable"] = True
                    entry["validated"] = False
                    entry["detail"] = unsupported_detail
                elif has_supported and not entry.get("not_usable"):
                    entry["kind"] = "exefs"
                    entry["validated"] = True
                    entry["not_usable"] = False
                    if not entry.get("detail"):
                        entry["detail"] = "ok"
                if has_built and not has_unsupported and not entry.get("not_usable"):
                    entry["built"] = True
                    if not entry.get("validated"):
                        entry["validated"] = True
                        if not entry.get("detail"):
                            entry["detail"] = "ok"

    return result


def _read(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as stream:
        return stream.read()
