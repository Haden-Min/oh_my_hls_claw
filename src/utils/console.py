from __future__ import annotations

import itertools
import threading
import time
from contextlib import contextmanager

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


class ProgressConsole:
    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def print(self, *args, **kwargs):
        self.console.print(*args, **kwargs)

    def input(self, prompt: str = "") -> str:
        return self.console.input(prompt)

    @contextmanager
    def spinner(self, message: str):
        stop_event = threading.Event()
        frames = itertools.cycle(["|", "/", "-", "\\"])

        def run() -> None:
            while not stop_event.is_set():
                frame = next(frames)
                print(f"\r{frame} {message}", end="", flush=True)
                time.sleep(0.12)
            print(f"\rOK {message}{' ' * 10}")

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop_event.set()
            thread.join(timeout=1.0)

    def status(self, message: str) -> None:
        self.print(f"[status] {message}")
