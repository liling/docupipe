from __future__ import annotations

from abc import ABC, abstractmethod

from docupipe.models import Bundle


class DestinationBase(ABC):
    name: str = ""

    @abstractmethod
    def write(self, bundle: Bundle) -> str:
        """写入文档包，返回目标系统中的 ID"""

    def remove(self, bundle_id: str) -> None:
        """删除文档包（可选实现）"""
        raise NotImplementedError(f"{self.name} 不支持删除操作")

    def update_config(self, config: dict) -> None:
        """用已解析的配置更新组件属性。"""
        for key, value in config.items():
            attr = f"_{key}"
            if hasattr(self, attr):
                setattr(self, attr, value)
