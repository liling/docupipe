from __future__ import annotations

from docupipe.models import Bundle, FileItem
from docupipe.destinations.hindsight import HindsightDestination
from docupipe.config import resolve_context_vars


def _make_dest(template=None, context_template=None, context_prefix=None, extra_tags=None, extra_metadata=None):
    kwargs = {"bank_id": "test", "api_url": "http://localhost", "api_key": "k"}
    if template:
        kwargs["document_id_template"] = template
    if context_template:
        kwargs["context_template"] = context_template
    if context_prefix:
        kwargs["context_prefix"] = context_prefix
    if extra_tags:
        kwargs["extra_tags"] = extra_tags
    if extra_metadata:
        kwargs["extra_metadata"] = extra_metadata
    return HindsightDestination(**kwargs)


def _make_bundle(**extra):
    ctx = {"id": "doc1", "title": "测试", "path": "space1/folder/doc", "hash": "abc123", "_source": "dingtalk", "space_name": "space1"}
    ctx.update(extra)
    return Bundle(
        files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
        context=ctx,
    )


class TestHindsightDocumentIdTemplate:
    def test_default_document_id(self):
        dest = _make_dest()
        item = dest._build_retain_item(_make_bundle())
        assert item["document_id"] == "dingtalk:doc1"

    def test_template_document_id(self):
        dest = _make_dest(template="${context.space_name}/${context.id}")
        config = {"document_id_template": "${context.space_name}/${context.id}"}
        resolved = resolve_context_vars(config, {"space_name": "myspace", "id": "doc1"})
        dest.update_config(resolved)
        item = dest._build_retain_item(_make_bundle())
        assert item["document_id"] == "myspace/doc1"


class TestHindsightContextTemplate:
    def test_default_context(self):
        dest = _make_dest()
        item = dest._build_retain_item(_make_bundle())
        assert "来自" in item["context"]

    def test_context_prefix(self):
        dest = _make_dest(context_prefix="产品知识库")
        item = dest._build_retain_item(_make_bundle())
        assert item["context"] == "产品知识库"

    def test_context_template_overrides_prefix(self):
        dest = _make_dest(context_template="来自${context.space_name}", context_prefix="产品知识库")
        config = {"context_template": "来自${context.space_name}"}
        resolved = resolve_context_vars(config, {"space_name": "myspace"})
        dest.update_config(resolved)
        item = dest._build_retain_item(_make_bundle())
        assert item["context"] == "来自myspace"


class TestHindsightExtraTags:
    def test_default_tags(self):
        dest = _make_dest()
        item = dest._build_retain_item(_make_bundle())
        assert "space:space1" in item["tags"]
        assert "path:folder" in item["tags"]

    def test_extra_tags_appended(self):
        dest = _make_dest()
        config = {"extra_tags": ["custom:${context.space_name}", "env:prod"]}
        resolved = resolve_context_vars(config, {"space_name": "myspace"})
        dest.update_config(resolved)
        item = dest._build_retain_item(_make_bundle())
        assert "space:space1" in item["tags"]
        assert "custom:myspace" in item["tags"]
        assert "env:prod" in item["tags"]


class TestHindsightExtraMetadata:
    def test_default_metadata(self):
        dest = _make_dest()
        item = dest._build_retain_item(_make_bundle())
        assert item["metadata"]["title"] == "测试"
        assert "author" not in item["metadata"]

    def test_extra_metadata_merged(self):
        dest = _make_dest()
        config = {"extra_metadata": {"author": "${context.author:-unknown}", "version": "1.0"}}
        resolved = resolve_context_vars(config, {"author": "张三"})
        dest.update_config(resolved)
        item = dest._build_retain_item(_make_bundle())
        assert item["metadata"]["title"] == "测试"
        assert item["metadata"]["author"] == "张三"
        assert item["metadata"]["version"] == "1.0"

    def test_extra_metadata_overwrites_existing(self):
        dest = _make_dest()
        config = {"extra_metadata": {"title": "自定义标题"}}
        resolved = resolve_context_vars(config, {})
        dest.update_config(resolved)
        item = dest._build_retain_item(_make_bundle())
        assert item["metadata"]["title"] == "自定义标题"
