# LocalDrive Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 `LocalDriveSource` 替换 `LocalSource`，支持从本地文件夹读取所有类型文件，通过 include/exclude 规则过滤，交给 pipeline 的 converter 系统处理格式转换。

**Architecture:** 新建 `docpipe/sources/localdrive.py`，注册为 `localdrive`。递归扫描目录（跳过隐藏文件/目录），用扩展名作为 content_type，支持 include/exclude glob 过滤。删除旧的 `local.py`。

**Tech Stack:** Python 标准库（pathlib, hashlib, fnmatch）

---

### Task 1: 编写 list_documents 基础测试

**Files:**
- Modify: `tests/test_docpipe.py` — 替换 `TestLocalSource` 为 `TestLocalDriveSource`

- [ ] **Step 1: 编写测试 — list_documents 扫描所有文件类型**

在 `tests/test_docpipe.py` 中，将 `TestLocalSource` 类（第 482-507 行）替换为：

```python
class TestLocalDriveSource:
    def test_list_all_file_types(self, tmp_path):
        (tmp_path / "a.md").write_text("hello a")
        (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4 fake")
        (tmp_path / "c.docx").write_bytes(b"PK fake docx")
        (tmp_path / "d.txt").write_text("plain text")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        docs = source.list_documents()
        titles = {d.title for d in docs}
        assert titles == {"a", "b", "c", "d"}

    def test_list_skips_hidden_dirs_and_files(self, tmp_path):
        (tmp_path / "visible.md").write_text("seen")
        hidden_dir = tmp_path / ".hidden_dir"
        hidden_dir.mkdir()
        (hidden_dir / "secret.md").write_text("hidden dir file")
        (tmp_path / ".hidden.md").write_text("hidden file")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        docs = source.list_documents()
        assert len(docs) == 1
        assert docs[0].title == "visible"

    def test_list_skips_no_extension(self, tmp_path):
        (tmp_path / "README").write_text("no extension")
        (tmp_path / "guide.md").write_text("has extension")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        docs = source.list_documents()
        assert len(docs) == 1
        assert docs[0].title == "guide"

    def test_list_recursive(self, tmp_path):
        sub = tmp_path / "sub" / "dir"
        sub.mkdir(parents=True)
        (tmp_path / "root.md").write_text("root")
        (sub / "deep.md").write_text("deep")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        docs = source.list_documents()
        paths = {d.path for d in docs}
        assert "root.md" in paths
        assert str(Path("sub") / "dir" / "deep.md") in paths

    def test_invalid_dir_raises(self):
        from docpipe.sources.localdrive import LocalDriveSource
        with pytest.raises(ValueError, match="目录不存在"):
            LocalDriveSource(input_dir="/nonexistent/path")
```

注意：在文件顶部添加 `from pathlib import Path` 的使用（`Path` 已在导入中）。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestLocalDriveSource -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'docpipe.sources.localdrive'`

---

### Task 2: 实现 LocalDriveSource 基础

**Files:**
- Create: `docpipe/sources/localdrive.py`

- [ ] **Step 1: 创建 localdrive.py**

创建 `docpipe/sources/localdrive.py`：

```python
from __future__ import annotations

import hashlib
from pathlib import Path

from docpipe.models import Document, DocumentMeta, SkipDocument
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

    def list_documents(self) -> list[DocumentMeta]:
        result = []
        for f in sorted(self._input_dir.rglob("*")):
            if not f.is_file():
                continue
            # 跳过隐藏文件和隐藏目录中的文件
            if any(part.startswith(".") for part in f.relative_to(self._input_dir).parts):
                continue
            # 跳过无扩展名文件
            if not f.suffix:
                continue

            relative = f.relative_to(self._input_dir)
            rel_str = str(relative)

            if not self._matches_filters(rel_str):
                continue

            file_hash = hashlib.sha256(f.read_bytes()).hexdigest()
            result.append(DocumentMeta(
                id=file_hash,
                title=f.stem,
                path=rel_str,
                hash=file_hash,
                extra={
                    "extension": f.suffix.lstrip("."),
                    "absolute_path": str(f),
                    "size": f.stat().st_size,
                },
            ))
        return result

    def fetch(self, doc_meta: DocumentMeta) -> Document:
        f = Path(doc_meta.extra["absolute_path"])
        extension = doc_meta.extra.get("extension", "")

        if extension in _TEXT_EXTENSIONS:
            content = f.read_text(encoding="utf-8")
        else:
            content = f.read_bytes()

        return Document(
            meta=doc_meta,
            content=content,
            content_type=extension,
        )

    def _matches_filters(self, rel_path: str) -> bool:
        # exclude 优先
        if self._exclude and self._glob_matches(rel_path, self._exclude):
            return False
        # include 为空表示包含所有
        if self._include and not self._glob_matches(rel_path, self._include):
            return False
        return True

    @staticmethod
    def _glob_matches(path: str, patterns: list[str]) -> bool:
        p = Path(path)
        return any(p.match(pattern) for pattern in patterns)


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

- [ ] **Step 2: 更新 sources/__init__.py**

将 `docpipe/sources/__init__.py` 第 27 行的 `import docpipe.sources.local` 替换为：

```python
import docpipe.sources.localdrive  # noqa: F401, E402
```

- [ ] **Step 3: 删除旧 local.py**

```bash
rm docpipe/sources/local.py
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestLocalDriveSource -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add docpipe/sources/localdrive.py docpipe/sources/__init__.py docpipe/sources/local.py tests/test_docpipe.py
git commit -m "feat: LocalDriveSource 替换 LocalSource，支持所有文件类型"
```

---

### Task 3: fetch 测试

**Files:**
- Modify: `tests/test_docpipe.py` — 在 `TestLocalDriveSource` 中添加

- [ ] **Step 1: 编写测试 — fetch 文本和二进制**

在 `TestLocalDriveSource` 类中添加：

```python
    def test_fetch_text_file(self, tmp_path):
        (tmp_path / "test.md").write_text("hello world", encoding="utf-8")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        docs = source.list_documents()
        doc = source.fetch(docs[0])
        assert isinstance(doc.content, str)
        assert doc.content == "hello world"
        assert doc.content_type == "md"

    def test_fetch_binary_file(self, tmp_path):
        (tmp_path / "test.pdf").write_bytes(b"%PDF-1.4 fake content")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        docs = source.list_documents()
        doc = source.fetch(docs[0])
        assert isinstance(doc.content, bytes)
        assert doc.content_type == "pdf"

    def test_fetch_metadata(self, tmp_path):
        (tmp_path / "report.pdf").write_bytes(b"%PDF fake")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        docs = source.list_documents()
        assert docs[0].title == "report"
        assert docs[0].extra["extension"] == "pdf"
        assert docs[0].extra["size"] > 0
        assert "report.pdf" in docs[0].path
```

- [ ] **Step 2: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestLocalDriveSource -v`
Expected: 全部 PASS（fetch 已在 Task 2 中实现）

- [ ] **Step 3: 提交**

```bash
git add tests/test_docpipe.py
git commit -m "test: LocalDriveSource fetch 文本/二进制测试"
```

---

### Task 4: include/exclude 过滤测试

**Files:**
- Modify: `tests/test_docpipe.py` — 在 `TestLocalDriveSource` 中添加

- [ ] **Step 1: 编写测试 — 过滤规则**

在 `TestLocalDriveSource` 类中添加：

```python
    def test_include_filter(self, tmp_path):
        (tmp_path / "a.md").write_text("md")
        (tmp_path / "b.pdf").write_bytes(b"pdf")
        (tmp_path / "c.docx").write_bytes(b"docx")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path), include=["*.md", "*.pdf"])
        docs = source.list_documents()
        titles = {d.title for d in docs}
        assert titles == {"a", "b"}

    def test_exclude_filter(self, tmp_path):
        (tmp_path / "a.md").write_text("md")
        (tmp_path / "b.pdf").write_bytes(b"pdf")
        (tmp_path / "c.docx").write_bytes(b"docx")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path), exclude=["*.pdf"])
        docs = source.list_documents()
        titles = {d.title for d in docs}
        assert titles == {"a", "c"}

    def test_exclude_overrides_include(self, tmp_path):
        (tmp_path / "a.md").write_text("md")
        (tmp_path / "b.pdf").write_bytes(b"pdf")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(
            input_dir=str(tmp_path),
            include=["*.md", "*.pdf"],
            exclude=["*.pdf"],
        )
        docs = source.list_documents()
        titles = {d.title for d in docs}
        assert titles == {"a"}

    def test_no_filters_includes_all(self, tmp_path):
        (tmp_path / "a.md").write_text("md")
        (tmp_path / "b.pdf").write_bytes(b"pdf")
        (tmp_path / "c.py").write_text("print('hi')")

        from docpipe.sources.localdrive import LocalDriveSource
        source = LocalDriveSource(input_dir=str(tmp_path))
        docs = source.list_documents()
        assert len(docs) == 3
```

- [ ] **Step 2: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestLocalDriveSource -v`
Expected: 全部 PASS

- [ ] **Step 3: 提交**

```bash
git add tests/test_docpipe.py
git commit -m "test: LocalDriveSource include/exclude 过滤测试"
```

---

### Task 5: CLI 集成

**Files:**
- Modify: `docpipe/cli.py:160-175` — `_extract_source_config` 函数
- Modify: `tests/test_docpipe.py` — 更新 `TestRegistration`

- [ ] **Step 1: 更新 _extract_source_config**

在 `docpipe/cli.py` 的 `_extract_source_config` 函数中，将 `elif source_name == "local":` 分支（第 172-174 行）替换为：

```python
    elif source_name in ("local", "localdrive"):
        if kwargs.get("input_dir"):
            config["input_dir"] = kwargs["input_dir"]
```

- [ ] **Step 2: 更新 TestRegistration**

在 `tests/test_docpipe.py` 的 `TestRegistration.test_sources_registered` 中，将：

```python
        assert "local" in SOURCES
```

替换为：

```python
        assert "localdrive" in SOURCES
```

- [ ] **Step 3: 运行全部测试**

Run: `python -m pytest tests/test_docpipe.py -v`
Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
git add docpipe/cli.py tests/test_docpipe.py
git commit -m "feat: CLI 集成 LocalDriveSource，更新注册测试"
```

---

### Task 6: 端到端验证

**Files:**
- 无代码变更

- [ ] **Step 1: 验证 CLI 注册**

Run: `python -m docpipe sources`
Expected: 输出包含 `localdrive`

- [ ] **Step 2: 验证 YAML 配置集成**

创建临时测试配置 `tmp_test.yaml`：

```yaml
pipelines:
  - name: local-test
    source: localdrive
    destination: localdrive
    source_config:
      input_dir: ./docs
      include: ["*.md"]
    destination_config:
      output_dir: ./tmp_output
```

Run: `python -m docpipe run --config tmp_test.yaml --dry-run`
Expected: 显示 pipeline 信息，dry-run 不写入文件

- [ ] **Step 3: 清理临时文件**

```bash
rm -f tmp_test.yaml
```

- [ ] **Step 4: 最终提交（如有变更）**

如果一切通过，无需额外提交。
