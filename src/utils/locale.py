from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class Locale:
    def __init__(self, language: str = "en", locale_dir: str | Path = "locale") -> None:
        self.language = language
        self.locale_dir = Path(locale_dir)
        self.strings = self._load(language)

    def _load(self, language: str) -> dict[str, Any]:
        file_path = self.locale_dir / f"{language}.yaml"
        if not file_path.exists():
            file_path = self.locale_dir / "en.yaml"
        with file_path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}

    def t(self, key: str, **kwargs: Any) -> str:
        current: Any = self.strings
        for part in key.split("."):
            current = current[part]
        if isinstance(current, str):
            return current.format(**kwargs) if kwargs else current
        raise KeyError(f"Locale key does not reference a string: {key}")
