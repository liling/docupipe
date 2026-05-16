from __future__ import annotations

from abc import ABC, abstractmethod

from docupipe.models import Bundle


class PipelineStep(ABC):
    name: str = ""

    @abstractmethod
    def process(self, bundle: Bundle) -> Bundle:
        """处理文档包，返回处理后的文档包"""
