"""测试腾讯文档 MCP source"""
import json
import os
from unittest.mock import MagicMock, patch

import pytest

from docupipe.sources.tencent import _TencentDocClient, TencentSource


def _make_call_tool_result(data):
    """构造 FastMCP call_tool 返回值的 mock"""
    mock = MagicMock()
    mock.content = [MagicMock(text=json.dumps(data))]
    return mock


class TestTencentDocClient:
    """测试 _TencentDocClient"""

    @patch("docupipe.sources.tencent._TencentDocClient._call_tool")
    def test_list_nodes(self, mock_call):
        expected = {"children": [{"node_id": "n1", "title": "文档1"}], "has_next": False}
        mock_call.return_value = _make_call_tool_result(expected)

        client = _TencentDocClient(token="fake-token")
        result = client.list_nodes("space_123")

        mock_call.assert_called_once_with(
            "query_space_node",
            {"space_id": "space_123", "num": 0},
        )
        assert result == expected

    @patch("docupipe.sources.tencent._TencentDocClient._call_tool")
    def test_list_nodes_with_parent(self, mock_call):
        expected = {"children": [{"node_id": "n2", "title": "子文档"}], "has_next": False}
        mock_call.return_value = _make_call_tool_result(expected)

        client = _TencentDocClient(token="fake-token")
        result = client.list_nodes("space_123", parent_id="parent_1", num=10)

        mock_call.assert_called_once_with(
            "query_space_node",
            {"space_id": "space_123", "parent_id": "parent_1", "num": 10},
        )
        assert result == expected

    @patch("docupipe.sources.tencent._TencentDocClient._call_tool")
    def test_get_content(self, mock_call):
        mock_call.return_value = _make_call_tool_result({"markdown": "# 标题\n内容"})

        client = _TencentDocClient(token="fake-token")
        result = client.get_content("file_123")

        mock_call.assert_called_once_with("get_content", {"file_id": "file_123"})
        assert result == "# 标题\n内容"

    @patch("docupipe.sources.tencent._TencentDocClient._call_tool")
    def test_get_content_with_content_key(self, mock_call):
        mock_call.return_value = _make_call_tool_result({"content": "备用内容"})

        client = _TencentDocClient(token="fake-token")
        result = client.get_content("file_123")

        assert result == "备用内容"

    @patch("docupipe.sources.tencent.time.sleep", return_value=None)
    @patch("docupipe.sources.tencent._TencentDocClient._call_tool")
    def test_export_file(self, mock_call, mock_sleep):
        mock_call.side_effect = [
            _make_call_tool_result({"task_id": "t1"}),
            _make_call_tool_result({"progress": 50}),
            _make_call_tool_result({"progress": 100, "file_url": "https://example.com/file.xlsx"}),
        ]

        client = _TencentDocClient(token="fake-token")
        file_url = client.export_file("file_123")

        assert file_url == "https://example.com/file.xlsx"
        assert mock_call.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("docupipe.sources.tencent.time.sleep", return_value=None)
    @patch("docupipe.sources.tencent._TencentDocClient._call_tool")
    def test_export_file_failed(self, mock_call, mock_sleep):
        mock_call.side_effect = [
            _make_call_tool_result({"task_id": "t1"}),
            _make_call_tool_result({"error": "权限不足"}),
        ]

        client = _TencentDocClient(token="fake-token")
        with pytest.raises(RuntimeError, match="权限不足"):
            client.export_file("file_123")


class TestTencentSourceInit:
    """测试 TencentSource 初始化"""

    def test_missing_space_id(self):
        with pytest.raises(ValueError, match="space_id"):
            TencentSource(space_id=None)

    def test_missing_token(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="TENCENT_DOCS_TOKEN"):
                TencentSource(space_id="s1")

    def test_init_with_space_id(self):
        with patch.dict(os.environ, {"TENCENT_DOCS_TOKEN": "tok"}):
            source = TencentSource(space_id="s1")
        assert source._space_id == "s1"
        assert source._parent_id is None
        assert source._include_types is None
        assert source._fetch_mode == "markdown"

    def test_init_with_include_types(self):
        with patch.dict(os.environ, {"TENCENT_DOCS_TOKEN": "tok"}):
            source = TencentSource(space_id="s1", include_types=["docx", "xlsx"])
        assert source._include_types == {"docx", "xlsx"}

    def test_init_with_fetch_mode(self):
        with patch.dict(os.environ, {"TENCENT_DOCS_TOKEN": "tok"}):
            source = TencentSource(space_id="s1", fetch_mode="export")
        assert source._fetch_mode == "export"


class TestTencentSourceList:
    """测试 TencentSource.list()"""

    def _make_source(self, **kwargs):
        with patch.dict(os.environ, {"TENCENT_DOCS_TOKEN": "tok"}):
            source = TencentSource(space_id="space_1", **kwargs)
        source._client = MagicMock(spec=_TencentDocClient)
        return source

    def test_flat_documents(self):
        source = self._make_source()
        source._client.list_nodes.return_value = {
            "children": [
                {"node_id": "n1", "title": "文档1", "node_type": "doc", "doc_type": "document", "has_child": False},
                {"node_id": "n2", "title": "文档2", "node_type": "sheet", "doc_type": "sheet", "has_child": False},
            ],
            "has_next": False,
        }

        metas = source.list()

        assert len(metas) == 2
        assert metas[0].id == "n1"
        assert metas[0].title == "文档1"
        assert metas[0].extra["tencent_doc_type"] == "document"
        assert metas[1].id == "n2"

    def test_skips_folders(self):
        source = self._make_source()
        source._client.list_nodes.return_value = {
            "children": [
                {"node_id": "f1", "title": "文件夹", "node_type": "wiki_folder", "doc_type": "", "has_child": False},
                {"node_id": "n1", "title": "文档1", "node_type": "doc", "doc_type": "document", "has_child": False},
            ],
            "has_next": False,
        }

        metas = source.list()

        assert len(metas) == 1
        assert metas[0].id == "n1"

    def test_filters_by_include_types(self):
        source = self._make_source(include_types=["sheet"])
        source._client.list_nodes.return_value = {
            "children": [
                {"node_id": "n1", "title": "文档1", "node_type": "doc", "doc_type": "document", "has_child": False},
                {"node_id": "n2", "title": "表格1", "node_type": "sheet", "doc_type": "sheet", "has_child": False},
            ],
            "has_next": False,
        }

        metas = source.list()

        assert len(metas) == 1
        assert metas[0].id == "n2"
        assert metas[0].extra["tencent_doc_type"] == "sheet"

    def test_recursive_folders(self):
        source = self._make_source()
        source._client.list_nodes.side_effect = [
            {
                "children": [
                    {"node_id": "f1", "title": "子文件夹", "node_type": "wiki_folder", "doc_type": "", "has_child": True},
                    {"node_id": "n1", "title": "根文档", "node_type": "doc", "doc_type": "document", "has_child": False},
                ],
                "has_next": False,
            },
            {
                "children": [
                    {"node_id": "n2", "title": "子文档", "node_type": "doc", "doc_type": "document", "has_child": False},
                ],
                "has_next": False,
            },
        ]

        metas = source.list()

        assert len(metas) == 2
        assert metas[0].id == "n2"
        assert metas[1].id == "n1"
        assert "子文件夹" in metas[0].path

    def test_parent_id_passthrough(self):
        source = self._make_source(parent_id="parent_1")
        source._client.list_nodes.return_value = {
            "children": [
                {"node_id": "n1", "title": "文档1", "node_type": "doc", "doc_type": "document", "has_child": False},
            ],
            "has_next": False,
        }

        metas = source.list()

        source._client.list_nodes.assert_called_with("space_1", parent_id="parent_1", num=0)

    def test_folders_config(self):
        source = self._make_source(folders=["产品/方案"])
        source._client.list_nodes.side_effect = [
            {
                "children": [
                    {"node_id": "f1", "title": "产品", "node_type": "wiki_folder", "doc_type": "", "has_child": True},
                ],
                "has_next": False,
            },
            {
                "children": [
                    {"node_id": "f2", "title": "方案", "node_type": "wiki_folder", "doc_type": "", "has_child": True},
                ],
                "has_next": False,
            },
            {
                "children": [
                    {"node_id": "n1", "title": "方案文档", "node_type": "doc", "doc_type": "document", "has_child": False},
                ],
                "has_next": False,
            },
        ]

        metas = source.list()

        assert len(metas) == 1
        assert metas[0].title == "方案文档"


class TestTencentSourceFetch:
    """测试 TencentSource.fetch()"""

    def _make_source(self, fetch_mode="markdown"):
        with patch.dict(os.environ, {"TENCENT_DOCS_TOKEN": "tok"}):
            source = TencentSource(space_id="space_1", fetch_mode=fetch_mode)
        source._client = MagicMock(spec=_TencentDocClient)
        return source

    def _make_meta(self, **overrides):
        from docupipe.models import BundleMeta
        defaults = {
            "id": "file_123",
            "title": "测试文档",
            "extra": {"tencent_doc_type": "word", "node_type": "wiki_file"},
        }
        defaults.update(overrides)
        return BundleMeta(**defaults)

    def test_fetch_markdown_mode(self):
        source = self._make_source(fetch_mode="markdown")
        source._client.get_content.return_value = "# 标题\n正文内容"

        meta = self._make_meta()
        bundle = source.fetch(meta)

        assert len(bundle.files) == 1
        assert bundle.files[0].name == "测试文档.md"
        assert bundle.files[0].content == "# 标题\n正文内容"
        assert bundle.files[0].content_type == "text/markdown"
        assert bundle.files[0].role == "main"

    @patch("docupipe.sources.tencent.requests.get")
    def test_fetch_export_mode(self, mock_get):
        source = self._make_source(fetch_mode="export")
        source._client.export_file.return_value = "https://example.com/file.xlsx"

        mock_resp = MagicMock()
        mock_resp.content = b"xlsx-bytes"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        meta = self._make_meta()
        bundle = source.fetch(meta)

        assert len(bundle.files) == 1
        assert bundle.files[0].name == "测试文档.docx"
        assert bundle.files[0].content == b"xlsx-bytes"
        assert bundle.files[0].role == "main"
        source._client.export_file.assert_called_once_with("file_123")

    @patch("docupipe.sources.tencent.requests.get")
    def test_fetch_both_mode(self, mock_get):
        source = self._make_source(fetch_mode="both")
        source._client.get_content.return_value = "# 标题"
        source._client.export_file.return_value = "https://example.com/file.docx"

        mock_resp = MagicMock()
        mock_resp.content = b"docx-bytes"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        meta = self._make_meta()
        bundle = source.fetch(meta)

        assert len(bundle.files) == 2
        assert bundle.files[0].name == "测试文档.md"
        assert bundle.files[0].content_type == "text/markdown"
        assert bundle.files[0].role == "main"
        assert bundle.files[1].name == "测试文档.docx"
        assert bundle.files[1].role == "attachment"
