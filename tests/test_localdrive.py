from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from docupipe.models import Bundle, FileItem
from docupipe.sources.localdrive import LocalDriveSource
from docupipe.destinations.localdrive import LocalDriveDestination


class TestLocalDriveSource:
    def test_list_all_file_types(self, tmp_path):
        (tmp_path / "a.md").write_text("hello a")
        (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4 fake")
        (tmp_path / "c.docx").write_bytes(b"PK fake docx")
        (tmp_path / "d.txt").write_text("plain text")

        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        titles = {m.title for m in metas}
        assert titles == {"a", "b", "c", "d"}

    def test_list_skips_hidden_dirs_and_files(self, tmp_path):
        (tmp_path / "visible.md").write_text("seen")
        hidden_dir = tmp_path / ".hidden_dir"
        hidden_dir.mkdir()
        (hidden_dir / "secret.md").write_text("hidden dir file")
        (tmp_path / ".hidden.md").write_text("hidden file")

        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        assert len(metas) == 1
        assert metas[0].title == "visible"

    def test_list_skips_no_extension(self, tmp_path):
        (tmp_path / "README").write_text("no extension")
        (tmp_path / "guide.md").write_text("has extension")

        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        assert len(metas) == 1
        assert metas[0].title == "guide"

    def test_list_recursive(self, tmp_path):
        sub = tmp_path / "sub" / "dir"
        sub.mkdir(parents=True)
        (tmp_path / "root.md").write_text("root")
        (sub / "deep.md").write_text("deep")

        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        paths = {m.path for m in metas}
        assert "root.md" in paths
        assert str(Path("sub") / "dir" / "deep.md") in paths

    def test_invalid_dir_raises(self):
        with pytest.raises(ValueError, match="目录不存在"):
            LocalDriveSource(input_dir="/nonexistent/path")

    def test_fetch_text_file(self, tmp_path):
        (tmp_path / "test.md").write_text("hello world", encoding="utf-8")

        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        bundle = source.fetch(metas[0])
        assert isinstance(bundle.main.content, str)
        assert bundle.main.content == "hello world"
        assert bundle.main.content_type == "text/markdown"

    def test_fetch_binary_file(self, tmp_path):
        (tmp_path / "test.pdf").write_bytes(b"%PDF-1.4 fake content")

        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        bundle = source.fetch(metas[0])
        assert isinstance(bundle.main.content, bytes)
        assert bundle.main.content_type == "application/pdf"

    def test_fetch_metadata(self, tmp_path):
        (tmp_path / "report.pdf").write_bytes(b"%PDF fake")

        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        assert metas[0].title == "report"
        assert metas[0].extra["extension"] == "pdf"
        assert metas[0].extra["size"] > 0
        assert "report.pdf" in metas[0].path

    def test_include_filter(self, tmp_path):
        (tmp_path / "a.md").write_text("md")
        (tmp_path / "b.pdf").write_bytes(b"pdf")
        (tmp_path / "c.docx").write_bytes(b"docx")

        source = LocalDriveSource(input_dir=str(tmp_path), include=["*.md", "*.pdf"])
        metas = source.list()
        titles = {m.title for m in metas}
        assert titles == {"a", "b"}

    def test_exclude_filter(self, tmp_path):
        (tmp_path / "a.md").write_text("md")
        (tmp_path / "b.pdf").write_bytes(b"pdf")
        (tmp_path / "c.docx").write_bytes(b"docx")

        source = LocalDriveSource(input_dir=str(tmp_path), exclude=["*.pdf"])
        metas = source.list()
        titles = {m.title for m in metas}
        assert titles == {"a", "c"}

    def test_exclude_overrides_include(self, tmp_path):
        (tmp_path / "a.md").write_text("md")
        (tmp_path / "b.pdf").write_bytes(b"pdf")

        source = LocalDriveSource(
            input_dir=str(tmp_path),
            include=["*.md", "*.pdf"],
            exclude=["*.pdf"],
        )
        metas = source.list()
        titles = {m.title for m in metas}
        assert titles == {"a"}

    def test_no_filters_includes_all(self, tmp_path):
        (tmp_path / "a.md").write_text("md")
        (tmp_path / "b.pdf").write_bytes(b"pdf")
        (tmp_path / "c.py").write_text("print('hi')")

        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        assert len(metas) == 3


class TestLocalDriveDestination:
    def test_write_creates_file_and_sidecar(self, tmp_path):
        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))
        bundle = Bundle(
            files=[FileItem(name="方案.md", content="# 方案内容", content_type="text/markdown", role="main")],
            context={
                "id": "node1",
                "title": "方案",
                "path": "产品规划/方案",
                "hash": "abc123",
                "space_name": "知识库A",
                "dingtalk_content_type": "ALIDOC",
                "extension": "md",
            },
        )

        result = dest.write(bundle)

        expected_file = output_dir / "产品规划" / "方案.md"
        assert expected_file.exists()
        assert expected_file.read_text(encoding="utf-8") == "# 方案内容"

        sidecar = expected_file.parent / "方案.md.json"
        assert sidecar.exists()
        meta_json = json.loads(sidecar.read_text(encoding="utf-8"))
        assert meta_json["id"] == "node1"
        assert meta_json["title"] == "方案"
        assert meta_json["space_name"] == "知识库A"
        assert meta_json["relative_path"] == "产品规划/方案"
        assert meta_json["full_path"] == "产品规划/方案"
        assert meta_json["content_hash"] == "abc123"

        assert result == str(expected_file)

    def test_write_with_attachments(self, tmp_path):
        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))

        bundle = Bundle(
            files=[
                FileItem(name="文档.md", content="# 文档\n\n![图片](图片.png)", content_type="text/markdown", role="main"),
                FileItem(name="图片.png", content=b"fake-png-data", content_type="image/png", role="attachment"),
            ],
            context={
                "id": "node1",
                "title": "文档",
                "path": "文档",
                "hash": "def456",
                "space_name": "知识库A",
            },
        )

        result = dest.write(bundle)

        main_file = output_dir / "文档.md"
        assert main_file.exists()
        assert main_file.read_text(encoding="utf-8") == "# 文档\n\n![图片](图片.png)"

        image_file = output_dir / "图片.png"
        assert image_file.exists()
        assert image_file.read_bytes() == b"fake-png-data"

        assert result == str(main_file)

    def test_write_skips_unchanged(self, tmp_path):
        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))
        bundle = Bundle(
            files=[FileItem(name="A.md", content="hello", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "A", "path": "A", "hash": "h1", "space_name": "S"},
        )

        dest.write(bundle)
        file_path = output_dir / "A.md"
        mtime1 = file_path.stat().st_mtime

        time.sleep(0.05)

        dest2 = LocalDriveDestination(output_dir=str(output_dir))
        dest2.write(bundle)
        mtime2 = file_path.stat().st_mtime

        assert mtime1 == mtime2

    def test_write_overwrites_changed(self, tmp_path):
        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))
        bundle1 = Bundle(
            files=[FileItem(name="A.md", content="old content", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "A", "path": "A", "hash": "h1", "space_name": "S"},
        )
        dest.write(bundle1)

        bundle2 = Bundle(
            files=[FileItem(name="A.md", content="new content", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "A", "path": "A", "hash": "h2", "space_name": "S"},
        )
        dest.write(bundle2)

        file_path = output_dir / "A.md"
        assert file_path.read_text(encoding="utf-8") == "new content"

    def test_remove_deletes_file_and_sidecar(self, tmp_path):
        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))
        bundle = Bundle(
            files=[FileItem(name="A.md", content="hello", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "A", "path": "A", "hash": "h1", "space_name": "S"},
        )

        file_path = dest.write(bundle)
        assert Path(file_path).exists()

        dest.remove_by_path(file_path)
        assert not Path(file_path).exists()
        assert not Path(file_path + ".json").exists()

    def test_remove_nonexistent_file_no_error(self, tmp_path):
        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))
        dest.remove_by_path(str(output_dir / "nonexistent.md"))


class TestLocalDrivePathTemplate:
    def test_default_uses_context_path(self, tmp_path):
        dest = LocalDriveDestination(output_dir=str(tmp_path))
        bundle = Bundle(
            files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "t", "path": "folder/doc", "extension": "md"},
        )
        path = dest._resolve_path(bundle)
        assert path == tmp_path / "folder" / "doc.md"

    def test_path_template_overrides_context_path(self, tmp_path):
        dest = LocalDriveDestination(output_dir=str(tmp_path), path_template="custom/name")
        bundle = Bundle(
            files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "t", "path": "folder/doc", "extension": "md"},
        )
        path = dest._resolve_path(bundle)
        assert path == tmp_path / "custom" / "name.md"

    def test_no_space_name_prefix(self, tmp_path):
        dest = LocalDriveDestination(output_dir=str(tmp_path))
        bundle = Bundle(
            files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "t", "path": "doc", "extension": "md", "space_name": "我的空间"},
        )
        path = dest._resolve_path(bundle)
        assert path == tmp_path / "doc.md"
        assert "我的空间" not in str(path)

    def test_path_template_with_context_filename_via_update_config(self, tmp_path):
        dest = LocalDriveDestination(output_dir=str(tmp_path), path_template="${context.filename}")
        bundle = Bundle(
            files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "t", "path": "folder/doc", "filename": "doc", "extension": "md"},
        )
        from docupipe.config import resolve_context_vars
        resolved = resolve_context_vars({"path_template": dest._path_template}, bundle.context)
        dest.update_config(resolved)
        path = dest._resolve_path(bundle)
        assert path == tmp_path / "doc.md"
