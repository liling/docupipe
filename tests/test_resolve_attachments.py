from __future__ import annotations

import pytest
from pathlib import Path

from docpipe.models import Bundle, FileItem
from docpipe.steps.resolve_attachments import ResolveAttachmentsStep


def _make_bundle(md_content: str, base_dir: str = "/tmp") -> Bundle:
    return Bundle(
        files=[FileItem(name="doc.md", content=md_content, content_type="text/markdown", role="main")],
        context={"absolute_path": f"{base_dir}/doc.md"},
    )


def _step() -> ResolveAttachmentsStep:
    return ResolveAttachmentsStep()


class TestResolveAttachmentsNoOp:

    def test_non_markdown_skipped(self):
        bundle = Bundle(files=[FileItem(name="doc.docx", content=b"\x00", role="main")])
        result = _step().process(bundle)
        assert len(result.files) == 1

    def test_no_absolute_path_skipped(self):
        bundle = Bundle(files=[FileItem(name="doc.md", content="hello", role="main")])
        result = _step().process(bundle)
        assert len(result.files) == 1

    def test_empty_bundle(self):
        result = _step().process(Bundle())
        assert result.files == []


class TestResolveAttachmentsLocalFiles:

    def test_image_reference(self, tmp_path):
        img = tmp_path / "images" / "photo.png"
        img.parent.mkdir()
        img.write_bytes(b"\x89PNG")

        md = "![photo](images/photo.png)\n"
        bundle = _make_bundle(md, str(tmp_path))
        result = _step().process(bundle)

        assert len(result.files) == 2
        image_item = result.files[1]
        assert image_item.role == "image"
        assert image_item.name == "images/photo.png"
        assert image_item.content == b"\x89PNG"

    def test_attachment_reference(self, tmp_path):
        pdf = tmp_path / "report.pdf"
        pdf.write_bytes(b"%PDF")

        md = "[download](report.pdf)\n"
        bundle = _make_bundle(md, str(tmp_path))
        result = _step().process(bundle)

        assert len(result.files) == 2
        att = result.files[1]
        assert att.role == "attachment"
        assert att.name == "report.pdf"

    def test_multiple_references(self, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"aaa")
        pdf = tmp_path / "b.pdf"
        pdf.write_bytes(b"bbb")

        md = "![a](a.png)\n[link](b.pdf)\n"
        bundle = _make_bundle(md, str(tmp_path))
        result = _step().process(bundle)

        assert len(result.files) == 3
        roles = [f.role for f in result.files]
        assert "image" in roles
        assert "attachment" in roles


class TestResolveAttachmentsFilter:

    def test_external_http_skipped(self, tmp_path):
        md = "![img](https://example.com/photo.png)\n"
        bundle = _make_bundle(md, str(tmp_path))
        result = _step().process(bundle)
        assert len(result.files) == 1

    def test_anchor_skipped(self, tmp_path):
        md = "[section](#intro)\n"
        bundle = _make_bundle(md, str(tmp_path))
        result = _step().process(bundle)
        assert len(result.files) == 1

    def test_data_uri_skipped(self, tmp_path):
        md = "![img](data:image/png;base64,abc)\n"
        bundle = _make_bundle(md, str(tmp_path))
        result = _step().process(bundle)
        assert len(result.files) == 1

    def test_missing_file_skipped(self, tmp_path):
        md = "![img](nonexistent.png)\n"
        bundle = _make_bundle(md, str(tmp_path))
        result = _step().process(bundle)
        assert len(result.files) == 1
