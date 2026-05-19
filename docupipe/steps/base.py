from __future__ import annotations

from abc import ABC, abstractmethod

from docupipe.models import Bundle


class Step(ABC):
    name: str = ""

    _config_keys: set[str] = set()

    @abstractmethod
    def process(self, bundle: Bundle) -> Bundle:
        """处理文档包，返回处理后的文档包"""

    def update_config(self, config: dict) -> None:
        """用已解析的配置更新组件属性。只更新 _config_keys 中声明的字段。"""
        for key in self._config_keys:
            if key in config:
                setattr(self, f"_{key}", config[key])
