from __future__ import annotations

from abc import ABC, abstractmethod

from docupipe.models import Bundle


class PostStep(ABC):
    name: str = ""

    @abstractmethod
    def process(self, bundle: Bundle) -> Bundle:
        """处理成功后的后置动作，返回 bundle"""
