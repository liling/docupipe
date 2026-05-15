from __future__ import annotations

import sys
import threading
import time

from rich.console import Console, Group
from rich.live import Live
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text


def _format_duration(seconds: float) -> str:
    total = int(seconds)
    if total >= 3600:
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f"{h}:{m:02d}:{s:02d}"
    m = total // 60
    s = total % 60
    return f"{m}分{s:02d}秒"


class Display:
    def __init__(self, console: Console | None = None, is_tty: bool | None = None):
        self._console = console or Console()
        self._is_tty = is_tty if is_tty is not None else sys.stdout.isatty()
        self._live: Live | None = None
        self._progress: Progress | None = None
        self._progress_task_id = None
        self._lock = threading.Lock()
        self._current_tasks: list[str] = []

        self.total: int = 0
        self.completed: int = 0
        self.skipped: int = 0
        self.failed: int = 0

        self._title: str = ""
        self._start_time: float = 0

    def start(self, title: str, total: int) -> None:
        self._title = title
        self.total = total
        self.completed = 0
        self.skipped = 0
        self.failed = 0
        self._start_time = time.time()

        if not self._is_tty:
            return

        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}", justify="left"),
            BarColumn(bar_width=40),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=self._console,
            transient=False,
        )
        self._progress_task_id = self._progress.add_task(title, total=total)
        self._live = Live(
            self._build_renderable(),
            console=self._console,
            refresh_per_second=4,
            transient=False,
        )
        self._live.start()

    def stop(self) -> None:
        if self._live:
            self._live.stop()
            self._live = None

    def result(self, status: str, message: str) -> None:
        icons = {"success": "✅", "skip": "⏭️ ", "error": "❌", "info": "ℹ️ "}
        icon = icons.get(status, "·")
        text = f"{icon} {message}"

        with self._lock:
            if status == "success":
                self.completed += 1
                self._advance_progress()
            elif status == "skip":
                self.skipped += 1
                self._advance_progress()
            else:
                # error/info: 不推进进度条，由 add_failure() 负责
                pass
            self._print(text)

    def add_failure(self) -> None:
        with self._lock:
            self.failed += 1
            self._advance_progress()

    def set_current(self, label: str) -> None:
        if not self._is_tty:
            return
        with self._lock:
            if label not in self._current_tasks:
                self._current_tasks.append(label)
            self._refresh_live()

    def clear_current(self, label: str) -> None:
        if not self._is_tty:
            return
        with self._lock:
            if label in self._current_tasks:
                self._current_tasks.remove(label)
            self._refresh_live()

    def print_summary(self) -> None:
        elapsed = time.time() - self._start_time
        table = Table(title=f"{self._title} 完成!", show_header=True, header_style="bold")
        table.add_column("总数", justify="right")
        table.add_column("成功", justify="right", style="green")
        table.add_column("跳过", justify="right", style="yellow")
        table.add_column("失败", justify="right", style="red" if self.failed > 0 else "default")
        table.add_column("耗时", justify="right")
        table.add_row(
            str(self.total),
            str(self.completed),
            str(self.skipped),
            str(self.failed),
            _format_duration(elapsed),
        )
        self._console.print()
        self._console.print(table)

    def _advance_progress(self) -> None:
        if self._progress and self._progress_task_id is not None:
            self._progress.update(self._progress_task_id, advance=1)
            done = self.completed + self.skipped + self.failed
            self._progress.update(
                self._progress_task_id,
                description=f"{self._title} {done}/{self.total}",
            )
            self._refresh_live()

    def _print(self, text: str) -> None:
        if self._live:
            try:
                self._live.console.print(text)
            except Exception:
                self._live.console.print(text, markup=False)
        else:
            print(text)

    def _build_renderable(self):
        elements = [self._progress]
        stats = self._build_stats_line()
        if stats:
            elements.append(stats)
        current = self._build_current_lines()
        if current:
            elements.append(current)
        return Group(*elements)

    def _build_stats_line(self) -> Text:
        parts = []
        parts.append(("✅ ", "green"))
        parts.append((f"{self.completed}  ", "default"))
        parts.append(("⏭️ ", "yellow"))
        parts.append((f"{self.skipped}  ", "default"))
        parts.append(("❌ ", "red" if self.failed > 0 else "default"))
        parts.append((f"{self.failed}", "default"))
        line = Text()
        for text, style in parts:
            line.append(text, style=style)
        return line

    def _build_current_lines(self) -> Text | None:
        if not self._current_tasks:
            return None
        lines = Text()
        for label in self._current_tasks:
            lines.append(f"⏳ {label}\n", style="yellow")
        return lines

    def _refresh_live(self) -> None:
        if self._live:
            self._live.update(self._build_renderable())