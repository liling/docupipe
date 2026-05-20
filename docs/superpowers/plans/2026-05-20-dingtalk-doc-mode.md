# Dingtalk Source doc 模式 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 DingtalkSource 中新增 doc 模式，支持从任意钉盘文件夹（包括共享文件夹）递归获取文档。

**Architecture:** 在现有 DingtalkSource 中新增 `mode` 参数，`list()` 方法根据 mode 分支。doc 模式通过 `_WikiClient.list_nodes_by_folder()` 按 folderId 列出节点并递归。`fetch()` 完全复用。

**Tech Stack:** Python 3.11+ / pytest / unittest.mock

---

### Task 1: _WikiClient 新增 list_nodes_by_folder 方法

**Files:**
- Modify: `docupipe/sources/dingtalk.py:21-81` (_WikiClient 类)
- Modify: `tests/test_docpipe.py`

- [ ] **Step 1: 写失败测试 — list_nodes_by_folder 调用正确的 dws 命令**

在 `tests/test_docpipe.py` 文件末尾新增测试类：

```python
class TestWikiClientListNodesByFolder:
    def test_calls_doc_list_with_folder(self, monkeypatch):
        from docupipe.sources.dingtalk import _WikiClient
        captured = {}
        def mock_run_dws(self, args):
            captured["args"] = args
            return {"nodes": [{"nodeId": "abc", "name": "doc1", "nodeType": "doc"}]}
        monkeypatch.setattr(_WikiClient, "_run_dws", mock_run_dws)
        client = _WikiClient()
        result = client.list_nodes_by_folder("folder123")
        assert captured["args"] == ["doc", "list", "--folder", "folder123", "--page-size", "50"]
        assert len(result) == 1
        assert result[0]["nodeId"] == "abc"

    def test_pagination(self, monkeypatch):
        from docupipe.sources.dingtalk import _WikiClient
        call_count = 0
        def mock_run_dws(self, args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"nodes": [{"nodeId": "a"}], "nextPageToken": "tok1"}
            return {"nodes": [{"nodeId": "b"}]}
        monkeypatch.setattr(_WikiClient, "_run_dws", mock_run_dws)
        client = _WikiClient()
        result = client.list_nodes_by_folder("f1")
        assert len(result) == 2
        assert call_count == 2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestWikiClientListNodesByFolder -v`
Expected: FAIL — `list_nodes_by_folder` 方法不存在

- [ ] **Step 3: 实现 list_nodes_by_folder**

在 `docupipe/sources/dingtalk.py` 的 `_WikiClient` 类中，在 `list_nodes` 方法之后（约第 81 行后）添加：

```python
    def list_nodes_by_folder(self, folder_id: str) -> list[dict]:
        """列出指定文件夹下的节点（用于 doc 模式）"""
        all_items: list[dict] = []
        page_token: str | None = None
        page_count = 0
        while True:
            page_count += 1
            args = ["doc", "list", "--folder", folder_id, "--page-size", "50"]
            if page_token:
                args += ["--page-token", page_token]
            data = self._run_dws(args)
            items = data.get("nodes", []) if isinstance(data, dict) else []
            all_items.extend(items)
            logger.debug("列出节点: 第 %d 页, 获取 %d 条", page_count, len(items))
            page_token = data.get("nextPageToken") if isinstance(data, dict) else None
            if not page_token:
                break
        logger.info("列出节点完成: folder=%s, 共 %d 页, %d 个节点", folder_id, page_count, len(all_items))
        return all_items
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestWikiClientListNodesByFolder -v`
Expected: PASS

- [ ] **Step 5: 运行全量测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add docupipe/sources/dingtalk.py tests/test_docpipe.py
git commit -m "feat: _WikiClient 新增 list_nodes_by_folder 方法"
```

---

### Task 2: DingtalkSource 新增 mode 参数和初始化逻辑

**Files:**
- Modify: `docupipe/sources/dingtalk.py:109-133` (DingtalkSource.__init__)
- Modify: `tests/test_docpipe.py`

- [ ] **Step 1: 写失败测试 — mode=doc 初始化**

在 `tests/test_docpipe.py` 文件末尾新增测试类：

```python
class TestDingtalkSourceDocMode:
    def test_doc_mode_requires_folder_id(self):
        from docupipe.sources.dingtalk import DingtalkSource
        with pytest.raises(ValueError, match="folder_id"):
            DingtalkSource(mode="doc")

    def test_doc_mode_stores_folder_id(self, monkeypatch):
        from docupipe.sources.dingtalk import DingtalkSource
        # 不需要 _WikiClient 调用，因为 doc 模式不解析 space
        source = DingtalkSource(mode="doc", folder_id="test_folder_id")
        assert source._mode == "doc"
        assert source._doc_folder_id == "test_folder_id"

    def test_wiki_mode_default(self, monkeypatch):
        from docupipe.sources.dingtalk import DingtalkSource
        monkeypatch.setattr("docupipe.sources.dingtalk._WikiClient.resolve_space_name", lambda self, x: "ws1")
        source = DingtalkSource(space="测试")
        assert source._mode == "wiki"

    def test_invalid_mode_raises(self):
        from docupipe.sources.dingtalk import DingtalkSource
        with pytest.raises(ValueError, match="mode"):
            DingtalkSource(mode="invalid", folder_id="f1")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestDingtalkSourceDocMode -v`
Expected: FAIL — `__init__` 不接受 `mode` 参数

- [ ] **Step 3: 修改 __init__ 支持 mode 参数**

将 `docupipe/sources/dingtalk.py` 中 DingtalkSource 的 `__init__` 方法替换为：

```python
@register_source("dingtalk")
class DingtalkSource(SourceBase):
    def __init__(self, space: str | None = None, space_id: str | None = None,
                 folder_id: str | None = None, folders: list[str] | None = None,
                 include_types: list[str] | None = None, mode: str = "wiki",
                 **kwargs):
        self._mode = mode
        if mode == "doc":
            if not folder_id:
                raise ValueError("doc 模式必须提供 folder_id 参数")
            self._doc_folder_id = folder_id
            self._include_types = set(include_types) if include_types else None
            self._client = _WikiClient()
            return

        if mode != "wiki":
            raise ValueError(f"不支持的 mode: {mode}，可选值: wiki, doc")

        # wiki 模式：原有逻辑
        if space and space_id:
            logger.warning("同时提供了 space 和 space_id，将优先使用 space")
        if space:
            resolved_id = _WikiClient().resolve_space_name(space)
            if not resolved_id:
                raise ValueError(f"无法找到知识库: '{space}'")
            self._space_id = resolved_id
            self._space_name = space
        elif space_id:
            self._space_id = space_id
            self._space_name = ""
        else:
            raise ValueError("wiki 模式必须提供 space 或 space_id 参数")

        self._folder_id = folder_id
        self._folders = folders
        self._include_types = set(include_types) if include_types else None
        self._client = _WikiClient()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestDingtalkSourceDocMode -v`
Expected: PASS

- [ ] **Step 5: 运行全量测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add docupipe/sources/dingtalk.py tests/test_docpipe.py
git commit -m "feat: DingtalkSource 新增 mode 参数和 doc 模式初始化"
```

---

### Task 3: 实现 list() 的 doc 模式分支

**Files:**
- Modify: `docupipe/sources/dingtalk.py:138-192` (list 方法)
- Modify: `tests/test_docpipe.py`

- [ ] **Step 1: 写失败测试 — doc 模式的 list 递归收集节点**

在 `tests/test_docpipe.py` 文件末尾新增测试类：

```python
class TestDingtalkSourceDocList:
    def _mock_list_nodes_by_folder(self, monkeypatch, folder_nodes):
        """mock list_nodes_by_folder，返回指定的节点树"""
        from docupipe.sources.dingtalk import _WikiClient

        def mock_list(self, folder_id):
            return folder_nodes.get(folder_id, [])
        monkeypatch.setattr(_WikiClient, "list_nodes_by_folder", mock_list)

    def test_doc_mode_list_collects_files(self, monkeypatch):
        from docupipe.sources.dingtalk import DingtalkSource
        nodes = {
            "f1": [
                {"nodeId": "doc1", "name": "文档1", "nodeType": "doc",
                 "contentType": "DOCUMENT", "extension": "", "updateTime": 1000},
                {"nodeId": "doc2", "name": "文档2.docx", "nodeType": "doc",
                 "contentType": "DOCUMENT", "extension": "docx", "updateTime": 2000},
            ]
        }
        self._mock_list_nodes_by_folder(monkeypatch, nodes)
        source = DingtalkSource(mode="doc", folder_id="f1")
        result = source.list()
        assert len(result) == 2
        assert result[0].id == "doc1"
        assert result[1].id == "doc2"

    def test_doc_mode_list_recursive_folders(self, monkeypatch):
        from docupipe.sources.dingtalk import DingtalkSource
        nodes = {
            "root": [
                {"nodeId": "sub1", "name": "子文件夹", "nodeType": "folder", "hasChildren": True},
                {"nodeId": "doc1", "name": "根文件.txt", "nodeType": "doc",
                 "contentType": "FILE", "extension": "txt", "updateTime": 1000},
            ],
            "sub1": [
                {"nodeId": "doc2", "name": "子文件.pdf", "nodeType": "doc",
                 "contentType": "FILE", "extension": "pdf", "updateTime": 2000},
            ]
        }
        self._mock_list_nodes_by_folder(monkeypatch, nodes)
        source = DingtalkSource(mode="doc", folder_id="root")
        result = source.list()
        assert len(result) == 2
        paths = [r.path for r in result]
        assert "根文件.txt" in paths
        assert "子文件夹/子文件.pdf" in paths

    def test_doc_mode_list_no_space_name(self, monkeypatch):
        from docupipe.sources.dingtalk import DingtalkSource
        nodes = {
            "f1": [
                {"nodeId": "doc1", "name": "文档", "nodeType": "doc",
                 "contentType": "DOCUMENT", "extension": "", "updateTime": 1000},
            ]
        }
        self._mock_list_nodes_by_folder(monkeypatch, nodes)
        source = DingtalkSource(mode="doc", folder_id="f1")
        result = source.list()
        assert result[0].extra["space_name"] == ""

    def test_doc_mode_list_skip_folders(self, monkeypatch):
        from docupipe.sources.dingtalk import DingtalkSource
        nodes = {
            "f1": [
                {"nodeId": "empty", "name": "空文件夹", "nodeType": "folder", "hasChildren": False},
            ]
        }
        self._mock_list_nodes_by_folder(monkeypatch, nodes)
        source = DingtalkSource(mode="doc", folder_id="f1")
        result = source.list()
        assert len(result) == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestDingtalkSourceDocList -v`
Expected: FAIL — list() 中没有 doc 模式分支

- [ ] **Step 3: 实现 list() 的 doc 模式分支和 _collect_doc_nodes**

在 `docupipe/sources/dingtalk.py` 的 `list()` 方法开头插入 doc 模式分支。将现有 list() 方法改为：

```python
    def list(self) -> list[BundleMeta]:
        if self._mode == "doc":
            return self._list_doc_mode()

        # --- wiki 模式（原有逻辑不变） ---
        # 如果通过 space_id 传入且没有名称，尝试获取名称
        if not self._space_name:
            try:
                space_info = self._client.get_space_info(self._space_id)
                self._space_name = space_info.get("name", self._space_id)
            except Exception as e:
                logger.warning("获取知识库名称失败: %s, 使用 ID 作为名称: %s", e, self._space_id)
                self._space_name = self._space_id
```

然后在 `_collect_nodes` 方法之前（约第 272 行）添加两个新方法：

```python
    def _list_doc_mode(self) -> list[BundleMeta]:
        """doc 模式：从指定文件夹递归列出文档"""
        logger.info("列出文档: folder=%s", self._doc_folder_id)
        nodes = self._collect_doc_nodes(self._doc_folder_id)
        result = []
        for node in nodes:
            node_type = node.get("nodeType", "")
            if node_type == "folder":
                continue
            node_id = node.get("nodeId", "")
            title = node.get("name", "未命名")
            content_type = node.get("contentType", "")
            if self._include_types is not None and content_type not in self._include_types:
                continue
            extension = node.get("extension", "")

            if content_type == "DOCUMENT" and not extension:
                info = self._client.get_node_info(node_id)
                extension = info.get("extension", "")
                logger.debug("doc info 补全 extension: %s → %s", title, extension or "(空)")

            result.append(BundleMeta(
                id=node_id,
                title=title,
                path=node.get("_path", ""),
                hash="",
                extra={
                    "dingtalk_content_type": content_type,
                    "extension": extension,
                    "dingtalk_extension": extension,
                    "dingtalk_update_time": node.get("updateTime"),
                    "dingtalk_node_type": node_type,
                    "space_name": "",
                    "mtime": node.get("updateTime"),
                },
            ))
        logger.info("列出文档完成: 共 %d 个文档", len(result))
        return result

    def _collect_doc_nodes(self, folder_id: str, parent_path: str = "") -> list[dict]:
        """doc 模式：递归收集文件夹下的所有文档节点"""
        logger.debug("收集 doc 节点: folder=%s", folder_id)
        nodes = self._client.list_nodes_by_folder(folder_id)
        result = []
        for node in nodes:
            title = node.get("name", "未命名")
            node_id = node.get("nodeId", "")
            node_type = node.get("nodeType", "")
            current_path = f"{parent_path}/{title}" if parent_path else title

            if node_type == "folder":
                if node.get("hasChildren"):
                    result.extend(self._collect_doc_nodes(node_id, current_path))
            else:
                node["_path"] = current_path
                result.append(node)
        return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestDingtalkSourceDocList -v`
Expected: PASS

- [ ] **Step 5: 运行全量测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add docupipe/sources/dingtalk.py tests/test_docpipe.py
git commit -m "feat: 实现 list() 的 doc 模式分支和递归节点收集"
```

---

### Task 4: 运行全量测试确认无回归

**Files:**
- 无修改

- [ ] **Step 1: 运行全量测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 2: 验证 wiki 模式不受影响**

Run: `python -m pytest tests/test_docpipe.py::TestDingtalkSource -v -k "wiki or dingtalk"`
Expected: 全部 PASS（原有 wiki 模式测试）
