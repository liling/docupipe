from __future__ import annotations

import json
from pathlib import Path

from docpipe.destinations import register_destination
from docpipe.destinations.base import DestinationBase
from docpipe.models import Document


@register_destination("localdrive")
class LocalDriveDestination(DestinationBase):
    def __init__(self, output_dir: str, **kwargs):
        self._output_dir = Path(output_dir)

    def write(self, doc: Document) -> str:
        file_path = self._resolve_path(doc)

        # 文件已存在且 hash 相同 → 跳过
        if file_path.exists() and doc.meta.hash:
            sidecar = Path(str(file_path) + ".json")
            if sidecar.exists():
                stored = json.loads(sidecar.read_text(encoding="utf-8"))
                if stored.get("content_hash") == doc.meta.hash:
                    return str(file_path)

        file_path.parent.mkdir(parents=True, exist_ok=True)

        content = doc.content
        if isinstance(content, bytes):
            file_path.write_bytes(content)
        else:
            file_path.write_text(content, encoding="utf-8")

        self._write_sidecar(file_path, doc)

        return str(file_path)

    def remove(self, doc_id: str) -> None:
        raise NotImplementedError("localdrive remove 需要路径信息")

    def remove_by_path(self, file_path: str) -> None:
        p = Path(file_path)
        if p.exists():
            p.unlink()
        sidecar = Path(file_path + ".json")
        if sidecar.exists():
            sidecar.unlink()

    def _resolve_path(self, doc: Document) -> Path:
        meta = doc.meta
        space_name = meta.extra.get("space_name", "")
        rel_path = meta.path

        # 追加扩展名
        ext = self._content_type_to_ext(doc.content_type)
        if ext and not rel_path.endswith(ext):
            rel_path = rel_path + ext

        if space_name:
            return self._output_dir / space_name / rel_path
        return self._output_dir / rel_path

    def _write_sidecar(self, file_path: Path, doc: Document) -> None:
        meta = doc.meta
        space_name = meta.extra.get("space_name", "")
        data = {
            "id": meta.id,
            "title": meta.title,
            "contentType": meta.extra.get("contentType", ""),
            "extension": meta.extra.get("extension", ""),
            "space_name": space_name,
            "relative_path": meta.path,
            "full_path": f"{space_name}/{meta.path}" if space_name else meta.path,
            "content_hash": meta.hash,
        }
        sidecar = Path(str(file_path) + ".json")
        sidecar.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _content_type_to_ext(content_type: str) -> str:
        mapping = {"markdown": ".md", "text": ".txt", "html": ".html"}
        mapped = mapping.get(content_type)
        if mapped:
            return mapped
        if content_type:
            return f".{content_type}"
        return ""
