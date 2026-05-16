from __future__ import annotations

import hashlib
from pathlib import Path

from docpipe.models import Document, DocumentMeta
from docpipe.sources import register_source
from docpipe.sources.base import SourceBase


@register_source("localdrive")
class LocalDriveSource(SourceBase):
    def __init__(
        self,
        input_dir: str,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        **kwargs,
    ):
        self._input_dir = Path(input_dir)
        if not self._input_dir.is_dir():
            raise ValueError(f"目录不存在: {input_dir}")
        self._include = include or []
        self._exclude = exclude or []

    def list_documents(self) -> list[DocumentMeta]:
        result = []
        for f in sorted(self._input_dir.rglob("*")):
            if not f.is_file():
                continue

            relative = f.relative_to(self._input_dir)

            # 跳过隐藏文件和隐藏目录中的文件
            if any(part.startswith(".") for part in relative.parts):
                continue
            # 跳过无扩展名文件
            if not f.suffix:
                continue

            rel_str = str(relative)

            if not self._matches_filters(rel_str):
                continue

            file_hash = hashlib.sha256(f.read_bytes()).hexdigest()
            result.append(DocumentMeta(
                id=file_hash,
                title=f.stem,
                path=rel_str,
                hash=file_hash,
                extra={
                    "contentType": f.suffix.lstrip("."),
                    "extension": f.suffix.lstrip("."),
                    "absolute_path": str(f),
                    "size": f.stat().st_size,
                },
            ))
        return result

    def fetch(self, doc_meta: DocumentMeta) -> Document:
        f = Path(doc_meta.extra["absolute_path"])
        extension = doc_meta.extra.get("extension", "")

        if extension in _TEXT_EXTENSIONS:
            content = f.read_text(encoding="utf-8")
        else:
            content = f.read_bytes()

        return Document(
            meta=doc_meta,
            content=content,
            content_type=extension,
        )

    def _matches_filters(self, rel_path: str) -> bool:
        # 跳过 sidecar .json 文件（与其同名主文件配对的元数据文件）
        if rel_path.endswith(".json"):
            main_file = rel_path[:-5]  # 去掉 .json
            if (self._input_dir / main_file).exists():
                return False
        # exclude 优先
        if self._exclude and self._glob_matches(rel_path, self._exclude):
            return False
        # exclude 优先
        if self._exclude and self._glob_matches(rel_path, self._exclude):
            return False
        # include 为空表示包含所有
        if self._include and not self._glob_matches(rel_path, self._include):
            return False
        return True

    @staticmethod
    def _glob_matches(path: str, patterns: list[str]) -> bool:
        p = Path(path)
        return any(p.match(pattern) for pattern in patterns)


_TEXT_EXTENSIONS = frozenset({
    "md", "markdown", "mdown", "mkd",
    "txt", "csv", "tsv",
    "json", "yaml", "yml", "toml", "ini", "cfg",
    "xml", "html", "htm", "css", "js", "ts",
    "py", "rb", "go", "rs", "java", "c", "cpp", "h",
    "sh", "bash", "zsh",
    "log", "rst", "adoc",
})
