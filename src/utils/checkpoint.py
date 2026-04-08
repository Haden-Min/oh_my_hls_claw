from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .console import Console, Panel
from .locale import Locale


class CheckpointRejected(RuntimeError):
    pass


@dataclass
class CheckpointManager:
    locale: Locale
    console: Console

    async def prompt(self, name: str, data: Any) -> Any:
        self.console.print(Panel(json.dumps(data, indent=2, ensure_ascii=False), title=self.locale.t("checkpoint.title", name=name)))
        choice = self.console.input(f"{self.locale.t('checkpoint.approve')}: ").strip().lower()
        if choice == "a":
            return True
        if choice == "r":
            reason = self.console.input(f"{self.locale.t('checkpoint.reject_reason')} ").strip()
            raise CheckpointRejected(reason)
        if choice == "e":
            return data
        return False
