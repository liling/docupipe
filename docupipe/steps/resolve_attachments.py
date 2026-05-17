from __future__ import annotations

import logging
import re
from pathlib import Path

from docupipe.models import Bundle, FileItem
from docupipe.steps import register_step
from docupipe.steps.base import Step

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico", ".emf"})
_REF_PATTERN = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')
_EXTERNAL_PREFIXES = ("http://", "https://", "#", "data:", "mailto:")


def _guess_content_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    return f"image/{ext.lstrip('.')}" if ext in _IMAGE_EXTENSIONS else ""


def _read_file(path: Path) -> tuple[str | bytes, str]:
    ext = path.suffix.lower()
    binary_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".emf", ".wmf",
                   ".x-wmf", ".pdf", ".zip", ".tar", ".gz", ".doc", ".docx", ".ppt", ".pptx",
                   ".xls", ".xlsx"}
    if ext in binary_exts:
        return path.read_bytes(), "application/octet-stream"
    return path.read_text(encoding="utf-8"), "text/plain"


@register_step("resolve_attachments")
class ResolveAttachmentsStep(Step):
    def __init__(self, **kwargs):
        pass

    def process(self, bundle: Bundle) -> Bundle:
        main = bundle.main
        if not main or not isinstance(main.content, str):
            return bundle

        abs_path = bundle.context.get("absolute_path")
        if not abs_path:
            logger.warning("resolve_attachments: context 中未找到 absolute_path，跳过")
            return bundle

        base_dir = Path(abs_path).parent
        content = main.content

        seen = set()
        for match in _REF_PATTERN.finditer(content):
            ref_path = match.group(2)
            if ref_path.startswith(_EXTERNAL_PREFIXES):
                continue
            if ref_path in seen:
                continue
            seen.add(ref_path)

            file_path = base_dir / ref_path
            if not file_path.exists():
                logger.warning("resolve_attachments: 文件不存在: %s", file_path)
                continue

            data, content_type = _read_file(file_path)
            ext = Path(ref_path).suffix.lower()
            role = "image" if ext in _IMAGE_EXTENSIONS else "attachment"

            item = FileItem(
                name=ref_path,
                content=data,
                content_type=_guess_content_type(ref_path) or content_type,
                role=role,
            )
            bundle.add(item)

        return bundle
