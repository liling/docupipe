from __future__ import annotations

from pathlib import Path

import pytest

from docpipe.converters import CONVERTERS, get_converter
from docpipe.converters.markitdown import MarkitdownConverter
from docpipe.converters.resolver import TypeRuleResolver


class TestMarkitdownConverter:
    def test_registered(self):
        assert "markitdown" in CONVERTERS

    def test_convert_txt(self, tmp_path):
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("hello world")
        converter = MarkitdownConverter()
        result = converter.convert(txt_file)
        assert "hello world" in result

    def test_convert_md(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("# Title\n\ncontent")
        converter = MarkitdownConverter()
        result = converter.convert(md_file)
        assert "Title" in result


class TestGetConverter:
    def test_known_converter(self):
        cls = get_converter("markitdown")
        assert cls is MarkitdownConverter

    def test_unknown_converter_raises(self):
        with pytest.raises(ValueError, match="未知的 converter"):
            get_converter("nonexistent")


class TestTypeRuleResolver:
    def test_resolve_by_extension(self):
        resolver = TypeRuleResolver(extension_rules={".pdf": "mineru", ".docx": "markitdown"})
        assert resolver.resolve(".pdf") == "mineru"
        assert resolver.resolve(".docx") == "markitdown"

    def test_resolve_unknown_returns_none(self):
        resolver = TypeRuleResolver(extension_rules={".pdf": "mineru"})
        assert resolver.resolve(".tar.gz") is None

    def test_empty_extension_returns_none(self):
        resolver = TypeRuleResolver(extension_rules={".pdf": "mineru"})
        assert resolver.resolve("") is None

    def test_resolve_by_mime(self):
        resolver = TypeRuleResolver(
            extension_rules={},
            mime_rules={"application/pdf": "mineru"},
        )
        assert resolver.resolve("", "application/pdf") == "mineru"

    def test_extension_takes_priority_over_mime(self):
        resolver = TypeRuleResolver(
            extension_rules={".pdf": "markitdown"},
            mime_rules={"application/pdf": "mineru"},
        )
        assert resolver.resolve(".pdf", "application/pdf") == "markitdown"

    def test_mime_no_match(self):
        resolver = TypeRuleResolver(
            extension_rules={},
            mime_rules={"application/pdf": "mineru"},
        )
        assert resolver.resolve(".docx", "text/plain") is None

    def test_no_mime_rules(self):
        resolver = TypeRuleResolver(extension_rules={".pdf": "mineru"})
        assert resolver.resolve(".pdf") == "mineru"
