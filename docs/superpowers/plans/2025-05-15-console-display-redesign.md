# 控制台界面重写实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 Rich Live + Progress 重写 Display 类，实现实时刷新的状态面板（Pipeline 标题 + 进度条 + 统计 + 当前任务），结果日志向上滚动。

**Architecture:** Display 类内部使用 Rich Live 实时渲染状态面板，通过 `Live.console.print()` 输出结果行到面板上方。非 TTY 环境自动降级为纯 print。Pipeline 仅新增 `set_current`/`clear_current` 调用，其余接口不变。

**Tech Stack:** Python 3.11+, Rich (Live, Progress, Console, Table, Text, Group), threading.Lock

---

### Task 1: 添加 rich 依赖，移除 tqdm

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 修改 pyproject.toml 依赖**

将 `tqdm>=4.66.0` 替换为 `rich>=13.0.0`：

```toml
dependencies = [
    "click>=8.1.0",
    "markitdown>=0.1.0",
    "hindsight-client>=0.1.0",
    "rich>=13.0.0",
    "python-dotenv>=1.0.0",
    "pyyaml>=6.0",
    "requests>=2.31.0",
    "openai>=1.0.0",
]
```

- [ ] **Step 2: 安装依赖**

Run: `pip install -e ".[dev]"`
Expected: 成功安装 rich

- [ ] **Step 3: 提交**

```bash
git add pyproject.toml
git commit -m "feat: 添加 rich 依赖，移除未使用的 tqdm"
```

---

### Task 2: 编写 Display 类的测试

**Files:**
- Create: `tests/test_display.py`

- [ ] **Step 1: 编写测试文件**

```python
from __future__ import annotations

import io
from unittest.mock import patch

from docpipe.display import Display


class TestDisplayNonTTY:
    """非 TTY 模式（纯文本输出）的测试"""

    def test_start_stop(self):
        display = Display(is_tty=False)
        display.start("Pipeline: a → b", 10)
        display.stop()
        # 不抛异常即可

    def test_result_success(self, capsys):
        display = Display(is_tty=False)
        display.start("Pipeline: a → b", 10)
        display.result("success", "文档1")
        display.stop()
        captured = capsys.readouterr()
        assert "✅" in captured.out
        assert "文档1" in captured.out

    def test_result_skip(self, capsys):
        display = Display(is_tty=False)
        display.start("Pipeline: a → b", 10)
        display.result("skip", "文档2 (无变化)")
        display.stop()
        captured = capsys.readouterr()
        assert "⏭️" in captured.out
        assert "文档2" in captured.out

    def test_result_error(self, capsys):
        display = Display(is_tty=False)
        display.start("Pipeline: a → b", 10)
        display.result("error", "文档3: 失败")
        display.stop()
        captured = capsys.readouterr()
        assert "❌" in captured.out
        assert "文档3" in captured.out

    def test_result_info(self, capsys):
        display = Display(is_tty=False)
        display.start("Pipeline: a → b", 10)
        display.result("info", "[dry-run] 文档4")
        display.stop()
        captured = capsys.readouterr()
        assert "ℹ️" in captured.out
        assert "文档4" in captured.out

    def test_add_failure_increments_counter(self):
        display = Display(is_tty=False)
        display.start("Pipeline: a → b", 10)
        display.add_failure()
        assert display.failed == 1

    def test_print_summary(self, capsys):
        display = Display(is_tty=False)
        display.start("Pipeline: a → b", 5)
        display.completed = 3
        display.skipped = 1
        display.failed = 1
        display.stop()
        display.print_summary()
        captured = capsys.readouterr()
        assert "完成" in captured.out

    def test_set_current_noop(self):
        """非 TTY 模式下 set_current/clear_current 不抛异常"""
        display = Display(is_tty=False)
        display.start("Pipeline: a → b", 10)
        display.set_current("文档1")
        display.clear_current("文档1")
        display.stop()


class TestDisplayCounters:
    """计数器逻辑测试（不依赖 TTY）"""

    def test_result_counts_success(self):
        display = Display(is_tty=False)
        display.start("Pipeline: a → b", 10)
        display.result("success", "a")
        display.result("success", "b")
        assert display.completed == 2

    def test_result_counts_skip(self):
        display = Display(is_tty=False)
        display.start("Pipeline: a → b", 10)
        display.result("skip", "a")
        display.result("skip", "b")
        assert display.skipped == 2

    def test_result_error_does_not_advance_progress(self):
        """result("error") 不计数也不推进进度条，由 add_failure 负责"""
        display = Display(is_tty=False)
        display.start("Pipeline: a → b", 10)
        display.result("error", "a")
        assert display.failed == 0
        assert display.completed == 0
        assert display.skipped == 0

    def test_result_error_then_add_failure(self):
        """pipeline 调用顺序: result("error") → add_failure()"""
        display = Display(is_tty=False)
        display.start("Pipeline: a → b", 10)
        display.result("error", "a")
        display.add_failure()
        assert display.failed == 1

    def test_add_failure(self):
        display = Display(is_tty=False)
        display.start("Pipeline: a → b", 10)
        display.add_failure()
        display.add_failure()
        assert display.failed == 2

    def test_total_set_by_start(self):
        display = Display(is_tty=False)
        display.start("Pipeline: a → b", 42)
        assert display.total == 42


class TestDisplayTTY:
    """TTY 模式的测试（验证 Rich 对象创建，不验证终端输出）"""

    def test_start_creates_live(self):
        display = Display(is_tty=True)
        display.start("Pipeline: a → b", 10)
        assert display._live is not None
        assert display._progress is not None
        display.stop()

    def test_stop_clears_live(self):
        display = Display(is_tty=True)
        display.start("Pipeline: a → b", 10)
        display.stop()
        assert display._live is None

    def test_set_current_adds_task(self):
        display = Display(is_tty=True)
        display.start("Pipeline: a → b", 10)
        display.set_current("文档1")
        assert "文档1" in display._current_tasks
        display.stop()

    def test_clear_current_removes_task(self):
        display = Display(is_tty=True)
        display.start("Pipeline: a → b", 10)
        display.set_current("文档1")
        display.clear_current("文档1")
        assert "文档1" not in display._current_tasks
        display.stop()

    def test_multiple_current_tasks(self):
        """验证支持多个当前任务（并行预留）"""
        display = Display(is_tty=True)
        display.start("Pipeline: a → b", 10)
        display.set_current("文档1")
        display.set_current("文档2")
        assert len(display._current_tasks) == 2
        display.clear_current("文档1")
        assert len(display._current_tasks) == 1
        display.stop()
```

- [ ] **Step 2: 运行测试，确认全部失败**

Run: `python -m pytest tests/test_display.py -v`
Expected: 全部 FAIL（Display 类尚未重写）

---

### Task 3: 重写 Display 类

**Files:**
- Modify: `docpipe/display.py`

- [ ] **Step 1: 完整重写 display.py**

```python
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
```

- [ ] **Step 2: 运行测试，确认全部通过**

Run: `python -m pytest tests/test_display.py -v`
Expected: 全部 PASS

- [ ] **Step 3: 运行全部测试，确认无回归**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
git add docpipe/display.py tests/test_display.py
git commit -m "feat: 用 Rich Live + Progress 重写 Display 类"
```

---

### Task 4: 适配 pipeline.py

**Files:**
- Modify: `docpipe/pipeline.py:86-108`

- [ ] **Step 1: 在 fetch 前后添加 set_current/clear_current**

修改 `pipeline.py` 的 `run` 方法中 for 循环部分，在 `try` 块内 fetch 前设置当前任务，finally 中清除：

将原来的：
```python
for doc_meta in docs:
    if sync and self.state.is_unchanged(doc_meta.id, doc_meta.hash):
        self._display.result("skip", f"{doc_meta.title} (无变化)")
        continue

    try:
        doc = self.source.fetch(doc_meta)
```

改为：
```python
for doc_meta in docs:
    if sync and self.state.is_unchanged(doc_meta.id, doc_meta.hash):
        self._display.result("skip", f"{doc_meta.title} (无变化)")
        continue

    self._display.set_current(doc_meta.title)
    try:
        doc = self.source.fetch(doc_meta)
```

并在 `except` 块后添加 `finally`：

将原来的：
```python
    except Exception as e:
        logger.error("文档处理失败: %s - %s", doc_meta.title, e)
        self._display.result("error", f"{doc_meta.title}: {e}")
        self._display.add_failure()
```

改为：
```python
    except Exception as e:
        logger.error("文档处理失败: %s - %s", doc_meta.title, e)
        self._display.result("error", f"{doc_meta.title}: {e}")
        self._display.add_failure()
    finally:
        self._display.clear_current(doc_meta.title)
```

- [ ] **Step 2: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 3: 提交**

```bash
git add docpipe/pipeline.py
git commit -m "feat: Pipeline 添加当前任务提示"
```

---

### Task 5: 手动验证

- [ ] **Step 1: 用本地 Source 运行 pipeline，观察控制台输出**

```bash
mkdir -p /tmp/test_docs
echo "# test1" > /tmp/test_docs/test1.md
echo "# test2" > /tmp/test_docs/test2.md
python -m docpipe run --source local --dest hindsight --input-dir /tmp/test_docs --dry-run
```

Expected: 看到实时刷新的状态面板（进度条 + 统计 + 当前任务），结果行向上滚动

- [ ] **Step 2: 验证非 TTY 降级**

```bash
python -m docpipe run --source local --dest hindsight --input-dir /tmp/test_docs --dry-run 2>&1 | cat
```

Expected: 纯文本输出，无 Rich 格式

- [ ] **Step 3: 清理测试文件**

```bash
rm -rf /tmp/test_docs
```
