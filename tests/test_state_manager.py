from __future__ import annotations

import hashlib

from docupipe.state import StateManager, content_hash, bundle_hash
from docupipe.models import Bundle, FileItem


class TestStateManager:
    def test_save_and_load(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.save({"a": {"hash": "hash1", "path": ""}, "b": {"hash": "hash2", "path": "x/y"}})
        assert sm.load() == {"a": {"hash": "hash1", "path": ""}, "b": {"hash": "hash2", "path": "x/y"}}

    def test_load_old_format(self, tmp_path):
        p = tmp_path / "state.json"
        p.write_text('{"a": "h1", "b": "h2"}', encoding="utf-8")
        sm = StateManager(p)
        assert sm.load() == {"a": {"hash": "h1", "path": "", "status": "done"}, "b": {"hash": "h2", "path": "", "status": "done"}}

    def test_load_empty(self, tmp_path):
        sm = StateManager(tmp_path / "nonexistent.json")
        assert sm.load() == {}

    def test_is_processed(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.save({"a": {"hash": "h1", "path": "", "status": "done"}})
        assert sm.is_processed("a")
        assert not sm.is_processed("b")

    def test_is_unchanged(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.save({"a": {"hash": "h1", "path": ""}})
        assert sm.is_unchanged("a", "h1")
        assert not sm.is_unchanged("a", "h2")
        assert not sm.is_unchanged("b", "h1")

    def test_find_removed(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.save({"a": {"hash": "h1", "path": ""}, "b": {"hash": "h2", "path": ""}, "c": {"hash": "h3", "path": ""}})
        removed = sm.find_removed(["a", "c"])
        assert removed == ["b"]

    def test_mark_removed(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.save({"a": {"hash": "h1", "path": ""}, "b": {"hash": "h2", "path": ""}})
        sm.mark_removed("a")
        assert sm.load() == {"b": {"hash": "h2", "path": ""}}

    def test_mark_done_stores_path(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.mark_done("a", "h1", "产品规划/方案")
        assert sm.get_path("a") == "产品规划/方案"
        assert sm.is_unchanged("a", "h1")

    def test_mark_done_with_mtime(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.mark_done("a", "h1", "path/a", mtime=1713571200000)
        entry = sm.load()["a"]
        assert entry["status"] == "done"
        assert entry["hash"] == "h1"
        assert entry["path"] == "path/a"
        assert entry["mtime"] == 1713571200000

    def test_get_mtime(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.mark_done("a", "h1", "path/a", mtime=1713571200000)
        assert sm.get_mtime("a") == 1713571200000

    def test_get_mtime_missing(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        assert sm.get_mtime("nonexistent") is None

    def test_is_mtime_unchanged(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.mark_done("a", "h1", "path/a", mtime=100)
        assert sm.is_mtime_unchanged("a", 100)
        assert not sm.is_mtime_unchanged("a", 200)
        assert not sm.is_mtime_unchanged("b", 100)

    def test_mark_pending(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.mark_pending([("id1", "path/a", "A", {"ext": "md"}), ("id2", "path/b", "B", {})])
        entries = sm.load()
        assert entries["id1"]["status"] == "pending"
        assert entries["id1"]["path"] == "path/a"
        assert entries["id1"]["title"] == "A"
        assert entries["id1"]["fetch_extra"] == {"ext": "md"}
        assert entries["id2"]["status"] == "pending"

    def test_find_pending(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.mark_pending([("id1", "path/a", "A", {})])
        sm.mark_done("id1", "h1", "path/a")
        sm.mark_pending([("id2", "path/b", "B", {})])
        pending = sm.find_pending()
        assert len(pending) == 1
        assert pending[0][0] == "id2"

    def test_find_pending_returns_meta_info(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.mark_pending([("id1", "path/a", "标题A", {"ext": "md"})])
        pending = sm.find_pending()
        assert len(pending) == 1
        doc_id, title, path, fetch_extra = pending[0]
        assert doc_id == "id1"
        assert title == "标题A"
        assert path == "path/a"
        assert fetch_extra == {"ext": "md"}


class TestContentHash:
    def test_string_hash(self):
        h = content_hash("hello")
        expected = hashlib.sha256(b"hello").hexdigest()
        assert h == expected

    def test_bytes_hash(self):
        h = content_hash(b"hello")
        expected = hashlib.sha256(b"hello").hexdigest()
        assert h == expected


class TestBundleHash:
    def test_bundle_hash_from_main_content(self):
        bundle = Bundle(
            files=[FileItem(name="test.md", content="# Hello\n\nWorld", content_type="text/markdown", role="main")],
            context={},
        )
        h = bundle_hash(bundle)
        expected = hashlib.sha256(b"# Hello\n\nWorld").hexdigest()
        assert h == expected

    def test_bundle_hash_empty_bundle(self):
        bundle = Bundle(files=[], context={})
        assert bundle_hash(bundle) == ""

    def test_bundle_hash_bytes_content(self):
        bundle = Bundle(
            files=[FileItem(name="test.pdf", content=b"binary data", content_type="application/pdf", role="main")],
            context={},
        )
        h = bundle_hash(bundle)
        expected = hashlib.sha256(b"binary data").hexdigest()
        assert h == expected
