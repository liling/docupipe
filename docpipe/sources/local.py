from __future__ import annotations

import hashlib
from pathlib import Path

from docpipe.models import Document, DocumentMeta
from docpipe.sources import register_source
from docpipe.sources.base import SourceBase

_MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdown", ".mkd"}


@register_source("local")
class LocalSource(SourceBase):
    def __init__(self, input_dir: str, **kwargs):
        self._input_dir = Path(input_dir)
        if not self._input_dir.is_dir():
            raise ValueError(f"目录不存在: {input_dir}")

    def list_documents(self) -> list[DocumentMeta]:
        result = []
        for f in sorted(self._input_dir.rglob("*")):
            if f.is_file() and f.suffix.lower() in _MARKDOWN_EXTENSIONS:
                relative = f.relative_to(self._input_dir)
                file_hash = hashlib.sha256(f.read_bytes()).hexdigest()
                result.append(DocumentMeta(
                    id=str(relative),
                    title=f.stem,
                    path=str(relative),
                    hash=file_hash,
                    extra={
                        "absolute_path": str(f),
                    },
                ))
        return result

    def fetch(self, doc_meta: DocumentMeta) -> Document:
        f = self._input_dir / doc_meta.path
        content = f.read_text(encoding="utf-8")
        return Document(
            meta=doc_meta,
            content=content,
            content_type="markdown",
        )
