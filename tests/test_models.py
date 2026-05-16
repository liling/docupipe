from __future__ import annotations

import pytest
from docupipe.models import FileItem, Bundle, BundleMeta, SkipBundle


class TestFileItem:
    def test_defaults(self):
        f = FileItem(name="a.md", content="hello")
        assert f.content_type == ""
        assert f.role == "main"
        assert f.metadata == {}

    def test_with_all_fields(self):
        f = FileItem(name="img.png", content=b"\x89PNG", content_type="image/png",
                     role="image", metadata={"description": "a diagram"})
        assert f.role == "image"
        assert isinstance(f.content, bytes)


class TestBundle:
    def test_empty_bundle(self):
        b = Bundle()
        assert b.files == []
        assert b.context == {}
        assert b.main is None

    def test_main_returns_first_main_role(self):
        b = Bundle(files=[
            FileItem(name="img.png", content=b"", role="image"),
            FileItem(name="doc.md", content="hello", role="main"),
        ])
        assert b.main is not None
        assert b.main.name == "doc.md"

    def test_main_returns_none_when_no_main(self):
        b = Bundle(files=[
            FileItem(name="img.png", content=b"", role="image"),
        ])
        assert b.main is None

    def test_get_by_role(self):
        b = Bundle(files=[
            FileItem(name="a.png", content=b"", role="image"),
            FileItem(name="b.png", content=b"", role="image"),
            FileItem(name="doc.md", content="", role="main"),
        ])
        images = b.get_by_role("image")
        assert len(images) == 2
        assert images[0].name == "a.png"

    def test_add_no_conflict(self):
        b = Bundle()
        b.add(FileItem(name="a.md", content="hello"))
        assert len(b.files) == 1
        assert b.files[0].name == "a.md"

    def test_add_auto_rename_on_conflict(self):
        b = Bundle(files=[FileItem(name="image.png", content=b"")])
        b.add(FileItem(name="image.png", content=b"\x89"))
        assert len(b.files) == 2
        assert b.files[0].name == "image.png"
        assert b.files[1].name == "image_1.png"

    def test_add_auto_rename_sequential(self):
        b = Bundle(files=[
            FileItem(name="image.png", content=b""),
            FileItem(name="image_1.png", content=b""),
        ])
        b.add(FileItem(name="image.png", content=b"\x89"))
        assert b.files[2].name == "image_2.png"

    def test_remove_by_name(self):
        b = Bundle(files=[
            FileItem(name="a.md", content=""),
            FileItem(name="b.md", content=""),
        ])
        b.remove("a.md")
        assert len(b.files) == 1
        assert b.files[0].name == "b.md"

    def test_remove_nonexistent_noop(self):
        b = Bundle(files=[FileItem(name="a.md", content="")])
        b.remove("z.md")
        assert len(b.files) == 1


class TestBundleMeta:
    def test_defaults(self):
        m = BundleMeta(id="1", title="test")
        assert m.hash == ""
        assert m.extra == {}


class TestSkipBundle:
    def test_is_exception(self):
        with pytest.raises(SkipBundle):
            raise SkipBundle("skip this")