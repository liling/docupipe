from __future__ import annotations

from pathlib import Path

import pytest

from dwsdocs_downloader.converter import FileConverter


@pytest.fixture
def converter():
    return FileConverter()


def test_convert_text_file(converter, tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("Hello World", encoding="utf-8")
    result = converter.convert(f)
    assert "Hello World" in result.markdown


def test_convert_md_file(converter, tmp_path):
    f = tmp_path / "test.md"
    f.write_text("# Title\n\nSome text", encoding="utf-8")
    result = converter.convert(f)
    assert "# Title" in result.markdown


def test_is_convertible(converter):
    assert converter.is_convertible("document.pdf")
    assert converter.is_convertible("sheet.xlsx")
    assert converter.is_convertible("report.docx")
    assert converter.is_convertible("data.pptx")
    assert not converter.is_convertible("image.png")
    assert not converter.is_convertible("video.mp4")


def test_convert_nonexistent_raises(converter):
    with pytest.raises(FileNotFoundError):
        converter.convert(Path("/nonexistent/file.pdf"))
