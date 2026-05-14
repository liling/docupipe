from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from dwsdocs_downloader.wiki_client import WikiClient


def _mock_run(stdout: str, returncode: int = 0):
    result = MagicMock()
    result.stdout = stdout
    result.returncode = returncode
    result.stderr = ""
    return result


@pytest.fixture
def client():
    return WikiClient()


def test_list_nodes(client):
    nodes = [
        {"nodeId": "abc123", "title": "文档1", "nodeType": "doc"},
        {"nodeId": "def456", "title": "文件夹", "nodeType": "folder"},
    ]
    with patch("dwsdocs_downloader.wiki_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_run(json.dumps({"items": nodes}))
        result = client.list_nodes(workspace_id="space1")
        assert len(result) == 2
        assert result[0]["nodeId"] == "abc123"
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "list" in cmd
        assert "--workspace" in cmd
        assert "space1" in cmd


def test_list_nodes_with_folder(client):
    with patch("dwsdocs_downloader.wiki_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_run(json.dumps({"items": []}))
        client.list_nodes(workspace_id="space1", folder_id="folder1")
        cmd = mock_run.call_args[0][0]
        assert "--folder" in cmd
        assert "folder1" in cmd


def test_list_nodes_pagination(client):
    page1 = {"items": [{"nodeId": "a"}], "nextPageToken": "tok1"}
    page2 = {"items": [{"nodeId": "b"}]}
    with patch("dwsdocs_downloader.wiki_client.subprocess.run") as mock_run:
        mock_run.side_effect = [
            _mock_run(json.dumps(page1)),
            _mock_run(json.dumps(page2)),
        ]
        result = client.list_nodes(workspace_id="space1")
        assert len(result) == 2
        assert mock_run.call_count == 2


def test_get_node_info(client):
    info = {"nodeId": "abc", "title": "测试文档", "contentType": "ALIDOC", "extension": "adoc"}
    with patch("dwsdocs_downloader.wiki_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_run(json.dumps(info))
        result = client.get_node_info("abc")
        assert result["contentType"] == "ALIDOC"


def test_read_document(client):
    with patch("dwsdocs_downloader.wiki_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_run(json.dumps({"result": [{"type": "markdown", "content": "# Hello"}]}))
        result = client.read_document("abc")
        assert "Hello" in result


def test_download_file(client):
    with patch("dwsdocs_downloader.wiki_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_run(json.dumps({"downloadUrl": "https://example.com/file.pdf"}))
        result = client.download_file("abc")
        assert result == "https://example.com/file.pdf"


def test_get_space_info(client):
    info = {"id": "space1", "name": "技术文档库"}
    with patch("dwsdocs_downloader.wiki_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_run(json.dumps(info))
        result = client.get_space_info("space1")
        assert result["name"] == "技术文档库"


def test_dws_error_raises(client):
    with patch("dwsdocs_downloader.wiki_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_run("", returncode=1)
        with pytest.raises(RuntimeError, match="dws 命令失败"):
            client.get_space_info("space1")
