from __future__ import annotations

import logging
import sys
import threading
import time

from rich.console import Console
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


class _DynamicRenderable:
    """每次渲染时读取 Display 最新状态，避免反复调用 _live.update() 导致光标偏移。"""

    def __init__(self, display: Display):
        self._display = display

    def __rich_console__(self, console, options):
        yield self._display._progress
        yield self._display._build_stats_line()
        current = self._display._build_current_lines()
        if current:
            yield current


class _StdioProxy:
    """将主线程的 stdout/stderr 写入重定向到 Live 显示上方，防止干扰进度条。

    非主线程（如 Rich 自动刷新线程）的写入直接透传，避免干扰 Live 渲染。
    """

    def __init__(self, original, display: Display):
        self._original = original
        self._display = display
        self._guard = False

    def write(self, text):
        if not text or not text.strip():
            return self._original.write(text)
        if self._guard or self._display._printing or threading.current_thread() is not threading.main_thread():
            return self._original.write(text)
        self._guard = True
        try:
            self._display._print(text.rstrip('\n'))
        finally:
            self._guard = False
        return len(text)

    def flush(self):
        self._original.flush()

    def isatty(self):
        return self._original.isatty()

    @property
    def encoding(self):
        return self._original.encoding

    def __getattr__(self, name):
        return getattr(self._original, name)


class Display:
    def __init__(self, console: Console | None = None, is_tty: bool | None = None):
        self._console = console or Console()
        self._is_tty = is_tty if is_tty is not None else sys.stdout.isatty()
        self._live: Live | None = None
        self._progress: Progress | None = None
        self._progress_task_id = None
        self._lock = threading.Lock()
        self._current_tasks: list[str] = []
        self._saved_log_level: int | None = None

        self.total: int = 0
        self.completed: int = 0
        self.skipped: int = 0
        self.failed: int = 0

        self._step_info: str = ""
        self._title: str = ""
        self._start_time: float = 0
        self._printing = False
        self._original_stdout = None
        self._original_stderr = None

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
            auto_refresh=False,
        )
        self._progress_task_id = self._progress.add_task(title, total=total)

        # 先安装 stdio 代理，再启动 Live（Live 会在代理之上安装 FileProxy）
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        sys.stdout = _StdioProxy(sys.stdout, self)
        sys.stderr = _StdioProxy(sys.stderr, self)

        self._live = Live(
            _DynamicRenderable(self),
            console=self._console,
            refresh_per_second=4,
            transient=False,
        )
        self._live.start()
        # Live 模式下抑制 INFO 日志，避免和面板输出交叉
        docpipe_logger = logging.getLogger("docpipe")
        self._saved_log_level = docpipe_logger.level
        docpipe_logger.setLevel(logging.WARNING)

    def stop(self) -> None:
        if self._live:
            # 恢复日志级别
            if self._saved_log_level is not None:
                logging.getLogger("docpipe").setLevel(self._saved_log_level)
                self._saved_log_level = None
            self._live.stop()
            self._live = None
            # Live 停止后恢复原始 stdio
            if self._original_stdout is not None:
                sys.stdout = self._original_stdout
                self._original_stdout = None
            if self._original_stderr is not None:
                sys.stderr = self._original_stderr
                self._original_stderr = None

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
            elif status == "info":
                self.completed += 1
                self._advance_progress()
            else:
                # error: 不计数不推进，由 add_failure() 负责
                pass
        self._print(text)

    def add_failure(self) -> None:
        with self._lock:
            self.failed += 1
            self._advance_progress()

    def set_step(self, label: str) -> None:
        self._step_info = label

    def clear_step(self) -> None:
        self._step_info = ""

    def set_current(self, label: str) -> None:
        if not self._is_tty:
            return
        with self._lock:
            if label not in self._current_tasks:
                self._current_tasks.append(label)

    def clear_current(self, label: str) -> None:
        if not self._is_tty:
            return
        with self._lock:
            if label in self._current_tasks:
                self._current_tasks.remove(label)

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

    def _print(self, text: str) -> None:
        if self._live:
            self._printing = True
            try:
                self._live.console.print(text)
            except Exception:
                self._live.console.print(text, markup=False)
            finally:
                self._printing = False
        else:
            print(text)

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
            lines.append(f"⏳ {label}", style="yellow")
            if self._step_info:
                lines.append(f" → {self._step_info}", style="cyan")
            lines.append("\n")
        return lines

