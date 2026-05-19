from __future__ import annotations

import hashlib
import json
from pathlib import Path

from docupipe.models import Bundle, BundleMeta, FileItem
from docupipe.sources import register_source
from docupipe.sources.base import SourceBase
from docupipe.utils import guess_mime_type


_TEXT_EXTENSIONS = frozenset({
    "md", "markdown", "mdown", "mkd",
    "txt", "csv", "tsv",
    "json", "yaml", "yml", "toml", "ini", "cfg",
    "xml", "html", "htm", "css", "js", "ts",
    "py", "rb", "go", "rs", "java", "c", "cpp", "h",
    "sh", "bash", "zsh",
    "log", "rst", "adoc",
})


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

    def list(self) -> list[BundleMeta]:
        result = []
        for f in sorted(self._input_dir.rglob("*")):
            if not f.is_file():
                continue

            relative = f.relative_to(self._input_dir)

            if any(part.startswith(".") for part in relative.parts):
                continue
            if not f.suffix:
                continue

            rel_str = str(relative)

            if not self._matches_filters(rel_str):
                continue

            file_hash = hashlib.sha256(f.read_bytes()).hexdigest()
            ext = f.suffix.lstrip(".")
            extra = {
                "extension": ext,
                "absolute_path": str(f),
                "size": f.stat().st_size,
                "mtime": int(f.stat().st_mtime * 1000),
            }

            doc_id = file_hash
            sidecar_path = Path(str(f) + ".json")
            if sidecar_path.exists():
                try:
                    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
                    if sidecar.get("id"):
                        doc_id = sidecar["id"]
                    for k in ("title", "content_type", "extension", "dingtalk_extension",
                              "space_name", "relative_path", "full_path"):
                        if k in sidecar:
                            extra[k] = sidecar[k]
                except (json.JSONDecodeError, OSError):
                    pass

            result.append(BundleMeta(
                id=doc_id,
                title=f.stem,
                path=rel_str,
                hash=file_hash,
                extra=extra,
            ))
        return result

    def fetch(self, meta: BundleMeta) -> Bundle:
        abs_path = Path(meta.extra["absolute_path"])
        extension = meta.extra.get("extension", "")

        if extension in _TEXT_EXTENSIONS:
            content = abs_path.read_text(encoding="utf-8")
        else:
            content = abs_path.read_bytes()

        content_type = guess_mime_type(extension) if extension else ""

        return Bundle(
            files=[FileItem(
                name=Path(meta.path).name,
                content=content,
                content_type=content_type,
                role="main",
            )],
            context=dict(meta.extra),
        )

    def supported_change_detection(self) -> list[str]:
        return ["mtime", "hash"]

    def delete(self, doc_id: str) -> None:
        """按 doc_id（content hash）查找并删除文件"""
        metas = self.list()
        for meta in metas:
            if meta.id == doc_id:
                abs_path = meta.extra.get("absolute_path", "")
                if abs_path and Path(abs_path).exists():
                    Path(abs_path).unlink()
                return

    def _matches_filters(self, rel_path: str) -> bool:
        if rel_path.endswith(".json"):
            main_file = rel_path[:-5]
            if (self._input_dir / main_file).exists():
                return False
        if self._exclude and self._glob_matches(rel_path, self._exclude):
            return False
        if self._include and not self._glob_matches(rel_path, self._include):
            return False
        return True

    @staticmethod
    def _glob_matches(path: str, patterns: list[str]) -> bool:
        p = Path(path)
        return any(p.match(pattern) for pattern in patterns)
