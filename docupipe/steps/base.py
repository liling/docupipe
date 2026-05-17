from __future__ import annotations

from abc import ABC, abstractmethod

from docupipe.models import Bundle


class Step(ABC):
    name: str = ""

    @abstractmethod
    def process(self, bundle: Bundle) -> Bundle:
        """处理文档包，返回处理后的文档包"""

    def update_config(self, config: dict) -> None:
        """用已解析的配置更新组件属性。"""
        for key, value in config.items():
            attr = f"_{key}"
            if hasattr(self, attr):
                setattr(self, attr, value)
