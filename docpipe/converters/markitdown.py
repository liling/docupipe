from __future__ import annotations

import logging
from pathlib import Path

from docpipe.converters import register_converter
from docpipe.converters.base import ConverterBase

logger = logging.getLogger(__name__)


@register_converter("markitdown")
class MarkitdownConverter(ConverterBase):
    name = "markitdown"

    def convert(self, file_path: Path) -> str:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(str(file_path))
        logger.debug("markitdown 转换完成: %s, 长度=%d", file_path.name, len(result.markdown))
        return result.markdown
