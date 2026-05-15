from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from docpipe.models import Document, DocumentMeta
from docpipe.pipeline import Pipeline, StateManager, content_hash, ContentTypeStrategy
from docpipe.sources.base import SourceBase
from docpipe.destinations.base import DestinationBase
from docpipe.converters.resolver import TypeRuleResolver


class FakeSource(SourceBase):
    name = "fake"

    def __init__(self, docs: list[Document] | None = None, **kwargs):
        self._docs = docs or []

    def list_documents(self) -> list[DocumentMeta]:
        return [d.meta for d in self._docs]

    def fetch(self, doc_meta: DocumentMeta) -> Document:
        for d in self._docs:
            if d.meta.id == doc_meta.id:
                return d
        raise ValueError(f"Document not found: {doc_meta.id}")


class FakeDestination(DestinationBase):
    name = "fake"

    def __init__(self, **kwargs):
        self.written: list[Document] = []
        self.removed: list[str] = []

    def write(self, doc: Document) -> str:
        self.written.append(doc)
        return doc.meta.id

    def remove(self, doc_id: str) -> None:
        self.removed.append(doc_id)


def _make_doc(id: str, title: str, content: str = "hello", **extra) -> Document:
    return Document(
        meta=DocumentMeta(id=id, title=title, path=f"{title}.md", hash="", extra=extra),
        content=content,
        content_type="markdown",
    )


class TestStateManager:
    def test_save_and_load(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.save({"a": "hash1", "b": "hash2"})
        assert sm.load() == {"a": "hash1", "b": "hash2"}

    def test_load_empty(self, tmp_path):
        sm = StateManager(tmp_path / "nonexistent.json")
        assert sm.load() == {}

    def test_is_processed(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.save({"a": "h1"})
        assert sm.is_processed("a")
        assert not sm.is_processed("b")

    def test_is_unchanged(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.save({"a": "h1"})
        assert sm.is_unchanged("a", "h1")
        assert not sm.is_unchanged("a", "h2")
        assert not sm.is_unchanged("b", "h1")

    def test_find_removed(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.save({"a": "h1", "b": "h2", "c": "h3"})
        removed = sm.find_removed(["a", "c"])
        assert removed == ["b"]

    def test_mark_removed(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.save({"a": "h1", "b": "h2"})
        sm.mark_removed("a")
        assert sm.load() == {"b": "h2"}


class TestContentHash:
    def test_string_hash(self):
        h = content_hash("hello")
        expected = hashlib.sha256(b"hello").hexdigest()
        assert h == expected

    def test_bytes_hash(self):
        h = content_hash(b"hello")
        expected = hashlib.sha256(b"hello").hexdigest()
        assert h == expected


class TestContentTypeStrategy:
    def test_resolve_known_type(self):
        from docpipe.pipeline import ContentTypeStrategy
        strategy = ContentTypeStrategy({"DOCUMENT": "convert", "ALIDOC": "source"})
        assert strategy.resolve("DOCUMENT") == "convert"
        assert strategy.resolve("ALIDOC") == "source"

    def test_resolve_unknown_returns_none(self):
        from docpipe.pipeline import ContentTypeStrategy
        strategy = ContentTypeStrategy({"DOCUMENT": "convert"})
        assert strategy.resolve("UNKNOWN") is None

    def test_empty_rules(self):
        from docpipe.pipeline import ContentTypeStrategy
        strategy = ContentTypeStrategy()
        assert strategy.resolve("DOCUMENT") is None

    def test_all_actions(self):
        from docpipe.pipeline import ContentTypeStrategy
        strategy = ContentTypeStrategy({
            "DOCUMENT": "convert",
            "ALIDOC": "source",
            "ARCHIVE": "skip",
            "IMAGE": "download",
        })
        assert strategy.resolve("DOCUMENT") == "convert"
        assert strategy.resolve("ALIDOC") == "source"
        assert strategy.resolve("ARCHIVE") == "skip"
        assert strategy.resolve("IMAGE") == "download"


class TestPipeline:
    def test_run_writes_all(self, tmp_path):
        docs = [_make_doc("1", "A"), _make_doc("2", "B")]
        source = FakeSource(docs)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path)
        pipeline.run()

        assert len(dest.written) == 2
        assert dest.written[0].meta.title == "A"
        assert dest.written[1].meta.title == "B"

    def test_run_resume_skips_processed(self, tmp_path):
        doc = _make_doc("1", "A")
        source = FakeSource([doc])
        dest = FakeDestination()

        # 先跑一次
        pipeline = Pipeline(source, dest, tmp_path)
        pipeline.run()
        assert len(dest.written) == 1

        # resume 模式下跳过已处理的
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source, dest2, tmp_path)
        pipeline2.run(resume=True)
        assert len(dest2.written) == 0

    def test_run_sync_skips_unchanged(self, tmp_path):
        doc = _make_doc("1", "A", content="hello")
        # 预设 hash
        doc.meta.hash = content_hash("hello")
        source = FakeSource([doc])
        dest = FakeDestination()

        # 先跑一次，记录 hash
        pipeline = Pipeline(source, dest, tmp_path)
        pipeline.run()
        assert len(dest.written) == 1

        # sync 模式下跳过无变化的
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source, dest2, tmp_path)
        pipeline2.run(sync=True)
        assert len(dest2.written) == 0

    def test_run_sync_removes_missing(self, tmp_path):
        # 第一次：两个文档
        docs1 = [_make_doc("1", "A"), _make_doc("2", "B")]
        source1 = FakeSource(docs1)
        dest = FakeDestination()
        pipeline1 = Pipeline(source1, dest, tmp_path)
        pipeline1.run()

        # 第二次：只有一个文档，另一个应该被移除
        docs2 = [_make_doc("1", "A")]
        source2 = FakeSource(docs2)
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source2, dest2, tmp_path)
        pipeline2.run(sync=True)

        assert dest2.removed == ["2"]

    def test_run_dry_run(self, tmp_path):
        doc = _make_doc("1", "A")
        source = FakeSource([doc])
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path)
        pipeline.run(dry_run=True)

        assert len(dest.written) == 0
        # 但状态应该已记录
        assert dest.written == []


class TestPipelineContentTypeStrategy:
    def test_skip_archives(self, tmp_path):
        """ContentTypeStrategy 返回 skip 时跳过"""
        docs = [_make_doc("1", "A", contentType="ARCHIVE")]
        source = FakeSource(docs)
        dest = FakeDestination()
        strategy = ContentTypeStrategy({"ARCHIVE": "skip", "DOCUMENT": "convert"})
        pipeline = Pipeline(source, dest, tmp_path, content_type_strategy=strategy)
        pipeline.run()
        assert len(dest.written) == 0

    def test_no_rule_skips(self, tmp_path):
        """ContentTypeStrategy 无规则时跳过"""
        docs = [_make_doc("1", "A", contentType="OTHER")]
        source = FakeSource(docs)
        dest = FakeDestination()
        strategy = ContentTypeStrategy({"DOCUMENT": "convert"})
        pipeline = Pipeline(source, dest, tmp_path, content_type_strategy=strategy)
        pipeline.run()
        assert len(dest.written) == 0

    def test_source_action_processes(self, tmp_path):
        """ContentTypeStrategy 返回 source 时走 Source 原生处理"""
        docs = [_make_doc("1", "A", contentType="ALIDOC")]
        source = FakeSource(docs)
        dest = FakeDestination()
        strategy = ContentTypeStrategy({"ALIDOC": "source"})
        pipeline = Pipeline(source, dest, tmp_path, content_type_strategy=strategy)
        pipeline.run()
        assert len(dest.written) == 1

    def test_convert_with_resolver(self, tmp_path):
        """convert 动作委托给 TypeRuleResolver 二次分发"""
        docs = [_make_doc("1", "A", contentType="DOCUMENT", extension="pdf")]
        source = FakeSource(docs)
        dest = FakeDestination()
        strategy = ContentTypeStrategy({"DOCUMENT": "convert"})
        resolver = TypeRuleResolver(extension_rules={".pdf": "markitdown"})
        pipeline = Pipeline(source, dest, tmp_path,
                            content_type_strategy=strategy, type_resolver=resolver)
        pipeline.run()
        assert len(dest.written) == 1

    def test_convert_no_converter_skips(self, tmp_path):
        """convert 但无匹配 converter 时跳过"""
        docs = [_make_doc("1", "A", contentType="DOCUMENT", extension="exe")]
        source = FakeSource(docs)
        dest = FakeDestination()
        strategy = ContentTypeStrategy({"DOCUMENT": "convert"})
        resolver = TypeRuleResolver(extension_rules={".pdf": "markitdown"})
        pipeline = Pipeline(source, dest, tmp_path,
                            content_type_strategy=strategy, type_resolver=resolver)
        pipeline.run()
        assert len(dest.written) == 0

    def test_convert_without_resolver_processes(self, tmp_path):
        """convert 但无 resolver 时仍处理（不转换）"""
        docs = [_make_doc("1", "A", contentType="DOCUMENT")]
        source = FakeSource(docs)
        dest = FakeDestination()
        strategy = ContentTypeStrategy({"DOCUMENT": "convert"})
        pipeline = Pipeline(source, dest, tmp_path, content_type_strategy=strategy)
        pipeline.run()
        assert len(dest.written) == 1

    def test_download_action_processes(self, tmp_path):
        """download 动作正常处理"""
        docs = [_make_doc("1", "A", contentType="IMAGE")]
        source = FakeSource(docs)
        dest = FakeDestination()
        strategy = ContentTypeStrategy({"IMAGE": "download"})
        pipeline = Pipeline(source, dest, tmp_path, content_type_strategy=strategy)
        pipeline.run()
        assert len(dest.written) == 1

    def test_no_strategy_uses_old_resolver(self, tmp_path):
        """无 ContentTypeStrategy 时走原有 TypeRuleResolver 逻辑（向后兼容）"""
        docs = [_make_doc("1", "A", extension="pdf")]
        source = FakeSource(docs)
        dest = FakeDestination()
        resolver = TypeRuleResolver(extension_rules={".pdf": "markitdown"})
        pipeline = Pipeline(source, dest, tmp_path, type_resolver=resolver)
        pipeline.run()
        assert len(dest.written) == 1


class TestRegistration:
    def test_sources_registered(self):
        from docpipe.sources import SOURCES
        assert "dingtalk" in SOURCES
        assert "local" in SOURCES

    def test_destinations_registered(self):
        from docpipe.destinations import DESTINATIONS
        assert "hindsight" in DESTINATIONS

    def test_get_source_unknown_raises(self):
        from docpipe.sources import get_source
        with pytest.raises(ValueError, match="未知的 source"):
            get_source("nonexistent")

    def test_get_destination_unknown_raises(self):
        from docpipe.destinations import get_destination
        with pytest.raises(ValueError, match="未知的 destination"):
            get_destination("nonexistent")


class TestLocalSource:
    def test_list_documents(self, tmp_path):
        (tmp_path / "a.md").write_text("hello a")
        (tmp_path / "b.md").write_text("hello b")
        (tmp_path / "c.txt").write_text("skip")

        from docpipe.sources.local import LocalSource
        source = LocalSource(input_dir=str(tmp_path))
        docs = source.list_documents()
        assert len(docs) == 2
        assert docs[0].title == "a"
        assert docs[1].title == "b"

    def test_fetch(self, tmp_path):
        (tmp_path / "test.md").write_text("content here")

        from docpipe.sources.local import LocalSource
        source = LocalSource(input_dir=str(tmp_path))
        docs = source.list_documents()
        doc = source.fetch(docs[0])
        assert doc.content == "content here"

    def test_invalid_dir_raises(self):
        from docpipe.sources.local import LocalSource
        with pytest.raises(ValueError, match="目录不存在"):
            LocalSource(input_dir="/nonexistent/path")


class TestPipelineTypeRules:
    def test_skip_unknown_type(self, tmp_path):
        """未知扩展名不在 type_rules 中，直接跳过"""
        docs = [_make_doc("1", "A", extension="tar.gz")]
        source = FakeSource(docs)
        dest = FakeDestination()
        resolver = TypeRuleResolver(extension_rules={".pdf": "markitdown"})
        pipeline = Pipeline(source, dest, tmp_path, type_resolver=resolver)
        pipeline.run()
        assert len(dest.written) == 0

    def test_skip_explicit_skip(self, tmp_path):
        """配置中显式标记 skip 的文件被跳过"""
        docs = [_make_doc("1", "A", extension="exe")]
        source = FakeSource(docs)
        dest = FakeDestination()
        resolver = TypeRuleResolver(extension_rules={".exe": "skip"})
        pipeline = Pipeline(source, dest, tmp_path, type_resolver=resolver)
        pipeline.run()
        assert len(dest.written) == 0

    def test_process_with_converter(self, tmp_path):
        """匹配到 converter 的文件正常处理"""
        docs = [_make_doc("1", "A", extension="txt")]
        source = FakeSource(docs)
        dest = FakeDestination()
        resolver = TypeRuleResolver(extension_rules={".txt": "markitdown"})
        pipeline = Pipeline(source, dest, tmp_path, type_resolver=resolver)
        pipeline.run()
        assert len(dest.written) == 1

    def test_no_resolver_processes_all(self, tmp_path):
        """无 resolver 时走原有逻辑，全部处理"""
        docs = [_make_doc("1", "A")]
        source = FakeSource(docs)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path)
        pipeline.run()
        assert len(dest.written) == 1
