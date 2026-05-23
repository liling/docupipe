from __future__ import annotations

from abc import ABC, abstractmethod

from docupipe.models import Bundle


class DestinationBase(ABC):
    name: str = ""

    _config_keys: set[str] = set()

    @abstractmethod
    def write(self, bundle: Bundle) -> str:
        """写入文档包，返回目标系统中的 ID"""

    def remove(self, bundle_id: str) -> None:
        """删除文档包（可选实现）"""
        raise NotImplementedError(f"{self.name} 不支持删除操作")

    def update_config(self, config: dict) -> None:
        """更新组件配置属性。只更新 _config_keys 中声明的字段。"""
        for key in self._config_keys:
            if key in config:
                setattr(self, f"_{key}", config[key])
