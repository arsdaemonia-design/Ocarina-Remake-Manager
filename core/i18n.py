"""Decoupled Spanish/English translation helper."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def resolve_i18n_dir() -> Path:
    candidates = [
        Path(__file__).resolve().parent.parent / "i18n",
    ]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "i18n")
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([exe_dir / "i18n", exe_dir / "_internal" / "i18n"])
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


class Translator:
    """Loads i18n JSON tables and supports live language switching."""

    def __init__(self, language: str = "es", i18n_dir: Path | None = None) -> None:
        self.i18n_dir = i18n_dir or resolve_i18n_dir()
        self._tables = {
            "es": self._load("es.json"),
            "en": self._load("en.json"),
        }
        self.language = "en" if language == "en" else "es"

    def _load(self, filename: str) -> dict[str, str]:
        path = self.i18n_dir / filename
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    def set_language(self, language: str) -> None:
        self.language = "en" if language == "en" else "es"

    def key(self, message_key: str, default: str | None = None) -> str:
        table = self._tables.get(self.language, {})
        if message_key in table:
            return table[message_key]
        fallback = self._tables.get("es", {})
        if message_key in fallback:
            return fallback[message_key]
        return default if default is not None else message_key

    def tr(self, text: str) -> str:
        if self.language == "en":
            return self._tables.get("en", {}).get(text, text)
        return text

    def tx(self, spanish: str, english: str) -> str:
        return english if self.language == "en" else spanish
