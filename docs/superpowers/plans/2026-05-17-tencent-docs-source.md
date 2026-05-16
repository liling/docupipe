# 腾讯文档 MCP Source 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 docupipe 新增 `tencent` source，通过 FastMCP Client 连接腾讯文档 MCP 服务，支持 markdown/export/both 三种 fetch 模式。

**Architecture:** 新增 `docupipe/sources/tencent.py`，内部封装 `_TencentDocClient` 类管理 MCP 连接和工具调用，对外提供同步接口。`TencentSource` 继承 `SourceBase`，实现 `list()` 遍历空间节点树和 `fetch()` 获取文档内容。

**Tech Stack:** Python 3.11+, fastmcp (MCP Python SDK), httpx (fastmcp 内置), requests (下载导出文件)

---

## 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `pyproject.toml` | 添加 `fastmcp` 依赖 |
| 创建 | `docupipe/sources/tencent.py` | `_TencentDocClient` + `TencentSource` |
| 修改 | `docupipe/sources/__init__.py` | 添加 `import docupipe.sources.tencent` 触发注册 |
| 创建 | `tests/test_tencent_source.py` | 全部测试用例 |

---

### Task 1: 添加 fastmcp 依赖

**Files:**
- Modify: `pyproject.toml:29`

- [ ] **Step 1: 在 dependencies 列表中添加 fastmcp**

在 `pyproject.toml` 的 `dependencies` 列表末尾添加 `fastmcp`：

```toml
    "boto3>=1.28.0",
    "fastmcp>=2.0.0",
```

- [ ] **Step 2: 安装依赖并验证**

Run: `cd /Users/liling/src/ai/docpipe && pip install -e ".[dev]" 2>&1 | tail -5`

- [ ] **Step 3: 验证 fastmcp 可导入**

Run: `python -c "from fastmcp import Client; print('fastmcp OK')"`

Expected: `fastmcp OK`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: 添加 fastmcp 依赖"
```

---

### Task 2: 实现 `_TencentDocClient` 核心方法

**Files:**
- Create: `docupipe/sources/tencent.py`

这个 Task 只实现 `_TencentDocClient`，不涉及 `TencentSource`。

- [ ] **Step 1: 写 `_TencentDocClient` 的测试**

创建 `tests/test_tencent_source.py`：

```python
"""测试腾讯文档 source"""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from docupipe.sources.tencent import _TencentDocClient


def _make_call_tool_result(data: dict) -> MagicMock:
    """构造一个模拟 fastmcp call_tool 返回值的结果对象"""
    result = MagicMock()
    # fastmcp call_tool 返回的对象，content 是 TextContent 列表
    text_content = MagicMock()
    text_content.text = json.dumps(data)
    result.content = [text_content]
    return result


class TestTencentDocClient(unittest.TestCase):
    """测试 _TencentDocClient"""

    def setUp(self):
        self.client = _TencentDocClient(token="test-token")

    @patch("docupipe.sources.tencent.Client")
    def test_list_nodes(self, mock_client_cls):
        """测试 list_nodes 调用 query_space_node 并返回节点列表"""
        mock_session = AsyncMock()
        mock_session.call_tool.return_value = _make_call_tool_result({
            "children": [
                {"node_id": "doc1", "title": "文档1", "node_type": "wiki_file", "has_child": False, "doc_type": "smartcanvas"},
                {"node_id": "folder1", "title": "文件夹", "node_type": "wiki_folder", "has_child": True},
            ],
            "has_next": False,
        })
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = self.client.list_nodes(space_id="space_123")

        self.assertEqual(len(result["children"]), 2)
        self.assertFalse(result["has_next"])
        mock_session.call_tool.assert_called_once_with(
            "query_space_node", {"space_id": "space_123", "num": 0}
        )

    @patch("docupipe.sources.tencent.Client")
    def test_get_content(self, mock_client_cls):
        """测试 get_content 返回 markdown 内容"""
        mock_session = AsyncMock()
        mock_session.call_tool.return_value = _make_call_tool_result({
            "content": "# 标题\n\n正文内容",
        })
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = self.client.get_content(file_id="doc1")

        self.assertEqual(result, "# 标题\n\n正文内容")
        mock_session.call_tool.assert_called_once_with(
            "get_content", {"file_id": "doc1"}
        )

    @patch("docupipe.sources.tencent.Client")
    def test_export_file(self, mock_client_cls):
        """测试 export_file 调用 export_file + export_progress 轮询"""
        mock_session = AsyncMock()
        call_count = 0

        async def mock_call_tool(name, args):
            nonlocal call_count
            call_count += 1
            if name == "manage.export_file":
                return _make_call_tool_result({"task_id": "task_001"})
            if name == "manage.export_progress":
                if call_count <= 2:
                    return _make_call_tool_result({"progress": 50})
                return _make_call_tool_result({
                    "progress": 100,
                    "file_name": "文档.docx",
                    "file_url": "https://example.com/download.docx",
                })

        mock_session.call_tool = mock_call_tool
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("time.sleep"):
            file_url, file_name = self.client.export_file(file_id="doc1")

        self.assertEqual(file_url, "https://example.com/download.docx")
        self.assertEqual(file_name, "文档.docx")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/liling/src/ai/docpipe && python -m pytest tests/test_tencent_source.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'docupipe.sources.tencent'`

- [ ] **Step 3: 实现 `_TencentDocClient`**

创建 `docupipe/sources/tencent.py`：

```python
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

import requests
from fastmcp import Client
from fastmcp.client.auth import BearerAuth

from docupipe.models import SkipBundle

logger = logging.getLogger(__name__)

_MCP_URL = "https://docs.qq.com/openapi/mcp"
_EXPORT_POLL_INTERVAL = 5
_EXPORT_MAX_POLLS = 60


class _TencentDocClient:
    def __init__(self, token: str):
        self._token = token

    def _create_client(self) -> Client:
        return Client(_MCP_URL, auth=BearerAuth(self._token))

    def _call_tool(self, tool_name: str, args: dict[str, Any]) -> Any:
        """同步包装：创建 MCP session 并调用工具"""
        return asyncio.run(self._async_call_tool(tool_name, args))

    async def _async_call_tool(self, tool_name: str, args: dict[str, Any]) -> Any:
        async with self._create_client() as session:
            result = await session.call_tool(tool_name, args)
            return self._parse_result(result)

    @staticmethod
    def _parse_result(result: Any) -> Any:
        """从 fastmcp call_tool 返回值中解析 JSON"""
        if hasattr(result, "content") and result.content:
            text = result.content[0].text
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return text
        return result

    def list_nodes(self, space_id: str, parent_id: str | None = None, num: int = 0) -> dict:
        """调用 query_space_node"""
        args: dict[str, Any] = {"space_id": space_id, "num": num}
        if parent_id:
            args["parent_id"] = parent_id
        return self._call_tool("query_space_node", args)

    def get_content(self, file_id: str) -> str:
        """调用 get_content，返回 markdown"""
        result = self._call_tool("get_content", {"file_id": file_id})
        if isinstance(result, dict):
            return result.get("content", "")
        return str(result)

    def export_file(self, file_id: str) -> tuple[str, str]:
        """调用 manage.export_file + 轮询 manage.export_progress，返回 (file_url, file_name)"""
        result = self._call_tool("manage.export_file", {"file_id": file_id})
        task_id = result.get("task_id", "") if isinstance(result, dict) else ""
        if not task_id:
            raise RuntimeError(f"export_file 未返回 task_id: {result}")

        for i in range(_EXPORT_MAX_POLLS):
            time.sleep(_EXPORT_POLL_INTERVAL)
            progress = self._call_tool("manage.export_progress", {"task_id": task_id})
            if not isinstance(progress, dict):
                continue
            if progress.get("progress") == 100:
                file_url = progress.get("file_url", "")
                file_name = progress.get("file_name", "")
                if not file_url:
                    raise RuntimeError(f"导出完成但无下载 URL: {progress}")
                return file_url, file_name
            if progress.get("error"):
                raise RuntimeError(f"导出失败: {progress['error']}")

        raise SkipBundle(f"导出轮询超时: file_id={file_id}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/liling/src/ai/docpipe && python -m pytest tests/test_tencent_source.py -v`

Expected: 所有 TestTencentDocClient 测试 PASS

- [ ] **Step 5: Commit**

```bash
git add docupipe/sources/tencent.py tests/test_tencent_source.py
git commit -m "feat: 实现 _TencentDocClient 核心方法"
```

---

### Task 3: 实现 `TencentSource.list()`

**Files:**
- Modify: `docupipe/sources/tencent.py`
- Modify: `tests/test_tencent_source.py`

- [ ] **Step 1: 写 `TencentSource` 初始化和 `list()` 的测试**

追加到 `tests/test_tencent_source.py`：

```python
from docupipe.sources.tencent import TencentSource


class TestTencentSourceInit(unittest.TestCase):
    """测试 TencentSource 初始化"""

    def test_missing_space_id_raises(self):
        """不提供 space_id 时应报错"""
        with self.assertRaises(ValueError) as ctx:
            TencentSource()
        self.assertIn("space_id", str(ctx.exception))

    @patch("docupipe.sources.tencent._TencentDocClient")
    def test_init_with_space_id(self, mock_client_cls):
        """提供 space_id 正常初始化"""
        source = TencentSource(space_id="space_123")
        self.assertEqual(source._space_id, "space_123")

    @patch("docupipe.sources.tencent._TencentDocClient")
    def test_init_with_include_types(self, mock_client_cls):
        """include_types 正确存储"""
        source = TencentSource(space_id="space_123", include_types=["smartcanvas", "word"])
        self.assertEqual(source._include_types, {"smartcanvas", "word"})


class TestTencentSourceList(unittest.TestCase):
    """测试 TencentSource.list()"""

    def _make_source(self, **kwargs):
        with patch("docupipe.sources.tencent._TencentDocClient"):
            return TencentSource(space_id="space_123", **kwargs)

    @patch.object(_TencentDocClient, "list_nodes")
    def test_list_flat_documents(self, mock_list_nodes):
        """测试列出扁平目录下的文档"""
        mock_list_nodes.return_value = {
            "children": [
                {"node_id": "doc1", "title": "文档1", "node_type": "wiki_file", "has_child": False, "doc_type": "smartcanvas"},
                {"node_id": "doc2", "title": "文档2", "node_type": "wiki_file", "has_child": False, "doc_type": "word"},
            ],
            "has_next": False,
        }
        source = self._make_source()
        result = source.list()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].id, "doc1")
        self.assertEqual(result[0].title, "文档1")
        self.assertEqual(result[1].id, "doc2")

    @patch.object(_TencentDocClient, "list_nodes")
    def test_list_skips_folders(self, mock_list_nodes):
        """测试跳过 wiki_folder 节点"""
        mock_list_nodes.return_value = {
            "children": [
                {"node_id": "doc1", "title": "文档1", "node_type": "wiki_file", "has_child": False, "doc_type": "smartcanvas"},
                {"node_id": "folder1", "title": "文件夹", "node_type": "wiki_folder", "has_child": False},
            ],
            "has_next": False,
        }
        source = self._make_source()
        result = source.list()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "doc1")

    @patch.object(_TencentDocClient, "list_nodes")
    def test_list_filters_by_include_types(self, mock_list_nodes):
        """测试 include_types 过滤"""
        mock_list_nodes.return_value = {
            "children": [
                {"node_id": "doc1", "title": "文档1", "node_type": "wiki_file", "has_child": False, "doc_type": "smartcanvas"},
                {"node_id": "doc2", "title": "文档2", "node_type": "wiki_file", "has_child": False, "doc_type": "word"},
            ],
            "has_next": False,
        }
        with patch("docupipe.sources.tencent._TencentDocClient"):
            source = TencentSource(space_id="space_123", include_types=["smartcanvas"])
        result = source.list()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "doc1")

    @patch.object(_TencentDocClient, "list_nodes")
    def test_list_recursive_folders(self, mock_list_nodes):
        """测试递归进入子文件夹"""
        mock_list_nodes.side_effect = [
            # 第一次调用：根目录
            {
                "children": [
                    {"node_id": "doc1", "title": "文档1", "node_type": "wiki_file", "has_child": False, "doc_type": "smartcanvas"},
                    {"node_id": "folder1", "title": "子文件夹", "node_type": "wiki_folder", "has_child": True},
                ],
                "has_next": False,
            },
            # 第二次调用：子文件夹
            {
                "children": [
                    {"node_id": "doc2", "title": "文档2", "node_type": "wiki_file", "has_child": False, "doc_type": "word"},
                ],
                "has_next": False,
            },
        ]
        source = self._make_source()
        result = source.list()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].id, "doc1")
        self.assertEqual(result[1].id, "doc2")
        self.assertEqual(result[1].path, "子文件夹/文档2")

    @patch.object(_TencentDocClient, "list_nodes")
    def test_list_with_parent_id(self, mock_list_nodes):
        """测试指定 parent_id 时只遍历该子目录"""
        mock_list_nodes.return_value = {
            "children": [
                {"node_id": "doc1", "title": "文档1", "node_type": "wiki_file", "has_child": False, "doc_type": "smartcanvas"},
            ],
            "has_next": False,
        }
        with patch("docupipe.sources.tencent._TencentDocClient"):
            source = TencentSource(space_id="space_123", parent_id="folder_abc")
        result = source.list()

        mock_list_nodes.assert_called_with("space_123", parent_id="folder_abc", num=0)
        self.assertEqual(len(result), 1)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/liling/src/ai/docpipe && python -m pytest tests/test_tencent_source.py::TestTencentSourceInit -v`

Expected: FAIL — `TencentSource` 不存在

- [ ] **Step 3: 实现 `TencentSource` 类（list 部分）**

在 `docupipe/sources/tencent.py` 末尾追加：

```python
from docupipe.sources import register_source
from docupipe.sources.base import SourceBase
from docupipe.models import Bundle, BundleMeta, FileItem


@register_source("tencent")
class TencentSource(SourceBase):
    def __init__(
        self,
        space_id: str | None = None,
        parent_id: str | None = None,
        folders: list[str] | None = None,
        include_types: list[str] | None = None,
        fetch_mode: str = "markdown",
        **kwargs,
    ):
        if not space_id:
            raise ValueError("必须提供 space_id 参数")

        token = os.environ.get("TENCENT_DOCS_TOKEN", "")
        if not token:
            raise ValueError("环境变量 TENCENT_DOCS_TOKEN 未设置")

        self._space_id = space_id
        self._parent_id = parent_id
        self._folders = folders
        self._include_types = set(include_types) if include_types else None
        self._fetch_mode = fetch_mode
        self._client = _TencentDocClient(token)

    def list(self) -> list[BundleMeta]:
        logger.info("列出文档: space_id=%s, parent_id=%s", self._space_id, self._parent_id or "(根)")

        if self._folders:
            nodes = []
            for folder_path in self._folders:
                folder_id = self._resolve_folder_path(folder_path)
                if folder_id:
                    nodes.extend(self._collect_nodes(self._space_id, folder_id, parent_path=folder_path))
                else:
                    logger.warning("跳过无效的文件夹路径: %s", folder_path)
        else:
            nodes = self._collect_nodes(self._space_id, self._parent_id)

        result = []
        for node in nodes:
            node_type = node.get("node_type", "")
            if node_type == "wiki_folder":
                continue
            doc_type = node.get("doc_type", "")
            if self._include_types is not None and doc_type not in self._include_types:
                continue

            result.append(BundleMeta(
                id=node.get("node_id", ""),
                title=node.get("title", "未命名"),
                path=node.get("_path", ""),
                hash="",
                extra={
                    "doc_type": doc_type,
                    "node_type": node_type,
                    "has_child": node.get("has_child", False),
                },
            ))

        logger.info("列出文档完成: 共 %d 个文档", len(result))
        return result

    def _collect_nodes(self, space_id: str, parent_id: str | None = None, parent_path: str = "") -> list[dict]:
        """递归收集空间节点"""
        all_items: list[dict] = []
        num = 0
        while True:
            data = self._client.list_nodes(space_id, parent_id=parent_id, num=num)
            children = data.get("children", []) if isinstance(data, dict) else []
            for child in children:
                title = child.get("title", "未命名")
                current_path = f"{parent_path}/{title}" if parent_path else title
                if child.get("node_type") == "wiki_folder" and child.get("has_child"):
                    all_items.extend(self._collect_nodes(space_id, child.get("node_id"), current_path))
                else:
                    child["_path"] = current_path
                    all_items.append(child)

            has_next = data.get("has_next", False) if isinstance(data, dict) else False
            if not has_next:
                break
            num += 1
        return all_items

    def _resolve_folder_path(self, path: str) -> str | None:
        """将文件夹路径解析为 node_id"""
        segments = [s.strip() for s in path.split("/") if s.strip()]
        if not segments:
            return None
        parent_id = None
        for segment in segments:
            data = self._client.list_nodes(self._space_id, parent_id=parent_id, num=0)
            children = data.get("children", []) if isinstance(data, dict) else []
            matched = None
            for child in children:
                if child.get("node_type") == "wiki_folder" and child.get("title") == segment:
                    matched = child
                    break
            if not matched:
                logger.warning("未找到文件夹: '%s'", segment)
                return None
            parent_id = matched.get("node_id")
        return parent_id
```

注意：`import` 语句需要在文件顶部添加：

在文件顶部的 import 区域添加：
```python
from docupipe.sources import register_source
from docupipe.sources.base import SourceBase
from docupipe.models import Bundle, BundleMeta, FileItem
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/liling/src/ai/docpipe && python -m pytest tests/test_tencent_source.py -v`

Expected: 所有测试 PASS

- [ ] **Step 5: Commit**

```bash
git add docupipe/sources/tencent.py tests/test_tencent_source.py
git commit -m "feat: 实现 TencentSource 初始化和 list()"
```

---

### Task 4: 实现 `TencentSource.fetch()`

**Files:**
- Modify: `docupipe/sources/tencent.py`
- Modify: `tests/test_tencent_source.py`

- [ ] **Step 1: 写 `fetch()` 三种模式的测试**

追加到 `tests/test_tencent_source.py`：

```python
class TestTencentSourceFetch(unittest.TestCase):
    """测试 TencentSource.fetch()"""

    def _make_source(self, fetch_mode="markdown"):
        with patch("docupipe.sources.tencent._TencentDocClient"):
            source = TencentSource(space_id="space_123", fetch_mode=fetch_mode)
        return source

    @patch.object(_TencentDocClient, "get_content")
    def test_fetch_markdown_mode(self, mock_get_content):
        """测试 markdown 模式返回 markdown FileItem"""
        mock_get_content.return_value = "# 标题\n\n正文"
        source = self._make_source(fetch_mode="markdown")
        meta = BundleMeta(id="doc1", title="测试文档", extra={"doc_type": "smartcanvas"})

        bundle = source.fetch(meta)

        self.assertEqual(len(bundle.files), 1)
        self.assertEqual(bundle.files[0].name, "测试文档.md")
        self.assertEqual(bundle.files[0].content, "# 标题\n\n正文")
        self.assertEqual(bundle.files[0].content_type, "text/markdown")
        self.assertEqual(bundle.files[0].role, "main")

    @patch("requests.get")
    @patch.object(_TencentDocClient, "export_file")
    def test_fetch_export_mode(self, mock_export, mock_requests_get):
        """测试 export 模式返回导出文件"""
        mock_export.return_value = ("https://example.com/doc.docx", "测试文档.docx")
        mock_resp = MagicMock()
        mock_resp.content = b"PK\x03\x04docx-bytes"
        mock_resp.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_resp

        source = self._make_source(fetch_mode="export")
        meta = BundleMeta(id="doc1", title="测试文档", extra={"doc_type": "word"})

        bundle = source.fetch(meta)

        self.assertEqual(len(bundle.files), 1)
        self.assertEqual(bundle.files[0].name, "测试文档.docx")
        self.assertEqual(bundle.files[0].content, b"PK\x03\x04docx-bytes")
        self.assertEqual(bundle.files[0].role, "main")
        self.assertTrue(bundle.context.get("_needs_conversion"))

    @patch("requests.get")
    @patch.object(_TencentDocClient, "get_content")
    @patch.object(_TencentDocClient, "export_file")
    def test_fetch_both_mode(self, mock_export, mock_get_content, mock_requests_get):
        """测试 both 模式返回两个 FileItem"""
        mock_get_content.return_value = "# 标题"
        mock_export.return_value = ("https://example.com/doc.docx", "文档.docx")
        mock_resp = MagicMock()
        mock_resp.content = b"docx-bytes"
        mock_resp.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_resp

        source = self._make_source(fetch_mode="both")
        meta = BundleMeta(id="doc1", title="测试文档", extra={"doc_type": "smartcanvas"})

        bundle = source.fetch(meta)

        self.assertEqual(len(bundle.files), 2)
        # markdown 是 main
        self.assertEqual(bundle.files[0].name, "测试文档.md")
        self.assertEqual(bundle.files[0].role, "main")
        # 导出文件是 attachment
        self.assertEqual(bundle.files[1].name, "文档.docx")
        self.assertEqual(bundle.files[1].role, "attachment")
        self.assertTrue(bundle.context.get("_needs_conversion"))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/liling/src/ai/docpipe && python -m pytest tests/test_tencent_source.py::TestTencentSourceFetch -v`

Expected: FAIL — `TencentSource` 没有 `fetch` 方法

- [ ] **Step 3: 实现 `fetch()` 方法**

在 `TencentSource` 类中追加 `fetch` 方法：

```python
    def fetch(self, meta: BundleMeta) -> Bundle:
        file_id = meta.id
        context = dict(meta.extra)

        if self._fetch_mode in ("markdown", "both"):
            markdown_content = self._client.get_content(file_id)
            md_file = FileItem(
                name=f"{meta.title}.md",
                content=markdown_content,
                content_type="text/markdown",
                role="main",
            )

        if self._fetch_mode in ("export", "both"):
            file_url, file_name = self._client.export_file(file_id)
            resp = requests.get(file_url, timeout=120)
            resp.raise_for_status()
            context["_needs_conversion"] = True
            export_file = FileItem(
                name=file_name or f"{meta.title}.docx",
                content=resp.content,
                content_type="application/octet-stream",
                role="main" if self._fetch_mode == "export" else "attachment",
            )

        if self._fetch_mode == "markdown":
            return Bundle(files=[md_file], context=context)
        elif self._fetch_mode == "export":
            return Bundle(files=[export_file], context=context)
        else:  # both
            return Bundle(files=[md_file, export_file], context=context)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/liling/src/ai/docpipe && python -m pytest tests/test_tencent_source.py -v`

Expected: 所有测试 PASS

- [ ] **Step 5: Commit**

```bash
git add docupipe/sources/tencent.py tests/test_tencent_source.py
git commit -m "feat: 实现 TencentSource.fetch() 三种模式"
```

---

### Task 5: 注册 source 并集成

**Files:**
- Modify: `docupipe/sources/__init__.py:27`

- [ ] **Step 1: 在 `__init__.py` 中添加 import**

在 `docupipe/sources/__init__.py` 末尾添加：

```python
import docupipe.sources.tencent  # noqa: F401, E402
```

- [ ] **Step 2: 验证注册成功**

Run: `cd /Users/liling/src/ai/docpipe && python -c "from docupipe.sources import SOURCES; print('tencent' in SOURCES)"`

Expected: `True`

- [ ] **Step 3: 运行全部测试确认无回归**

Run: `cd /Users/liling/src/ai/docpipe && python -m pytest tests/ -v`

Expected: 所有测试 PASS

- [ ] **Step 4: Commit**

```bash
git add docupipe/sources/__init__.py
git commit -m "feat: 注册 tencent source"
```

---

## Self-Review

**Spec 覆盖检查：**
- `_TencentDocClient` 封装 MCP 调用 → Task 2 ✓
- `list()` 遍历节点树、分页、递归、过滤 → Task 3 ✓
- `fetch()` markdown/export/both 三种模式 → Task 4 ✓
- `@register_source("tencent")` 注册 → Task 5 ✓
- `fastmcp` 依赖 → Task 1 ✓
- 环境变量 `TENCENT_DOCS_TOKEN` → Task 3 ✓
- export 轮询超时 → Task 2（`_EXPORT_MAX_POLLS=60`）✓
- `folders` 路径解析 → Task 3（`_resolve_folder_path`）✓

**Placeholder 扫描：** 无 TBD/TODO。

**类型一致性：** `list_nodes` 返回 `dict`，`get_content` 返回 `str`，`export_file` 返回 `tuple[str, str]`，在所有 Task 中一致。
