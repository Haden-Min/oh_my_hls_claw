from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

import yaml


class FileManager:
    _PROJECT_NAME_PATTERN = re.compile(r"[^a-zA-Z0-9._-]+")

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def ensure_project(self, project_name: str) -> Path:
        project_root = self.project_root(project_name)
        for name in ("spec", "rtl", "tb", "sim", "docs", "onboard", "logs"):
            (project_root / name).mkdir(parents=True, exist_ok=True)
        return project_root

    def project_root(self, project_name: str) -> Path:
        workspace_root = self.root / "workspace"
        safe_name = self.safe_project_name(project_name)
        project_root = workspace_root / safe_name
        self._assert_inside(project_root, workspace_root)
        return project_root

    @classmethod
    def safe_project_name(cls, project_name: str | Path) -> str:
        raw_name = str(project_name).strip()
        normalized = cls._PROJECT_NAME_PATTERN.sub("_", raw_name).strip("._-")
        return normalized[:80] or "unnamed_project"

    def read_text(self, path: str | Path, default: str = "") -> str:
        target = Path(path)
        if not target.exists():
            return default
        return target.read_text(encoding="utf-8")

    def write_text(self, path: str | Path, content: str) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def read_yaml(self, path: str | Path) -> dict[str, Any]:
        target = Path(path)
        if not target.exists():
            return {}
        with target.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}

    def write_yaml(self, path: str | Path, data: dict[str, Any]) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)
        return target

    def read_json(self, path: str | Path, default: Any = None) -> Any:
        target = Path(path)
        if not target.exists():
            return {} if default is None else default
        with target.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def write_json(self, path: str | Path, data: Any) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
        return target

    @staticmethod
    def _assert_inside(path: Path, parent: Path) -> None:
        resolved_path = path.resolve()
        resolved_parent = parent.resolve()
        try:
            resolved_path.relative_to(resolved_parent)
        except ValueError as exc:
            raise ValueError(f"Unsafe project path outside workspace: {path}") from exc
