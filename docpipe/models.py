from __future__ import annotations

from dataclasses import dataclass, field


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
