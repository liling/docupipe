from __future__ import annotations

from pathlib import Path
from typing import Any

from markitdown import MarkItDown

_CONVERTIBLE_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt",
    ".html", ".htm", ".csv", ".json", ".xml", ".txt", ".md",
    ".rtf", ".odt", ".ods",
}


class FileConverter:
    def __init__(self):
        self._md = MarkItDown()

    def is_convertible(self, filename: str) -> bool:
        ext = Path(filename).suffix.lower()
        return ext in _CONVERTIBLE_EXTENSIONS

    def convert(self, file_path: Path) -> Any:
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        result = self._md.convert(str(file_path))
        return result
