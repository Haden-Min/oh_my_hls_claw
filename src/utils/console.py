from __future__ import annotations

try:
    from rich.console import Console
    from rich.panel import Panel
except ImportError:  # pragma: no cover
    class Console:  # type: ignore[no-redef]
        def print(self, *args, **kwargs):
            print(*args)

        def input(self, prompt: str = "") -> str:
            return input(prompt)

    class Panel(str):  # type: ignore[no-redef]
        def __new__(cls, renderable, title: str | None = None):
            prefix = f"[{title}] " if title else ""
            return str.__new__(cls, prefix + str(renderable))
