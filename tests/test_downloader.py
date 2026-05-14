from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dwsdocs_downloader.downloader import Downloader
from dwsdocs_downloader.wiki_client import WikiClient
from dwsdocs_downloader.display import Display


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "output"


@pytest.fixture
def mock_client():
    return MagicMock(spec=WikiClient)


@pytest.fixture
def display():
    return Display()


def test_download_single_doc(mock_client, output_dir, display):
    mock_client.get_space_info.return_value = {"id": "sp1", "name": "测试知识库"}
    mock_client.list_nodes.return_value = [
        {"nodeId": "n1", "title": "文档1", "nodeType": "doc", "contentType": "ALIDOC", "extension": "adoc"},
    ]
    mock_client.get_node_info.return_value = {
        "nodeId": "n1", "title": "文档1", "contentType": "ALIDOC", "extension": "adoc",
    }
    mock_client.read_document.return_value = "# 文档1\n\n这是内容"

    dl = Downloader(mock_client, output_dir, display=display)
    dl.download(space_id="sp1")

    md_file = output_dir / "测试知识库" / "文档1.md"
    assert md_file.exists()
    assert "# 文档1" in md_file.read_text(encoding="utf-8")

    meta_file = output_dir / "测试知识库" / "文档1.meta.json"
    assert meta_file.exists()
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    assert meta["nodeId"] == "n1"
    assert meta["contentType"] == "ALIDOC"


def test_download_nested_folders(mock_client, output_dir, display):
    mock_client.get_space_info.return_value = {"id": "sp1", "name": "测试知识库"}
    mock_client.list_nodes.side_effect = [
        [{"nodeId": "f1", "title": "子文件夹", "nodeType": "folder", "hasChildren": True}],
        [{"nodeId": "n1", "title": "嵌套文档", "nodeType": "doc", "contentType": "ALIDOC", "extension": "adoc"}],
    ]
    mock_client.get_node_info.return_value = {
        "nodeId": "n1", "title": "嵌套文档", "contentType": "ALIDOC", "extension": "adoc",
    }
    mock_client.read_document.return_value = "# 嵌套文档"

    dl = Downloader(mock_client, output_dir, display=display)
    dl.download(space_id="sp1")

    md_file = output_dir / "测试知识库" / "子文件夹" / "嵌套文档.md"
    assert md_file.exists()


def test_download_file_type(mock_client, output_dir, display):
    mock_client.get_space_info.return_value = {"id": "sp1", "name": "测试知识库"}
    mock_client.list_nodes.return_value = [
        {"nodeId": "n2", "title": "报告", "nodeType": "file", "contentType": "FILE", "extension": "pdf"},
    ]
    mock_client.get_node_info.return_value = {
        "nodeId": "n2", "title": "报告", "contentType": "FILE", "extension": "pdf",
    }
    mock_client.download_file.return_value = "https://example.com/report.pdf"

    dl = Downloader(mock_client, output_dir, display=display)
    with patch("dwsdocs_downloader.downloader.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.content = b"%PDF-1.4 fake content"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        with patch("dwsdocs_downloader.downloader.FileConverter") as mock_conv_cls:
            mock_conv = MagicMock()
            mock_conv.is_convertible.return_value = True
            mock_conv.convert.return_value = MagicMock(markdown="# PDF 内容")
            mock_conv_cls.return_value = mock_conv
            dl.download(space_id="sp1")

    md_file = output_dir / "测试知识库" / "报告.md"
    assert md_file.exists()
    assert "PDF 内容" in md_file.read_text(encoding="utf-8")


def test_download_resume_skips_existing(mock_client, output_dir, display):
    mock_client.get_space_info.return_value = {"id": "sp1", "name": "测试知识库"}
    mock_client.list_nodes.return_value = [
        {"nodeId": "n1", "title": "已有文档", "nodeType": "doc"},
    ]

    space_dir = output_dir / "测试知识库"
    space_dir.mkdir(parents=True, exist_ok=True)
    (space_dir / "已有文档.md").write_text("old content")
    (space_dir / "已有文档.meta.json").write_text(json.dumps({"nodeId": "n1"}))

    dl = Downloader(mock_client, output_dir, display=display)
    dl.download(space_id="sp1", resume=True)

    mock_client.read_document.assert_not_called()


def test_sanitize_filename():
    from dwsdocs_downloader.downloader import sanitize_filename
    assert sanitize_filename("a/b:c*d?e") == "a_b_c_d_e"
    assert sanitize_filename("  ") == "未命名"
    assert sanitize_filename("正常名称") == "正常名称"
