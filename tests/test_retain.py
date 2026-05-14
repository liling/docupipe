from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dwsdocs_downloader.retain import RetainRunner
from dwsdocs_downloader.display import Display


def _create_doc(output_dir: Path, space_name: str, folder: str, name: str, node_id: str, content: str = "test content"):
    doc_dir = output_dir / space_name / folder if folder else output_dir / space_name
    doc_dir.mkdir(parents=True, exist_ok=True)
    md_path = doc_dir / f"{name}.md"
    md_path.write_text(content, encoding="utf-8")
    meta_path = doc_dir / f"{name}.meta.json"
    meta_path.write_text(json.dumps({
        "nodeId": node_id,
        "title": name,
        "contentType": "ALIDOC",
        "extension": "adoc",
    }), encoding="utf-8")
    return md_path


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "output"


@pytest.fixture
def display():
    return Display()


def test_scan_documents(output_dir, display):
    _create_doc(output_dir, "知识库", "子目录", "文档1", "n1")
    _create_doc(output_dir, "知识库", "", "文档2", "n2")

    runner = RetainRunner(output_dir, display=display)
    docs = runner.scan_documents()
    assert len(docs) == 2
    ids = {d["node_id"] for d in docs}
    assert ids == {"n1", "n2"}


def test_scan_documents_sync_no_changes(output_dir, display):
    _create_doc(output_dir, "知识库", "", "文档1", "n1")

    runner = RetainRunner(output_dir, display=display)
    md_path = output_dir / "知识库" / "文档1.md"
    from dwsdocs_downloader.state import content_hash
    runner._state.save({"n1": content_hash(md_path)})

    changed, skipped = runner.scan_documents_sync()
    assert len(changed) == 0
    assert skipped == 1


def test_scan_documents_sync_with_changes(output_dir, display):
    _create_doc(output_dir, "知识库", "", "文档1", "n1", "原始内容")

    runner = RetainRunner(output_dir, display=display)
    runner._state.save({"n1": "old_hash"})

    changed, skipped = runner.scan_documents_sync()
    assert len(changed) == 1
    assert skipped == 0


def test_build_retain_item(output_dir, display):
    _create_doc(output_dir, "知识库", "子目录", "文档1", "n1", "# 测试\n\n正文内容")

    runner = RetainRunner(output_dir, display=display)
    docs = runner.scan_documents()
    item = runner.build_retain_item(docs[0])

    assert item["document_id"] == "dingtalk:wiki:n1"
    assert "dingtalk" in item["tags"]
    assert "wiki" in item["tags"]
    assert item["metadata"]["nodeId"] == "n1"
    assert "# 测试" in item["content"]


def test_build_retain_item_context(output_dir, display):
    _create_doc(output_dir, "技术文档", "部署指南", "安装手册", "n2", "安装步骤")

    runner = RetainRunner(output_dir, display=display)
    docs = runner.scan_documents()
    item = runner.build_retain_item(docs[0])

    assert "技术文档" in item["context"]
    assert "部署指南" in item["context"]


def test_build_retain_item_custom_context(output_dir, display):
    _create_doc(output_dir, "知识库", "", "文档1", "n1", "# 测试")

    runner = RetainRunner(output_dir, display=display)
    docs = runner.scan_documents()
    item = runner.build_retain_item(docs[0], context_prefix="自定义上下文")

    # 自定义 context 完全替换默认 context
    assert item["context"] == "自定义上下文"
    assert "知识库" not in item["context"]
