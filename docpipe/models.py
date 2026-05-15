from __future__ import annotations

from dataclasses import dataclass, field


class SkipDocument(Exception):
    """Source 发出此异常表示该文档应跳过"""


@dataclass
class DocumentMeta:
    id: str
    title: str
    path: str
    hash: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class Document:
    meta: DocumentMeta
    content: str | bytes
    content_type: str = "markdown"
