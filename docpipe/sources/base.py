from __future__ import annotations

from abc import ABC, abstractmethod

from docpipe.models import Document, DocumentMeta


class SourceBase(ABC):
    name: str = ""

    @abstractmethod
    def list_documents(self) -> list[DocumentMeta]:
        """列出所有可获取的文档及其元信息"""

    @abstractmethod
    def fetch(self, doc_meta: DocumentMeta) -> Document:
        """获取单个文档的完整内容"""
