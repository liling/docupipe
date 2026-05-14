from __future__ import annotations

import sys
import time


class Display:
    def __init__(self):
        self.total: int = 0
        self.completed: int = 0
        self.failed: int = 0
        self._start_time: float = 0
        self._title: str = ""

    def start(self, title: str, total: int) -> None:
        self._title = title
        self.total = total if total > 0 else None  # None 表示未知总数
        self.completed = 0
        self.failed = 0
        self._start_time = time.time()

    def stop(self) -> None:
        pass

    def log(self, level: str, message: str) -> None:
        print(f"[{level}] {message}")

    def result(self, status: str, message: str) -> None:
        icons = {"success": "✅", "skip": "⏭️ ", "error": "❌", "info": "ℹ️ "}
        icon = icons.get(status, "·")
        print(f"{icon} {message}")
        if status == "success":
            self.completed += 1
        elif status == "error":
            self.failed += 1

    def update_progress(self) -> None:
        self.completed += 1
        done = self.completed + self.failed
        self.log("INFO", f"{self._title} {done}/{self.total}")

    def add_failure(self) -> None:
        self.failed += 1

    def print_summary(self) -> None:
        elapsed = time.time() - self._start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        total = self.completed + self.failed
        print(f"\n{self._title}完成!")
        if self.total is not None:
            print(f"  总数: {self.total}  成功: {self.completed}  失败: {self.failed}  耗时: {minutes}分{seconds}秒")
        else:
            print(f"  总数: {total}  成功: {self.completed}  失败: {self.failed}  耗时: {minutes}分{seconds}秒")
