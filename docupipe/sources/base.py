from __future__ import annotations

from abc import ABC, abstractmethod

from docupipe.models import Bundle, BundleMeta


class SourceBase(ABC):
    name: str = ""

    @abstractmethod
    def list(self) -> list[BundleMeta]:
        """列出所有可获取的文档包"""

    @abstractmethod
    def fetch(self, meta: BundleMeta) -> Bundle:
        """获取单个文档包的完整内容"""