from __future__ import annotations

import logging
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

        return doc
