from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ConverterBase(ABC):
    name: str = ""

    @abstractmethod
    def convert(self, file_path: Path) -> str:
        """将文件转换为 Markdown，返回 Markdown 文本"""
