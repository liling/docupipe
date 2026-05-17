# Context 字段标准化 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一 `Bundle.context` 和 `FileItem.content_type` 的命名与值格式，消除扩展名/类型/MIME 混用。

**Architecture:** 新增 `guess_mime_type()` 工具函数，修改三个 source 的 extra/context key 为 snake_case + source 前缀，修复 FileItem.content_type 为标准 MIME type，更新 destination 和测试。在 models.py 维护 context 字段注册表注释。

**Tech Stack:** Python 3.11+ / pytest

---

### Task 1: 新建 guess_mime_type 工具函数

**Files:**
- Create: `docupipe/utils.py`
- Test: `tests/test_utils.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_utils.py
from docupipe.utils import guess_mime_type


def test_known_extensions():
    assert guess_mime_type("pdf") == "application/pdf"
    assert guess_mime_type("md") == "text/markdown"
    assert guess_mime_type("docx") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert guess_mime_type("xlsx") == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert guess_mime_type("pptx") == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    assert guess_mime_type("png") == "image/png"
    assert guess_mime_type("jpg") == "image/jpeg"
    assert guess_mime_type("txt") == "text/plain"
    assert guess_mime_type("html") == "text/html"
    assert guess_mime_type("adoc") == "text/markdown"


def test_unknown_extension_returns_default():
    assert guess_mime_type("xyz") == "application/octet-stream"
    assert guess_mime_type("xyz", default="") == ""
    assert guess_mime_type("") == ""
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_utils.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: 实现**

```python
# docupipe/utils.py
from __future__ import annotations

_MIME_MAP = {
    "md": "text/markdown",
    "markdown": "text/markdown",
    "adoc": "text/markdown",
    "txt": "text/plain",
    "csv": "text/csv",
    "html": "text/html",
    "htm": "text/html",
    "json": "application/json",
    "xml": "application/xml",
    "yaml": "application/x-yaml",
    "yml": "application/x-yaml",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "doc": "application/msword",
    "xls": "application/vnd.ms-excel",
    "ppt": "application/vnd.ms-powerpoint",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "svg": "image/svg+xml",
    "emf": "image/x-emf",
    "xmind": "application/octet-stream",
}


def guess_mime_type(extension: str, default: str = "application/octet-stream") -> str:
    if not extension:
        return default or "application/octet-stream"
    return _MIME_MAP.get(extension.lower(), default)
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_utils.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add docupipe/utils.py tests/test_utils.py
git commit -m "feat: 新增 guess_mime_type 工具函数"
```

---

### Task 2: 在 models.py 添加 context 字段注册表

**Files:**
- Modify: `docupipe/models.py`

- [ ] **Step 1: 在 models.py 顶部（SkipBundle 类之前）添加注册表注释**

```python
# Bundle context 字段注册表
#
# 新增 source/step 时必须先查阅此表，复用已有 key 或按规则添加。
# 规则：
#   - 通用字段：snake_case，无前缀
#   - Source 特有字段：{source}_前缀 + snake_case
#   - 值类型：extension 是纯扩展名不含点号，content_type 必须是 MIME type
#
# Pipeline 注入字段（pipeline.py）：
#   id              | str  | 文档唯一标识
#   title           | str  | 文档标题
#   path            | str  | 文档路径
#   filename        | str  | 文件名
#   _source         | str  | 来源名称
#   hash            | str  | 内容 SHA-256 哈希
#   _step_progress  | callable | 进度回调（临时，step 执行期间存在）
#
# 通用字段（多个 source 共用）：
#   extension       | str  | 文件扩展名，不含点号 | Source 写入 | ConvertStep 读取
#   space_name      | str  | 知识库/空间名称      | 钉钉/腾讯写入 | Destination 读取
#   absolute_path   | str  | 本地文件绝对路径      | LocalDrive 写入 | ResolveAttachmentsStep 读取
#   image_metadata  | dict | 图片描述 AI 处理结果  | ImageDescriptionStep 写入
#
# Source 特有字段：
#   dingtalk_content_type | str | 钉钉文档类型枚举（ALIDOC/DOCUMENT 等）| DingtalkSource 写入
#   dingtalk_update_time  | int | 钉钉文档更新时间戳（毫秒）| DingtalkSource 写入 | HindsightDestination 读取
#   dingtalk_node_type    | str | 钉钉节点类型（folder/doc 等）| DingtalkSource 写入
#   tencent_doc_type      | str | 腾讯文档类型枚举（document/sheet 等）| TencentSource 写入
#   tencent_node_type     | str | 腾讯节点类型（wiki_folder/doc 等）| TencentSource 写入
#   tencent_has_child     | bool | 腾讯节点是否有子节点 | TencentSource 写入
```

- [ ] **Step 2: 运行测试确认无破坏**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add docupipe/models.py
git commit -m "docs: 在 models.py 添加 context 字段注册表"
```

---

### Task 3: 修改 localdrive source

**Files:**
- Modify: `docupipe/sources/localdrive.py:57-67`（list 方法 extra 字段）
- Modify: `docupipe/sources/localdrive.py:71-89`（fetch 方法 content_type）
- Test: `tests/test_docpipe.py:514-543`（TestLocalDriveSource 相关测试）

- [ ] **Step 1: 修改 list() 方法的 extra 字段**

将 `localdrive.py:62-67` 从：
```python
                extra={
                    "contentType": ext,
                    "extension": ext,
                    "absolute_path": str(f),
                    "size": f.stat().st_size,
                },
```
改为：
```python
                extra={
                    "extension": ext,
                    "absolute_path": str(f),
                    "size": f.stat().st_size,
                },
```

- [ ] **Step 2: 修改 fetch() 方法的 content_type**

将 `localdrive.py:71-89` 从：
```python
    def fetch(self, meta: BundleMeta) -> Bundle:
        abs_path = Path(meta.extra["absolute_path"])
        extension = meta.extra.get("extension", "")
        content_type = extension

        if extension in _TEXT_EXTENSIONS:
            content = abs_path.read_text(encoding="utf-8")
            content_type = "markdown"
        else:
            content = abs_path.read_bytes()

        return Bundle(
            files=[FileItem(
                name=Path(meta.path).name,
                content=content,
                content_type=content_type,
                role="main",
            )],
            context=dict(meta.extra),
        )
```
改为：
```python
    def fetch(self, meta: BundleMeta) -> Bundle:
        from docupipe.utils import guess_mime_type
        abs_path = Path(meta.extra["absolute_path"])
        extension = meta.extra.get("extension", "")

        if extension in _TEXT_EXTENSIONS:
            content = abs_path.read_text(encoding="utf-8")
        else:
            content = abs_path.read_bytes()

        content_type = guess_mime_type(extension) if extension else ""

        return Bundle(
            files=[FileItem(
                name=Path(meta.path).name,
                content=content,
                content_type=content_type,
                role="main",
            )],
            context=dict(meta.extra),
        )
```

- [ ] **Step 3: 修改 localdrive destination 的 _content_type_to_ext**

`localdrive.py` destination 的 `_content_type_to_ext` 已经处理了 `text/markdown` → `.md` 和通用 MIME → `.ext` 的映射，无需改动。

- [ ] **Step 4: 修改测试**

`tests/test_docpipe.py:523` — `assert bundle.main.content_type == "markdown"` 改为：
```python
assert bundle.main.content_type == "text/markdown"
```

`tests/test_docpipe.py:533` — `assert bundle.main.content_type == "pdf"` 改为：
```python
assert bundle.main.content_type == "application/pdf"
```

- [ ] **Step 5: 运行测试验证通过**

Run: `python -m pytest tests/test_docpipe.py::TestLocalDriveSource -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add docupipe/sources/localdrive.py tests/test_docpipe.py
git commit -m "fix: localdrive source 统一使用 MIME type 和 snake_case key"
```

---

### Task 4: 修改 dingtalk source

**Files:**
- Modify: `docupipe/sources/dingtalk.py:178-184`（list 方法 extra 字段）
- Modify: `docupipe/sources/dingtalk.py:222-237`（fetch 方法 content_type）
- Test: `tests/test_docpipe.py` 相关测试

- [ ] **Step 1: 修改 list() 方法的 extra 字段**

将 `dingtalk.py:178-184` 从：
```python
                extra={
                    "contentType": content_type,
                    "extension": extension,
                    "updateTime": node.get("updateTime"),
                    "nodeType": node_type,
                    "space_name": self._space_name,
                },
```
改为：
```python
                extra={
                    "dingtalk_content_type": content_type,
                    "extension": extension,
                    "dingtalk_update_time": node.get("updateTime"),
                    "dingtalk_node_type": node_type,
                    "space_name": self._space_name,
                },
```

- [ ] **Step 2: 修改 fetch() 方法**

将 `dingtalk.py:190` 从：
```python
        content_type = meta.extra.get("contentType", "")
```
改为：
```python
        content_type = meta.extra.get("dingtalk_content_type", "")
```

将 `dingtalk.py:234` 从：
```python
                    content_type=extension,
```
改为：
```python
                    content_type=guess_mime_type(extension),
```

在文件顶部添加 import：
```python
from docupipe.utils import guess_mime_type
```

- [ ] **Step 3: 修改测试**

`tests/test_docpipe.py:328-329` 中 dingtalk 相关测试 context 里的 `"contentType": "ALIDOC"` 改为 `"dingtalk_content_type": "ALIDOC"`。

搜索测试中所有引用 `contentType` 的地方，替换为 `dingtalk_content_type`。

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_docpipe.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add docupipe/sources/dingtalk.py tests/test_docpipe.py
git commit -m "fix: dingtalk source key 改为 snake_case + source 前缀，content_type 改为 MIME"
```

---

### Task 5: 修改 tencent source

**Files:**
- Modify: `docupipe/sources/tencent.py:194-199`（list 方法 extra 字段）
- Modify: `docupipe/sources/tencent.py:229-233`（fetch 方法 content_type）
- Test: `tests/test_tencent_source.py`

- [ ] **Step 1: 修改 list() 方法的 extra 字段**

将 `tencent.py:194-199` 从：
```python
                extra={
                    "doc_type": doc_type,
                    "node_type": node_type,
                    "has_child": node.get("has_child", False),
                },
```
改为：
```python
                extra={
                    "tencent_doc_type": doc_type,
                    "tencent_node_type": node_type,
                    "tencent_has_child": node.get("has_child", False),
                },
```

- [ ] **Step 2: 修改 fetch() 方法**

将 `tencent.py:227` 从：
```python
            ext = _DOC_TYPE_EXT.get(meta.extra.get("doc_type", ""), "docx")
```
改为：
```python
            ext = _DOC_TYPE_EXT.get(meta.extra.get("tencent_doc_type", ""), "docx")
```

将 `tencent.py:232` 从：
```python
                content_type=ext,
```
改为：
```python
                content_type=guess_mime_type(ext),
```

在文件顶部添加 import：
```python
from docupipe.utils import guess_mime_type
```

- [ ] **Step 3: 修改测试**

在 `tests/test_tencent_source.py` 中搜索 `"doc_type"` 在 extra 或 assert 中的引用，全部替换为 `"tencent_doc_type"`。具体行：
- 行 169: `self.assertEqual(metas[0].extra["doc_type"], "document")` → `metas[0].extra["tencent_doc_type"]`
- 行 203: `self.assertEqual(metas[0].extra["doc_type"], "sheet")` → `metas[0].extra["tencent_doc_type"]`
- 行 296: `"doc_type": "word"` → `"tencent_doc_type": "word"`
- 所有测试中 mock 数据里的 `"doc_type"` 键 → `"tencent_doc_type"`

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_tencent_source.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add docupipe/sources/tencent.py tests/test_tencent_source.py
git commit -m "fix: tencent source key 改为 snake_case + source 前缀，content_type 改为 MIME"
```

---

### Task 6: 修改 destination 读取端

**Files:**
- Modify: `docupipe/destinations/localdrive.py:109`（sidecar JSON key）
- Modify: `docupipe/destinations/hindsight.py:76,97,103`（context key 读取）

- [ ] **Step 1: 修改 localdrive destination sidecar**

将 `destinations/localdrive.py:109` 从：
```python
            "contentType": context.get("contentType", ""),
```
改为：
```python
            "content_type": context.get("dingtalk_content_type", ""),
```

- [ ] **Step 2: 修改 hindsight destination**

将 `destinations/hindsight.py:76` 从：
```python
        update_time = bundle_context.get("updateTime")
```
改为：
```python
        update_time = bundle_context.get("dingtalk_update_time")
```

将 `destinations/hindsight.py:97` 从：
```python
                "contentType": bundle_context.get("contentType", ""),
```
改为：
```python
                "content_type": bundle_context.get("dingtalk_content_type", ""),
```

将 `destinations/hindsight.py:103` 从：
```python
                "updateTime": str(update_time) if update_time else "",
```
改为：
```python
                "update_time": str(update_time) if update_time else "",
```

- [ ] **Step 3: 修改测试**

`tests/test_docpipe.py:328-329` 中 destination 测试如果断言了 sidecar JSON 内容（如 `meta_json["contentType"]`），需更新为 `meta_json["content_type"]`。

- [ ] **Step 4: 运行全部测试验证通过**

Run: `python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 5: 提交**

```bash
git add docupipe/destinations/localdrive.py docupipe/destinations/hindsight.py tests/
git commit -m "fix: destination 端 context key 更新为 snake_case"
```

---

### Task 7: 最终验证

- [ ] **Step 1: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 2: 检查是否有遗漏的旧 key 引用**

Run: `grep -rn '"contentType"\|"updateTime"\|"doc_type"' docupipe/`
Expected: 无结果（旧 key 全部清除）

- [ ] **Step 3: 确认新 key 已生效**

Run: `grep -rn 'dingtalk_content_type\|dingtalk_update_time\|tencent_doc_type' docupipe/`
Expected: 在 source、destination、测试中都有引用

- [ ] **Step 4: 提交（如有修复）**

```bash
git add -A
git commit -m "fix: 清理遗漏的旧 key 引用"
```
