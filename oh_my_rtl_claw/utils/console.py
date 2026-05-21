from __future__ import annotations

import itertools
import threading
import time
from contextlib import contextmanager

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
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

    Text = None  # type: ignore[assignment]


class ProgressConsole:
    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()
        self._last_kind = "plain"

    def print(self, *args, **kwargs):
        if self._last_kind == "spinner":
            print()
        self.console.print(*args, **kwargs)
        self._last_kind = "plain"

    def input(self, prompt: str = "") -> str:
        return self.console.input(prompt)

    @contextmanager
    def spinner(self, message: str):
        stop_event = threading.Event()
        frames = itertools.cycle(["|", "/", "-", "\\"])
        started_at = time.perf_counter()

        def run() -> None:
            while not stop_event.is_set():
                frame = next(frames)
                elapsed = self.format_duration(time.perf_counter() - started_at)
                print(f"\r\033[96m{frame}\033[0m {message} \033[2m[{elapsed}]\033[0m", end="", flush=True)
                time.sleep(0.12)
            elapsed = self.format_duration(time.perf_counter() - started_at)
            print(f"\r\033[92mOK\033[0m {message} \033[2m[{elapsed}]\033[0m{' ' * 10}")

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop_event.set()
            thread.join(timeout=1.0)
            self._last_kind = "spinner"

    def status(self, message: str) -> None:
        if self._last_kind == "spinner":
            print()
            self._last_kind = "plain"
        if self._is_major_status(message):
            self.section(message)
        elif message.lower().startswith("step ") and " complete " in message.lower():
            self.success(message)
        else:
            self.detail(message)

    def section(self, message: str) -> None:
        if self._last_kind == "spinner":
            print()
            self._last_kind = "plain"
        if self._last_kind != "section":
            self.console.print()
        if Text is not None:
            text = Text(message, style="bold bright_cyan")
            self.console.print(text)
        else:
            self.console.print(f"\n== {message} ==")
        self._last_kind = "section"

    def detail(self, message: str) -> None:
        if self._last_kind == "spinner":
            print()
            self._last_kind = "plain"
        if Text is not None:
            prefix = Text("  >", style="bright_blue")
            body = Text(f" {message}", style="white")
            self.console.print(prefix + body)
        else:
            self.console.print(f"  > {message}")
        self._last_kind = "detail"

    def success(self, message: str) -> None:
        if self._last_kind == "spinner":
            print()
            self._last_kind = "plain"
        if Text is not None:
            prefix = Text("  OK", style="bold green")
            body = Text(f" {message}", style="green")
            self.console.print(prefix + body)
        else:
            self.console.print(f"  OK {message}")
        self._last_kind = "success"

    @staticmethod
    def _is_major_status(message: str) -> bool:
        prefixes = (
            "Planning architecture",
            "Refining spec with manager",
            "Ready steps:",
            "Step ",
            "Generating onboarding assets",
            "Writing final project documentation",
            "Project completed:",
        )
        return message.startswith(prefixes) and "complete for" not in message

    @staticmethod
    def format_duration(seconds: float) -> str:
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes = int(seconds // 60)
        remaining = seconds - (minutes * 60)
        return f"{minutes}m {remaining:.1f}s"
