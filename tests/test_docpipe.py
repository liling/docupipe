from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from docupipe.models import Bundle, BundleMeta, FileItem, SkipBundle
from docupipe.pipeline import Pipeline, StateManager, content_hash, bundle_hash
from docupipe.sources.base import SourceBase
from docupipe.destinations.base import DestinationBase


class FakeSource(SourceBase):
    name = "fake"

    def __init__(self, bundles: list[Bundle] | None = None, **kwargs):
        self._bundles = bundles or []

    def list(self) -> list[BundleMeta]:
        return [
            BundleMeta(
                id=b.context.get("id", ""),
                title=b.context.get("title", ""),
                path=b.context.get("path", ""),
                hash=bundle_hash(b),
                extra=b.context.get("extra", {}),
            )
            for b in self._bundles
        ]

    def fetch(self, meta: BundleMeta) -> Bundle:
        for b in self._bundles:
            if b.context.get("id") == meta.id:
                return b
        raise ValueError(f"Bundle not found: {meta.id}")


class FakeDestination(DestinationBase):
    name = "fake"

    def __init__(self, **kwargs):
        self.written: list[Bundle] = []
        self.removed: list[str] = []

    def remove(self, doc_id: str) -> None:
        self.removed.append(doc_id)

    def write(self, bundle: Bundle) -> str:
        self.written.append(bundle)
        return bundle.context.get("id", "")


def _make_bundle(id: str, title: str, content: str = "hello", path: str = "", **extra) -> Bundle:
    return Bundle(
        files=[FileItem(name=f"{title}.md", content=content, content_type="text/markdown", role="main")],
        context={"id": id, "title": title, "path": path or f"{title}.md", **extra},
    )


def _make_meta(id: str, title: str, content: str = "hello", path: str = "",
                mtime: int | None = None, **extra) -> BundleMeta:
    return BundleMeta(
        id=id, title=title, path=path or f"{title}.md",
        hash=content_hash(content),
        extra={"mtime": mtime, **extra} if mtime else extra,
    )


class _FakeSourceWithMeta(SourceBase):
    """支持自定义 list 结果和 mtime 的 FakeSource"""
    name = "fake"

    def __init__(self, metas: list[BundleMeta] | None = None, bundles: dict[str, Bundle] | None = None, **kwargs):
        self._metas = metas or []
        self._bundles = bundles or {}

    def list(self) -> list[BundleMeta]:
        return self._metas

    def fetch(self, meta: BundleMeta) -> Bundle:
        if meta.id in self._bundles:
            return self._bundles[meta.id]
        return _make_bundle(meta.id, meta.title, path=meta.path)

    def supported_change_detection(self) -> list[str]:
        return ["mtime", "hash"]

    def delete(self, doc_id: str) -> None:
        self._metas = [m for m in self._metas if m.id != doc_id]


class TestPipelineModes:
    def test_full_mode_processes_all(self, tmp_path):
        bundles = [_make_bundle("1", "A"), _make_bundle("2", "B")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.run(mode="full")
        assert len(dest.written) == 2
        state = pipeline.state.load()
        assert state["1"]["status"] == "done"
        assert state["2"]["status"] == "done"

    def test_full_mode_resume_skips_processed(self, tmp_path):
        bundles = [_make_bundle("1", "A"), _make_bundle("2", "B")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.run(mode="full")
        assert len(dest.written) == 2
        dest2 = FakeDestination()
        pipeline2 = Pipeline(FakeSource([]), dest2, tmp_path, pipeline_name="test")
        pipeline2.run(mode="full", resume=True)
        assert len(dest2.written) == 0

    def test_incremental_only_processes_new(self, tmp_path):
        metas = [_make_meta("1", "A", "hello"), _make_meta("2", "B", "world")]
        source = _FakeSourceWithMeta(metas)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.run(mode="incremental")
        assert len(dest.written) == 2
        metas2 = [_make_meta("1", "A", "hello"), _make_meta("2", "B", "world"), _make_meta("3", "C", "new")]
        source2 = _FakeSourceWithMeta(metas2)
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source2, dest2, tmp_path, pipeline_name="test")
        pipeline2.run(mode="incremental")
        assert len(dest2.written) == 1
        assert dest2.written[0].context["title"] == "C"

    def test_mirror_mtime_skips_unchanged(self, tmp_path):
        metas = [_make_meta("1", "A", "hello", mtime=1000)]
        source = _FakeSourceWithMeta(metas)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test", change_detection="mtime")
        pipeline.run(mode="mirror")
        assert len(dest.written) == 1
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source, dest2, tmp_path, pipeline_name="test", change_detection="mtime")
        pipeline2.run(mode="mirror")
        assert len(dest2.written) == 0

    def test_mirror_mtime_reprocesses_changed(self, tmp_path):
        metas1 = [_make_meta("1", "A", "hello", mtime=1000)]
        source1 = _FakeSourceWithMeta(metas1)
        dest = FakeDestination()
        pipeline = Pipeline(source1, dest, tmp_path, pipeline_name="test", change_detection="mtime")
        pipeline.run(mode="mirror")
        assert len(dest.written) == 1
        metas2 = [_make_meta("1", "A", "hello", mtime=2000)]
        source2 = _FakeSourceWithMeta(metas2)
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source2, dest2, tmp_path, pipeline_name="test", change_detection="mtime")
        pipeline2.run(mode="mirror")
        assert len(dest2.written) == 1

    def test_mirror_hash_skips_unchanged(self, tmp_path):
        metas = [_make_meta("1", "A", "hello")]
        source = _FakeSourceWithMeta(metas)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test", change_detection="hash")
        pipeline.run(mode="mirror")
        assert len(dest.written) == 1
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source, dest2, tmp_path, pipeline_name="test", change_detection="hash")
        pipeline2.run(mode="mirror")
        assert len(dest2.written) == 0

    def test_mirror_removes_deleted_from_dest(self, tmp_path):
        metas1 = [_make_meta("1", "A", "hello"), _make_meta("2", "B", "world")]
        source1 = _FakeSourceWithMeta(metas1)
        dest = FakeDestination()
        pipeline = Pipeline(source1, dest, tmp_path, pipeline_name="test", change_detection="mtime")
        pipeline.run(mode="mirror")
        assert len(dest.written) == 2
        metas2 = [_make_meta("1", "A", "hello")]
        source2 = _FakeSourceWithMeta(metas2)
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source2, dest2, tmp_path, pipeline_name="test", change_detection="mtime")
        pipeline2.run(mode="mirror")
        assert dest2.removed == ["2"]

    def test_mirror_delete_disabled(self, tmp_path):
        metas1 = [_make_meta("1", "A"), _make_meta("2", "B")]
        source1 = _FakeSourceWithMeta(metas1)
        dest = FakeDestination()
        pipeline = Pipeline(source1, dest, tmp_path, pipeline_name="test", change_detection="mtime", mirror_delete=False)
        pipeline.run(mode="mirror")
        metas2 = [_make_meta("1", "A")]
        source2 = _FakeSourceWithMeta(metas2)
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source2, dest2, tmp_path, pipeline_name="test", change_detection="mtime", mirror_delete=False)
        pipeline2.run(mode="mirror")
        assert dest2.removed == []

    def test_mirror_unsupported_change_detection_raises(self, tmp_path):
        source = FakeSource([])
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test", change_detection="mtime")
        with pytest.raises(ValueError, match="不支持"):
            pipeline.run(mode="mirror")

    def test_post_steps_executed_after_write(self, tmp_path):
        from docupipe.post_steps.base import PostStep
        executed = []
        class SpyPostStep(PostStep):
            name = "spy"
            def process(self, bundle):
                executed.append(bundle.context["id"])
                return bundle
        bundles = [_make_bundle("1", "A")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test", post_steps=[SpyPostStep()])
        pipeline.run(mode="full")
        assert executed == ["1"]

    def test_post_steps_not_executed_on_skip(self, tmp_path):
        from docupipe.post_steps.base import PostStep
        executed = []
        class SpyPostStep(PostStep):
            name = "spy"
            def process(self, bundle):
                executed.append(bundle.context["id"])
                return bundle
        metas = [_make_meta("1", "A", "hello", mtime=1000)]
        source = _FakeSourceWithMeta(metas)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test", change_detection="mtime", post_steps=[SpyPostStep()])
        pipeline.run(mode="mirror")
        assert len(executed) == 1
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source, dest2, tmp_path, pipeline_name="test", change_detection="mtime", post_steps=[SpyPostStep()])
        pipeline2.run(mode="mirror")
        assert len(executed) == 1

    def test_state_file_named_by_pipeline(self, tmp_path):
        bundles = [_make_bundle("1", "A")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="my-pipeline")
        pipeline.run(mode="full")
        assert (tmp_path / "my-pipeline_state.json").exists()

    def test_state_file_custom_name(self, tmp_path):
        bundles = [_make_bundle("1", "A")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test", state_file="custom.json")
        pipeline.run(mode="full")
        assert (tmp_path / "custom.json").exists()

    def test_full_resume_from_interrupted_state(self, tmp_path):
        bundles = [_make_bundle("1", "A"), _make_bundle("2", "B"), _make_bundle("3", "C")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.state.mark_done("1", "hash1", "A")
        pipeline.state.mark_pending([("2", "B", "B", {})])
        pipeline.state.mark_done("3", "hash3", "C")
        source2 = FakeSource(bundles)
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source2, dest2, tmp_path, pipeline_name="test")
        pipeline2.run(mode="full", resume=True)
        assert len(dest2.written) == 1
        assert dest2.written[0].context["title"] == "B"


class TestSourceBaseInterface:
    def test_supported_change_detection_default_empty(self):
        from docupipe.sources.base import SourceBase
        # SourceBase 默认不支持任何变更检测
        assert SourceBase.supported_change_detection is not None

    def test_delete_default_raises(self, tmp_path):
        from docupipe.sources.base import SourceBase
        source = FakeSource([])
        with pytest.raises(NotImplementedError):
            source.delete("some_id")


class TestStateManager:
    def test_save_and_load(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.save({"a": {"hash": "hash1", "path": ""}, "b": {"hash": "hash2", "path": "x/y"}})
        assert sm.load() == {"a": {"hash": "hash1", "path": ""}, "b": {"hash": "hash2", "path": "x/y"}}

    def test_load_old_format(self, tmp_path):
        """兼容旧格式：{id: hash} → {id: {"hash": hash, "path": "", "status": "done"}}"""
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


class TestPipeline:
    def test_run_writes_all(self, tmp_path):
        bundles = [_make_bundle("1", "A"), _make_bundle("2", "B")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.run()

        assert len(dest.written) == 2
        assert dest.written[0].context["title"] == "A"
        assert dest.written[1].context["title"] == "B"

    def test_run_resume_skips_processed(self, tmp_path):
        bundle = _make_bundle("1", "A")
        source = FakeSource([bundle])
        dest = FakeDestination()

        # 先跑一次
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.run()
        assert len(dest.written) == 1

        # resume 模式下跳过已处理的
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source, dest2, tmp_path, pipeline_name="test")
        pipeline2.run(mode="full", resume=True)
        assert len(dest2.written) == 0

    def test_run_sync_skips_unchanged(self, tmp_path):
        metas = [_make_meta("1", "A", "hello")]
        source = _FakeSourceWithMeta(metas)
        dest = FakeDestination()

        # 先跑一次，记录 hash
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.run()
        assert len(dest.written) == 1

        # sync 模式下跳过无变化的
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source, dest2, tmp_path, pipeline_name="test", change_detection="hash")
        pipeline2.run(mode="mirror", change_detection="hash")
        assert len(dest2.written) == 0

    def test_run_sync_removes_missing(self, tmp_path):
        # 第一次：两个文档
        metas1 = [_make_meta("1", "A", "hello"), _make_meta("2", "B", "world")]
        source1 = _FakeSourceWithMeta(metas1)
        dest = FakeDestination()
        pipeline1 = Pipeline(source1, dest, tmp_path, pipeline_name="test")
        pipeline1.run()

        # 第二次：只有一个文档，另一个应该被移除
        metas2 = [_make_meta("1", "A", "hello")]
        source2 = _FakeSourceWithMeta(metas2)
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source2, dest2, tmp_path, pipeline_name="test", change_detection="hash")
        pipeline2.run(mode="mirror", change_detection="hash")

        assert dest2.removed == ["2"]

    def test_run_dry_run(self, tmp_path):
        bundle = _make_bundle("1", "A")
        source = FakeSource([bundle])
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.run(dry_run=True)

        assert len(dest.written) == 0
        # dry_run 不应写入状态
        assert pipeline.state.load() == {}

    def test_dry_run_sync_no_state_mutation(self, tmp_path):
        """dry_run + sync 不应修改状态，连续执行结果一致"""
        metas = [_make_meta("1", "A", "hello")]
        source = _FakeSourceWithMeta(metas)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test", change_detection="hash")

        # 第一次 dry_run
        pipeline.run(mode="mirror", change_detection="hash", dry_run=True)
        assert len(dest.written) == 0
        assert len(dest.removed) == 0
        assert pipeline.state.load() == {}

        # 第二次 dry_run —— 应该和第一次行为一致
        pipeline.run(mode="mirror", change_detection="hash", dry_run=True)
        assert len(dest.written) == 0
        assert len(dest.removed) == 0
        assert pipeline.state.load() == {}

    def test_dry_run_resume_idempotent(self, tmp_path):
        """dry_run + resume 连续执行，不应因状态累积改变行为"""
        bundles = [_make_bundle("1", "A"), _make_bundle("2", "B")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")

        pipeline.run(mode="full", resume=True, dry_run=True)
        assert len(dest.written) == 0
        assert pipeline.state.load() == {}

        # 第二次 resume=True，因为状态未被 dry_run 写入，仍应处理全部文档
        pipeline.run(mode="full", resume=True, dry_run=True)
        assert len(dest.written) == 0
        assert pipeline.state.load() == {}

    def test_run_with_steps(self, tmp_path):
        """steps 模式下 pipeline 执行 steps"""
        bundles = [_make_bundle("1", "A", content="hello")]
        source = FakeSource(bundles)
        dest = FakeDestination()

        from docupipe.steps.base import Step

        class UpperStep(Step):
            name = "upper"
            def process(self, bundle):
                bundle.main.content = bundle.main.content.upper()
                return bundle

        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test", steps=[UpperStep()])
        pipeline.run()
        assert len(dest.written) == 1
        assert dest.written[0].main.content == "HELLO"

    def test_run_with_empty_steps_processes_all(self, tmp_path):
        """空 steps 列表等价于无处理"""
        bundles = [_make_bundle("1", "A")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test", steps=[])
        pipeline.run()
        assert len(dest.written) == 1


class TestRegistration:
    def test_sources_registered(self):
        from docupipe.sources import SOURCES
        assert "dingtalk" in SOURCES
        assert "localdrive" in SOURCES

    def test_destinations_registered(self):
        from docupipe.destinations import DESTINATIONS
        assert "hindsight" in DESTINATIONS

    def test_localdrive_registered(self):
        from docupipe.destinations import DESTINATIONS
        assert "localdrive" in DESTINATIONS

    def test_get_source_unknown_raises(self):
        from docupipe.sources import get_source
        with pytest.raises(ValueError, match="未知的 source"):
            get_source("nonexistent")

    def test_get_destination_unknown_raises(self):
        from docupipe.destinations import get_destination
        with pytest.raises(ValueError, match="未知的 destination"):
            get_destination("nonexistent")

    def test_mineru_converter_registered(self):
        from docupipe.converters import CONVERTERS
        assert "mineru" in CONVERTERS


class TestLocalDriveDestination:
    def test_write_creates_file_and_sidecar(self, tmp_path):
        from docupipe.destinations.localdrive import LocalDriveDestination

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
                "extension": "adoc",
            },
        )

        result = dest.write(bundle)

        # 文件已创建，路径不再包含 space_name
        expected_file = output_dir / "产品规划" / "方案.md"
        assert expected_file.exists()
        assert expected_file.read_text(encoding="utf-8") == "# 方案内容"

        # 伴生 json
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
        """测试 Bundle 带附件的场景"""
        from docupipe.destinations.localdrive import LocalDriveDestination

        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))

        # Bundle 包含主文档和图片附件
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

        # 主文件已创建（不再包含 space_name 路径）
        main_file = output_dir / "文档.md"
        assert main_file.exists()
        assert main_file.read_text(encoding="utf-8") == "# 文档\n\n![图片](图片.png)"

        # 附件已创建（与主文件同目录）
        image_file = output_dir / "图片.png"
        assert image_file.exists()
        assert image_file.read_bytes() == b"fake-png-data"

        assert result == str(main_file)

    def test_write_skips_unchanged(self, tmp_path):
        from docupipe.destinations.localdrive import LocalDriveDestination

        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))
        bundle = Bundle(
            files=[FileItem(name="A.md", content="hello", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "A", "path": "A", "hash": "h1", "space_name": "S"},
        )

        # 第一次写入（不再包含 space_name 路径）
        dest.write(bundle)
        file_path = output_dir / "A.md"
        mtime1 = file_path.stat().st_mtime

        # 修改时间不同则说明被重写了
        time.sleep(0.05)

        # 第二次写入（内容相同，hash 相同）
        dest2 = LocalDriveDestination(output_dir=str(output_dir))
        dest2.write(bundle)
        mtime2 = file_path.stat().st_mtime

        assert mtime1 == mtime2

    def test_write_overwrites_changed(self, tmp_path):
        from docupipe.destinations.localdrive import LocalDriveDestination

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
        from docupipe.destinations.localdrive import LocalDriveDestination

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
        from docupipe.destinations.localdrive import LocalDriveDestination

        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))
        # 不应抛异常
        dest.remove_by_path(str(output_dir / "nonexistent.md"))


class TestLocalDriveSource:
    def test_list_all_file_types(self, tmp_path):
        (tmp_path / "a.md").write_text("hello a")
        (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4 fake")
        (tmp_path / "c.docx").write_bytes(b"PK fake docx")
        (tmp_path / "d.txt").write_text("plain text")

        from docupipe.sources.localdrive import LocalDriveSource
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

        from docupipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        assert len(metas) == 1
        assert metas[0].title == "visible"

    def test_list_skips_no_extension(self, tmp_path):
        (tmp_path / "README").write_text("no extension")
        (tmp_path / "guide.md").write_text("has extension")

        from docupipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        assert len(metas) == 1
        assert metas[0].title == "guide"

    def test_list_recursive(self, tmp_path):
        sub = tmp_path / "sub" / "dir"
        sub.mkdir(parents=True)
        (tmp_path / "root.md").write_text("root")
        (sub / "deep.md").write_text("deep")

        from docupipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        paths = {m.path for m in metas}
        assert "root.md" in paths
        assert str(Path("sub") / "dir" / "deep.md") in paths

    def test_invalid_dir_raises(self):
        from docupipe.sources.localdrive import LocalDriveSource
        with pytest.raises(ValueError, match="目录不存在"):
            LocalDriveSource(input_dir="/nonexistent/path")

    def test_fetch_text_file(self, tmp_path):
        (tmp_path / "test.md").write_text("hello world", encoding="utf-8")

        from docupipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        bundle = source.fetch(metas[0])
        assert isinstance(bundle.main.content, str)
        assert bundle.main.content == "hello world"
        assert bundle.main.content_type == "text/markdown"

    def test_fetch_binary_file(self, tmp_path):
        (tmp_path / "test.pdf").write_bytes(b"%PDF-1.4 fake content")

        from docupipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        bundle = source.fetch(metas[0])
        assert isinstance(bundle.main.content, bytes)
        assert bundle.main.content_type == "application/pdf"

    def test_fetch_metadata(self, tmp_path):
        (tmp_path / "report.pdf").write_bytes(b"%PDF fake")

        from docupipe.sources.localdrive import LocalDriveSource
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

        from docupipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path), include=["*.md", "*.pdf"])
        metas = source.list()
        titles = {m.title for m in metas}
        assert titles == {"a", "b"}

    def test_exclude_filter(self, tmp_path):
        (tmp_path / "a.md").write_text("md")
        (tmp_path / "b.pdf").write_bytes(b"pdf")
        (tmp_path / "c.docx").write_bytes(b"docx")

        from docupipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path), exclude=["*.pdf"])
        metas = source.list()
        titles = {m.title for m in metas}
        assert titles == {"a", "c"}

    def test_exclude_overrides_include(self, tmp_path):
        (tmp_path / "a.md").write_text("md")
        (tmp_path / "b.pdf").write_bytes(b"pdf")

        from docupipe.sources.localdrive import LocalDriveSource
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

        from docupipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        assert len(metas) == 3


class TestEnvInterpolation:
    def test_resolve_simple(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "secret123")
        from docupipe.config import resolve_env_vars
        assert resolve_env_vars("${MY_KEY}") == "secret123"

    def test_resolve_with_default(self, monkeypatch):
        monkeypatch.delenv("MISSING_KEY", raising=False)
        from docupipe.config import resolve_env_vars
        assert resolve_env_vars("${MISSING_KEY:-fallback}") == "fallback"

    def test_resolve_existing_overrides_default(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "actual")
        from docupipe.config import resolve_env_vars
        assert resolve_env_vars("${MY_KEY:-fallback}") == "actual"

    def test_resolve_missing_no_default_keeps_original(self):
        from docupipe.config import resolve_env_vars
        assert resolve_env_vars("${NONEXISTENT_VAR_XYZ}") == "${NONEXISTENT_VAR_XYZ}"

    def test_resolve_nested_dict(self, monkeypatch):
        monkeypatch.setenv("URL", "http://localhost")
        from docupipe.config import resolve_env_vars
        config = {"api_url": "${URL}", "nested": {"key": "${URL}/path"}}
        result = resolve_env_vars(config)
        assert result == {"api_url": "http://localhost", "nested": {"key": "http://localhost/path"}}

    def test_resolve_in_list(self, monkeypatch):
        monkeypatch.setenv("KEY", "val")
        from docupipe.config import resolve_env_vars
        assert resolve_env_vars(["${KEY}", "plain"]) == ["val", "plain"]

    def test_resolve_non_string_unchanged(self):
        from docupipe.config import resolve_env_vars
        assert resolve_env_vars(42) == 42
        assert resolve_env_vars(True) is True
        assert resolve_env_vars(None) is None

    def test_resolve_python_vars_override_env(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "from_env")
        from docupipe.config import resolve_env_vars
        result = resolve_env_vars("${MY_KEY}", variables={"MY_KEY": "from_python"})
        assert result == "from_python"

    def test_resolve_python_vars_without_env(self):
        from docupipe.config import resolve_env_vars
        result = resolve_env_vars("${MY_VAR}", variables={"MY_VAR": "python_value"})
        assert result == "python_value"

    def test_resolve_python_vars_with_default(self):
        from docupipe.config import resolve_env_vars
        result = resolve_env_vars("${MISSING:-fallback}", variables={"MISSING": "from_python"})
        assert result == "from_python"

    def test_resolve_python_vars_fallback_to_env(self, monkeypatch):
        monkeypatch.setenv("ENV_ONLY", "env_val")
        from docupipe.config import resolve_env_vars
        result = resolve_env_vars("${ENV_ONLY}", variables={"OTHER": "val"})
        assert result == "env_val"

    def test_resolve_python_vars_in_dict(self):
        from docupipe.config import resolve_env_vars
        config = {"key": "${my_var}", "nested": {"k2": "${my_var}/path"}}
        result = resolve_env_vars(config, variables={"my_var": "hello"})
        assert result == {"key": "hello", "nested": {"k2": "hello/path"}}

    def test_resolve_no_variables_same_behavior(self, monkeypatch):
        monkeypatch.setenv("KEY", "val")
        from docupipe.config import resolve_env_vars
        assert resolve_env_vars("${KEY}") == "val"
        assert resolve_env_vars("${MISSING}") == "${MISSING}"


class TestContextInterpolation:
    def test_simple_field(self):
        from docupipe.config import resolve_context_vars
        result = resolve_context_vars("hello ${context.name}", {"name": "world"})
        assert result == "hello world"

    def test_field_with_slash(self):
        from docupipe.config import resolve_context_vars
        result = resolve_context_vars("/path/${context.space_name}/file", {"space_name": "我的空间"})
        assert result == "/path/我的空间/file"

    def test_multiple_fields(self):
        from docupipe.config import resolve_context_vars
        result = resolve_context_vars("${context.a}/${context.b}", {"a": "x", "b": "y"})
        assert result == "x/y"

    def test_missing_field_keeps_original(self):
        from docupipe.config import resolve_context_vars
        result = resolve_context_vars("${context.missing}", {})
        assert result == "${context.missing}"

    def test_missing_field_with_default(self):
        from docupipe.config import resolve_context_vars
        result = resolve_context_vars("${context.missing:-fallback}", {})
        assert result == "fallback"

    def test_existing_field_overrides_default(self):
        from docupipe.config import resolve_context_vars
        result = resolve_context_vars("${context.name:-default}", {"name": "actual"})
        assert result == "actual"

    def test_none_value_keeps_original(self):
        from docupipe.config import resolve_context_vars
        result = resolve_context_vars("${context.val}", {"val": None})
        assert result == "${context.val}"

    def test_value_converted_to_string(self):
        from docupipe.config import resolve_context_vars
        result = resolve_context_vars("${context.num}", {"num": 42})
        assert result == "42"

    def test_dict_recursive(self):
        from docupipe.config import resolve_context_vars
        config = {"key": "${context.name}", "nested": {"k2": "${context.name}/path"}}
        result = resolve_context_vars(config, {"name": "hello"})
        assert result == {"key": "hello", "nested": {"k2": "hello/path"}}

    def test_list_recursive(self):
        from docupipe.config import resolve_context_vars
        result = resolve_context_vars(["${context.a}", "plain"], {"a": "val"})
        assert result == ["val", "plain"]

    def test_non_string_unchanged(self):
        from docupipe.config import resolve_context_vars
        assert resolve_context_vars(42, {}) == 42
        assert resolve_context_vars(True, {}) is True
        assert resolve_context_vars(None, {}) is None

    def test_no_context_template_unchanged(self):
        from docupipe.config import resolve_context_vars
        assert resolve_context_vars("plain text", {}) == "plain text"
        assert resolve_context_vars("${ENV_VAR}", {}) == "${ENV_VAR}"

    def test_env_var_not_touched(self):
        from docupipe.config import resolve_context_vars
        result = resolve_context_vars("${MY_VAR} ${context.name}", {"name": "x"})
        assert result == "${MY_VAR} x"


class TestExecuteVariablesScript:
    def test_inline_script_returns_dict(self):
        from docupipe.config import execute_variables_script
        raw = {"variables": {"script": "return {'today': '2026-01-01'}"}}
        result = execute_variables_script(raw)
        assert result == {"today": "2026-01-01"}

    def test_inline_script_with_import(self):
        from docupipe.config import execute_variables_script
        raw = {"variables": {"script": "import datetime\nreturn {'day': datetime.date(2026, 1, 1).isoformat()}"}}
        result = execute_variables_script(raw)
        assert result == {"day": "2026-01-01"}

    def test_script_file_reads_external_file(self, tmp_path):
        from docupipe.config import execute_variables_script
        script = tmp_path / "vars.py"
        script.write_text("return {'key': 'from_file'}\n", encoding="utf-8")
        raw = {"variables": {"script_file": str(script)}}
        result = execute_variables_script(raw)
        assert result == {"key": "from_file"}

    def test_script_file_not_found_raises(self):
        from docupipe.config import execute_variables_script
        raw = {"variables": {"script_file": "/nonexistent/vars.py"}}
        with pytest.raises(FileNotFoundError, match="script_file"):
            execute_variables_script(raw)

    def test_returns_non_dict_raises(self):
        from docupipe.config import execute_variables_script
        raw = {"variables": {"script": "return 'not a dict'"}}
        with pytest.raises(TypeError, match="dict"):
            execute_variables_script(raw)

    def test_non_string_key_raises(self):
        from docupipe.config import execute_variables_script
        raw = {"variables": {"script": "return {1: 'value'}"}}
        with pytest.raises(TypeError, match="key.*字符串"):
            execute_variables_script(raw)

    def test_value_converted_to_string(self):
        from docupipe.config import execute_variables_script
        raw = {"variables": {"script": "return {'num': 42, 'flag': True}"}}
        result = execute_variables_script(raw)
        assert result == {"num": "42", "flag": "True"}

    def test_empty_dict_returns_empty(self):
        from docupipe.config import execute_variables_script
        raw = {"variables": {"script": "return {}"}}
        result = execute_variables_script(raw)
        assert result == {}

    def test_no_variables_block_returns_empty(self):
        from docupipe.config import execute_variables_script
        assert execute_variables_script({}) == {}
        assert execute_variables_script({"pipelines": []}) == {}

    def test_no_script_or_file_returns_empty(self):
        from docupipe.config import execute_variables_script
        raw = {"variables": {}}
        assert execute_variables_script(raw) == {}

    def test_both_script_and_file_prefers_file(self, tmp_path):
        from docupipe.config import execute_variables_script
        script = tmp_path / "vars.py"
        script.write_text("return {'source': 'file'}\n", encoding="utf-8")
        raw = {"variables": {"script": "return {'source': 'inline'}", "script_file": str(script)}}
        result = execute_variables_script(raw)
        assert result == {"source": "file"}

    def test_script_exception_propagates(self):
        from docupipe.config import execute_variables_script
        raw = {"variables": {"script": "raise ValueError('boom')"}}
        with pytest.raises(ValueError, match="boom"):
            execute_variables_script(raw)


class TestDeepMerge:
    def test_simple_override(self):
        from docupipe.config import deep_merge
        assert deep_merge({"a": 1, "b": 2}, {"b": 3}) == {"a": 1, "b": 3}

    def test_nested_merge(self):
        from docupipe.config import deep_merge
        base = {"api_url": "http://default", "bank_id": "default_bank", "nested": {"a": 1, "b": 2}}
        override = {"bank_id": "my_bank", "nested": {"b": 3, "c": 4}}
        result = deep_merge(base, override)
        assert result == {"api_url": "http://default", "bank_id": "my_bank", "nested": {"a": 1, "b": 3, "c": 4}}

    def test_empty_override(self):
        from docupipe.config import deep_merge
        assert deep_merge({"a": 1}, {}) == {"a": 1}


class TestParseComponentConfig:
    def test_simple_parse(self):
        from docupipe.config import parse_component_config
        type_name, config = parse_component_config(
            {"source": {"localdrive": {"input_dir": "./docs"}}},
            {},
            "source",
        )
        assert type_name == "localdrive"
        assert config == {"input_dir": "./docs"}

    def test_merge_with_global(self):
        from docupipe.config import parse_component_config
        type_name, config = parse_component_config(
            {"destination": {"hindsight": {"bank_id": "my_bank"}}},
            {"hindsight": {"api_url": "http://default", "api_key": "secret"}},
            "destination",
        )
        assert type_name == "hindsight"
        assert config == {"api_url": "http://default", "api_key": "secret", "bank_id": "my_bank"}

    def test_missing_component_raises(self):
        from docupipe.config import parse_component_config
        import pytest
        with pytest.raises(ValueError, match="缺少"):
            parse_component_config({}, {}, "source")


class TestUpdateConfig:
    def test_destination_update_config(self):
        from docupipe.destinations.localdrive import LocalDriveDestination
        dest = LocalDriveDestination(output_dir="/old")
        dest.update_config({"output_dir": "/new"})
        assert str(dest._output_dir) == "/new"

    def test_update_config_skips_unknown_keys(self):
        from docupipe.destinations.localdrive import LocalDriveDestination
        dest = LocalDriveDestination(output_dir="/old")
        dest.update_config({"output_dir": "/new", "unknown_key": "value"})
        assert str(dest._output_dir) == "/new"
        assert not hasattr(dest, "_unknown_key")

    def test_update_config_no_attr_noop(self):
        from docupipe.destinations.localdrive import LocalDriveDestination
        dest = LocalDriveDestination(output_dir="/old")
        dest.update_config({"nonexistent": "value"})
        assert str(dest._output_dir) == "/old"


class TestLocalDrivePathTemplate:
    def test_default_uses_context_path(self, tmp_path):
        from docupipe.destinations.localdrive import LocalDriveDestination
        dest = LocalDriveDestination(output_dir=str(tmp_path))
        bundle = Bundle(
            files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "t", "path": "folder/doc", "extension": "md"},
        )
        path = dest._resolve_path(bundle)
        assert path == tmp_path / "folder" / "doc.md"

    def test_path_template_overrides_context_path(self, tmp_path):
        from docupipe.destinations.localdrive import LocalDriveDestination
        dest = LocalDriveDestination(output_dir=str(tmp_path), path_template="custom/name")
        bundle = Bundle(
            files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "t", "path": "folder/doc", "extension": "md"},
        )
        path = dest._resolve_path(bundle)
        assert path == tmp_path / "custom" / "name.md"

    def test_no_space_name_prefix(self, tmp_path):
        from docupipe.destinations.localdrive import LocalDriveDestination
        dest = LocalDriveDestination(output_dir=str(tmp_path))
        bundle = Bundle(
            files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "t", "path": "doc", "extension": "md", "space_name": "我的空间"},
        )
        path = dest._resolve_path(bundle)
        assert path == tmp_path / "doc.md"
        assert "我的空间" not in str(path)

    def test_path_template_with_context_filename_via_update_config(self, tmp_path):
        from docupipe.destinations.localdrive import LocalDriveDestination
        dest = LocalDriveDestination(output_dir=str(tmp_path), path_template="${context.filename}")
        bundle = Bundle(
            files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "t", "path": "folder/doc", "filename": "doc", "extension": "md"},
        )
        # Simulate pipeline's update_config flow
        from docupipe.config import resolve_context_vars
        resolved = resolve_context_vars({"path_template": dest._path_template}, bundle.context)
        dest.update_config(resolved)
        path = dest._resolve_path(bundle)
        assert path == tmp_path / "doc.md"


class TestStepRegistry:
    def test_convert_step_registered(self):
        from docupipe.steps import STEPS
        assert "convert" in STEPS

    def test_get_step_unknown_raises(self):
        from docupipe.steps import get_step
        with pytest.raises(ValueError, match="未知的 step"):
            get_step("nonexistent")


class TestConvertStep:
    def test_needs_conversion_with_matching_extension(self):
        from docupipe.steps.convert import ConvertStep
        bundle = Bundle(
            files=[FileItem(name="t.pdf", content=b"", content_type="application/pdf", role="main")],
            context={"id": "1", "title": "t", "path": "t.pdf", "extension": "pdf"},
        )
        step = ConvertStep(extension_rules={".pdf": "markitdown"})
        assert step.needs_conversion(bundle) is True

    def test_no_conversion_without_matching_extension(self):
        from docupipe.steps.convert import ConvertStep
        bundle = Bundle(
            files=[FileItem(name="t.txt", content="hello", content_type="text/plain", role="main")],
            context={"id": "1", "title": "t", "path": "t.txt", "extension": "txt"},
        )
        step = ConvertStep(extension_rules={".pdf": "markitdown"})
        assert step.needs_conversion(bundle) is False

    def test_source_rule_skips_conversion(self):
        from docupipe.steps.convert import ConvertStep
        bundle = Bundle(
            files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "t", "path": "t.md", "extension": "md"},
        )
        step = ConvertStep(extension_rules={".md": "source"})
        assert step.needs_conversion(bundle) is False

    def test_process_no_rule_returns_unchanged(self):
        from docupipe.steps.convert import ConvertStep
        bundle = Bundle(
            files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "t", "path": "t.md", "extension": "md"},
        )
        step = ConvertStep(extension_rules={".pdf": "markitdown"})
        result = step.process(bundle)
        assert result.main.content == "hello"


class TestImageDescriptionStep:
    def test_non_text_content_skipped(self):
        """非文本内容直接跳过"""
        from docupipe.steps.image_description import ImageDescriptionStep
        step = ImageDescriptionStep(api_key="k", base_url="http://x", model="m")
        bundle = Bundle(
            files=[FileItem(name="t.pdf", content=b"binary data", content_type="application/pdf", role="main")],
            context={"id": "1", "title": "t", "path": "t.pdf"},
        )
        result = step.process(bundle)
        assert result.main.content == b"binary data"

    def test_no_images_unchanged(self):
        """无图片的 markdown 不变"""
        from docupipe.steps.image_description import ImageDescriptionStep
        step = ImageDescriptionStep(api_key="k", base_url="http://x", model="m")
        bundle = Bundle(
            files=[FileItem(name="t.md", content="# Hello\n\nNo images here.", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "t", "path": "t.md"},
        )
        result = step.process(bundle)
        assert result.main.content == "# Hello\n\nNo images here."

    def test_with_image_files_from_bundle(self, monkeypatch):
        """测试从 bundle 中获取图片文件"""
        from docupipe.steps.image_description import ImageDescriptionStep
        from docupipe.image import ImagePostProcessor, OpenAIVisionClient

        # Mock OpenAIVisionClient
        mock_vision_client = MagicMock()
        mock_vision_client.describe.return_value = ("image-1", "图片描述")
        monkeypatch.setattr("docupipe.steps.image_description.OpenAIVisionClient", lambda **kw: mock_vision_client)

        # Mock ImagePostProcessor 的 process 方法
        fake_metadata = {"image_1.png": {"description": "图片描述"}}
        original_process = None
        def mock_process(markdown, source_context, images_dir=None, image_files=None, progress_callback=None):
            # 验证 image_files 参数
            assert "images/image_1.png" in image_files
            assert image_files["images/image_1.png"].content == b"fake-image"
            return ("# 标题\n\n![image_1](images/image_1.png)", fake_metadata)

        step = ImageDescriptionStep(api_key="k", base_url="http://x", model="m")
        step._processor.process = mock_process

        bundle = Bundle(
            files=[
                FileItem(name="test.md", content="# 标题\n\n![原始引用](images/image_1.png)", content_type="text/markdown", role="main"),
                FileItem(name="images/image_1.png", content=b"fake-image", content_type="image/png", role="image"),
            ],
            context={"id": "1", "title": "测试文档", "path": "test.md"},
        )

        result = step.process(bundle)

        # 验证结果
        assert result.main.content == "# 标题\n\n![image_1](images/image_1.png)"

    def test_image_files_without_path_prefix(self, monkeypatch):
        """测试图片文件名没有路径前缀的情况（向后兼容）"""
        from docupipe.steps.image_description import ImageDescriptionStep

        # Mock OpenAIVisionClient
        mock_vision_client = MagicMock()
        mock_vision_client.describe.return_value = ("image-1", "描述")
        monkeypatch.setattr("docupipe.steps.image_description.OpenAIVisionClient", lambda **kw: mock_vision_client)

        # Mock ImagePostProcessor 的 process 方法
        fake_metadata = {"image_1.png": {"description": "描述"}}
        def mock_process(markdown, source_context, images_dir=None, image_files=None, progress_callback=None):
            # 验证 image_files 参数包含 short_name 映射
            assert "image_1.png" in image_files
            return ("# 标题\n\n![image_1](image_1.png)", fake_metadata)

        step = ImageDescriptionStep(api_key="k", base_url="http://x", model="m")
        step._processor.process = mock_process

        bundle = Bundle(
            files=[
                FileItem(name="test.md", content="# 标题\n\n![img](image_1.png)", content_type="text/markdown", role="main"),
                FileItem(name="image_1.png", content=b"fake", content_type="image/png", role="image"),
            ],
            context={"id": "1", "title": "测试", "path": "test.md"},
        )

        result = step.process(bundle)


class TestPostStepRegistry:
    def test_get_unknown_raises(self):
        from docupipe.post_steps import get_post_step
        with pytest.raises(ValueError, match="未知的 post_step"):
            get_post_step("nonexistent")

    def test_register_and_get(self):
        from docupipe.post_steps import POST_STEPS, register_post_step, get_post_step
        from docupipe.post_steps.base import PostStep

        @register_post_step("test_post")
        class _TestPost(PostStep):
            def process(self, bundle):
                return bundle

        assert "test_post" in POST_STEPS
        assert get_post_step("test_post") is _TestPost
        # 清理
        POST_STEPS.pop("test_post", None)


class TestSourceChangeDetection:
    def test_localdrive_supports_mtime_and_hash(self, tmp_path):
        from docupipe.sources.localdrive import LocalDriveSource
        (tmp_path / "test.md").write_text("hello")
        source = LocalDriveSource(input_dir=str(tmp_path))
        assert sorted(source.supported_change_detection()) == ["hash", "mtime"]

    def test_localdrive_list_provides_mtime(self, tmp_path):
        from docupipe.sources.localdrive import LocalDriveSource
        (tmp_path / "test.md").write_text("hello")
        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        assert len(metas) == 1
        assert metas[0].extra.get("mtime") is not None
        assert isinstance(metas[0].extra["mtime"], int)

    def test_dingtalk_supports_mtime_and_hash(self):
        from docupipe.sources.dingtalk import DingtalkSource
        assert "mtime" in DingtalkSource.supported_change_detection(DingtalkSource)
        assert "hash" in DingtalkSource.supported_change_detection(DingtalkSource)

    def test_tencent_supports_hash_only(self):
        from docupipe.sources.tencent import TencentSource
        assert sorted(TencentSource.supported_change_detection(TencentSource)) == ["hash"]


class TestCLIConfig:
    def test_parse_mode_from_config(self, tmp_path):
        import yaml
        config = {
            "pipelines": [{
                "name": "test",
                "mode": "incremental",
                "source": {"fake": {}},
                "destination": {"fake": {}},
            }]
        }
        path = tmp_path / "test.yaml"
        path.write_text(yaml.dump(config), encoding="utf-8")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert raw["pipelines"][0]["mode"] == "incremental"

    def test_parse_post_steps_from_config(self, tmp_path):
        import yaml
        config = {
            "pipelines": [{
                "name": "test",
                "post_steps": ["some_post_step"],
                "source": {"fake": {}},
                "destination": {"fake": {}},
            }]
        }
        path = tmp_path / "test.yaml"
        path.write_text(yaml.dump(config), encoding="utf-8")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert raw["pipelines"][0]["post_steps"] == ["some_post_step"]

    def test_parse_state_file_from_config(self, tmp_path):
        import yaml
        config = {
            "pipelines": [{
                "name": "test",
                "state_file": "custom_state.json",
                "source": {"fake": {}},
                "destination": {"fake": {}},
            }]
        }
        path = tmp_path / "test.yaml"
        path.write_text(yaml.dump(config), encoding="utf-8")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert raw["pipelines"][0]["state_file"] == "custom_state.json"