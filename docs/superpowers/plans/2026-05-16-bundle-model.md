# Bundle 模型重构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 pipeline 数据传递单元从单个 Document 改为 Bundle（文档包），支持主文档 + 附件的显式传递。

**Architecture:** 引入 FileItem / Bundle / BundleMeta 三个数据类替代 Document / DocumentMeta。Source / Step / Destination 接口签名改为接收/返回 Bundle。图片等附件作为 FileItem 保留在 Bundle 中，不再写入临时目录，由 Destination 一并输出。

**Tech Stack:** Python 3.11+ / dataclasses / pytest

---

## 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| 改 | `docpipe/models.py` | 删除 DocumentMeta / Document / SkipDocument，新增 FileItem / Bundle / BundleMeta / SkipBundle |
| 改 | `docpipe/sources/base.py` | SourceBase 接口改为 Bundle 体系 |
| 改 | `docpipe/sources/dingtalk.py` | DingtalkSource 适配 Bundle |
| 改 | `docpipe/sources/localdrive.py` | LocalDriveSource 适配 Bundle |
| 改 | `docpipe/steps/base.py` | PipelineStep.process 签名改为 Bundle |
| 改 | `docpipe/steps/convert.py` | ConvertStep 适配 Bundle，图片不再写临时文件 |
| 改 | `docpipe/steps/image_description.py` | ImageDescriptionStep 适配 Bundle |
| 改 | `docpipe/destinations/base.py` | DestinationBase.write 签名改为 Bundle |
| 改 | `docpipe/destinations/hindsight.py` | HindsightDestination 适配 Bundle |
| 改 | `docpipe/destinations/localdrive.py` | LocalDriveDestination 适配 Bundle，输出附件 |
| 改 | `docpipe/pipeline.py` | Pipeline.run 流程改为 Bundle，删除旧逻辑 |
| 改 | `docpipe/image.py` | ImagePostProcessor.process 适配从 Bundle 中获取图片 |
| 改 | `docpipe/cli.py` | 消除旧逻辑引用 |
| 改 | `tests/test_docpipe.py` | 全面适配 Bundle |
| 改 | `tests/test_image.py` | 适配 Bundle |

---

### Task 1: 新数据模型 + 旧模型兼容层

**Files:**
- Modify: `docpipe/models.py`
- Test: `tests/test_models.py`（新建）

**目标:** 一次性引入 FileItem / Bundle / BundleMeta，同时临时保留 Document / DocumentMeta 作为兼容别名，让后续 Task 可以逐个文件迁移。

- [ ] **Step 1: 写 Bundle 数据模型的测试**

```python
# tests/test_models.py
from __future__ import annotations

import pytest
from docpipe.models import FileItem, Bundle, BundleMeta, SkipBundle


class TestFileItem:
    def test_defaults(self):
        f = FileItem(name="a.md", content="hello")
        assert f.content_type == ""
        assert f.role == "main"
        assert f.metadata == {}

    def test_with_all_fields(self):
        f = FileItem(name="img.png", content=b"\x89PNG", content_type="image/png",
                     role="image", metadata={"description": "a diagram"})
        assert f.role == "image"
        assert isinstance(f.content, bytes)


class TestBundle:
    def test_empty_bundle(self):
        b = Bundle()
        assert b.files == []
        assert b.context == {}
        assert b.main is None

    def test_main_returns_first_main_role(self):
        b = Bundle(files=[
            FileItem(name="img.png", content=b"", role="image"),
            FileItem(name="doc.md", content="hello", role="main"),
        ])
        assert b.main is not None
        assert b.main.name == "doc.md"

    def test_main_returns_none_when_no_main(self):
        b = Bundle(files=[
            FileItem(name="img.png", content=b"", role="image"),
        ])
        assert b.main is None

    def test_get_by_role(self):
        b = Bundle(files=[
            FileItem(name="a.png", content=b"", role="image"),
            FileItem(name="b.png", content=b"", role="image"),
            FileItem(name="doc.md", content="", role="main"),
        ])
        images = b.get_by_role("image")
        assert len(images) == 2
        assert images[0].name == "a.png"

    def test_add_no_conflict(self):
        b = Bundle()
        b.add(FileItem(name="a.md", content="hello"))
        assert len(b.files) == 1
        assert b.files[0].name == "a.md"

    def test_add_auto_rename_on_conflict(self):
        b = Bundle(files=[FileItem(name="image.png", content=b"")])
        b.add(FileItem(name="image.png", content=b"\x89"))
        assert len(b.files) == 2
        assert b.files[0].name == "image.png"
        assert b.files[1].name == "image_1.png"

    def test_add_auto_rename_sequential(self):
        b = Bundle(files=[
            FileItem(name="image.png", content=b""),
            FileItem(name="image_1.png", content=b""),
        ])
        b.add(FileItem(name="image.png", content=b"\x89"))
        assert b.files[2].name == "image_2.png"

    def test_remove_by_name(self):
        b = Bundle(files=[
            FileItem(name="a.md", content=""),
            FileItem(name="b.md", content=""),
        ])
        b.remove("a.md")
        assert len(b.files) == 1
        assert b.files[0].name == "b.md"

    def test_remove_nonexistent_noop(self):
        b = Bundle(files=[FileItem(name="a.md", content="")])
        b.remove("z.md")
        assert len(b.files) == 1


class TestBundleMeta:
    def test_defaults(self):
        m = BundleMeta(id="1", title="test")
        assert m.hash == ""
        assert m.extra == {}


class TestSkipBundle:
    def test_is_exception(self):
        with pytest.raises(SkipBundle):
            raise SkipBundle("skip this")
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL — `ImportError` 或 `AttributeError`，因为新类尚不存在

- [ ] **Step 3: 实现 FileItem / Bundle / BundleMeta，保留旧类作为兼容别名**

```python
# docpipe/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath


class SkipBundle(Exception):
    """Source 发出此异常表示该文档包应跳过"""
    pass


# 旧异常兼容别名
SkipDocument = SkipBundle


@dataclass
class FileItem:
    name: str
    content: str | bytes
    content_type: str = ""
    role: str = "main"
    metadata: dict = field(default_factory=dict)


@dataclass
class Bundle:
    files: list[FileItem] = field(default_factory=list)
    context: dict = field(default_factory=dict)

    @property
    def main(self) -> FileItem | None:
        """获取 role=main 的主文件"""
        return next((f for f in self.files if f.role == "main"), None)

    def get_by_role(self, role: str) -> list[FileItem]:
        return [f for f in self.files if f.role == role]

    def add(self, file: FileItem) -> None:
        if any(f.name == file.name for f in self.files):
            stem = PurePosixPath(file.name).stem
            suffix = PurePosixPath(file.name).suffix
            seq = 1
            while any(f.name == f"{stem}_{seq}{suffix}" for f in self.files):
                seq += 1
            file.name = f"{stem}_{seq}{suffix}"
        self.files.append(file)

    def remove(self, name: str) -> None:
        self.files = [f for f in self.files if f.name != name]


@dataclass
class BundleMeta:
    id: str
    title: str
    path: str = ""
    hash: str = ""
    extra: dict = field(default_factory=dict)


# 旧模型兼容别名 —— 迁移完成后删除
@dataclass
class DocumentMeta:
    id: str
    title: str
    path: str
    hash: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class Document:
    meta: DocumentMeta
    content: str | bytes
    content_type: str = "markdown"
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_models.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 运行全量测试确保未破坏旧代码**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS（旧代码仍使用 Document/DocumentMeta）

- [ ] **Step 6: 提交**

```bash
git add docpipe/models.py tests/test_models.py
git commit -m "feat: 新增 FileItem / Bundle / BundleMeta 数据模型，保留旧模型兼容"
```

---

### Task 2: 更新 Source 基类 + LocalDriveSource

**Files:**
- Modify: `docpipe/sources/base.py`
- Modify: `docpipe/sources/localdrive.py`

- [ ] **Step 1: 更新 SourceBase 接口**

```python
# docpipe/sources/base.py
from __future__ import annotations

from abc import ABC, abstractmethod

from docpipe.models import Bundle, BundleMeta


class SourceBase(ABC):
    name: str = ""

    @abstractmethod
    def list(self) -> list[BundleMeta]:
        """列出所有可获取的文档包"""

    @abstractmethod
    def fetch(self, meta: BundleMeta) -> Bundle:
        """获取单个文档包的完整内容"""
```

- [ ] **Step 2: 更新 LocalDriveSource**

关键变化：
- `list_documents()` → `list()`，返回 `list[BundleMeta]`
- `fetch()` 返回 `Bundle`，内容放入 `FileItem(role="main")`
- BundleMeta.path 使用 relative path

```python
# docpipe/sources/localdrive.py
from __future__ import annotations

import hashlib
from pathlib import Path

from docpipe.models import Bundle, BundleMeta, FileItem
from docpipe.sources import register_source
from docpipe.sources.base import SourceBase


@register_source("localdrive")
class LocalDriveSource(SourceBase):
    def __init__(
        self,
        input_dir: str,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        **kwargs,
    ):
        self._input_dir = Path(input_dir)
        if not self._input_dir.is_dir():
            raise ValueError(f"目录不存在: {input_dir}")
        self._include = include or []
        self._exclude = exclude or []

    def list(self) -> list[BundleMeta]:
        result = []
        for f in sorted(self._input_dir.rglob("*")):
            if not f.is_file():
                continue

            relative = f.relative_to(self._input_dir)

            if any(part.startswith(".") for part in relative.parts):
                continue
            if not f.suffix:
                continue

            rel_str = str(relative)

            if not self._matches_filters(rel_str):
                continue

            file_hash = hashlib.sha256(f.read_bytes()).hexdigest()
            ext = f.suffix.lstrip(".")
            content_type = _TEXT_EXTENSIONS.get(ext, ext) if ext in _TEXT_EXTENSIONS else ext
            result.append(BundleMeta(
                id=file_hash,
                title=f.stem,
                path=rel_str,
                hash=file_hash,
                extra={
                    "contentType": ext,
                    "extension": ext,
                    "absolute_path": str(f),
                    "size": f.stat().st_size,
                },
            ))
        return result

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
                metadata={"absolute_path": str(abs_path)},
            )],
            context=dict(meta.extra),
        )

    def _matches_filters(self, rel_path: str) -> bool:
        if rel_path.endswith(".json"):
            main_file = rel_path[:-5]
            if (self._input_dir / main_file).exists():
                return False
        if self._exclude and self._glob_matches(rel_path, self._exclude):
            return False
        if self._include and not self._glob_matches(rel_path, self._include):
            return False
        return True

    @staticmethod
    def _glob_matches(path: str, patterns: list[str]) -> bool:
        p = Path(path)
        return any(p.match(pattern) for pattern in patterns)


# content_type 映射
_MIME_MAP = {
    "md": "text/markdown", "markdown": "text/markdown", "mdown": "text/markdown",
    "txt": "text/plain", "csv": "text/csv", "tsv": "text/tab-separated-values",
    "html": "text/html", "htm": "text/html",
}

_TEXT_EXTENSIONS = frozenset({
    "md", "markdown", "mdown", "mkd",
    "txt", "csv", "tsv",
    "json", "yaml", "yml", "toml", "ini", "cfg",
    "xml", "html", "htm", "css", "js", "ts",
    "py", "rb", "go", "rs", "java", "c", "cpp", "h",
    "sh", "bash", "zsh",
    "log", "rst", "adoc",
})
```

- [ ] **Step 3: 暂时运行现有测试确认 Source 注册等仍通过**

由于测试尚未迁移，Source 接口签名改变会导致测试失败。暂时跳过，统一在 Task 8 中迁移所有测试。

- [ ] **Step 4: 提交**

```bash
git add docpipe/sources/base.py docpipe/sources/localdrive.py
git commit -m "feat: SourceBase 和 LocalDriveSource 迁移到 Bundle 模型"
```

---

### Task 3: 更新 DingtalkSource

**Files:**
- Modify: `docpipe/sources/dingtalk.py`

- [ ] **Step 1: 迁移 DingtalkSource 到 Bundle**

关键变化：
- `list_documents()` → `list()`，返回 `list[BundleMeta]`
- `fetch()` 返回 `Bundle`
- ALIDOC 类型：内容放入 FileItem(role="main")
- 文件类型：下载到临时文件，内容作为 FileItem(role="main") 的 bytes content，标记 `_needs_conversion` 在 context 中

```python
# docpipe/sources/dingtalk.py
from __future__ import annotations

import json
import logging
import re
import tempfile
from pathlib import Path

import requests

from docpipe.models import Bundle, BundleMeta, FileItem, SkipBundle
from docpipe.sources import register_source
from docpipe.sources.base import SourceBase

logger = logging.getLogger(__name__)

_ALIDOC_UNSUPPORTED = frozenset({"axls", "amindmap", "aform", "abitable", "able"})


class _WikiClient:
    # (保持不变，与当前实现完全相同)
    def _run_dws(self, args: list[str]) -> dict | list:
        import subprocess
        cmd = ["dws"] + args + ["--format", "json", "--yes", "--timeout", "300"]
        logger.debug("执行 dws 命令: %s", " ".join(args))
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
            raise RuntimeError(f"dws 命令失败: {' '.join(args)}\n{stderr}")
        stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
        if not stdout.strip():
            return {}
        return json.loads(stdout)

    def list_nodes(self, workspace_id: str, folder_id: str | None = None, folder_name: str = "", workspace_name: str = "") -> list[dict]:
        all_items: list[dict] = []
        page_token: str | None = None
        page_count = 0
        while True:
            page_count += 1
            args = ["doc", "list", "--workspace", workspace_id, "--page-size", "50"]
            if folder_id:
                args += ["--folder", folder_id]
            if page_token:
                args += ["--page-token", page_token]
            data = self._run_dws(args)
            items = data.get("nodes", []) if isinstance(data, dict) else []
            all_items.extend(items)
            logger.debug("列出节点: 第 %d 页, 获取 %d 条", page_count, len(items))
            page_token = data.get("nextPageToken") if isinstance(data, dict) else None
            if not page_token:
                break
        logger.info("列出节点完成: %s/%s, 共 %d 页, %d 个节点",
                     workspace_name or workspace_id, folder_name or "(根)", page_count, len(all_items))
        return all_items

    def read_document(self, node_id: str) -> str:
        logger.debug("读取文档: node_id=%s", node_id)
        data = self._run_dws(["doc", "read", "--node", node_id])
        if isinstance(data, dict):
            content = data.get("markdown", "")
            logger.debug("读取文档完成: node_id=%s, 长度=%d", node_id, len(content))
            return content
        return str(data)

    def download_file(self, node_id: str) -> str:
        logger.debug("下载文件: node_id=%s", node_id)
        data = self._run_dws(["doc", "download", "--node", node_id])
        if isinstance(data, dict):
            url = data.get("resourceUrl", "") or data.get("downloadUrl", "")
            logger.debug("下载文件完成: node_id=%s, URL 长度=%d", node_id, len(url))
            return url
        raise RuntimeError(f"下载失败，无法获取 URL: {node_id}")

    def get_space_info(self, space_id: str) -> dict:
        return self._run_dws(["wiki", "space", "get", "--id", space_id])

    def get_node_info(self, node_id: str) -> dict:
        data = self._run_dws(["doc", "info", "--node", node_id])
        return data if isinstance(data, dict) else {}


@register_source("dingtalk")
class DingtalkSource(SourceBase):
    def __init__(self, space_id: str, folder_id: str | None = None, folders: list[str] | None = None,
                 include_types: list[str] | None = None, **kwargs):
        self._space_id = space_id
        self._folder_id = folder_id
        self._folders = folders
        self._include_types = set(include_types) if include_types else None
        self._client = _WikiClient()
        self._space_name = ""

    def list(self) -> list[BundleMeta]:
        if not self._space_name:
            try:
                space_info = self._client.get_space_info(self._space_id)
                self._space_name = space_info.get("name", self._space_id)
            except Exception as e:
                logger.warning("获取知识库名称失败: %s, 使用 ID 作为名称: %s", e, self._space_id)
                self._space_name = self._space_id
        logger.info("列出文档: 知识库=%s, 文件夹=%s", self._space_name, self._folders or self._folder_id or "(根目录)")
        if self._folders:
            nodes = []
            for folder_path in self._folders:
                folder_id = self._resolve_folder_path(folder_path)
                if folder_id:
                    nodes.extend(self._collect_nodes(self._space_id, folder_id, parent_path=folder_path))
                else:
                    logger.warning("跳过无效的文件夹路径: %s", folder_path)
        else:
            nodes = self._collect_nodes(self._space_id, self._folder_id)
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
                    "contentType": content_type,
                    "extension": extension,
                    "updateTime": node.get("updateTime"),
                    "nodeType": node_type,
                    "space_name": self._space_name,
                },
            ))
        logger.info("列出文档完成: 共 %d 个文档", len(result))
        return result

    def fetch(self, meta: BundleMeta) -> Bundle:
        content_type = meta.extra.get("contentType", "")
        extension = meta.extra.get("extension", "")
        node_id = meta.id
        logger.info("获取文档: id=%s, title=%s, type=%s, ext=%s", meta.id, meta.title, content_type, extension or "(空)")

        if content_type == "ALIDOC" or extension == "adoc":
            if not extension:
                info = self._client.get_node_info(node_id)
                extension = info.get("extension", "")

            if extension in _ALIDOC_UNSUPPORTED:
                raise SkipBundle(f"ALIDOC 子类型暂不支持: extension={extension}")

            markdown = self._client.read_document(node_id)
            markdown = self._clean_html_tags(markdown)

            return Bundle(
                files=[FileItem(
                    name=f"{meta.title}.md",
                    content=markdown,
                    content_type="text/markdown",
                    role="main",
                )],
                context=dict(meta.extra),
            )
        else:
            # 下载文件
            tmp_path = self._download_to_temp(node_id, extension)
            content = tmp_path.read_bytes()
            tmp_path.unlink(missing_ok=True)

            filename = f"{meta.title}.{extension}" if extension else meta.title
            needs_conversion = True

            return Bundle(
                files=[FileItem(
                    name=filename,
                    content=content,
                    content_type=extension,
                    role="main",
                )],
                context={
                    **meta.extra,
                    "_needs_conversion": needs_conversion,
                },
            )

    # _resolve_folder_path, _collect_nodes, _download_to_temp, _clean_html_tags 保持不变
    def _resolve_folder_path(self, path: str) -> str | None:
        segments = [s.strip() for s in path.split("/") if s.strip()]
        if not segments:
            return None
        parent_id = None
        resolved = ""
        for segment in segments:
            folder_label = resolved or "(根)"
            nodes = self._client.list_nodes(self._space_id, parent_id,
                                            folder_name=folder_label, workspace_name=self._space_name)
            matched = None
            for node in nodes:
                if node.get("nodeType") == "folder" and node.get("name") == segment:
                    matched = node
                    break
            if not matched:
                logger.warning("未找到文件夹: '%s' (在 %s 下)", segment, resolved or "根目录")
                return None
            parent_id = matched.get("nodeId")
            resolved = f"{resolved}/{segment}" if resolved else segment
        return parent_id

    def _collect_nodes(self, space_id: str, folder_id: str | None, parent_path: str = "") -> list[dict]:
        folder_label = parent_path or "(根)"
        logger.debug("收集节点: %s/%s", self._space_name, folder_label)
        nodes = self._client.list_nodes(space_id, folder_id, folder_name=folder_label, workspace_name=self._space_name)
        result = []
        folder_count = 0
        doc_count = 0
        for node in nodes:
            title = node.get("name", "未命名")
            node_id = node.get("nodeId", "")
            node_type = node.get("nodeType", "")
            current_path = f"{parent_path}/{title}" if parent_path else title
            if node_type == "folder":
                folder_count += 1
                if node.get("hasChildren"):
                    result.extend(self._collect_nodes(space_id, node_id, current_path))
            else:
                doc_count += 1
                node["_path"] = current_path
                result.append(node)
        logger.debug("收集节点完成: 文件夹=%d, 文档=%d", folder_count, doc_count)
        return result

    def _download_to_temp(self, node_id: str, extension: str) -> Path:
        logger.debug("下载文件: node_id=%s, extension=%s", node_id, extension)
        download_url = self._client.download_file(node_id)
        resp = requests.get(download_url, timeout=120)
        resp.raise_for_status()
        logger.debug("文件下载成功: node_id=%s, 大小=%d bytes", node_id, len(resp.content))
        suffix = f".{extension}" if extension else ".bin"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(resp.content)
            return Path(tmp.name)

    @staticmethod
    def _clean_html_tags(markdown: str) -> str:
        markdown = re.sub(r'</?span[^>]*>', '', markdown)
        markdown = re.sub(r'</?font[^>]*>', '', markdown)
        markdown = re.sub(r'<div[^>]*>', '\n', markdown)
        markdown = re.sub(r'</div>', '', markdown)
        markdown = re.sub(r'<br\s*/?>', '\n', markdown)
        markdown = re.sub(r'</?u>', '', markdown)
        markdown = re.sub(r'<strong[^>]*>(.*?)</strong>', r'*\1*', markdown, flags=re.DOTALL)
        markdown = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', markdown, flags=re.DOTALL)
        markdown = re.sub(r'<p[^>]*>', '', markdown)
        markdown = re.sub(r'</p>', '\n', markdown)
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        return markdown.strip()
```

- [ ] **Step 2: 提交**

```bash
git add docpipe/sources/dingtalk.py
git commit -m "feat: DingtalkSource 迁移到 Bundle 模型"
```

---

### Task 4: 更新 Step 基类 + ConvertStep

**Files:**
- Modify: `docpipe/steps/base.py`
- Modify: `docpipe/steps/convert.py`

- [ ] **Step 1: 更新 PipelineStep 接口**

```python
# docpipe/steps/base.py
from __future__ import annotations

from abc import ABC, abstractmethod

from docpipe.models import Bundle


class PipelineStep(ABC):
    name: str = ""

    @abstractmethod
    def process(self, bundle: Bundle) -> Bundle:
        """处理文档包，返回处理后的文档包"""
```

- [ ] **Step 2: 更新 ConvertStep**

关键变化：
- 从 `bundle.main` 取主文件进行转换
- 提取的 base64 内联图片解码后作为 FileItem(role="image") 加入 Bundle，不再写临时文件
- 删除 `_temp_file`、`_images_dir` 相关逻辑

```python
# docpipe/steps/convert.py
from __future__ import annotations

import base64
import logging
import re
import tempfile
from pathlib import Path

from docpipe.models import Bundle, FileItem
from docpipe.steps import register_step
from docpipe.steps.base import PipelineStep

logger = logging.getLogger(__name__)


@register_step("convert")
class ConvertStep(PipelineStep):
    def __init__(self, extension_rules: dict[str, str] | None = None, **kwargs):
        self._extension_rules = extension_rules or {}

    def process(self, bundle: Bundle) -> Bundle:
        main = bundle.main
        if not main:
            return bundle

        ext = bundle.context.get("extension", "")
        key = f".{ext}" if ext else ""
        converter_name = self._extension_rules.get(key)

        if not converter_name or converter_name == "source":
            return bundle

        from docpipe.converters import get_converter
        converter_cls = get_converter(converter_name)
        converter = converter_cls()

        # 需要写临时文件给 converter
        suffix = f".{ext}" if ext else ""
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            if isinstance(main.content, bytes):
                tmp.write(main.content)
            else:
                tmp.write(main.content.encode("utf-8"))
            tmp_path = Path(tmp.name)

        try:
            markdown = converter.convert(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        # 提取内联图片，转为 FileItem
        markdown, images = self._extract_inline_images(markdown)
        for img in images:
            bundle.add(img)

        # 更新主文件
        main.content = markdown
        main.content_type = "text/markdown"
        main.name = _replace_extension(main.name, ".md")

        return bundle

    def _extract_inline_images(self, content: str) -> tuple[str, list[FileItem]]:
        """将 markdown 中的 data:image base64 内联图片提取为 FileItem，替换为引用路径"""
        if "data:image" not in content:
            return content, []

        pattern = r'!\[([^\]]*)\]\((data:image/([^;]+);base64,([^)]+))\)'
        images: list[FileItem] = []
        counter = 0

        def replace_inline(match: re.Match) -> str:
            nonlocal counter
            alt = match.group(1)
            mime_type = match.group(3)
            b64_data = match.group(4)

            ext = _mime_to_ext(mime_type)
            counter += 1
            filename = f"image_{counter}{ext}"

            try:
                image_bytes = base64.b64decode(b64_data)
            except Exception as e:
                logger.warning("提取内联图片失败: %s", e)
                return match.group(0)

            images.append(FileItem(
                name=filename,
                content=image_bytes,
                content_type=f"image/{mime_type}",
                role="image",
            ))

            return f"![{alt}](images/{filename})"

        new_content = re.sub(pattern, replace_inline, content)
        return new_content, images


def _mime_to_ext(mime: str) -> str:
    mapping = {"png": ".png", "jpeg": ".jpg", "jpg": ".jpg", "gif": ".gif", "webp": ".webp", "x-emf": ".emf"}
    return mapping.get(mime, f".{mime}")


def _replace_extension(name: str, new_ext: str) -> str:
    p = Path(name)
    return f"{p.stem}{new_ext}"
```

- [ ] **Step 3: 提交**

```bash
git add docpipe/steps/base.py docpipe/steps/convert.py
git commit -m "feat: PipelineStep 和 ConvertStep 迁移到 Bundle 模型"
```

---

### Task 5: 更新 ImageDescriptionStep + ImagePostProcessor

**Files:**
- Modify: `docpipe/steps/image_description.py`
- Modify: `docpipe/image.py`

- [ ] **Step 1: 更新 ImagePostProcessor，支持从 Bundle 的 FileItem 获取图片**

ImagePostProcessor.process 增加一个 `image_files: dict[str, FileItem]` 参数，当图片引用路径能匹配到 Bundle 中的 FileItem 时，直接使用其 content，不再从磁盘读取。

```python
# docpipe/image.py 中的 ImagePostProcessor.process 方法修改为：

    def process(self, markdown: str, source_context: str,
                images_dir: str | None = None,
                image_files: dict[str, FileItem] | None = None) -> tuple[str, dict]:
        """处理 markdown 中的图片引用

        Args:
            images_dir: 旧方式，从磁盘目录读取图片（向后兼容）
            image_files: Bundle 模式，从 FileItem 字典读取图片 {"images/image.png": FileItem}
        """
        image_metadata: dict[str, dict] = {}
        pattern = r'!\[([^\]]*)\]\(([^)]+)\)'

        def replace_image(match: re.Match) -> str:
            url = match.group(2).strip().strip('"').strip("'").strip()

            if url.startswith("image://"):
                return match.group(0)

            try:
                # 优先从 Bundle 的 FileItem 获取
                if image_files and url in image_files:
                    image_bytes = image_files[url].content if isinstance(image_files[url].content, bytes) else image_files[url].content.encode()
                elif url.startswith("data:"):
                    image_bytes = self._decode_data_uri(url)
                elif "://" in url:
                    resp = req.get(url, timeout=30)
                    resp.raise_for_status()
                    image_bytes = resp.content
                elif images_dir:
                    local_path = Path(images_dir) / url
                    if local_path.is_file():
                        image_bytes = local_path.read_bytes()
                    else:
                        return match.group(0)
                else:
                    return match.group(0)

                if not image_bytes or len(image_bytes) > self.max_image_size:
                    return match.group(0)

                image_bytes = validate_image(image_bytes)
                if image_bytes is None:
                    logger.debug("图片不满足处理条件，保留原引用: %s", url[:80])
                    return match.group(0)

                filename, description = self.vision_client.describe(image_bytes, source_context)

                full_filename = f"{filename}.png"
                image_metadata[full_filename] = {
                    "original_url": url[:200],
                    "description": description,
                }

                new_alt = filename.replace("-", " ")
                return f"**{new_alt}**：{description}\n\n![{new_alt}](image://{full_filename})"

            except Exception as e:
                logger.warning("图片处理失败 %s: %s", url[:80], e)
                return match.group(0)

        new_markdown = re.sub(pattern, replace_image, markdown)
        return new_markdown, image_metadata
```

需要在 `image.py` 文件顶部增加导入：

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docpipe.models import FileItem
```

- [ ] **Step 2: 更新 ImageDescriptionStep**

```python
# docpipe/steps/image_description.py
from __future__ import annotations

import logging

from docpipe.image import ImagePostProcessor, OpenAIVisionClient
from docpipe.models import Bundle, FileItem
from docpipe.steps import register_step
from docpipe.steps.base import PipelineStep

logger = logging.getLogger(__name__)


@register_step("image_description")
class ImageDescriptionStep(PipelineStep):
    def __init__(self, api_key: str = "", base_url: str = "", model: str = "gpt-4o", **kwargs):
        vision_client = OpenAIVisionClient(api_key=api_key, base_url=base_url, model=model)
        self._processor = ImagePostProcessor(vision_client)

    def process(self, bundle: Bundle) -> Bundle:
        main = bundle.main
        if not main or not isinstance(main.content, str):
            return bundle

        if "![" not in main.content:
            return bundle

        # 构建 image_files 映射：{"images/xxx.png": FileItem}
        image_files: dict[str, FileItem] = {}
        for f in bundle.get_by_role("image"):
            # ConvertStep 写的引用是 images/filename，FileItem.name 是 filename
            image_files[f"images/{f.name}"] = f
            image_files[f.name] = f

        source_context = bundle.context.get("title", "")
        path = bundle.context.get("path", "")
        if path:
            source_context = f"{source_context} - {path}"

        new_content, image_metadata = self._processor.process(
            main.content, source_context, image_files=image_files,
        )

        main.content = new_content
        bundle.context["image_metadata"] = image_metadata
        logger.info("图片处理完成: %s, 处理了 %d 张图片",
                     bundle.context.get("title", ""), len(image_metadata) if image_metadata else 0)

        return bundle
```

- [ ] **Step 3: 提交**

```bash
git add docpipe/steps/image_description.py docpipe/image.py
git commit -m "feat: ImageDescriptionStep 和 ImagePostProcessor 迁移到 Bundle 模型"
```

---

### Task 6: 更新 Destination 基类 + 实现类

**Files:**
- Modify: `docpipe/destinations/base.py`
- Modify: `docpipe/destinations/hindsight.py`
- Modify: `docpipe/destinations/localdrive.py`

- [ ] **Step 1: 更新 DestinationBase 接口**

```python
# docpipe/destinations/base.py
from __future__ import annotations

from abc import ABC, abstractmethod

from docpipe.models import Bundle


class DestinationBase(ABC):
    name: str = ""

    @abstractmethod
    def write(self, bundle: Bundle) -> str:
        """写入文档包，返回目标系统中的 ID"""

    def remove(self, bundle_id: str) -> None:
        """删除文档包（可选实现）"""
        raise NotImplementedError(f"{self.name} 不支持删除操作")
```

- [ ] **Step 2: 更新 HindsightDestination**

```python
# docpipe/destinations/hindsight.py
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from docpipe.destinations import register_destination
from docpipe.destinations.base import DestinationBase
from docpipe.models import Bundle


@register_destination("hindsight")
class HindsightDestination(DestinationBase):
    def __init__(
        self,
        bank_id: str | None = None,
        api_url: str | None = None,
        api_key: str | None = None,
        context_prefix: str | None = None,
        **kwargs,
    ):
        self.bank_id = bank_id or os.environ.get("HINDSIGHT_BANK_ID", "")
        self.api_url = api_url or os.environ.get("HINDSIGHT_API_URL", "")
        self.api_key = api_key or os.environ.get("HINDSIGHT_API_KEY", "")
        self.context_prefix = context_prefix or os.environ.get("HINDSIGHT_CONTEXT", "")
        self._client = None

    def _get_client(self):
        if self._client is None:
            from hindsight_client import Hindsight
            self._client = Hindsight(base_url=self.api_url, api_key=self.api_key or None)
            self._client.__enter__()
        return self._client

    def write(self, bundle: Bundle) -> str:
        item = self._build_retain_item(bundle)
        client = self._get_client()
        client.retain_batch(self.bank_id, items=[item], retain_async=True)
        return item["document_id"]

    def remove(self, bundle_id: str) -> None:
        raise NotImplementedError("Hindsight 不支持删除文档")

    def close(self) -> None:
        if self._client is not None:
            self._client.__exit__(None, None, None)
            self._client = None

    def _build_retain_item(self, bundle: Bundle) -> dict:
        main = bundle.main
        content = main.content if isinstance(main.content, str) else main.content.decode("utf-8")
        ctx = bundle.context

        # 从 path 构建标签
        path = ctx.get("path", "")
        path_parts = Path(path).parts if path else ()
        space_name = path_parts[0] if path_parts else ""
        path_tags = [f"path:{part}" for part in path_parts[1:]]
        tags = ([f"space:{space_name}"] if space_name else []) + path_tags

        # context
        title = ctx.get("title", "")
        if self.context_prefix:
            context = self.context_prefix
        else:
            folder_display = "/".join(path_parts[1:]) if len(path_parts) > 1 else ""
            if folder_display:
                context = f"文档：{title}，来自 {space_name}/{folder_display}"
            elif space_name:
                context = f"文档：{title}，来自 {space_name}"
            else:
                context = f"文档：{title}"

        # timestamp
        update_time = ctx.get("updateTime")
        if update_time:
            tz = timezone(timedelta(hours=8))
            dt = datetime.fromtimestamp(update_time / 1000, tz=tz)
            timestamp = dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        else:
            timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")

        # document_id
        source_name = ctx.get("_source", "local")
        bundle_id = ctx.get("id", "")
        document_id = f"{source_name}:{bundle_id}"

        return {
            "content": content,
            "document_id": document_id,
            "timestamp": timestamp,
            "context": context,
            "tags": tags,
            "metadata": {
                "id": bundle_id,
                "title": title,
                "contentType": ctx.get("contentType", ""),
                "extension": ctx.get("extension", ""),
                "space_name": ctx.get("space_name", ""),
                "relative_path": path,
                "full_path": f"{ctx.get('space_name', '')}/{path}" if ctx.get("space_name") else path,
                "content_hash": ctx.get("hash", ""),
                "updateTime": str(update_time) if update_time else "",
            },
        }
```

- [ ] **Step 3: 更新 LocalDriveDestination —— 输出附件**

关键变化：write 方法除了写主文件，还写 role != "main" 的附件到同目录。

```python
# docpipe/destinations/localdrive.py
from __future__ import annotations

import json
from pathlib import Path

from docpipe.destinations import register_destination
from docpipe.destinations.base import DestinationBase
from docpipe.models import Bundle


@register_destination("localdrive")
class LocalDriveDestination(DestinationBase):
    def __init__(self, output_dir: str, **kwargs):
        self._output_dir = Path(output_dir)

    def write(self, bundle: Bundle) -> str:
        main = bundle.main
        file_path = self._resolve_path(bundle)

        file_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(main.content, bytes):
            file_path.write_bytes(main.content)
        else:
            file_path.write_text(main.content, encoding="utf-8")

        # 写附件（图片等）
        for f in bundle.files:
            if f.role == "main":
                continue
            # 引用路径可能含子目录（如 "images/image_1.png"）
            att_path = file_path.parent / f.name
            att_path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(f.content, bytes):
                att_path.write_bytes(f.content)
            else:
                att_path.write_text(f.content, encoding="utf-8")

        self._write_sidecar(file_path, bundle)
        return str(file_path)

    def remove(self, bundle_id: str) -> None:
        raise NotImplementedError("localdrive remove 需要路径信息")

    def remove_by_path(self, file_path: str) -> None:
        p = Path(file_path)
        if p.exists():
            p.unlink()
        sidecar = Path(file_path + ".json")
        if sidecar.exists():
            sidecar.unlink()

    def _resolve_path(self, bundle: Bundle) -> Path:
        ctx = bundle.context
        main = bundle.main
        space_name = ctx.get("space_name", "")
        path = ctx.get("path", "")

        ext = self._content_type_to_ext(main.content_type) if main else ""
        if ext and not path.endswith(ext):
            path = path + ext

        if space_name:
            return self._output_dir / space_name / path
        return self._output_dir / path

    def _write_sidecar(self, file_path: Path, bundle: Bundle) -> None:
        ctx = bundle.context
        space_name = ctx.get("space_name", "")
        path = ctx.get("path", "")
        data = {
            "id": ctx.get("id", ""),
            "title": ctx.get("title", ""),
            "contentType": ctx.get("contentType", ""),
            "extension": ctx.get("extension", ""),
            "space_name": space_name,
            "relative_path": path,
            "full_path": f"{space_name}/{path}" if space_name else path,
            "content_hash": ctx.get("hash", ""),
        }
        sidecar = Path(str(file_path) + ".json")
        sidecar.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _content_type_to_ext(content_type: str) -> str:
        mapping = {"markdown": ".md", "text/markdown": ".md", "text": ".txt", "html": ".html"}
        mapped = mapping.get(content_type)
        if mapped:
            return mapped
        if content_type:
            return f".{content_type}"
        return ""
```

- [ ] **Step 4: 提交**

```bash
git add docpipe/destinations/base.py docpipe/destinations/hindsight.py docpipe/destinations/localdrive.py
git commit -m "feat: Destination 基类和实现类迁移到 Bundle 模型，支持附件输出"
```

---

### Task 7: 更新 Pipeline 核心 + CLI

**Files:**
- Modify: `docpipe/pipeline.py`
- Modify: `docpipe/cli.py`

- [ ] **Step 1: 重写 Pipeline.run**

删除所有旧逻辑（`_process_with_legacy_rules`、`_run_converter`、legacy `type_resolver` / `content_type_strategy` 参数），统一为 Bundle 流程。

```python
# docpipe/pipeline.py
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from docpipe.destinations.base import DestinationBase
from docpipe.display import Display
from docpipe.models import Bundle, BundleMeta, SkipBundle
from docpipe.sources.base import SourceBase

logger = logging.getLogger(__name__)


class StateManager:
    def __init__(self, path: Path):
        self._path = path

    def load(self) -> dict[str, dict]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        result = {}
        for k, v in raw.items():
            if isinstance(v, str):
                result[k] = {"hash": v, "path": ""}
            else:
                result[k] = v
        return result

    def save(self, entries: dict[str, dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def is_processed(self, bundle_id: str) -> bool:
        return bundle_id in self.load()

    def is_unchanged(self, bundle_id: str, content_hash: str) -> bool:
        entry = self.load().get(bundle_id, {})
        return entry.get("hash") == content_hash

    def mark_done(self, bundle_id: str, content_hash: str, path: str = "") -> None:
        entries = self.load()
        entries[bundle_id] = {"hash": content_hash, "path": path}
        self.save(entries)

    def get_path(self, bundle_id: str) -> str:
        return self.load().get(bundle_id, {}).get("path", "")

    def find_removed(self, current_ids: list[str]) -> list[str]:
        stored = self.load()
        current_set = set(current_ids)
        return [bid for bid in stored if bid not in current_set]

    def mark_removed(self, bundle_id: str) -> None:
        entries = self.load()
        entries.pop(bundle_id, None)
        self.save(entries)


def content_hash(content: str | bytes) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def bundle_hash(bundle: Bundle) -> str:
    """基于主文件内容计算 Bundle 的 hash"""
    main = bundle.main
    if main:
        return content_hash(main.content)
    return content_hash("")


class Pipeline:
    def __init__(
        self,
        source: SourceBase,
        dest: DestinationBase,
        state_dir: Path,
        display: Display | None = None,
        steps: list | None = None,
    ):
        self.source = source
        self.dest = dest
        self.state = StateManager(state_dir / f"{source.name}_{dest.name}_state.json")
        self._display = display or Display()
        self._steps = steps or []

    def run(self, *, resume: bool = False, sync: bool = False, dry_run: bool = False) -> None:
        logger.info("Pipeline 开始: %s → %s (resume=%s, sync=%s, dry_run=%s)",
                     self.source.name, self.dest.name, resume, sync, dry_run)
        metas = self.source.list()

        if resume:
            metas = [m for m in metas if not self.state.is_processed(m.id)]

        logger.info("待处理文档: %d 个", len(metas))
        self._display.start(f"Pipeline: {self.source.name} → {self.dest.name}", len(metas))

        for meta in metas:
            if sync and self.state.is_unchanged(meta.id, meta.hash):
                self._display.result("skip", f"{meta.path} (无变化)")
                continue

            display_path = meta.path
            self._display.set_current(display_path)
            try:
                bundle = self.source.fetch(meta)

                # 设置 context 中的公共字段
                bundle.context.setdefault("id", meta.id)
                bundle.context.setdefault("title", meta.title)
                bundle.context.setdefault("path", meta.path)
                bundle.context["_source"] = self.source.name

                for step in self._steps:
                    bundle = step.process(bundle)

                # 计算 hash
                final_hash = bundle_hash(bundle)
                bundle.context["hash"] = final_hash

                if dry_run:
                    self._display.result("info", f"[dry-run] {display_path}")
                else:
                    self.dest.write(bundle)
                    self._display.result("success", display_path)
                    self.state.mark_done(meta.id, final_hash, meta.path)
            except SkipBundle as e:
                logger.info("跳过文档: %s - %s", display_path, e)
                self._display.result("skip", f"{display_path} ({e})")
            except Exception as e:
                logger.error("文档处理失败: %s - %s", display_path, e)
                self._display.result("error", f"{display_path}: {e}")
                self._display.add_failure()
            finally:
                self._display.clear_current(display_path)

        if sync:
            removed = self.state.find_removed([m.id for m in metas])
            for bundle_id in removed:
                doc_path = self.state.get_path(bundle_id) or bundle_id
                try:
                    if not dry_run:
                        self.dest.remove(bundle_id)
                        self.state.mark_removed(bundle_id)
                    self._display.result("info", f"从 {self.dest.name} 移除: {doc_path}")
                except NotImplementedError:
                    pass
                except Exception as e:
                    self._display.result("error", f"移除失败 {doc_path}: {e}")

        self._display.stop()
        self._display.print_summary()
        logger.info("Pipeline 完成: %s → %s", self.source.name, self.dest.name)
```

- [ ] **Step 2: 更新 CLI**

删除旧逻辑（`type_resolver`、`content_type_strategy`），Pipeline 构造去掉旧参数。

```python
# docpipe/cli.py
from __future__ import annotations

import logging
import os
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()


def _setup_logging(level: str):
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.option("--state-dir", default="./.state", help="状态文件目录")
@click.option("--log-level", default="INFO", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
              help="日志级别")
@click.pass_context
def main(ctx, state_dir, log_level):
    """通用文档传输 pipeline"""
    _setup_logging(log_level)
    ctx.ensure_object(dict)
    ctx.obj["state_dir"] = Path(state_dir)


@main.command()
@click.option("--config", "config_path", default="docpipe.yaml", help="配置文件路径")
@click.option("--pipeline", "pipeline_name", default=None, help="配置文件中的 pipeline 名称")
@click.option("--resume", is_flag=True, default=False, help="跳过已处理的文档")
@click.option("--sync", "sync_mode", is_flag=True, default=False, help="仅同步有变化的文档")
@click.option("--dry-run", is_flag=True, default=False, help="只打印不执行")
@click.pass_context
def run(ctx, config_path, pipeline_name, resume, sync_mode, dry_run):
    """运行文档传输 pipeline"""
    _run_from_config(ctx, config_path, pipeline_name, resume, sync_mode, dry_run)


def _run_from_config(ctx, config_path, pipeline_name, resume, sync_mode, dry_run):
    import yaml

    from docpipe.config import deep_merge, parse_component_config, resolve_env_vars
    from docpipe.destinations import get_destination
    from docpipe.display import Display
    from docpipe.pipeline import Pipeline
    from docpipe.sources import get_source
    from docpipe.steps import get_step

    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    config = resolve_env_vars(raw)

    global_config = {k: v for k, v in config.items() if k != "pipelines"}
    converters_config = global_config.pop("converters", global_config.pop("type_rules", {}))
    extension_rules = converters_config.get("extensions", {})

    pipelines = config.get("pipelines", [])

    if pipeline_name:
        pipelines = [p for p in pipelines if p.get("name") == pipeline_name]
        if not pipelines:
            click.echo(f"未找到 pipeline: {pipeline_name}")
            raise SystemExit(1)

    for pipe_config in pipelines:
        source_name, source_kwargs = parse_component_config(pipe_config, global_config, "source")
        source = get_source(source_name)(**source_kwargs)

        dest_name, dest_kwargs = parse_component_config(pipe_config, global_config, "destination")
        dest = get_destination(dest_name)(**dest_kwargs)

        steps = []
        for step_spec in pipe_config.get("steps", []):
            if isinstance(step_spec, str):
                step_name = step_spec
                step_kwargs = {}
            else:
                items = list(step_spec.items())
                step_name, step_kwargs = items[0] if items else ("", {})

            global_step_config = global_config.get(step_name, {})
            if global_step_config:
                step_kwargs = deep_merge(global_step_config, step_kwargs)

            if step_name == "convert":
                step_kwargs["extension_rules"] = extension_rules

            step_cls = get_step(step_name)
            steps.append(step_cls(**step_kwargs))

        options = pipe_config.get("options", {})
        try:
            pipeline = Pipeline(source, dest, ctx.obj["state_dir"],
                                display=Display(), steps=steps)
            pipeline.run(
                resume=resume or options.get("resume", False),
                sync=sync_mode or options.get("sync", False),
                dry_run=dry_run,
            )
        finally:
            if hasattr(dest, "close"):
                dest.close()


@main.command("sources")
def list_sources():
    """列出可用的 Source"""
    from docpipe.sources import SOURCES
    for name, cls in SOURCES.items():
        click.echo(f"  {name}")


@main.command("destinations")
def list_destinations():
    """列出可用的 Destination"""
    from docpipe.destinations import DESTINATIONS
    for name, cls in DESTINATIONS.items():
        click.echo(f"  {name}")
```

- [ ] **Step 3: 提交**

```bash
git add docpipe/pipeline.py docpipe/cli.py
git commit -m "feat: Pipeline 和 CLI 迁移到 Bundle 模型，删除旧逻辑"
```

---

### Task 8: 迁移全部测试

**Files:**
- Rewrite: `tests/test_docpipe.py`
- Rewrite: `tests/test_image.py`

这是最大的迁移工作。所有使用 Document / DocumentMeta 的测试都要改为 Bundle / BundleMeta / FileItem。

- [ ] **Step 1: 重写 test_docpipe.py 的测试辅助类和工厂函数**

```python
# tests/test_docpipe.py
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest

from docpipe.models import Bundle, BundleMeta, FileItem, SkipBundle
from docpipe.pipeline import Pipeline, StateManager, content_hash, bundle_hash
from docpipe.sources.base import SourceBase
from docpipe.destinations.base import DestinationBase
from docpipe.steps.base import PipelineStep


class FakeSource(SourceBase):
    name = "fake"

    def __init__(self, bundles: list[Bundle] | None = None, **kwargs):
        self._metas: list[BundleMeta] = []
        self._bundles: dict[str, Bundle] = {}
        if bundles:
            for b in bundles:
                meta = BundleMeta(
                    id=b.context.get("id", ""),
                    title=b.context.get("title", ""),
                    path=b.context.get("path", ""),
                    hash=b.context.get("hash", ""),
                )
                self._metas.append(meta)
                self._bundles[meta.id] = b

    def list(self) -> list[BundleMeta]:
        return self._metas

    def fetch(self, meta: BundleMeta) -> Bundle:
        if meta.id in self._bundles:
            return self._bundles[meta.id]
        raise ValueError(f"Bundle not found: {meta.id}")


class FakeDestination(DestinationBase):
    name = "fake"

    def __init__(self, **kwargs):
        self.written: list[Bundle] = []
        self.removed: list[str] = []

    def write(self, bundle: Bundle) -> str:
        self.written.append(bundle)
        return bundle.context.get("id", "")

    def remove(self, bundle_id: str) -> None:
        self.removed.append(bundle_id)


def _make_bundle(id: str, title: str, content: str = "hello", path: str = "", **extra) -> Bundle:
    return Bundle(
        files=[FileItem(name=f"{title}.md", content=content, content_type="text/markdown", role="main")],
        context={"id": id, "title": title, "path": path or f"{title}.md", **extra},
    )
```

- [ ] **Step 2: 迁移 StateManager 和 content_hash 测试**

```python
class TestStateManager:
    def test_save_and_load(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.save({"a": {"hash": "hash1", "path": ""}, "b": {"hash": "hash2", "path": "x/y"}})
        assert sm.load() == {"a": {"hash": "hash1", "path": ""}, "b": {"hash": "hash2", "path": "x/y"}}

    def test_load_old_format(self, tmp_path):
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


class TestBundleHash:
    def test_hash_from_main_content(self):
        b = _make_bundle("1", "A", content="hello")
        h = bundle_hash(b)
        assert h == content_hash("hello")

    def test_hash_empty_bundle(self):
        b = Bundle()
        assert bundle_hash(b) == content_hash("")
```

- [ ] **Step 3: 迁移 Pipeline 核心测试**

```python
class TestPipeline:
    def test_run_writes_all(self, tmp_path):
        bundles = [_make_bundle("1", "A"), _make_bundle("2", "B")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path)
        pipeline.run()
        assert len(dest.written) == 2
        assert dest.written[0].context["title"] == "A"
        assert dest.written[1].context["title"] == "B"

    def test_run_resume_skips_processed(self, tmp_path):
        bundle = _make_bundle("1", "A")
        source = FakeSource([bundle])
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path)
        pipeline.run()
        assert len(dest.written) == 1

        dest2 = FakeDestination()
        pipeline2 = Pipeline(source, dest2, tmp_path)
        pipeline2.run(resume=True)
        assert len(dest2.written) == 0

    def test_run_sync_skips_unchanged(self, tmp_path):
        bundle = _make_bundle("1", "A", content="hello")
        bundle.context["hash"] = content_hash("hello")
        source = FakeSource([bundle])
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path)
        pipeline.run()
        assert len(dest.written) == 1

        dest2 = FakeDestination()
        pipeline2 = Pipeline(source, dest2, tmp_path)
        pipeline2.run(sync=True)
        assert len(dest2.written) == 0

    def test_run_sync_removes_missing(self, tmp_path):
        bundles1 = [_make_bundle("1", "A"), _make_bundle("2", "B")]
        source1 = FakeSource(bundles1)
        dest = FakeDestination()
        pipeline1 = Pipeline(source1, dest, tmp_path)
        pipeline1.run()

        bundles2 = [_make_bundle("1", "A")]
        source2 = FakeSource(bundles2)
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source2, dest2, tmp_path)
        pipeline2.run(sync=True)
        assert dest2.removed == ["2"]

    def test_run_dry_run(self, tmp_path):
        bundle = _make_bundle("1", "A")
        source = FakeSource([bundle])
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path)
        pipeline.run(dry_run=True)
        assert len(dest.written) == 0
        assert pipeline.state.load() == {}

    def test_dry_run_sync_no_state_mutation(self, tmp_path):
        bundle = _make_bundle("1", "A")
        source = FakeSource([bundle])
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path)
        pipeline.run(sync=True, dry_run=True)
        assert len(dest.written) == 0
        assert len(dest.removed) == 0
        assert pipeline.state.load() == {}
        pipeline.run(sync=True, dry_run=True)
        assert len(dest.written) == 0
        assert len(dest.removed) == 0
        assert pipeline.state.load() == {}

    def test_dry_run_resume_idempotent(self, tmp_path):
        bundles = [_make_bundle("1", "A"), _make_bundle("2", "B")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path)
        pipeline.run(resume=True, dry_run=True)
        assert len(dest.written) == 0
        assert pipeline.state.load() == {}
        pipeline.run(resume=True, dry_run=True)
        assert len(dest.written) == 0
        assert pipeline.state.load() == {}

    def test_run_with_steps(self, tmp_path):
        bundles = [_make_bundle("1", "A", content="hello")]
        source = FakeSource(bundles)
        dest = FakeDestination()

        class UpperStep(PipelineStep):
            name = "upper"
            def process(self, bundle):
                bundle.main.content = bundle.main.content.upper()
                return bundle

        pipeline = Pipeline(source, dest, tmp_path, steps=[UpperStep()])
        pipeline.run()
        assert len(dest.written) == 1
        assert dest.written[0].main.content == "HELLO"

    def test_run_with_empty_steps_processes_all(self, tmp_path):
        bundles = [_make_bundle("1", "A")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, steps=[])
        pipeline.run()
        assert len(dest.written) == 1
```

- [ ] **Step 4: 迁移注册测试和 LocalDrive 测试**

```python
class TestRegistration:
    def test_sources_registered(self):
        from docpipe.sources import SOURCES
        assert "dingtalk" in SOURCES
        assert "localdrive" in SOURCES

    def test_destinations_registered(self):
        from docpipe.destinations import DESTINATIONS
        assert "hindsight" in DESTINATIONS
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
        bundle = _make_bundle(
            id="node1", title="方案", content="# 方案内容",
            path="产品规划/方案",
            space_name="知识库A", contentType="ALIDOC", extension="adoc",
        )
        bundle.context["hash"] = "abc123"

        result = dest.write(bundle)
        expected_file = output_dir / "知识库A" / "产品规划" / "方案.md"
        assert expected_file.exists()
        assert expected_file.read_text(encoding="utf-8") == "# 方案内容"

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

    def test_write_with_attachments(self, tmp_path):
        """附件文件写入主文件同目录"""
        from docpipe.destinations.localdrive import LocalDriveDestination

        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))
        bundle = Bundle(
            files=[
                FileItem(name="doc.md", content="# hello", content_type="text/markdown", role="main"),
                FileItem(name="image_1.png", content=b"\x89PNG fake", content_type="image/png", role="image"),
            ],
            context={"id": "1", "title": "doc", "path": "doc", "hash": "h1"},
        )

        dest.write(bundle)

        main_file = output_dir / "doc.md"
        assert main_file.exists()
        assert main_file.read_text(encoding="utf-8") == "# hello"

        img_file = output_dir / "image_1.png"
        assert img_file.exists()
        assert img_file.read_bytes() == b"\x89PNG fake"

    def test_write_skips_unchanged(self, tmp_path):
        from docpipe.destinations.localdrive import LocalDriveDestination

        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))
        bundle = _make_bundle(id="1", title="A", content="hello", path="A", space_name="S")
        bundle.context["hash"] = "h1"

        dest.write(bundle)
        file_path = output_dir / "S" / "A.md"
        mtime1 = file_path.stat().st_mtime
        time.sleep(0.05)

        dest2 = LocalDriveDestination(output_dir=str(output_dir))
        dest2.write(bundle)
        mtime2 = file_path.stat().st_mtime
        assert mtime1 == mtime2

    def test_write_overwrites_changed(self, tmp_path):
        from docpipe.destinations.localdrive import LocalDriveDestination

        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))
        b1 = _make_bundle(id="1", title="A", content="old content", path="A", space_name="S")
        b1.context["hash"] = "h1"
        dest.write(b1)

        b2 = _make_bundle(id="1", title="A", content="new content", path="A", space_name="S")
        b2.context["hash"] = "h2"
        dest.write(b2)

        file_path = output_dir / "S" / "A.md"
        assert file_path.read_text(encoding="utf-8") == "new content"

    def test_remove_deletes_file_and_sidecar(self, tmp_path):
        from docpipe.destinations.localdrive import LocalDriveDestination

        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))
        bundle = _make_bundle(id="1", title="A", content="hello", path="A", space_name="S")
        bundle.context["hash"] = "h1"

        file_path = dest.write(bundle)
        assert Path(file_path).exists()
        dest.remove_by_path(file_path)
        assert not Path(file_path).exists()
        assert not Path(file_path + ".json").exists()

    def test_remove_nonexistent_file_no_error(self, tmp_path):
        from docpipe.destinations.localdrive import LocalDriveDestination
        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))
        dest.remove_by_path(str(output_dir / "nonexistent.md"))


class TestLocalDriveSource:
    def test_list_all_file_types(self, tmp_path):
        (tmp_path / "a.md").write_text("hello a")
        (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4 fake")
        (tmp_path / "c.docx").write_bytes(b"PK fake docx")
        (tmp_path / "d.txt").write_text("plain text")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        titles = {m.title for m in metas}
        assert titles == {"a", "b", "c", "d"}

    def test_list_skips_hidden_dirs_and_files(self, tmp_path):
        (tmp_path / "visible.md").write_text("seen")
        hidden_dir = tmp_path / ".hidden_dir"
        hidden_dir.mkdir()
        (hidden_dir / "secret.md").write_text("hidden dir file")
        (tmp_path / ".hidden.md").write_text("hidden file")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        assert len(metas) == 1
        assert metas[0].title == "visible"

    def test_list_skips_no_extension(self, tmp_path):
        (tmp_path / "README").write_text("no extension")
        (tmp_path / "guide.md").write_text("has extension")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        assert len(metas) == 1
        assert metas[0].title == "guide"

    def test_list_recursive(self, tmp_path):
        sub = tmp_path / "sub" / "dir"
        sub.mkdir(parents=True)
        (tmp_path / "root.md").write_text("root")
        (sub / "deep.md").write_text("deep")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        paths = {m.path for m in metas}
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
        metas = source.list()
        bundle = source.fetch(metas[0])
        main = bundle.main
        assert isinstance(main.content, str)
        assert main.content == "hello world"
        assert main.content_type == "markdown"

    def test_fetch_binary_file(self, tmp_path):
        (tmp_path / "test.pdf").write_bytes(b"%PDF-1.4 fake content")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        bundle = source.fetch(metas[0])
        main = bundle.main
        assert isinstance(main.content, bytes)

    def test_fetch_metadata(self, tmp_path):
        (tmp_path / "report.pdf").write_bytes(b"%PDF fake")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        assert metas[0].title == "report"
        assert metas[0].extra["extension"] == "pdf"
        assert metas[0].extra["size"] > 0
        assert "report.pdf" in metas[0].path

    def test_include_filter(self, tmp_path):
        (tmp_path / "a.md").write_text("md")
        (tmp_path / "b.pdf").write_bytes(b"pdf")
        (tmp_path / "c.docx").write_bytes(b"docx")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path), include=["*.md", "*.pdf"])
        metas = source.list()
        titles = {m.title for m in metas}
        assert titles == {"a", "b"}

    def test_exclude_filter(self, tmp_path):
        (tmp_path / "a.md").write_text("md")
        (tmp_path / "b.pdf").write_bytes(b"pdf")
        (tmp_path / "c.docx").write_bytes(b"docx")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path), exclude=["*.pdf"])
        metas = source.list()
        titles = {m.title for m in metas}
        assert titles == {"a", "c"}

    def test_exclude_overrides_include(self, tmp_path):
        (tmp_path / "a.md").write_text("md")
        (tmp_path / "b.pdf").write_bytes(b"pdf")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path), include=["*.md", "*.pdf"], exclude=["*.pdf"])
        metas = source.list()
        titles = {m.title for m in metas}
        assert titles == {"a"}

    def test_no_filters_includes_all(self, tmp_path):
        (tmp_path / "a.md").write_text("md")
        (tmp_path / "b.pdf").write_bytes(b"pdf")
        (tmp_path / "c.py").write_text("print('hi')")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        assert len(metas) == 3


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
    def test_process_no_rule_returns_unchanged(self):
        from docpipe.steps.convert import ConvertStep
        bundle = Bundle(
            files=[FileItem(name="t.md", content="hello", role="main")],
            context={"extension": "md"},
        )
        step = ConvertStep(extension_rules={".pdf": "markitdown"})
        result = step.process(bundle)
        assert result.main.content == "hello"


class TestImageDescriptionStep:
    def test_non_text_content_skipped(self):
        from docpipe.steps.image_description import ImageDescriptionStep
        step = ImageDescriptionStep(api_key="k", base_url="http://x", model="m")
        bundle = Bundle(
            files=[FileItem(name="t.pdf", content=b"binary data", role="main")],
            context={},
        )
        result = step.process(bundle)
        assert result.main.content == b"binary data"

    def test_no_images_unchanged(self):
        from docpipe.steps.image_description import ImageDescriptionStep
        step = ImageDescriptionStep(api_key="k", base_url="http://x", model="m")
        bundle = Bundle(
            files=[FileItem(name="t.md", content="# Hello\n\nNo images here.", role="main")],
            context={},
        )
        result = step.process(bundle)
        assert result.main.content == "# Hello\n\nNo images here."
```

- [ ] **Step 5: 迁移 test_image.py**

```python
# tests/test_image.py
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from docpipe.image import OpenAIVisionClient
from docpipe.models import FileItem


class TestOpenAIVisionClient:
    def test_describe_returns_filename_and_description(self, monkeypatch):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "filename": "system-architecture-diagram",
            "description": "展示微服务三层架构，包含网关层、服务层和数据层",
        })
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        monkeypatch.setattr("docpipe.image.OpenAI", lambda **kwargs: mock_client)

        client = OpenAIVisionClient(api_key="test-key", base_url="https://api.example.com/v1", model="gpt-4o")
        filename, description = client.describe(b"fake-image-bytes", "测试文档")
        assert filename == "system-architecture-diagram"
        assert description == "展示微服务三层架构，包含网关层、服务层和数据层"

    def test_describe_invalid_json_response_falls_back(self, monkeypatch):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not valid json"
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        monkeypatch.setattr("docpipe.image.OpenAI", lambda **kwargs: mock_client)

        client = OpenAIVisionClient(api_key="test-key", base_url="https://api.example.com/v1", model="gpt-4o")
        filename, description = client.describe(b"fake-image-bytes", "测试文档")
        assert filename
        assert description


from docpipe.image import ImagePostProcessor


class _FakeVisionClient:
    def __init__(self, results: dict[str, tuple[str, str]] | None = None):
        self.results = results or {}
        self.calls: list[tuple[bytes, str]] = []

    def describe(self, image_bytes: bytes, context: str) -> tuple[str, str]:
        self.calls.append((image_bytes, context))
        if self.results:
            for _, val in self.results.items():
                return val
        return "test-image", "测试图片描述"


def _mock_get(url, **kwargs):
    mock_resp = MagicMock()
    mock_resp.content = b"fake-image-data"
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


class TestImagePostProcessor:
    def test_process_replaces_image_refs(self, monkeypatch):
        monkeypatch.setattr("docpipe.image.req.get", _mock_get)
        monkeypatch.setattr("docpipe.image.validate_image", lambda b: b)
        vision = _FakeVisionClient(results={"default": ("architecture-diagram", "展示微服务三层架构")})
        processor = ImagePostProcessor(vision_client=vision)
        markdown = '![imag.png](https://example.com/test.png)'
        result, metadata = processor.process(markdown, "测试文档")
        assert "**architecture diagram**：展示微服务三层架构" in result
        assert "image://architecture-diagram.png" in result
        assert "architecture-diagram.png" in metadata

    def test_process_keeps_original_on_failure(self):
        vision = _FakeVisionClient()
        vision.describe = lambda img, ctx: (_ for _ in ()).throw(RuntimeError("API error"))
        processor = ImagePostProcessor(vision_client=vision)
        markdown = '![img.png](https://example.com/broken.png)'
        result, metadata = processor.process(markdown, "测试文档")
        assert "https://example.com/broken.png" in result
        assert metadata == {}

    def test_process_skips_already_processed(self):
        vision = _FakeVisionClient()
        processor = ImagePostProcessor(vision_client=vision)
        markdown = '![test](image://already-done.png)'
        result, metadata = processor.process(markdown, "测试文档")
        assert result == '![test](image://already-done.png)'
        assert metadata == {}
        assert len(vision.calls) == 0

    def test_process_multiple_images(self, monkeypatch):
        monkeypatch.setattr("docpipe.image.req.get", _mock_get)
        monkeypatch.setattr("docpipe.image.validate_image", lambda b: b)
        call_count = [0]

        def mock_describe(img, ctx):
            call_count[0] += 1
            return f"image-{call_count[0]}", f"描述{call_count[0]}"

        vision = _FakeVisionClient()
        vision.describe = mock_describe
        processor = ImagePostProcessor(vision_client=vision)
        markdown = '![a](https://example.com/a.png)\n一些文字\n![b](https://example.com/b.png)'
        result, metadata = processor.process(markdown, "测试文档")
        assert len(metadata) == 2

    def test_process_no_images(self):
        vision = _FakeVisionClient()
        processor = ImagePostProcessor(vision_client=vision)
        markdown = "这是一段没有图片的文字"
        result, metadata = processor.process(markdown, "测试文档")
        assert result == markdown
        assert metadata == {}
        assert len(vision.calls) == 0

    def test_process_with_image_files_from_bundle(self, monkeypatch):
        """从 Bundle 的 FileItem 获取图片"""
        monkeypatch.setattr("docpipe.image.validate_image", lambda b: b)
        vision = _FakeVisionClient(results={"default": ("diagram", "架构图")})
        processor = ImagePostProcessor(vision_client=vision)

        image_files = {
            "images/diagram.png": FileItem(name="diagram.png", content=b"fake-png-data", role="image"),
            "diagram.png": FileItem(name="diagram.png", content=b"fake-png-data", role="image"),
        }
        markdown = "![diagram](images/diagram.png)"
        result, metadata = processor.process(markdown, "测试文档", image_files=image_files)
        assert "image://diagram.png" in result
        assert len(vision.calls) == 1
        assert vision.calls[0][0] == b"fake-png-data"
```

- [ ] **Step 6: 删除旧兼容别名，运行全量测试**

在 `docpipe/models.py` 中删除 `DocumentMeta`、`Document`、`SkipDocument` 类定义。

```python
# docpipe/models.py 最终版
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath


class SkipBundle(Exception):
    """Source 发出此异常表示该文档包应跳过"""


@dataclass
class FileItem:
    name: str
    content: str | bytes
    content_type: str = ""
    role: str = "main"
    metadata: dict = field(default_factory=dict)


@dataclass
class Bundle:
    files: list[FileItem] = field(default_factory=list)
    context: dict = field(default_factory=dict)

    @property
    def main(self) -> FileItem | None:
        return next((f for f in self.files if f.role == "main"), None)

    def get_by_role(self, role: str) -> list[FileItem]:
        return [f for f in self.files if f.role == role]

    def add(self, file: FileItem) -> None:
        if any(f.name == file.name for f in self.files):
            stem = PurePosixPath(file.name).stem
            suffix = PurePosixPath(file.name).suffix
            seq = 1
            while any(f.name == f"{stem}_{seq}{suffix}" for f in self.files):
                seq += 1
            file.name = f"{stem}_{seq}{suffix}"
        self.files.append(file)

    def remove(self, name: str) -> None:
        self.files = [f for f in self.files if f.name != name]


@dataclass
class BundleMeta:
    id: str
    title: str
    path: str = ""
    hash: str = ""
    extra: dict = field(default_factory=dict)
```

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add docpipe/models.py tests/test_docpipe.py tests/test_image.py
git commit -m "feat: 全部测试迁移到 Bundle 模型，删除旧数据模型"
```

---

### Task 9: 清理和最终验证

**Files:**
- Verify: `docpipe/pipeline.py` — 删除不再使用的 ContentTypeStrategy 类
- Verify: `docpipe/models.py` — 确认旧类已清理
- Verify: 所有 `from docpipe.models import Document, DocumentMeta` 引用已消除

- [ ] **Step 1: 确认无残留的旧导入**

Run: `grep -rn "DocumentMeta\|from docpipe.models import Document\b" docpipe/`
Expected: 无输出（所有旧引用已清除）

- [ ] **Step 2: 删除 pipeline.py 中的 ContentTypeStrategy 类**

确认 ContentTypeStrategy 已从 pipeline.py 中移除（在 Task 7 中已删除）。

- [ ] **Step 3: 运行全量测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
git add -A
git commit -m "refactor: 清理旧模型残留引用"
```

---

## 自检结果

**Spec 覆盖：**
- FileItem / Bundle / BundleMeta 数据模型 → Task 1
- SourceBase.list() / fetch() 新接口 → Task 2, 3
- PipelineStep.process(Bundle) → Task 4
- DestinationBase.write(Bundle) → Task 6
- ConvertStep 图片不再写临时文件 → Task 4
- ImageDescriptionStep 从 Bundle 获取图片 → Task 5
- Bundle.add() 文件名冲突避免 → Task 1
- Destination 输出附件 → Task 6 (LocalDriveDestination)
- Pipeline.run 流程简化 → Task 7
- 删除旧 Document/DocumentMeta → Task 8

**Placeholder 扫描：** 无 TBD / TODO / "implement later"。

**类型一致性：** 所有 Task 中 Bundle / FileItem / BundleMeta / SourceBase / PipelineStep / DestinationBase 的方法签名一致。
