from __future__ import annotations

from abc import ABC, abstractmethod

from docpipe.models import Document


class PipelineStep(ABC):
    name: str = ""

    @abstractmethod
    def process(self, doc: Document) -> Document:
        """处理文档，返回处理后的文档"""
