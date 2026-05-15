from __future__ import annotations

from abc import ABC, abstractmethod

from docpipe.models import Document


class DestinationBase(ABC):
    name: str = ""

    @abstractmethod
    def write(self, doc: Document) -> str:
        """写入单个文档，返回目标系统中的 ID"""

    def remove(self, doc_id: str) -> None:
        """删除单个文档（可选实现）"""
        raise NotImplementedError(f"{self.name} 不支持删除操作")
