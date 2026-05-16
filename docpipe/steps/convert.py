from __future__ import annotations

import base64
import logging
import re
import tempfile
from pathlib import Path

from docpipe.models import Document
from docpipe.steps import register_step
from docpipe.steps.base import PipelineStep

logger = logging.getLogger(__name__)


@register_step("convert")
class ConvertStep(PipelineStep):
    def __init__(self, extension_rules: dict[str, str] | None = None, **kwargs):
        self._extension_rules = extension_rules or {}

    def needs_conversion(self, doc: Document) -> bool:
        ext = doc.meta.extra.get("extension", "")
        key = f".{ext}" if ext else ""
        rule = self._extension_rules.get(key)
        return rule is not None and rule != "source"

    def process(self, doc: Document) -> Document:
        ext = doc.meta.extra.get("extension", "")
        key = f".{ext}" if ext else ""
        converter_name = self._extension_rules.get(key)

        if not converter_name or converter_name == "source":
            return doc

        from docpipe.converters import get_converter
        converter_cls = get_converter(converter_name)
        converter = converter_cls()

        file_path = doc.meta.extra.get("_temp_file") or doc.meta.extra.get("absolute_path")
        if not file_path:
            logger.warning("convert step: 无文件路径，跳过转换: %s", doc.meta.title)
            return doc

        file_path = Path(file_path)
        try:
            doc.content = converter.convert(file_path)
            doc.content_type = "markdown"
        finally:
            if doc.meta.extra.get("_temp_file"):
                file_path.unlink(missing_ok=True)

        if isinstance(doc.content, str):
            doc.content = self._extract_inline_images(doc)

        return doc

    def _extract_inline_images(self, doc: Document) -> str:
        """将 markdown 中的 data:image base64 内联图片提取到磁盘，替换为相对路径"""
        content = doc.content
        if not isinstance(content, str) or "data:image" not in content:
            return content

        tmp_dir = tempfile.mkdtemp(prefix="docpipe_images_")
        images_dir = Path(tmp_dir) / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        doc.meta.extra["_images_dir"] = str(Path(tmp_dir))

        pattern = r'!\[([^\]]*)\]\((data:image/([^;]+);base64,([^)]+))\)'
        counter = 0

        def replace_inline(match: re.Match) -> str:
            nonlocal counter
            alt = match.group(1)
            mime_type = match.group(3)
            b64_data = match.group(4)

            ext = _mime_to_ext(mime_type)
            counter += 1
            filename = f"image_{counter}{ext}"
            filepath = images_dir / filename

            try:
                image_bytes = base64.b64decode(b64_data)
                filepath.write_bytes(image_bytes)
            except Exception as e:
                logger.warning("提取内联图片失败: %s", e)
                return match.group(0)

            return f"![{alt}](images/{filename})"

        new_content = re.sub(pattern, replace_inline, content)
        return new_content


def _mime_to_ext(mime: str) -> str:
    mapping = {"png": ".png", "jpeg": ".jpg", "jpg": ".jpg", "gif": ".gif", "webp": ".webp", "x-emf": ".emf"}
    return mapping.get(mime, f".{mime}")
