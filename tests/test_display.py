from __future__ import annotations

from docupipe.display import Display


class TestDisplayNonTTY:
    """非 TTY 模式（纯文本输出）的测试"""

    def test_start_stop(self):
        display = Display(is_tty=False)
        display.start("Pipeline: a → b", 10)
        display.stop()

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
        display = Display(is_tty=False)
        display.start("Pipeline: a → b", 10)
        display.set_current("文档1")
        display.clear_current("文档1")
        display.stop()


class TestDisplayCounters:
    """计数器逻辑测试"""

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
        display = Display(is_tty=False)
        display.start("Pipeline: a → b", 10)
        display.result("error", "a")
        assert display.failed == 0
        assert display.completed == 0
        assert display.skipped == 0

    def test_result_error_then_add_failure(self):
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
    """TTY 模式的测试"""

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
        display = Display(is_tty=True)
        display.start("Pipeline: a → b", 10)
        display.set_current("文档1")
        display.set_current("文档2")
        assert len(display._current_tasks) == 2
        display.clear_current("文档1")
        assert len(display._current_tasks) == 1
        display.stop()