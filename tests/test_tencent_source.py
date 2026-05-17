"""测试腾讯文档 MCP source"""
import json
import os
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

from docupipe.sources.tencent import _TencentDocClient, TencentSource


def _make_call_tool_result(data):
    """构造 FastMCP call_tool 返回值的 mock"""
    mock = MagicMock()
    mock.content = [MagicMock(text=json.dumps(data))]
    return mock


class TestTencentDocClient(unittest.TestCase):
    """测试 _TencentDocClient"""

    @patch("docupipe.sources.tencent._TencentDocClient._call_tool")
    def test_list_nodes(self, mock_call):
        """测试列出节点"""
        expected = {"children": [{"node_id": "n1", "title": "文档1"}], "has_next": False}
        mock_call.return_value = _make_call_tool_result(expected)

        client = _TencentDocClient(token="fake-token")
        result = client.list_nodes("space_123")

        mock_call.assert_called_once_with(
            "query_space_node",
            {"space_id": "space_123", "num": 0},
        )
        self.assertEqual(result, expected)

    @patch("docupipe.sources.tencent._TencentDocClient._call_tool")
    def test_list_nodes_with_parent(self, mock_call):
        """测试列出指定父节点下的节点"""
        expected = {"children": [{"node_id": "n2", "title": "子文档"}], "has_next": False}
        mock_call.return_value = _make_call_tool_result(expected)

        client = _TencentDocClient(token="fake-token")
        result = client.list_nodes("space_123", parent_id="parent_1", num=10)

        mock_call.assert_called_once_with(
            "query_space_node",
            {"space_id": "space_123", "parent_id": "parent_1", "num": 10},
        )
        self.assertEqual(result, expected)

    @patch("docupipe.sources.tencent._TencentDocClient._call_tool")
    def test_get_content(self, mock_call):
        """测试获取文档 markdown 内容"""
        mock_call.return_value = _make_call_tool_result({"markdown": "# 标题\n内容"})

        client = _TencentDocClient(token="fake-token")
        result = client.get_content("file_123")

        mock_call.assert_called_once_with("get_content", {"file_id": "file_123"})
        self.assertEqual(result, "# 标题\n内容")

    @patch("docupipe.sources.tencent._TencentDocClient._call_tool")
    def test_get_content_with_content_key(self, mock_call):
        """测试获取内容时使用 content 字段"""
        mock_call.return_value = _make_call_tool_result({"content": "备用内容"})

        client = _TencentDocClient(token="fake-token")
        result = client.get_content("file_123")

        self.assertEqual(result, "备用内容")

    @patch("docupipe.sources.tencent.time.sleep", return_value=None)
    @patch("docupipe.sources.tencent._TencentDocClient._call_tool")
    def test_export_file(self, mock_call, mock_sleep):
        """测试导出文件（轮询成功）"""
        # 第一次调用：发起导出
        # 后续调用：轮询进度
        mock_call.side_effect = [
            _make_call_tool_result({"task_id": "t1"}),
            _make_call_tool_result({"progress": 50}),
            _make_call_tool_result({"progress": 100, "file_url": "https://example.com/file.xlsx"}),
        ]

        client = _TencentDocClient(token="fake-token")
        file_url = client.export_file("file_123")

        self.assertEqual(file_url, "https://example.com/file.xlsx")
        self.assertEqual(mock_call.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("docupipe.sources.tencent.time.sleep", return_value=None)
    @patch("docupipe.sources.tencent._TencentDocClient._call_tool")
    def test_export_file_failed(self, mock_call, mock_sleep):
        """测试导出失败"""
        mock_call.side_effect = [
            _make_call_tool_result({"task_id": "t1"}),
            _make_call_tool_result({"error": "权限不足"}),
        ]

        client = _TencentDocClient(token="fake-token")
        with self.assertRaises(RuntimeError) as ctx:
            client.export_file("file_123")
        self.assertIn("权限不足", str(ctx.exception))


class TestTencentSourceInit(unittest.TestCase):
    """测试 TencentSource 初始化"""

    def test_missing_space_id(self):
        """缺少 space_id 应抛出 ValueError"""
        with self.assertRaises(ValueError) as ctx:
            TencentSource(space_id=None)
        self.assertIn("space_id", str(ctx.exception))

    def test_missing_token(self):
        """缺少 TENCENT_DOCS_TOKEN 应抛出 ValueError"""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                TencentSource(space_id="s1")
            self.assertIn("TENCENT_DOCS_TOKEN", str(ctx.exception))

    def test_init_with_space_id(self):
        """正常初始化"""
        with patch.dict(os.environ, {"TENCENT_DOCS_TOKEN": "tok"}):
            source = TencentSource(space_id="s1")
        self.assertEqual(source._space_id, "s1")
        self.assertIsNone(source._parent_id)
        self.assertIsNone(source._include_types)
        self.assertEqual(source._fetch_mode, "markdown")

    def test_init_with_include_types(self):
        """include_types 参数正确存储"""
        with patch.dict(os.environ, {"TENCENT_DOCS_TOKEN": "tok"}):
            source = TencentSource(space_id="s1", include_types=["docx", "xlsx"])
        self.assertEqual(source._include_types, {"docx", "xlsx"})

    def test_init_with_fetch_mode(self):
        """fetch_mode 参数正确存储"""
        with patch.dict(os.environ, {"TENCENT_DOCS_TOKEN": "tok"}):
            source = TencentSource(space_id="s1", fetch_mode="export")
        self.assertEqual(source._fetch_mode, "export")


class TestTencentSourceList(unittest.TestCase):
    """测试 TencentSource.list()"""

    def _make_source(self, **kwargs):
        """创建测试用 TencentSource，mock 掉 _TencentDocClient"""
        with patch.dict(os.environ, {"TENCENT_DOCS_TOKEN": "tok"}):
            source = TencentSource(space_id="space_1", **kwargs)
        source._client = MagicMock(spec=_TencentDocClient)
        return source

    def test_flat_documents(self):
        """列出扁平文档列表"""
        source = self._make_source()
        source._client.list_nodes.return_value = {
            "children": [
                {"node_id": "n1", "title": "文档1", "node_type": "doc", "doc_type": "document", "has_child": False},
                {"node_id": "n2", "title": "文档2", "node_type": "sheet", "doc_type": "sheet", "has_child": False},
            ],
            "has_next": False,
        }

        metas = source.list()

        self.assertEqual(len(metas), 2)
        self.assertEqual(metas[0].id, "n1")
        self.assertEqual(metas[0].title, "文档1")
        self.assertEqual(metas[0].extra["doc_type"], "document")
        self.assertEqual(metas[1].id, "n2")

    def test_skips_folders(self):
        """跳过 wiki_folder 类型节点"""
        source = self._make_source()
        source._client.list_nodes.return_value = {
            "children": [
                {"node_id": "f1", "title": "文件夹", "node_type": "wiki_folder", "doc_type": "", "has_child": False},
                {"node_id": "n1", "title": "文档1", "node_type": "doc", "doc_type": "document", "has_child": False},
            ],
            "has_next": False,
        }

        metas = source.list()

        self.assertEqual(len(metas), 1)
        self.assertEqual(metas[0].id, "n1")

    def test_filters_by_include_types(self):
        """按 include_types 过滤"""
        source = self._make_source(include_types=["sheet"])
        source._client.list_nodes.return_value = {
            "children": [
                {"node_id": "n1", "title": "文档1", "node_type": "doc", "doc_type": "document", "has_child": False},
                {"node_id": "n2", "title": "表格1", "node_type": "sheet", "doc_type": "sheet", "has_child": False},
            ],
            "has_next": False,
        }

        metas = source.list()

        self.assertEqual(len(metas), 1)
        self.assertEqual(metas[0].id, "n2")
        self.assertEqual(metas[0].extra["doc_type"], "sheet")

    def test_recursive_folders(self):
        """递归收集子文件夹中的文档"""
        source = self._make_source()
        source._client.list_nodes.side_effect = [
            # 第一次调用：根目录，含一个文件夹和一个文档
            {
                "children": [
                    {"node_id": "f1", "title": "子文件夹", "node_type": "wiki_folder", "doc_type": "", "has_child": True},
                    {"node_id": "n1", "title": "根文档", "node_type": "doc", "doc_type": "document", "has_child": False},
                ],
                "has_next": False,
            },
            # 第二次调用：子文件夹内容
            {
                "children": [
                    {"node_id": "n2", "title": "子文档", "node_type": "doc", "doc_type": "document", "has_child": False},
                ],
                "has_next": False,
            },
        ]

        metas = source.list()

        # _collect_nodes 遇到文件夹时先递归，所以子节点在前面
        self.assertEqual(len(metas), 2)
        self.assertEqual(metas[0].id, "n2")
        self.assertEqual(metas[1].id, "n1")
        self.assertIn("子文件夹", metas[0].path)

    def test_parent_id_passthrough(self):
        """parent_id 传递到 list_nodes"""
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
        """通过 folders 配置解析路径"""
        source = self._make_source(folders=["产品/方案"])
        source._client.list_nodes.side_effect = [
            # 1. _resolve_folder_path: 解析 "产品" 文件夹
            {
                "children": [
                    {"node_id": "f1", "title": "产品", "node_type": "wiki_folder", "doc_type": "", "has_child": True},
                ],
                "has_next": False,
            },
            # 2. _resolve_folder_path: 解析 "方案" 子文件夹
            {
                "children": [
                    {"node_id": "f2", "title": "方案", "node_type": "wiki_folder", "doc_type": "", "has_child": True},
                ],
                "has_next": False,
            },
            # 3. _collect_nodes: 列出方案文件夹下的文档
            {
                "children": [
                    {"node_id": "n1", "title": "方案文档", "node_type": "doc", "doc_type": "document", "has_child": False},
                ],
                "has_next": False,
            },
        ]

        metas = source.list()

        self.assertEqual(len(metas), 1)
        self.assertEqual(metas[0].title, "方案文档")


class TestTencentSourceFetch(unittest.TestCase):
    """测试 TencentSource.fetch()"""

    def _make_source(self, fetch_mode="markdown"):
        """创建测试用 TencentSource"""
        with patch.dict(os.environ, {"TENCENT_DOCS_TOKEN": "tok"}):
            source = TencentSource(space_id="space_1", fetch_mode=fetch_mode)
        source._client = MagicMock(spec=_TencentDocClient)
        return source

    def _make_meta(self, **overrides):
        from docupipe.models import BundleMeta
        defaults = {
            "id": "file_123",
            "title": "测试文档",
            "extra": {"doc_type": "word", "node_type": "wiki_file"},
        }
        defaults.update(overrides)
        return BundleMeta(**defaults)

    def test_fetch_markdown_mode(self):
        """markdown 模式获取内容"""
        source = self._make_source(fetch_mode="markdown")
        source._client.get_content.return_value = "# 标题\n正文内容"

        meta = self._make_meta()
        bundle = source.fetch(meta)

        self.assertEqual(len(bundle.files), 1)
        self.assertEqual(bundle.files[0].name, "测试文档.md")
        self.assertEqual(bundle.files[0].content, "# 标题\n正文内容")
        self.assertEqual(bundle.files[0].content_type, "text/markdown")
        self.assertEqual(bundle.files[0].role, "main")
        self.assertNotIn("_needs_conversion", bundle.context)

    @patch("docupipe.sources.tencent.requests.get")
    def test_fetch_export_mode(self, mock_get):
        """export 模式下载文件"""
        source = self._make_source(fetch_mode="export")
        source._client.export_file.return_value = "https://example.com/file.xlsx"

        mock_resp = MagicMock()
        mock_resp.content = b"xlsx-bytes"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        meta = self._make_meta()
        bundle = source.fetch(meta)

        self.assertEqual(len(bundle.files), 1)
        self.assertEqual(bundle.files[0].name, "测试文档.docx")
        self.assertEqual(bundle.files[0].content, b"xlsx-bytes")
        self.assertEqual(bundle.files[0].role, "main")
        self.assertTrue(bundle.context.get("_needs_conversion"))
        source._client.export_file.assert_called_once_with("file_123")

    def test_fetch_both_mode(self):
        """both 模式同时获取 markdown 和导出文件"""
        source = self._make_source(fetch_mode="both")
        source._client.get_content.return_value = "# 标题"

        with patch("docupipe.sources.tencent.requests.get") as mock_get:
            source._client.export_file.return_value = "https://example.com/file.docx"
            mock_resp = MagicMock()
            mock_resp.content = b"docx-bytes"
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            meta = self._make_meta()
            bundle = source.fetch(meta)

        self.assertEqual(len(bundle.files), 2)
        # markdown 文件
        self.assertEqual(bundle.files[0].name, "测试文档.md")
        self.assertEqual(bundle.files[0].content_type, "text/markdown")
        self.assertEqual(bundle.files[0].role, "main")
        # 导出文件
        self.assertEqual(bundle.files[1].name, "测试文档.docx")
        self.assertEqual(bundle.files[1].role, "attachment")
        self.assertTrue(bundle.context.get("_needs_conversion"))


if __name__ == "__main__":
    unittest.main()
