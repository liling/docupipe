# 可配置文件类型处理器实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将文件类型判断和内容转换从 Source 解耦到可配置的 Converter + TypeRuleResolver，通过 YAML 配置文件定义类型→处理器映射。

**Architecture:** 新建 `docpipe/converters/` 包，包含抽象基类、注册机制、TypeRuleResolver。Pipeline 用 TypeRuleResolver 过滤文件并调用对应 Converter 转换。Source 不再做类型过滤和内容转换，只负责下载。

**Tech Stack:** Python 3.11+, markitdown, yaml

---

### Task 1: 创建 Converter 抽象基类和注册机制

**Files:**
- Create: `docpipe/converters/__init__.py`
- Create: `docpipe/converters/base.py`

- [ ] **Step 1: 创建 converters 包**

创建 `docpipe/converters/__init__.py`：

```python
from __future__ import annotations

CONVERTERS: dict[str, type] = {}


def register_converter(name: str):
    def decorator(cls):
        CONVERTERS[name] = cls
        return cls
    return decorator


def get_converter(name: str):
    if name not in CONVERTERS:
        raise ValueError(f"未知的 converter: {name}")
    return CONVERTERS[name]
```

创建 `docpipe/converters/base.py`：

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ConverterBase(ABC):
    name: str = ""

    @abstractmethod
    def convert(self, file_path: Path) -> str:
        """将文件转换为 Markdown，返回 Markdown 文本"""
```

- [ ] **Step 2: 提交**

```bash
git add docpipe/converters/__init__.py docpipe/converters/base.py
git commit -m "feat: 创建 Converter 抽象基类和注册机制"
```

---

### Task 2: 创建 MarkitdownConverter

**Files:**
- Create: `docpipe/converters/markitdown.py`
- Create: `tests/test_converters.py`

- [ ] **Step 1: 编写 MarkitdownConverter 测试**

创建 `tests/test_converters.py`：

```python
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from docpipe.converters import CONVERTERS, get_converter
from docpipe.converters.markitdown import MarkitdownConverter


class TestMarkitdownConverter:
    def test_registered(self):
        assert "markitdown" in CONVERTERS

    def test_convert_txt(self, tmp_path):
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("hello world")
        converter = MarkitdownConverter()
        result = converter.convert(txt_file)
        assert "hello world" in result

    def test_convert_md(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("# Title\n\ncontent")
        converter = MarkitdownConverter()
        result = converter.convert(md_file)
        assert "Title" in result


class TestGetConverter:
    def test_known_converter(self):
        cls = get_converter("markitdown")
        assert cls is MarkitdownConverter

    def test_unknown_converter_raises(self):
        with pytest.raises(ValueError, match="未知的 converter"):
            get_converter("nonexistent")
```

- [ ] **Step 2: 实现 MarkitdownConverter**

创建 `docpipe/converters/markitdown.py`：

```python
from __future__ import annotations

import logging
from pathlib import Path

from docpipe.converters import register_converter
from docpipe.converters.base import ConverterBase

logger = logging.getLogger(__name__)


@register_converter("markitdown")
class MarkitdownConverter(ConverterBase):
    name = "markitdown"

    def convert(self, file_path: Path) -> str:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(str(file_path))
        logger.debug("markitdown 转换完成: %s, 长度=%d", file_path.name, len(result.markdown))
        return result.markdown
```

- [ ] **Step 3: 运行测试**

Run: `python -m pytest tests/test_converters.py -v`
Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
git add docpipe/converters/markitdown.py tests/test_converters.py
git commit -m "feat: 添加 MarkitdownConverter"
```

---

### Task 3: 创建 TypeRuleResolver

**Files:**
- Create: `docpipe/converters/resolver.py`

- [ ] **Step 1: 编写 TypeRuleResolver 测试**

追加到 `tests/test_converters.py`：

```python
from docpipe.converters.resolver import TypeRuleResolver


class TestTypeRuleResolver:
    def test_resolve_by_extension(self):
        resolver = TypeRuleResolver(extension_rules={".pdf": "mineru", ".docx": "markitdown"})
        assert resolver.resolve(".pdf") == "mineru"
        assert resolver.resolve(".docx") == "markitdown"

    def test_resolve_unknown_returns_none(self):
        resolver = TypeRuleResolver(extension_rules={".pdf": "mineru"})
        assert resolver.resolve(".tar.gz") is None

    def test_empty_extension_returns_none(self):
        resolver = TypeRuleResolver(extension_rules={".pdf": "mineru"})
        assert resolver.resolve("") is None

    def test_resolve_by_mime(self):
        resolver = TypeRuleResolver(
            extension_rules={},
            mime_rules={"application/pdf": "mineru"},
        )
        assert resolver.resolve("", "application/pdf") == "mineru"

    def test_extension_takes_priority_over_mime(self):
        resolver = TypeRuleResolver(
            extension_rules={".pdf": "markitdown"},
            mime_rules={"application/pdf": "mineru"},
        )
        assert resolver.resolve(".pdf", "application/pdf") == "markitdown"

    def test_mime_no_match(self):
        resolver = TypeRuleResolver(
            extension_rules={},
            mime_rules={"application/pdf": "mineru"},
        )
        assert resolver.resolve(".docx", "text/plain") is None

    def test_no_mime_rules(self):
        resolver = TypeRuleResolver(extension_rules={".pdf": "mineru"})
        assert resolver.resolve(".pdf") == "mineru"
```

- [ ] **Step 2: 实现 TypeRuleResolver**

创建 `docpipe/converters/resolver.py`：

```python
from __future__ import annotations


class TypeRuleResolver:
    def __init__(
        self,
        extension_rules: dict[str, str],
        mime_rules: dict[str, str] | None = None,
    ):
        self._extension_rules = extension_rules
        self._mime_rules = mime_rules or {}

    def resolve(self, extension: str, mime_type: str = "") -> str | None:
        if extension in self._extension_rules:
            return self._extension_rules[extension]
        if mime_type and mime_type in self._mime_rules:
            return self._mime_rules[mime_type]
        return None
```

- [ ] **Step 3: 运行测试**

Run: `python -m pytest tests/test_converters.py -v`
Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
git add docpipe/converters/resolver.py tests/test_converters.py
git commit -m "feat: 添加 TypeRuleResolver"
```

---

### Task 4: 改造 Pipeline 集成 TypeRuleResolver + Converter

**Files:**
- Modify: `docpipe/pipeline.py`

- [ ] **Step 1: 编写 Pipeline 集成测试**

追加到 `tests/test_docpipe.py`：

```python
from docpipe.converters.resolver import TypeRuleResolver


class TestPipelineTypeRules:
    def test_skip_unknown_type(self, tmp_path):
        """未知扩展名不在 type_rules 中，直接跳过"""
        docs = [_make_doc("1", "A", extra={"extension": "tar.gz"})]
        source = FakeSource(docs)
        dest = FakeDestination()
        resolver = TypeRuleResolver(extension_rules={".pdf": "markitdown"})
        pipeline = Pipeline(source, dest, tmp_path, type_resolver=resolver)
        pipeline.run()
        assert len(dest.written) == 0
        assert pipeline._display.skipped >= 1

    def test_skip_explicit_skip(self, tmp_path):
        """配置中显式标记 skip 的文件被跳过"""
        docs = [_make_doc("1", "A", extra={"extension": "exe"})]
        source = FakeSource(docs)
        dest = FakeDestination()
        resolver = TypeRuleResolver(extension_rules={".exe": "skip"})
        pipeline = Pipeline(source, dest, tmp_path, type_resolver=resolver)
        pipeline.run()
        assert len(dest.written) == 0

    def test_process_with_converter(self, tmp_path):
        """匹配到 converter 的文件正常处理（FakeSource 直接返回 markdown）"""
        docs = [_make_doc("1", "A", extra={"extension": "txt"})]
        source = FakeSource(docs)
        dest = FakeDestination()
        resolver = TypeRuleResolver(extension_rules={".txt": "markitdown"})
        pipeline = Pipeline(source, dest, tmp_path, type_resolver=resolver)
        pipeline.run()
        assert len(dest.written) == 1

    def test_no_resolver_processes_all(self, tmp_path):
        """无 resolver 时走原有逻辑，全部处理"""
        docs = [_make_doc("1", "A")]
        source = FakeSource(docs)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path)
        pipeline.run()
        assert len(dest.written) == 1
```

注意：现有测试中 `FakeSource.fetch()` 已经直接返回内容为 markdown 的 Document，且 extension 为空，所以新测试需要在 `_make_doc` 中通过 `extra` 传入 extension。

当前 `_make_doc` 的签名：
```python
def _make_doc(id: str, title: str, content: str = "hello", **extra) -> Document:
    return Document(
        meta=DocumentMeta(id=id, title=title, path=f"{title}.md", hash="", extra=extra),
        content=content,
        content_type="markdown",
    )
```

`**extra` 已经会传入 `DocumentMeta.extra`，所以直接使用即可。

- [ ] **Step 2: 改造 Pipeline 构造函数**

在 `docpipe/pipeline.py` 中修改 Pipeline 构造函数，添加 `type_resolver` 参数：

将原来的：
```python
class Pipeline:
    def __init__(
        self,
        source: SourceBase,
        dest: DestinationBase,
        state_dir: Path,
        display: Display | None = None,
    ):
        self.source = source
        self.dest = dest
        self.state = StateManager(state_dir / f"{source.name}_{dest.name}_state.json")
        self._display = display or Display()
```

改为：
```python
class Pipeline:
    def __init__(
        self,
        source: SourceBase,
        dest: DestinationBase,
        state_dir: Path,
        display: Display | None = None,
        type_resolver=None,
    ):
        self.source = source
        self.dest = dest
        self.state = StateManager(state_dir / f"{source.name}_{dest.name}_state.json")
        self._display = display or Display()
        self._type_resolver = type_resolver
```

- [ ] **Step 3: 改造 Pipeline.run() 主循环**

在 `docpipe/pipeline.py` 的 `run()` 方法中，将原来的主循环：

```python
        for doc_meta in docs:
            if sync and self.state.is_unchanged(doc_meta.id, doc_meta.hash):
                self._display.result("skip", f"{doc_meta.title} (无变化)")
                continue

            self._display.set_current(doc_meta.title)
            try:
                doc = self.source.fetch(doc_meta)
                if not doc.meta.hash:
                    doc.meta.hash = content_hash(doc.content)
                # 标记来源
                doc.meta.extra["_source"] = self.source.name

                if dry_run:
                    self._display.result("info", f"[dry-run] {doc_meta.title}")
                else:
                    self.dest.write(doc)
                    self._display.result("success", doc_meta.title)

                self.state.mark_done(doc_meta.id, doc.meta.hash)
            except Exception as e:
                logger.error("文档处理失败: %s - %s", doc_meta.title, e)
                self._display.result("error", f"{doc_meta.title}: {e}")
                self._display.add_failure()
            finally:
                self._display.clear_current(doc_meta.title)
```

改为：

```python
        for doc_meta in docs:
            if sync and self.state.is_unchanged(doc_meta.id, doc_meta.hash):
                self._display.result("skip", f"{doc_meta.title} (无变化)")
                continue

            # 类型规则过滤
            if self._type_resolver:
                converter_name = self._resolve_type(doc_meta)
                if converter_name is None:
                    self._display.result("skip", f"{doc_meta.title} (无处理规则)")
                    continue
                if converter_name == "skip":
                    self._display.result("skip", f"{doc_meta.title} (跳过)")
                    continue
            else:
                converter_name = None

            self._display.set_current(doc_meta.title)
            try:
                doc = self.source.fetch(doc_meta)

                # 转换：如果 Source 标记需要转换，调用 converter
                if doc.meta.extra.get("_needs_conversion") and converter_name:
                    from docpipe.converters import get_converter
                    converter_cls = get_converter(converter_name)
                    converter = converter_cls()
                    file_path = Path(doc.meta.extra["_temp_file"])
                    try:
                        doc.content = converter.convert(file_path)
                    finally:
                        file_path.unlink(missing_ok=True)

                if not doc.meta.hash:
                    doc.meta.hash = content_hash(doc.content)
                # 标记来源
                doc.meta.extra["_source"] = self.source.name

                if dry_run:
                    self._display.result("info", f"[dry-run] {doc_meta.title}")
                else:
                    self.dest.write(doc)
                    self._display.result("success", doc_meta.title)

                self.state.mark_done(doc_meta.id, doc.meta.hash)
            except Exception as e:
                logger.error("文档处理失败: %s - %s", doc_meta.title, e)
                self._display.result("error", f"{doc_meta.title}: {e}")
                self._display.add_failure()
            finally:
                self._display.clear_current(doc_meta.title)
```

并在 Pipeline 类中添加 `_resolve_type` 方法：

```python
    def _resolve_type(self, doc_meta: DocumentMeta) -> str | None:
        ext_raw = doc_meta.extra.get("extension", "")
        extension = f".{ext_raw}" if ext_raw else ""
        mime_type = doc_meta.extra.get("contentType", "")
        return self._type_resolver.resolve(extension, mime_type)
```

- [ ] **Step 4: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add docpipe/pipeline.py tests/test_converters.py tests/test_docpipe.py
git commit -m "feat: Pipeline 集成 TypeRuleResolver + Converter"
```

---

### Task 5: 改造 DingtalkSource

**Files:**
- Modify: `docpipe/sources/dingtalk.py`

- [ ] **Step 1: 简化 list_documents()，移除类型过滤**

将 `docpipe/sources/dingtalk.py` 的 `list_documents()` 方法中的过滤逻辑移除。

将原来的（第 104-143 行）：

```python
    def list_documents(self) -> list[DocumentMeta]:
        logger.info("列出文档: space_id=%s, folder_id=%s", self._space_id, self._folder_id or "(根目录)")
        nodes = self._collect_nodes(self._space_id, self._folder_id)
        result = []
        skipped_count = 0
        for node in nodes:
            node_type = node.get("nodeType", "")
            if node_type == "folder":
                continue
            content_type = node.get("contentType", "")
            extension = node.get("extension", "")
            # 跳过钉钉表格、思维导图、表单等无法处理的类型
            if content_type in _SKIP_CONTENT_TYPES or extension in ("axls", "amindmap"):
                logger.debug("跳过不支持的类型: %s (contentType=%s, extension=%s)",
                             node.get("name", "未命名"), content_type, extension)
                skipped_count += 1
                continue
            # 非钉钉原生文档，必须扩展名在可转换白名单中才处理
            if content_type != "ALIDOC" and extension != "adoc":
                ext_lower = f".{extension}" if extension else ""
                if ext_lower not in _CONVERTIBLE_EXTENSIONS:
                    logger.debug("跳过不可转换的文件: %s (extension=%s)", node.get("name", "未命名"), extension or "(无)")
                    skipped_count += 1
                    continue
            node_id = node.get("nodeId", "")
            title = node.get("name", "未命名")
            result.append(DocumentMeta(
                id=node_id,
                title=title,
                path=node.get("_path", ""),
                hash="",
                extra={
                    "contentType": content_type,
                    "extension": extension,
                    "updateTime": node.get("updateTime"),
                    "nodeType": node_type,
                },
            ))
        logger.info("列出文档完成: 共 %d 个文档, 跳过 %d 个", len(result), skipped_count)
        return result
```

改为：

```python
    def list_documents(self) -> list[DocumentMeta]:
        logger.info("列出文档: space_id=%s, folder_id=%s", self._space_id, self._folder_id or "(根目录)")
        nodes = self._collect_nodes(self._space_id, self._folder_id)
        result = []
        for node in nodes:
            node_type = node.get("nodeType", "")
            if node_type == "folder":
                continue
            node_id = node.get("nodeId", "")
            title = node.get("name", "未命名")
            result.append(DocumentMeta(
                id=node_id,
                title=title,
                path=node.get("_path", ""),
                hash="",
                extra={
                    "contentType": node.get("contentType", ""),
                    "extension": node.get("extension", ""),
                    "updateTime": node.get("updateTime"),
                    "nodeType": node_type,
                },
            ))
        logger.info("列出文档完成: 共 %d 个文档", len(result))
        return result
```

- [ ] **Step 2: 改造 fetch()，分离下载和转换**

将原来的 `fetch()` 方法（第 145-179 行）：

```python
    def fetch(self, doc_meta: DocumentMeta) -> Document:
        content_type = doc_meta.extra.get("contentType", "")
        extension = doc_meta.extra.get("extension", "")
        node_id = doc_meta.id

        logger.info("获取文档: id=%s, title=%s, type=%s", doc_meta.id, doc_meta.title, content_type)

        if content_type == "ALIDOC" or extension == "adoc":
            markdown = self._client.read_document(node_id)
        else:
            ext = extension if extension else "bin"
            markdown = self._download_and_convert(node_id, ext)

        markdown = self._clean_html_tags(markdown)

        if self._image_processor:
            source_context = f"{doc_meta.title} - {doc_meta.path}"
            logger.debug("处理文档中的图片: %s", doc_meta.title)
            markdown, image_metadata = self._image_processor.process(markdown, source_context)
            doc_meta.extra["image_metadata"] = image_metadata
            logger.info("图片处理完成: %s, 处理了 %d 张图片", doc_meta.title, len(image_metadata) if image_metadata else 0)

        content_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        logger.debug("文档获取完成: id=%s, 内容长度=%d, hash=%s...", doc_meta.id, len(markdown), content_hash[:12])
        return Document(
            meta=DocumentMeta(
                id=doc_meta.id,
                title=doc_meta.title,
                path=doc_meta.path,
                hash=content_hash,
                extra=doc_meta.extra,
            ),
            content=markdown,
            content_type="markdown",
        )
```

改为：

```python
    def fetch(self, doc_meta: DocumentMeta) -> Document:
        content_type = doc_meta.extra.get("contentType", "")
        extension = doc_meta.extra.get("extension", "")
        node_id = doc_meta.id

        logger.info("获取文档: id=%s, title=%s, type=%s", doc_meta.id, doc_meta.title, content_type)

        extra = dict(doc_meta.extra)

        if content_type == "ALIDOC" or extension == "adoc":
            markdown = self._client.read_document(node_id)
            markdown = self._clean_html_tags(markdown)
        else:
            # 下载到临时文件，标记需要 converter 转换
            tmp_path = self._download_to_temp(node_id, extension)
            extra["_temp_file"] = str(tmp_path)
            extra["_needs_conversion"] = True
            markdown = ""

        if markdown and self._image_processor:
            source_context = f"{doc_meta.title} - {doc_meta.path}"
            logger.debug("处理文档中的图片: %s", doc_meta.title)
            markdown, image_metadata = self._image_processor.process(markdown, source_context)
            extra["image_metadata"] = image_metadata
            logger.info("图片处理完成: %s, 处理了 %d 张图片", doc_meta.title, len(image_metadata) if image_metadata else 0)

        return Document(
            meta=DocumentMeta(
                id=doc_meta.id,
                title=doc_meta.title,
                path=doc_meta.path,
                hash="",
                extra=extra,
            ),
            content=markdown,
            content_type="markdown",
        )
```

- [ ] **Step 3: 将 _download_and_convert 拆分为 _download_to_temp**

将原来的 `_download_and_convert` 方法（第 204-223 行）：

```python
    def _download_and_convert(self, node_id: str, extension: str) -> str:
        logger.debug("下载并转换文件: node_id=%s, extension=%s", node_id, extension)
        download_url = self._client.download_file(node_id)
        resp = requests.get(download_url, timeout=120)
        resp.raise_for_status()
        logger.debug("文件下载成功: node_id=%s, 大小=%d bytes", node_id, len(resp.content))

        suffix = f".{extension}" if extension else ".bin"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = Path(tmp.name)

        try:
            from markitdown import MarkItDown
            md = MarkItDown()
            result = md.convert(str(tmp_path))
            logger.debug("文件转换完成: node_id=%s, Markdown 长度=%d", node_id, len(result.markdown))
            return result.markdown
        finally:
            tmp_path.unlink(missing_ok=True)
```

替换为：

```python
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
```

- [ ] **Step 4: 移除顶部不再使用的常量**

删除 `_CONVERTIBLE_EXTENSIONS` 和 `_SKIP_CONTENT_TYPES` 常量（第 18-24 行），以及 `from markitdown import MarkItDown` 相关的 import（不再在 dingtalk.py 中使用）。

- [ ] **Step 5: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add docpipe/sources/dingtalk.py
git commit -m "feat: DingtalkSource 移除类型过滤和转换逻辑，改为只下载"
```

---

### Task 6: 改造 CLI 解析 type_rules 配置

**Files:**
- Modify: `docpipe/cli.py`
- Modify: `docpipe.yaml`

- [ ] **Step 1: 改造 _run_from_config 解析 type_rules**

将 `docpipe/cli.py` 的 `_run_from_config` 函数（第 102-141 行）：

```python
def _run_from_config(ctx, config_path, pipeline_name, resume, sync_mode, dry_run):
    import yaml

    from docpipe.destinations import get_destination
    from docpipe.display import Display
    from docpipe.pipeline import Pipeline
    from docpipe.sources import get_source

    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    pipelines = config.get("pipelines", [])

    if pipeline_name:
        pipelines = [p for p in pipelines if p.get("name") == pipeline_name]
        if not pipelines:
            click.echo(f"未找到 pipeline: {pipeline_name}")
            raise SystemExit(1)

    for pipe_config in pipelines:
        source_name = pipe_config["source"]
        dest_name = pipe_config["destination"]
        options = pipe_config.get("options", {})
        source_config = pipe_config.get("source_config", {})
        dest_config = pipe_config.get("dest_config", {})

        source_cls = get_source(source_name)
        dest_cls = get_destination(dest_name)

        source = source_cls(**source_config)
        dest = dest_cls(**dest_config)

        try:
            pipeline = Pipeline(source, dest, ctx.obj["state_dir"], display=Display())
            pipeline.run(
                resume=resume or options.get("resume", False),
                sync=sync_mode or options.get("sync", False),
                dry_run=dry_run,
            )
        finally:
            if hasattr(dest, "close"):
                dest.close()
```

改为：

```python
def _run_from_config(ctx, config_path, pipeline_name, resume, sync_mode, dry_run):
    import yaml

    from docpipe.converters.resolver import TypeRuleResolver
    from docpipe.destinations import get_destination
    from docpipe.display import Display
    from docpipe.pipeline import Pipeline
    from docpipe.sources import get_source

    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))

    type_rules = config.get("type_rules", {})
    resolver = TypeRuleResolver(
        extension_rules=type_rules.get("extensions", {}),
        mime_rules=type_rules.get("mime_types", {}),
    )

    pipelines = config.get("pipelines", [])

    if pipeline_name:
        pipelines = [p for p in pipelines if p.get("name") == pipeline_name]
        if not pipelines:
            click.echo(f"未找到 pipeline: {pipeline_name}")
            raise SystemExit(1)

    for pipe_config in pipelines:
        source_name = pipe_config["source"]
        dest_name = pipe_config["destination"]
        options = pipe_config.get("options", {})
        source_config = pipe_config.get("source_config", {})
        dest_config = pipe_config.get("dest_config", {})

        source_cls = get_source(source_name)
        dest_cls = get_destination(dest_name)

        source = source_cls(**source_config)
        dest = dest_cls(**dest_config)

        try:
            pipeline = Pipeline(source, dest, ctx.obj["state_dir"],
                                display=Display(), type_resolver=resolver)
            pipeline.run(
                resume=resume or options.get("resume", False),
                sync=sync_mode or options.get("sync", False),
                dry_run=dry_run,
            )
        finally:
            if hasattr(dest, "close"):
                dest.close()
```

- [ ] **Step 2: 更新 docpipe.yaml 添加 type_rules**

将 `docpipe.yaml` 更新为：

```yaml
type_rules:
  extensions:
    ".pdf": markitdown
    ".docx": markitdown
    ".xlsx": markitdown
    ".pptx": markitdown
    ".doc": markitdown
    ".xls": markitdown
    ".ppt": markitdown
    ".html": markitdown
    ".htm": markitdown
    ".csv": markitdown
    ".json": markitdown
    ".xml": markitdown
    ".txt": markitdown
    ".md": markitdown
    ".rtf": markitdown
    ".odt": markitdown
    ".ods": markitdown
  mime_types: {}

pipelines:

  - name: shujuxian-to-hindsight
    source: dingtalk
    destination: hindsight
    source_config:
      space_id: "nb9XJB7qpnkxQXyA"
      image_description: true
      image_description_base_url: "http://172.16.4.197:8002/v1"
      image_description_api_key: "sk-MTc3MzY0ODE4NDc4NdJiiX-Lt6vvfVMtMVR38-4e6BDBmdTg_ixoQGQQCfwV"
      image_description_model: "qwen3.5-flash"
    dest_config:
      api_url: "http://127.0.0.1:8888"
      api_key: "hsm_USLTwNV2CzyuOoaSebz2jiZpIrD91tj2lGvkmPWW6Vk"
      bank_id: "docpipe"
      context_prefix: "数据线知识库文档"
    options:
      resume: true
      sync: true
```

- [ ] **Step 3: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
git add docpipe/cli.py docpipe.yaml tests/test_converters.py
git commit -m "feat: CLI 解析 type_rules 配置，更新 docpipe.yaml"
```

---

### Task 7: 手动验证

- [ ] **Step 1: 用配置文件跑 dingtalk pipeline**

```bash
python -m docpipe run --config docpipe.yaml --dry-run
```

Expected: 看到 `.tar.gz`、`.exe` 等文件被跳过（显示 "无处理规则"），支持的类型正常处理

- [ ] **Step 2: 用 local source 测试**

```bash
mkdir -p /tmp/test_docs
echo "# test" > /tmp/test_docs/test.md
python -m docpipe run --config docpipe.yaml --dry-run
```

Expected: 正常处理

- [ ] **Step 3: 清理测试文件**

```bash
rm -rf /tmp/test_docs
```
