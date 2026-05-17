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

    def supported_change_detection(self) -> list[str]:
        """返回支持的变更检测策略，如 ['mtime', 'hash']"""
        return []

    def delete(self, doc_id: str) -> None:
        """删除指定文档（可选实现）"""
        raise NotImplementedError