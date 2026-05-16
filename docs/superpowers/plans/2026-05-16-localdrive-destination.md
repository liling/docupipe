# LocalDrive Destination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 LocalDrive Destination，将 Pipeline 处理后的文档保存到本地磁盘，按原始路径重建目录结构，并生成伴生 `.json` 元信息文件。

**Architecture:** 新增 `LocalDriveDestination` 类，实现 `write()` 和 `remove()` 接口。`write()` 将 `doc.content` 写入 `output_dir/space_name/meta.path`（追加 content_type 对应扩展名），同时在同路径生成 `.json` 伴生文件。`remove()` 删除文件和伴生文件。

**Tech Stack:** Python 标准库（pathlib, json, hashlib）

---

### Task 1: 编写 write 基础测试

**Files:**
- Test: `tests/test_docpipe.py` — 在 `TestLocalSource` 之前添加 `TestLocalDriveDestination` 类

- [ ] **Step 1: 编写测试 — write 创建文件和伴生 json**

在 `tests/test_docpipe.py` 的 `TestRegistration` 类之后添加：

```python
class TestLocalDriveDestination:
    def test_write_creates_file_and_sidecar(self, tmp_path):
        from docpipe.destinations.localdrive import LocalDriveDestination

        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))
        doc = Document(
            meta=DocumentMeta(
                id="node1",
                title="方案",
                path="产品规划/方案",
                hash="abc123",
                extra={"space_name": "知识库A", "contentType": "ALIDOC", "extension": "adoc"},
            ),
            content="# 方案内容",
            content_type="markdown",
        )

        result = dest.write(doc)

        # 文件已创建，路径包含 space_name 和原始路径，扩展名由 content_type 推断
        expected_file = output_dir / "知识库A" / "产品规划" / "方案.md"
        assert expected_file.exists()
        assert expected_file.read_text(encoding="utf-8") == "# 方案内容"

        # 伴生 json
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestLocalDriveDestination::test_write_creates_file_and_sidecar -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'docpipe.destinations.localdrive'`

- [ ] **Step 3: 实现 LocalDriveDestination.write()**

创建 `docpipe/destinations/localdrive.py`：

```python
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from docpipe.destinations import register_destination
from docpipe.destinations.base import DestinationBase
from docpipe.models import Document


@register_destination("localdrive")
class LocalDriveDestination(DestinationBase):
    def __init__(self, output_dir: str, **kwargs):
        self._output_dir = Path(output_dir)

    def write(self, doc: Document) -> str:
        file_path = self._resolve_path(doc)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        content = doc.content
        if isinstance(content, bytes):
            file_path.write_bytes(content)
        else:
            file_path.write_text(content, encoding="utf-8")

        self._write_sidecar(file_path, doc)

        return str(file_path)

    def remove(self, doc_id: str) -> None:
        raise NotImplementedError("localdrive remove 需要路径信息")

    def remove_by_path(self, file_path: str) -> None:
        p = Path(file_path)
        if p.exists():
            p.unlink()
        sidecar = Path(file_path + ".json")
        if sidecar.exists():
            sidecar.unlink()

    def _resolve_path(self, doc: Document) -> Path:
        meta = doc.meta
        space_name = meta.extra.get("space_name", "")
        rel_path = meta.path

        # 追加扩展名
        ext = self._content_type_to_ext(doc.content_type)
        if ext and not rel_path.endswith(ext):
            rel_path = rel_path + ext

        if space_name:
            return self._output_dir / space_name / rel_path
        return self._output_dir / rel_path

    def _write_sidecar(self, file_path: Path, doc: Document) -> None:
        meta = doc.meta
        space_name = meta.extra.get("space_name", "")
        data = {
            "id": meta.id,
            "title": meta.title,
            "contentType": meta.extra.get("contentType", ""),
            "extension": meta.extra.get("extension", ""),
            "space_name": space_name,
            "relative_path": meta.path,
            "full_path": f"{space_name}/{meta.path}" if space_name else meta.path,
            "content_hash": meta.hash,
        }
        sidecar = Path(str(file_path) + ".json")
        sidecar.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _content_type_to_ext(content_type: str) -> str:
        mapping = {"markdown": ".md", "text": ".txt", "html": ".html"}
        return mapping.get(content_type, "")
```

- [ ] **Step 4: 注册 localdrive**

在 `docpipe/destinations/__init__.py` 末尾添加：

```python
import docpipe.destinations.localdrive  # noqa: F401, E402
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestLocalDriveDestination::test_write_creates_file_and_sidecar -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add docpipe/destinations/localdrive.py docpipe/destinations/__init__.py tests/test_docpipe.py
git commit -m "feat: 添加 LocalDrive Destination（write + sidecar json）"
```

---

### Task 2: write 跳过/覆盖逻辑

**Files:**
- Modify: `docpipe/destinations/localdrive.py`
- Modify: `tests/test_docpipe.py`

- [ ] **Step 1: 编写测试 — 文件已存在且内容相同则跳过**

在 `TestLocalDriveDestination` 添加：

```python
    def test_write_skips_unchanged(self, tmp_path):
        from docpipe.destinations.localdrive import LocalDriveDestination

        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))
        doc = Document(
            meta=DocumentMeta(id="1", title="A", path="A", hash="h1", extra={"space_name": "S"}),
            content="hello",
            content_type="markdown",
        )

        # 第一次写入
        dest.write(doc)
        file_path = output_dir / "S" / "A.md"
        mtime1 = file_path.stat().st_mtime

        # 修改时间不同则说明被重写了
        import time
        time.sleep(0.05)

        # 第二次写入（内容相同，hash 相同）
        dest2 = LocalDriveDestination(output_dir=str(output_dir))
        dest2.write(doc)
        mtime2 = file_path.stat().st_mtime

        assert mtime1 == mtime2
```

- [ ] **Step 2: 编写测试 — 文件已存在但内容不同则覆盖**

```python
    def test_write_overwrites_changed(self, tmp_path):
        from docpipe.destinations.localdrive import LocalDriveDestination

        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))
        doc1 = Document(
            meta=DocumentMeta(id="1", title="A", path="A", hash="h1", extra={"space_name": "S"}),
            content="old content",
            content_type="markdown",
        )
        dest.write(doc1)

        doc2 = Document(
            meta=DocumentMeta(id="1", title="A", path="A", hash="h2", extra={"space_name": "S"}),
            content="new content",
            content_type="markdown",
        )
        dest.write(doc2)

        file_path = output_dir / "S" / "A.md"
        assert file_path.read_text(encoding="utf-8") == "new content"
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestLocalDriveDestination::test_write_skips_unchanged tests/test_docpipe.py::TestLocalDriveDestination::test_write_overwrites_changed -v`
Expected: `test_write_overwrites_changed` PASS，`test_write_skips_unchanged` FAIL（当前总是覆盖）

- [ ] **Step 4: 修改 write() 增加跳过逻辑**

修改 `docpipe/destinations/localdrive.py` 的 `write` 方法，在写入前检查：

```python
    def write(self, doc: Document) -> str:
        file_path = self._resolve_path(doc)

        # 文件已存在且 hash 相同 → 跳过
        if file_path.exists() and doc.meta.hash:
            sidecar = Path(str(file_path) + ".json")
            if sidecar.exists():
                stored = json.loads(sidecar.read_text(encoding="utf-8"))
                if stored.get("content_hash") == doc.meta.hash:
                    return str(file_path)

        file_path.parent.mkdir(parents=True, exist_ok=True)

        content = doc.content
        if isinstance(content, bytes):
            file_path.write_bytes(content)
        else:
            file_path.write_text(content, encoding="utf-8")

        self._write_sidecar(file_path, doc)

        return str(file_path)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestLocalDriveDestination -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add docpipe/destinations/localdrive.py tests/test_docpipe.py
git commit -m "feat: LocalDrive write 跳过内容不变的文件"
```

---

### Task 3: remove 和注册测试

**Files:**
- Modify: `tests/test_docpipe.py`

- [ ] **Step 1: 编写测试 — remove 删除文件和伴生 json**

在 `TestLocalDriveDestination` 添加：

```python
    def test_remove_deletes_file_and_sidecar(self, tmp_path):
        from docpipe.destinations.localdrive import LocalDriveDestination

        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))
        doc = Document(
            meta=DocumentMeta(id="1", title="A", path="A", hash="h1", extra={"space_name": "S"}),
            content="hello",
            content_type="markdown",
        )

        file_path = dest.write(doc)
        assert Path(file_path).exists()

        dest.remove_by_path(file_path)
        assert not Path(file_path).exists()
        assert not Path(file_path + ".json").exists()

    def test_remove_nonexistent_file_no_error(self, tmp_path):
        from docpipe.destinations.localdrive import LocalDriveDestination

        output_dir = tmp_path / "output"
        dest = LocalDriveDestination(output_dir=str(output_dir))
        # 不应抛异常
        dest.remove_by_path(str(output_dir / "nonexistent.md"))
```

- [ ] **Step 2: 编写测试 — 注册表包含 localdrive**

在 `TestRegistration` 中添加：

```python
    def test_localdrive_registered(self):
        from docpipe.destinations import DESTINATIONS
        assert "localdrive" in DESTINATIONS
```

- [ ] **Step 3: 运行全部测试**

Run: `python -m pytest tests/test_docpipe.py -v`
Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
git add tests/test_docpipe.py
git commit -m "test: 添加 LocalDrive remove 和注册测试"
```

---

### Task 4: YAML 配置集成

**Files:**
- No code changes needed — `cli.py` 的 `_run_from_config` 已经通过 `dest_config` 传递 `kwargs`，`LocalDriveDestination.__init__` 接收 `output_dir` 参数，YAML 配置 `destination_config.output_dir` 自动映射。

- [ ] **Step 1: 验证 YAML 配置可用**

在 `docpipe.yaml` 中添加测试 pipeline：

```yaml
  - name: wiki-to-local
    source: dingtalk
    destination: localdrive
    destination_config:
      output_dir: ./output
    content_type_rules:
      DOCUMENT: convert
      ALIDOC: source
    source_config:
      space_id: "nb9XJB7qpnkxQXyA"
```

Run: `python -m docpipe run --config docpipe.yaml --pipeline wiki-to-local --dry-run`
Expected: 显示 pipeline 信息，dry-run 模式不写入文件

- [ ] **Step 2: 还原 docpipe.yaml（如果需要）**

- [ ] **Step 3: 提交**

```bash
git add -A
git commit -m "feat: LocalDrive Destination 集成完成"
```
