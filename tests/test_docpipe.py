from __future__ import annotations

import hashlib
import json
import time
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
        sm.save({"a": {"hash": "hash1", "path": ""}, "b": {"hash": "hash2", "path": "x/y"}})
        assert sm.load() == {"a": {"hash": "hash1", "path": ""}, "b": {"hash": "hash2", "path": "x/y"}}

    def test_load_old_format(self, tmp_path):
        """兼容旧格式：{id: hash} → {id: {"hash": hash, "path": ""}}"""
        p = tmp_path / "state.json"
        p.write_text('{"a": "h1", "b": "h2"}', encoding="utf-8")
        sm = StateManager(p)
        assert sm.load() == {"a": {"hash": "h1", "path": ""}, "b": {"hash": "h2", "path": ""}}

    def test_load_empty(self, tmp_path):
        sm = StateManager(tmp_path / "nonexistent.json")
        assert sm.load() == {}

    def test_is_processed(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.save({"a": {"hash": "h1", "path": ""}})
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
        # dry_run 不应写入状态
        assert pipeline.state.load() == {}

    def test_dry_run_sync_no_state_mutation(self, tmp_path):
        """dry_run + sync 不应修改状态，连续执行结果一致"""
        doc = _make_doc("1", "A")
        source = FakeSource([doc])
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path)

        # 第一次 dry_run
        pipeline.run(sync=True, dry_run=True)
        assert len(dest.written) == 0
        assert len(dest.removed) == 0
        assert pipeline.state.load() == {}

        # 第二次 dry_run —— 应该和第一次行为一致
        pipeline.run(sync=True, dry_run=True)
        assert len(dest.written) == 0
        assert len(dest.removed) == 0
        assert pipeline.state.load() == {}

    def test_dry_run_resume_idempotent(self, tmp_path):
        """dry_run + resume 连续执行，不应因状态累积改变行为"""
        docs = [_make_doc("1", "A"), _make_doc("2", "B")]
        source = FakeSource(docs)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path)

        pipeline.run(resume=True, dry_run=True)
        assert len(dest.written) == 0
        assert pipeline.state.load() == {}

        # 第二次 resume=True，因为状态未被 dry_run 写入，仍应处理全部文档
        pipeline.run(resume=True, dry_run=True)
        assert len(dest.written) == 0
        assert pipeline.state.load() == {}

    def test_run_with_steps(self, tmp_path):
        """steps 模式下 pipeline 执行 steps"""
        docs = [_make_doc("1", "A", content="hello")]
        source = FakeSource(docs)
        dest = FakeDestination()

        from docpipe.steps.base import PipelineStep

        class UpperStep(PipelineStep):
            name = "upper"
            def process(self, doc):
                doc.content = doc.content.upper()
                return doc

        pipeline = Pipeline(source, dest, tmp_path, steps=[UpperStep()])
        pipeline.run()
        assert len(dest.written) == 1
        assert dest.written[0].content == "HELLO"

    def test_run_with_empty_steps_processes_all(self, tmp_path):
        """空 steps 列表等价于无处理"""
        docs = [_make_doc("1", "A")]
        source = FakeSource(docs)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, steps=[])
        pipeline.run()
        assert len(dest.written) == 1


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

    def test_convert_no_converter_processes(self, tmp_path):
        """convert 但无匹配 converter 时仍处理（交给 Source）"""
        docs = [_make_doc("1", "A", contentType="DOCUMENT", extension="exe")]
        source = FakeSource(docs)
        dest = FakeDestination()
        strategy = ContentTypeStrategy({"DOCUMENT": "convert"})
        resolver = TypeRuleResolver(extension_rules={".pdf": "markitdown"})
        pipeline = Pipeline(source, dest, tmp_path,
                            content_type_strategy=strategy, type_resolver=resolver)
        pipeline.run()
        assert len(dest.written) == 1

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
        assert "localdrive" in SOURCES

    def test_destinations_registered(self):
        from docpipe.destinations import DESTINATIONS
        assert "hindsight" in DESTINATIONS

    def test_localdrive_registered(self):
        from docpipe.destinations import DESTINATIONS
        assert "localdrive" in DESTINATIONS

    def test_get_source_unknown_raises(self):
        from docpipe.sources import get_source
        with pytest.raises(ValueError, match="未知的 source"):
            get_source("nonexistent")

    def test_get_destination_unknown_raises(self):
        from docpipe.destinations import get_destination
        with pytest.raises(ValueError, match="未知的 destination"):
            get_destination("nonexistent")

    def test_mineru_converter_registered(self):
        from docpipe.converters import CONVERTERS
        assert "mineru" in CONVERTERS


class TestLocalDriveDestination:
    def test_write_creates_file_and_sidecar(self, tmp_path):
        from docpipe.destinations.localdrive import LocalDriveDestination

        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))
        doc = Document(
            meta=DocumentMeta(
                id="node1",
                title="方案",
                path="产品规划/方案",
                hash="abc123",
                extra={"space_name": "知识库A", "contentType": "ALIDOC", "extension": "adoc"},
            ),
            content="# 方案内容",
            content_type="markdown",
        )

        result = dest.write(doc)

        # 文件已创建，路径包含 space_name 和原始路径，扩展名由 content_type 推断
        expected_file = output_dir / "知识库A" / "产品规划" / "方案.md"
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
        assert meta_json["full_path"] == "知识库A/产品规划/方案"
        assert meta_json["content_hash"] == "abc123"

        assert result == str(expected_file)

    def test_write_skips_unchanged(self, tmp_path):
        from docpipe.destinations.localdrive import LocalDriveDestination

        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))
        doc = Document(
            meta=DocumentMeta(id="1", title="A", path="A", hash="h1", extra={"space_name": "S"}),
            content="hello",
            content_type="markdown",
        )

        # 第一次写入
        dest.write(doc)
        file_path = output_dir / "S" / "A.md"
        mtime1 = file_path.stat().st_mtime

        # 修改时间不同则说明被重写了
        time.sleep(0.05)

        # 第二次写入（内容相同，hash 相同）
        dest2 = LocalDriveDestination(output_dir=str(output_dir))
        dest2.write(doc)
        mtime2 = file_path.stat().st_mtime

        assert mtime1 == mtime2

    def test_write_overwrites_changed(self, tmp_path):
        from docpipe.destinations.localdrive import LocalDriveDestination

        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))
        doc1 = Document(
            meta=DocumentMeta(id="1", title="A", path="A", hash="h1", extra={"space_name": "S"}),
            content="old content",
            content_type="markdown",
        )
        dest.write(doc1)

        doc2 = Document(
            meta=DocumentMeta(id="1", title="A", path="A", hash="h2", extra={"space_name": "S"}),
            content="new content",
            content_type="markdown",
        )
        dest.write(doc2)

        file_path = output_dir / "S" / "A.md"
        assert file_path.read_text(encoding="utf-8") == "new content"

    def test_remove_deletes_file_and_sidecar(self, tmp_path):
        from docpipe.destinations.localdrive import LocalDriveDestination

        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))
        doc = Document(
            meta=DocumentMeta(id="1", title="A", path="A", hash="h1", extra={"space_name": "S"}),
            content="hello",
            content_type="markdown",
        )

        file_path = dest.write(doc)
        assert Path(file_path).exists()

        dest.remove_by_path(file_path)
        assert not Path(file_path).exists()
        assert not Path(file_path + ".json").exists()

    def test_remove_nonexistent_file_no_error(self, tmp_path):
        from docpipe.destinations.localdrive import LocalDriveDestination

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

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        docs = source.list_documents()
        titles = {d.title for d in docs}
        assert titles == {"a", "b", "c", "d"}

    def test_list_skips_hidden_dirs_and_files(self, tmp_path):
        (tmp_path / "visible.md").write_text("seen")
        hidden_dir = tmp_path / ".hidden_dir"
        hidden_dir.mkdir()
        (hidden_dir / "secret.md").write_text("hidden dir file")
        (tmp_path / ".hidden.md").write_text("hidden file")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        docs = source.list_documents()
        assert len(docs) == 1
        assert docs[0].title == "visible"

    def test_list_skips_no_extension(self, tmp_path):
        (tmp_path / "README").write_text("no extension")
        (tmp_path / "guide.md").write_text("has extension")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        docs = source.list_documents()
        assert len(docs) == 1
        assert docs[0].title == "guide"

    def test_list_recursive(self, tmp_path):
        sub = tmp_path / "sub" / "dir"
        sub.mkdir(parents=True)
        (tmp_path / "root.md").write_text("root")
        (sub / "deep.md").write_text("deep")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        docs = source.list_documents()
        paths = {d.path for d in docs}
        assert "root.md" in paths
        assert str(Path("sub") / "dir" / "deep.md") in paths

    def test_invalid_dir_raises(self):
        from docpipe.sources.localdrive import LocalDriveSource
        with pytest.raises(ValueError, match="目录不存在"):
            LocalDriveSource(input_dir="/nonexistent/path")

    def test_fetch_text_file(self, tmp_path):
        (tmp_path / "test.md").write_text("hello world", encoding="utf-8")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        docs = source.list_documents()
        doc = source.fetch(docs[0])
        assert isinstance(doc.content, str)
        assert doc.content == "hello world"
        assert doc.content_type == "md"

    def test_fetch_binary_file(self, tmp_path):
        (tmp_path / "test.pdf").write_bytes(b"%PDF-1.4 fake content")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        docs = source.list_documents()
        doc = source.fetch(docs[0])
        assert isinstance(doc.content, bytes)
        assert doc.content_type == "pdf"

    def test_fetch_metadata(self, tmp_path):
        (tmp_path / "report.pdf").write_bytes(b"%PDF fake")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        docs = source.list_documents()
        assert docs[0].title == "report"
        assert docs[0].extra["extension"] == "pdf"
        assert docs[0].extra["size"] > 0
        assert "report.pdf" in docs[0].path

    def test_include_filter(self, tmp_path):
        (tmp_path / "a.md").write_text("md")
        (tmp_path / "b.pdf").write_bytes(b"pdf")
        (tmp_path / "c.docx").write_bytes(b"docx")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path), include=["*.md", "*.pdf"])
        docs = source.list_documents()
        titles = {d.title for d in docs}
        assert titles == {"a", "b"}

    def test_exclude_filter(self, tmp_path):
        (tmp_path / "a.md").write_text("md")
        (tmp_path / "b.pdf").write_bytes(b"pdf")
        (tmp_path / "c.docx").write_bytes(b"docx")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path), exclude=["*.pdf"])
        docs = source.list_documents()
        titles = {d.title for d in docs}
        assert titles == {"a", "c"}

    def test_exclude_overrides_include(self, tmp_path):
        (tmp_path / "a.md").write_text("md")
        (tmp_path / "b.pdf").write_bytes(b"pdf")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(
            input_dir=str(tmp_path),
            include=["*.md", "*.pdf"],
            exclude=["*.pdf"],
        )
        docs = source.list_documents()
        titles = {d.title for d in docs}
        assert titles == {"a"}

    def test_no_filters_includes_all(self, tmp_path):
        (tmp_path / "a.md").write_text("md")
        (tmp_path / "b.pdf").write_bytes(b"pdf")
        (tmp_path / "c.py").write_text("print('hi')")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        docs = source.list_documents()
        assert len(docs) == 3


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


class TestEnvInterpolation:
    def test_resolve_simple(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "secret123")
        from docpipe.config import resolve_env_vars
        assert resolve_env_vars("${MY_KEY}") == "secret123"

    def test_resolve_with_default(self, monkeypatch):
        monkeypatch.delenv("MISSING_KEY", raising=False)
        from docpipe.config import resolve_env_vars
        assert resolve_env_vars("${MISSING_KEY:-fallback}") == "fallback"

    def test_resolve_existing_overrides_default(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "actual")
        from docpipe.config import resolve_env_vars
        assert resolve_env_vars("${MY_KEY:-fallback}") == "actual"

    def test_resolve_missing_no_default_keeps_original(self):
        from docpipe.config import resolve_env_vars
        assert resolve_env_vars("${NONEXISTENT_VAR_XYZ}") == "${NONEXISTENT_VAR_XYZ}"

    def test_resolve_nested_dict(self, monkeypatch):
        monkeypatch.setenv("URL", "http://localhost")
        from docpipe.config import resolve_env_vars
        config = {"api_url": "${URL}", "nested": {"key": "${URL}/path"}}
        result = resolve_env_vars(config)
        assert result == {"api_url": "http://localhost", "nested": {"key": "http://localhost/path"}}

    def test_resolve_in_list(self, monkeypatch):
        monkeypatch.setenv("KEY", "val")
        from docpipe.config import resolve_env_vars
        assert resolve_env_vars(["${KEY}", "plain"]) == ["val", "plain"]

    def test_resolve_non_string_unchanged(self):
        from docpipe.config import resolve_env_vars
        assert resolve_env_vars(42) == 42
        assert resolve_env_vars(True) is True
        assert resolve_env_vars(None) is None


class TestDeepMerge:
    def test_simple_override(self):
        from docpipe.config import deep_merge
        assert deep_merge({"a": 1, "b": 2}, {"b": 3}) == {"a": 1, "b": 3}

    def test_nested_merge(self):
        from docpipe.config import deep_merge
        base = {"api_url": "http://default", "bank_id": "default_bank", "nested": {"a": 1, "b": 2}}
        override = {"bank_id": "my_bank", "nested": {"b": 3, "c": 4}}
        result = deep_merge(base, override)
        assert result == {"api_url": "http://default", "bank_id": "my_bank", "nested": {"a": 1, "b": 3, "c": 4}}

    def test_empty_override(self):
        from docpipe.config import deep_merge
        assert deep_merge({"a": 1}, {}) == {"a": 1}


class TestParseComponentConfig:
    def test_simple_parse(self):
        from docpipe.config import parse_component_config
        type_name, config = parse_component_config(
            {"source": {"localdrive": {"input_dir": "./docs"}}},
            {},
            "source",
        )
        assert type_name == "localdrive"
        assert config == {"input_dir": "./docs"}

    def test_merge_with_global(self):
        from docpipe.config import parse_component_config
        type_name, config = parse_component_config(
            {"destination": {"hindsight": {"bank_id": "my_bank"}}},
            {"hindsight": {"api_url": "http://default", "api_key": "secret"}},
            "destination",
        )
        assert type_name == "hindsight"
        assert config == {"api_url": "http://default", "api_key": "secret", "bank_id": "my_bank"}

    def test_missing_component_raises(self):
        from docpipe.config import parse_component_config
        import pytest
        with pytest.raises(ValueError, match="缺少"):
            parse_component_config({}, {}, "source")


class TestStepRegistry:
    def test_convert_step_registered(self):
        from docpipe.steps import STEPS
        assert "convert" in STEPS

    def test_get_step_unknown_raises(self):
        from docpipe.steps import get_step
        with pytest.raises(ValueError, match="未知的 step"):
            get_step("nonexistent")


class TestConvertStep:
    def test_needs_conversion_with_matching_extension(self):
        from docpipe.steps.convert import ConvertStep
        doc = Document(
            meta=DocumentMeta(id="1", title="t", path="t.pdf", hash="", extra={"extension": "pdf"}),
            content="",
            content_type="pdf",
        )
        step = ConvertStep(extension_rules={".pdf": "markitdown"})
        assert step.needs_conversion(doc) is True

    def test_no_conversion_without_matching_extension(self):
        from docpipe.steps.convert import ConvertStep
        doc = Document(
            meta=DocumentMeta(id="1", title="t", path="t.txt", hash="", extra={"extension": "txt"}),
            content="hello",
            content_type="txt",
        )
        step = ConvertStep(extension_rules={".pdf": "markitdown"})
        assert step.needs_conversion(doc) is False

    def test_source_rule_skips_conversion(self):
        from docpipe.steps.convert import ConvertStep
        doc = Document(
            meta=DocumentMeta(id="1", title="t", path="t.md", hash="", extra={"extension": "md"}),
            content="hello",
            content_type="md",
        )
        step = ConvertStep(extension_rules={".md": "source"})
        assert step.needs_conversion(doc) is False

    def test_process_no_rule_returns_unchanged(self):
        from docpipe.steps.convert import ConvertStep
        doc = Document(
            meta=DocumentMeta(id="1", title="t", path="t.md", hash="", extra={"extension": "md"}),
            content="hello",
            content_type="md",
        )
        step = ConvertStep(extension_rules={".pdf": "markitdown"})
        result = step.process(doc)
        assert result.content == "hello"


class TestImageDescriptionStep:
    def test_non_text_content_skipped(self):
        """非文本内容直接跳过"""
        from docpipe.steps.image_description import ImageDescriptionStep
        step = ImageDescriptionStep(api_key="k", base_url="http://x", model="m")
        doc = Document(
            meta=DocumentMeta(id="1", title="t", path="t.pdf", hash=""),
            content=b"binary data",
            content_type="pdf",
        )
        result = step.process(doc)
        assert result.content == b"binary data"

    def test_no_images_unchanged(self):
        """无图片的 markdown 不变"""
        from docpipe.steps.image_description import ImageDescriptionStep
        step = ImageDescriptionStep(api_key="k", base_url="http://x", model="m")
        doc = Document(
            meta=DocumentMeta(id="1", title="t", path="t.md", hash=""),
            content="# Hello\n\nNo images here.",
            content_type="markdown",
        )
        result = step.process(doc)
        assert result.content == "# Hello\n\nNo images here."
