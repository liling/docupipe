from __future__ import annotations

from abc import ABC, abstractmethod

from docpipe.models import Bundle


class DestinationBase(ABC):
    name: str = ""

    @abstractmethod
    def write(self, bundle: Bundle) -> str:
        """写入文档包，返回目标系统中的 ID"""

    def remove(self, bundle_id: str) -> None:
        """删除文档包（可选实现）"""
        raise NotImplementedError(f"{self.name} 不支持删除操作")
