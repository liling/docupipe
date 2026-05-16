# Resolve Attachments Step 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `resolve_attachments` 步骤，解析 markdown 中的本地文件引用，从磁盘读取文件加入 bundle。

**Architecture:** 单一步骤类，正则扫描 markdown 引用，过滤外部链接，按基准目录读取本地文件加入 bundle。

**Tech Stack:** Python 3.11+ / re / pathlib / pytest

---

### Task 1: 实现 ResolveAttachmentsStep + 测试

**Files:**
- Create: `docpipe/steps/resolve_attachments.py`
- Create: `tests/test_resolve_attachments.py`
- Modify: `docpipe/steps/__init__.py`

- [ ] **Step 1: 编写测试**

创建 `tests/test_resolve_attachments.py`：

```python
from __future__ import annotations

import pytest
from pathlib import Path

from docpipe.models import Bundle, FileItem
from docpipe.steps.resolve_attachments import ResolveAttachmentsStep


def _make_bundle(md_content: str, base_dir: str = "/tmp") -> Bundle:
    return Bundle(
        files=[FileItem(name="doc.md", content=md_content, content_type="text/markdown", role="main")],
        context={"absolute_path": f"{base_dir}/doc.md"},
    )


def _step() -> ResolveAttachmentsStep:
    return ResolveAttachmentsStep()


class TestResolveAttachmentsNoOp:

    def test_non_markdown_skipped(self):
        bundle = Bundle(files=[FileItem(name="doc.docx", content=b"\x00", role="main")])
        result = _step().process(bundle)
        assert len(result.files) == 1

    def test_no_absolute_path_skipped(self):
        bundle = Bundle(files=[FileItem(name="doc.md", content="hello", role="main")])
        result = _step().process(bundle)
        assert len(result.files) == 1

    def test_empty_bundle(self):
        result = _step().process(Bundle())
        assert result.files == []


class TestResolveAttachmentsLocalFiles:

    def test_image_reference(self, tmp_path):
        img = tmp_path / "images" / "photo.png"
        img.parent.mkdir()
        img.write_bytes(b"\x89PNG")

        md = "![photo](images/photo.png)\n"
        bundle = _make_bundle(md, str(tmp_path))
        result = _step().process(bundle)

        assert len(result.files) == 2
        image_item = result.files[1]
        assert image_item.role == "image"
        assert image_item.name == "images/photo.png"
        assert image_item.content == b"\x89PNG"

    def test_attachment_reference(self, tmp_path):
        pdf = tmp_path / "report.pdf"
        pdf.write_bytes(b"%PDF")

        md = "[download](report.pdf)\n"
        bundle = _make_bundle(md, str(tmp_path))
        result = _step().process(bundle)

        assert len(result.files) == 2
        att = result.files[1]
        assert att.role == "attachment"
        assert att.name == "report.pdf"

    def test_multiple_references(self, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"aaa")
        pdf = tmp_path / "b.pdf"
        pdf.write_bytes(b"bbb")

        md = "![a](a.png)\n[link](b.pdf)\n"
        bundle = _make_bundle(md, str(tmp_path))
        result = _step().process(bundle)

        assert len(result.files) == 3
        roles = [f.role for f in result.files]
        assert "image" in roles
        assert "attachment" in roles


class TestResolveAttachmentsFilter:

    def test_external_http_skipped(self, tmp_path):
        md = "![img](https://example.com/photo.png)\n"
        bundle = _make_bundle(md, str(tmp_path))
        result = _step().process(bundle)
        assert len(result.files) == 1

    def test_anchor_skipped(self, tmp_path):
        md = "[section](#intro)\n"
        bundle = _make_bundle(md, str(tmp_path))
        result = _step().process(bundle)
        assert len(result.files) == 1

    def test_data_uri_skipped(self, tmp_path):
        md = "![img](data:image/png;base64,abc)\n"
        bundle = _make_bundle(md, str(tmp_path))
        result = _step().process(bundle)
        assert len(result.files) == 1

    def test_missing_file_skipped(self, tmp_path):
        md = "![img](nonexistent.png)\n"
        bundle = _make_bundle(md, str(tmp_path))
        result = _step().process(bundle)
        assert len(result.files) == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_resolve_attachments.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'docpipe.steps.resolve_attachments'`

- [ ] **Step 3: 实现 ResolveAttachmentsStep**

创建 `docpipe/steps/resolve_attachments.py`：

```python
from __future__ import annotations

import logging
import re
from pathlib import Path

from docpipe.models import Bundle, FileItem
from docpipe.steps import register_step
from docpipe.steps.base import PipelineStep

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico", ".emf"})
_REF_PATTERN = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')
_EXTERNAL_PREFIXES = ("http://", "https://", "#", "data:", "mailto:")


def _guess_content_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    return f"image/{ext.lstrip('.')}" if ext in _IMAGE_EXTENSIONS else ""


def _read_file(path: Path) -> tuple[str | bytes, str]:
    ext = path.suffix.lower()
    binary_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".emf", ".pdf",
                   ".zip", ".tar", ".gz", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}
    if ext in binary_exts:
        return path.read_bytes(), f"application/octet-stream"
    return path.read_text(encoding="utf-8"), "text/plain"


@register_step("resolve_attachments")
class ResolveAttachmentsStep(PipelineStep):
    def __init__(self, **kwargs):
        pass

    def process(self, bundle: Bundle) -> Bundle:
        main = bundle.main
        if not main or not isinstance(main.content, str):
            return bundle

        abs_path = bundle.context.get("absolute_path")
        if not abs_path:
            logger.warning("resolve_attachments: context 中未找到 absolute_path，跳过")
            return bundle

        base_dir = Path(abs_path).parent
        content = main.content

        seen = set()
        for match in _REF_PATTERN.finditer(content):
            ref_path = match.group(2)
            if ref_path.startswith(_EXTERNAL_PREFIXES):
                continue
            if ref_path in seen:
                continue
            seen.add(ref_path)

            file_path = base_dir / ref_path
            if not file_path.exists():
                logger.warning("resolve_attachments: 文件不存在: %s", file_path)
                continue

            data, content_type = _read_file(file_path)
            ext = Path(ref_path).suffix.lower()
            role = "image" if ext in _IMAGE_EXTENSIONS else "attachment"

            item = FileItem(
                name=ref_path,
                content=data,
                content_type=_guess_content_type(ref_path) or content_type,
                role=role,
            )
            bundle.add(item)

        return bundle
```

- [ ] **Step 4: 注册 step**

在 `docpipe/steps/__init__.py` 末尾添加：

```python
import docpipe.steps.resolve_attachments  # noqa: F401, E402
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_resolve_attachments.py -v`
Expected: 全部 PASS

- [ ] **Step 6: 运行全部测试确认无回归**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
git add docpipe/steps/resolve_attachments.py docpipe/steps/__init__.py tests/test_resolve_attachments.py
git commit -m "feat: 实现 resolve_attachments 步骤"
```

---

### Task 2: 更新 docpipe.yaml 配置

**Files:**
- Modify: `docpipe.yaml`

- [ ] **Step 1: 在 markdown-to-hindsight pipeline 的 steps 中添加 resolve_attachments**

将 `steps: [s3_upload]` 改为 `steps: [resolve_attachments, s3_upload]`：

```yaml
    steps:
      - resolve_attachments
      - s3_upload
```

- [ ] **Step 2: Commit**

```bash
git add docpipe.yaml
git commit -m "feat: 在 markdown-to-hindsight pipeline 中启用 resolve_attachments"
```
