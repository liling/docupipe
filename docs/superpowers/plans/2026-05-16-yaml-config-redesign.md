# YAML 配置重设计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 docpipe.yaml 配置结构 — 合并 source/destination 声明、引入 steps 管线、支持 ${ENV_VAR} 插值、移除 content_type_rules、过滤下沉到 source。

**Architecture:** 新建 `docpipe/config.py` 负责配置解析（env 插值 + 深度合并 + source/dest 解析）。新建 `docpipe/steps/` 模块实现 PipelineStep 抽象 + ConvertStep + ImageDescriptionStep。Pipeline 使用 steps 列表替代 ContentTypeStrategy。DingtalkSource 移除 image 处理、新增 include_types。

**Tech Stack:** Python 标准库（re, os, pathlib, abc, dataclasses）

---

### Task 1: ${ENV_VAR} 环境变量插值

**Files:**
- Create: `docpipe/config.py`
- Modify: `tests/test_docpipe.py`

- [ ] **Step 1: 编写 env 插值测试**

在 `tests/test_docpipe.py` 末尾添加：

```python
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
        assert result == {"api_url": "http://localhost", "nested": {"key": "http://localhost/path"}}}

    def test_resolve_in_list(self, monkeypatch):
        monkeypatch.setenv("KEY", "val")
        from docpipe.config import resolve_env_vars
        assert resolve_env_vars(["${KEY}", "plain"]) == ["val", "plain"]

    def test_resolve_non_string_unchanged(self):
        from docpipe.config import resolve_env_vars
        assert resolve_env_vars(42) == 42
        assert resolve_env_vars(True) is True
        assert resolve_env_vars(None) is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestEnvInterpolation -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'docpipe.config'`

- [ ] **Step 3: 创建 config.py 实现 resolve_env_vars**

创建 `docpipe/config.py`：

```python
from __future__ import annotations

import os
import re
from typing import Any

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def resolve_env_vars(value: Any) -> Any:
    """递归替换 ${ENV_VAR} 和 ${ENV_VAR:-default}"""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(_replace_env, value)
    if isinstance(value, dict):
        return {k: resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_env_vars(v) for v in value]
    return value


def _replace_env(match: re.Match) -> str:
    expr = match.group(1)
    if ":-" in expr:
        var, default = expr.split(":-", 1)
        return os.environ.get(var.strip(), default)
    val = os.environ.get(expr.strip())
    return val if val is not None else match.group(0)


def deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典，override 覆盖 base"""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def parse_component_config(pipeline_config: dict, global_config: dict, component_key: str) -> tuple[str, dict]:
    """解析 source 或 destination 配置，返回 (type_name, merged_config)"""
    comp = pipeline_config.get(component_key, {})
    if not comp:
        raise ValueError(f"缺少 {component_key} 配置")

    items = list(comp.items())
    if len(items) != 1:
        raise ValueError(f"{component_key} 必须只有一个 type，当前有: {list(comp.keys())}")

    type_name, config = items[0]
    config = dict(config) if config else {}

    # 与全局配置合并
    global_comp = global_config.get(type_name, {})
    if global_comp:
        config = deep_merge(global_comp, config)

    return type_name, config
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestEnvInterpolation -v`
Expected: 7 passed

- [ ] **Step 5: 提交**

```bash
git add docpipe/config.py tests/test_docpipe.py
git commit -m "feat: ${ENV_VAR} 环境变量插值 + deep_merge + parse_component_config"
```

---

### Task 2: Steps 系统 + ConvertStep

**Files:**
- Create: `docpipe/steps/__init__.py`
- Create: `docpipe/steps/base.py`
- Create: `docpipe/steps/convert.py`
- Modify: `tests/test_docpipe.py`

- [ ] **Step 1: 编写 steps 和 ConvertStep 测试**

在 `tests/test_docpipe.py` 末尾添加：

```python
class TestSteps:
    def test_convert_step_with_matching_extension(self, tmp_path):
        """extension 有映射时调用 converter"""
        from docpipe.steps.convert import ConvertStep
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF fake")
        doc = Document(
            meta=DocumentMeta(id="1", title="t", path="t.pdf", hash="", extra={"extension": "pdf", "_temp_file": str(test_file)}),
            content="",
            content_type="pdf",
        )
        step = ConvertStep(extension_rules={".pdf": "fake_converter"})
        # fake_converter 不存在，这里验证逻辑走到 converter 查找
        # 实际 converter 由 pipeline 调用，此处只测试 step 判断
        assert step.needs_conversion(doc)

    def test_convert_step_no_matching_extension(self):
        """extension 无映射时不转换"""
        from docpipe.steps.convert import ConvertStep
        doc = Document(
            meta=DocumentMeta(id="1", title="t", path="t.txt", hash="", extra={"extension": "txt"}),
            content="hello",
            content_type="txt",
        )
        step = ConvertStep(extension_rules={".pdf": "markitdown"})
        assert not step.needs_conversion(doc)

    def test_convert_step_source_rule_skips(self):
        """映射为 source 时不转换"""
        from docpipe.steps.convert import ConvertStep
        doc = Document(
            meta=DocumentMeta(id="1", title="t", path="t.md", hash="", extra={"extension": "md"}),
            content="hello",
            content_type="md",
        )
        step = ConvertStep(extension_rules={".md": "source"})
        assert not step.needs_conversion(doc)

    def test_deep_merge(self):
        from docpipe.config import deep_merge
        base = {"api_url": "http://default", "bank_id": "default_bank", "nested": {"a": 1, "b": 2}}
        override = {"bank_id": "my_bank", "nested": {"b": 3, "c": 4}}
        result = deep_merge(base, override)
        assert result == {"api_url": "http://default", "bank_id": "my_bank", "nested": {"a": 1, "b": 3, "c": 4}}

    def test_parse_component_config(self):
        from docpipe.config import parse_component_config
        global_config = {"hindsight": {"api_url": "http://default", "api_key": "secret"}}
        pipeline_config = {"destination": {"hindsight": {"bank_id": "my_bank"}}}
        type_name, config = parse_component_config(pipeline_config, global_config, "destination")
        assert type_name == "hindsight"
        assert config == {"api_url": "http://default", "api_key": "secret", "bank_id": "my_bank"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestSteps -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 创建 steps 模块**

创建 `docpipe/steps/__init__.py`：

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docpipe.steps.base import PipelineStep

STEPS: dict[str, type[PipelineStep]] = {}


def register_step(name: str):
    def decorator(cls: type[PipelineStep]):
        STEPS[name] = cls
        cls.name = name
        return cls
    return decorator


def get_step(name: str) -> type[PipelineStep]:
    if name not in STEPS:
        raise ValueError(f"未知的 step: {name}，可选: {', '.join(STEPS.keys())}")
    return STEPS[name]
```

创建 `docpipe/steps/base.py`：

```python
from __future__ import annotations

from abc import ABC, abstractmethod

from docpipe.models import Document


class PipelineStep(ABC):
    name: str = ""

    @abstractmethod
    def process(self, doc: Document) -> Document:
        """处理文档，返回处理后的文档"""
```

创建 `docpipe/steps/convert.py`：

```python
from __future__ import annotations

import logging
from pathlib import Path

from docpipe.converters import get_converter
from docpipe.models import Document
from docpipe.steps import register_step
from docpipe.steps.base import PipelineStep

logger = logging.getLogger(__name__)


@register_step("convert")
class ConvertStep(PipelineStep):
    def __init__(self, extension_rules: dict[str, str] | None = None, **kwargs):
        self._extension_rules = extension_rules or {}

    def needs_conversion(self, doc: Document) -> bool:
        ext = doc.meta.extra.get("extension", "")
        key = f".{ext}" if ext else ""
        rule = self._extension_rules.get(key)
        return rule is not None and rule != "source"

    def process(self, doc: Document) -> Document:
        ext = doc.meta.extra.get("extension", "")
        key = f".{ext}" if ext else ""
        converter_name = self._extension_rules.get(key)

        if not converter_name or converter_name == "source":
            return doc

        converter_cls = get_converter(converter_name)
        converter = converter_cls()

        file_path = doc.meta.extra.get("_temp_file")
        if not file_path:
            file_path = doc.meta.extra.get("absolute_path")
        if not file_path:
            logger.warning("convert step: 无文件路径，跳过转换: %s", doc.meta.title)
            return doc

        file_path = Path(file_path)
        try:
            doc.content = converter.convert(file_path)
            doc.content_type = "markdown"
        finally:
            # 清理临时文件
            if doc.meta.extra.get("_temp_file"):
                file_path.unlink(missing_ok=True)

        return doc
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestSteps -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add docpipe/steps/ tests/test_docpipe.py
git commit -m "feat: Steps 系统 + ConvertStep"
```

---

### Task 3: ImageDescriptionStep

**Files:**
- Create: `docpipe/steps/image_description.py`
- Modify: `tests/test_docpipe.py`

- [ ] **Step 1: 编写 ImageDescriptionStep 测试**

在 `tests/test_docpipe.py` 末尾添加：

```python
class TestImageDescriptionStep:
    def test_non_text_content_skipped(self):
        """非文本内容直接跳过"""
        from docpipe.steps.image_description import ImageDescriptionStep
        step = ImageDescriptionStep(api_key="k", base_url="http://x", model="m")
        doc = Document(
            meta=DocumentMeta(id="1", title="t", path="t.pdf", hash=""),
            content=b"binary data",
            content_type="pdf",
        )
        result = step.process(doc)
        assert result.content == b"binary data"

    def test_no_images_unchanged(self):
        """无图片的 markdown 不变"""
        from docpipe.steps.image_description import ImageDescriptionStep
        step = ImageDescriptionStep(api_key="k", base_url="http://x", model="m")
        doc = Document(
            meta=DocumentMeta(id="1", title="t", path="t.md", hash=""),
            content="# Hello\n\nNo images here.",
            content_type="markdown",
        )
        result = step.process(doc)
        assert result.content == "# Hello\n\nNo images here."
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestImageDescriptionStep -v`
Expected: FAIL

- [ ] **Step 3: 创建 ImageDescriptionStep**

创建 `docpipe/steps/image_description.py`：

```python
from __future__ import annotations

import logging

from docpipe.image import ImagePostProcessor, OpenAIVisionClient
from docpipe.models import Document
from docpipe.steps import register_step
from docpipe.steps.base import PipelineStep

logger = logging.getLogger(__name__)


@register_step("image_description")
class ImageDescriptionStep(PipelineStep):
    def __init__(self, api_key: str = "", base_url: str = "", model: str = "gpt-4o", **kwargs):
        vision_client = OpenAIVisionClient(api_key=api_key, base_url=base_url, model=model)
        self._processor = ImagePostProcessor(vision_client)

    def process(self, doc: Document) -> Document:
        if not isinstance(doc.content, str):
            return doc

        if "![" not in doc.content:
            return doc

        source_context = f"{doc.meta.title} - {doc.meta.path}"
        new_content, image_metadata = self._processor.process(doc.content, source_context)

        doc.content = new_content
        doc.meta.extra["image_metadata"] = image_metadata
        logger.info("图片处理完成: %s, 处理了 %d 张图片", doc.meta.title, len(image_metadata) if image_metadata else 0)

        return doc
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestImageDescriptionStep -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add docpipe/steps/image_description.py tests/test_docpipe.py
git commit -m "feat: ImageDescriptionStep 从 dingtalk source 抽取"
```

---

### Task 4: Pipeline 重构 — 移除 ContentTypeStrategy，增加 steps

**Files:**
- Modify: `docpipe/pipeline.py`
- Modify: `tests/test_docpipe.py`

这是最大的变更。将 pipeline.py 中的 ContentTypeStrategy 相关逻辑替换为 steps 执行。

- [ ] **Step 1: 重写 Pipeline.run 中的文档处理循环**

将 `docpipe/pipeline.py` 中的 `Pipeline` 类修改：

1. 构造函数增加 `steps` 参数：

```python
class Pipeline:
    def __init__(
        self,
        source: SourceBase,
        dest: DestinationBase,
        state_dir: Path,
        display: Display | None = None,
        steps: list | None = None,
        # 保留 type_resolver 和 content_type_strategy 用于 CLI 参数模式向后兼容
        type_resolver=None,
        content_type_strategy=None,
    ):
        self.source = source
        self.dest = dest
        self.state = StateManager(state_dir / f"{source.name}_{dest.name}_state.json")
        self._display = display or Display()
        self._steps = steps or []
        # 向后兼容：CLI 参数模式
        self._type_resolver = type_resolver
        self._content_type_strategy = content_type_strategy
```

2. 重写 `run()` 中 for 循环的核心逻辑（替换第 120-211 行），关键变化：
   - 移除 `_content_type_strategy` 和 `_resolve_type` 的复杂分支
   - 有 steps 时用 steps 处理，无 steps 时走旧逻辑（CLI 向后兼容）
   - 新逻辑：source fetch → 循环执行 steps → dest write

```python
        for doc_meta in docs:
            if sync and self.state.is_unchanged(doc_meta.id, doc_meta.hash):
                self._display.result("skip", f"{doc_meta.path} (无变化)")
                continue

            _display_path = doc_meta.path
            self._display.set_current(_display_path)
            try:
                doc = self.source.fetch(doc_meta)

                # Steps 模式
                if self._steps:
                    for step in self._steps:
                        doc = step.process(doc)
                elif self._type_resolver or self._content_type_strategy:
                    # 向后兼容：CLI 参数模式的旧逻辑
                    doc = self._process_with_legacy_rules(doc, doc_meta)
                    if doc is None:
                        continue

                if not doc.meta.hash:
                    doc.meta.hash = content_hash(doc.content)
                doc.meta.extra["_source"] = self.source.name

                if dry_run:
                    self._display.result("info", f"[dry-run] {_display_path}")
                else:
                    self.dest.write(doc)
                    self._display.result("success", _display_path)
                    self.state.mark_done(doc_meta.id, doc.meta.hash, doc_meta.path)
            except SkipDocument as e:
                logger.info("跳过文档: %s - %s", doc_meta.path, e)
                self._display.result("skip", f"{doc_meta.path} ({e})")
            except Exception as e:
                logger.error("文档处理失败: %s - %s", doc_meta.path, e)
                self._display.result("error", f"{doc_meta.path}: {e}")
                self._display.add_failure()
            finally:
                self._display.clear_current(_display_path)
```

3. 将旧的类型策略逻辑移到 `_process_with_legacy_rules` 方法（保持 CLI 参数模式工作）：

```python
    def _process_with_legacy_rules(self, doc: Document, doc_meta: DocumentMeta) -> Document | None:
        """CLI 参数模式的旧逻辑，返回 None 表示跳过"""
        if self._content_type_strategy:
            ct = doc_meta.extra.get("contentType", "")
            action = self._content_type_strategy.resolve(ct)
            if action is None or action == "skip":
                self._display.result("skip", f"{doc_meta.path} [contentType={ct or '未知'}]")
                return None
            if action == "convert" and self._type_resolver:
                ext_raw = doc_meta.extra.get("extension", "")
                extension = f".{ext_raw}" if ext_raw else ""
                mime_type = doc_meta.extra.get("contentType", "")
                converter_name = self._type_resolver.resolve(extension, mime_type)
                if converter_name is None or converter_name == "skip":
                    self._display.result("skip", f"{doc_meta.path} [无匹配 converter: {extension}]")
                    return None
                if converter_name != "source":
                    return self._run_converter(doc, converter_name)
        elif self._type_resolver:
            ext_raw = doc_meta.extra.get("extension", "")
            extension = f".{ext_raw}" if ext_raw else ""
            mime_type = doc_meta.extra.get("contentType", "")
            converter_name = self._type_resolver.resolve(extension, mime_type)
            if converter_name is None or converter_name == "skip":
                self._display.result("skip", f"{doc_meta.path} [无匹配 converter: {extension}]")
                return None
            if converter_name != "source":
                return self._run_converter(doc, converter_name)
        return doc

    def _run_converter(self, doc: Document, converter_name: str) -> Document:
        from docpipe.converters import get_converter
        converter_cls = get_converter(converter_name)
        converter = converter_cls()
        file_path = Path(doc.meta.extra.get("_temp_file", doc.meta.extra.get("absolute_path", "")))
        try:
            doc.content = converter.convert(file_path)
            doc.content_type = "markdown"
        finally:
            if doc.meta.extra.get("_temp_file"):
                file_path.unlink(missing_ok=True)
        return doc
```

- [ ] **Step 2: 运行全部测试**

Run: `python -m pytest tests/test_docpipe.py -v`
Expected: 全部 PASS（旧的 TestPipelineContentTypeStrategy 测试走 `_process_with_legacy_rules` 路径）

- [ ] **Step 3: 编写 steps 模式的 Pipeline 测试**

在 `tests/test_docpipe.py` 的 `TestPipeline` 类中添加：

```python
    def test_run_with_steps(self, tmp_path):
        """steps 模式下 pipeline 执行 steps"""
        docs = [_make_doc("1", "A", content="hello")]
        source = FakeSource(docs)
        dest = FakeDestination()

        from docpipe.steps.base import PipelineStep
        class UpperStep(PipelineStep):
            name = "upper"
            def process(self, doc):
                doc.content = doc.content.upper()
                return doc

        pipeline = Pipeline(source, dest, tmp_path, steps=[UpperStep()])
        pipeline.run()
        assert len(dest.written) == 1
        assert dest.written[0].content == "HELLO"

    def test_run_with_empty_steps_processes_all(self, tmp_path):
        """空 steps 列表等价于无处理"""
        docs = [_make_doc("1", "A")]
        source = FakeSource(docs)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, steps=[])
        pipeline.run()
        assert len(dest.written) == 1
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestPipeline -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add docpipe/pipeline.py tests/test_docpipe.py
git commit -m "refactor: Pipeline 支持 steps，旧逻辑保留为 CLI 向后兼容"
```

---

### Task 5: DingtalkSource — 移除 image 处理，新增 include_types

**Files:**
- Modify: `docpipe/sources/dingtalk.py`
- Modify: `tests/test_docpipe.py`（如有 dingtalk 相关测试）

- [ ] **Step 1: 修改 DingtalkSource**

修改 `docpipe/sources/dingtalk.py`：

1. 构造函数移除 `image_description` 相关代码（第 93-102 行），替换为 `include_types` 参数：

```python
    def __init__(self, space_id: str, folder_id: str | None = None, folders: list[str] | None = None,
                 include_types: list[str] | None = None, **kwargs):
        self._space_id = space_id
        self._folder_id = folder_id
        self._folders = folders
        self._include_types = set(include_types) if include_types else None
        self._client = _WikiClient()
        self._space_name = ""
        self._nodes_cache: list[dict] | None = None
```

2. `list_documents()` 中新增 include_types 过滤（在第 123 行 result=[] 之后的循环中）：

```python
            content_type = node.get("contentType", "")
            # include_types 过滤
            if self._include_types is not None and content_type not in self._include_types:
                continue
```

3. `fetch()` 中移除图片处理代码（第 183-188 行）：

删除：
```python
        if markdown and self._image_processor:
            source_context = f"{doc_meta.title} - {doc_meta.path}"
            logger.debug("处理文档中的图片: %s", doc_meta.title)
            markdown, image_metadata = self._image_processor.process(markdown, source_context)
            extra["image_metadata"] = image_metadata
            logger.info("图片处理完成: %s, 处理了 %d 张图片", doc_meta.title, len(image_metadata) if image_metadata else 0)
```

4. 移除文件顶部的 `import os`（第 95 行，已不需要）

- [ ] **Step 2: 运行全部测试**

Run: `python -m pytest tests/test_docpipe.py -v`
Expected: 全部 PASS

- [ ] **Step 3: 提交**

```bash
git add docpipe/sources/dingtalk.py
git commit -m "refactor: DingtalkSource 移除 image 处理，新增 include_types 过滤"
```

---

### Task 6: CLI 集成 — 新配置解析

**Files:**
- Modify: `docpipe/cli.py`

- [ ] **Step 1: 重写 `_run_from_config`**

将 `docpipe/cli.py` 的 `_run_from_config` 函数（第 102-157 行）替换为：

```python
def _run_from_config(ctx, config_path, pipeline_name, resume, sync_mode, dry_run):
    import yaml

    from docpipe.config import parse_component_config, resolve_env_vars
    from docpipe.display import Display
    from docpipe.pipeline import Pipeline
    from docpipe.destinations import get_destination
    from docpipe.sources import get_source
    from docpipe.steps import get_step

    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    config = resolve_env_vars(raw)

    # 全局配置 = 除 pipelines 外的所有顶层 key
    global_config = {k: v for k, v in config.items() if k != "pipelines"}

    # 全局 converters 配置
    converters_config = global_config.pop("converters", global_config.pop("type_rules", {}))
    extension_rules = converters_config.get("extensions", {})

    pipelines = config.get("pipelines", [])

    if pipeline_name:
        pipelines = [p for p in pipelines if p.get("name") == pipeline_name]
        if not pipelines:
            click.echo(f"未找到 pipeline: {pipeline_name}")
            raise SystemExit(1)

    for pipe_config in pipelines:
        # 解析 source
        source_name, source_kwargs = parse_component_config(pipe_config, global_config, "source")
        source = get_source(source_name)(**source_kwargs)

        # 解析 destination
        dest_name, dest_kwargs = parse_component_config(pipe_config, global_config, "destination")
        dest = get_destination(dest_name)(**dest_kwargs)

        # 解析 steps
        steps = []
        for step_spec in pipe_config.get("steps", []):
            if isinstance(step_spec, str):
                step_name = step_spec
                step_kwargs = {}
            else:
                items = list(step_spec.items())
                step_name, step_kwargs = items[0] if items else ("", {})

            # 与全局配置合并
            global_step_config = global_config.get(step_name, {})
            if global_step_config:
                from docpipe.config import deep_merge
                step_kwargs = deep_merge(global_step_config, step_kwargs)

            # ConvertStep 特殊处理：注入 extension_rules
            if step_name == "convert":
                step_kwargs["extension_rules"] = extension_rules

            step_cls = get_step(step_name)
            steps.append(step_cls(**step_kwargs))

        # 触发 step 模块的自动导入
        import docpipe.steps.convert  # noqa: F401
        import docpipe.steps.image_description  # noqa: F401

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
```

- [ ] **Step 2: 更新 `_extract_source_config`**

修改 `docpipe/cli.py` 的 `_extract_source_config`（第 160-175 行），为 dingtalk 增加 `include_types` 透传：

```python
def _extract_source_config(source_name, kwargs):
    config = {}
    if source_name == "dingtalk":
        if kwargs.get("space"):
            config["space_id"] = kwargs["space"]
        if kwargs.get("folder"):
            config["folder_id"] = kwargs["folder"]
    elif source_name in ("local", "localdrive"):
        if kwargs.get("input_dir"):
            config["input_dir"] = kwargs["input_dir"]
    return config
```

注意：CLI 参数模式下不再传 `image_description` 相关参数给 dingtalk source。

- [ ] **Step 3: 运行全部测试**

Run: `python -m pytest tests/test_docpipe.py -v`
Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
git add docpipe/cli.py
git commit -m "refactor: CLI 集成新配置解析（source/dest 合并 + env 插值 + steps）"
```

---

### Task 7: 改写 docpipe.yaml

**Files:**
- Modify: `docpipe.yaml`

- [ ] **Step 1: 改写配置文件为新的 YAML 结构**

用新格式重写 `docpipe.yaml`：

```yaml
hindsight:
  api_url: ${HINDSIGHT_API_URL}
  api_key: ${HINDSIGHT_API_KEY}
  bank_id: ${HINDSIGHT_BANK_ID}

image_description:
  api_key: ${IMAGE_API_KEY}
  base_url: ${IMAGE_BASE_URL}
  model: ${IMAGE_MODEL:-qwen3.5-flash}

converters:
  extensions:
    ".pdf": mineru
    ".docx": mineru
    ".pptx": mineru
    ".xlsx": mineru
    ".doc": mineru
    ".xls": mineru
    ".ppt": mineru

pipelines:

  - name: shujuxian-to-hindsight
    source:
      dingtalk:
        space_id: nb9XJB7qpnkxQXyA
        folders: ["产品规划物料/解决方案"]
        include_types: [DOCUMENT, ALIDOC]
    destination:
      hindsight:
        context_prefix: "数据线知识库文档"
    steps:
      - convert
      - image_description
    options:
      resume: true
      sync: true

  - name: shujuxian-to-local
    source:
      dingtalk:
        space_id: nb9XJB7qpnkxQXyA
        folders: ["产品规划物料/解决方案"]
        include_types: [DOCUMENT, ALIDOC]
    destination:
      localdrive:
        output_dir: ./output
    steps:
      - convert
      - image_description

  - name: local-to-hindsight
    source:
      localdrive:
        input_dir: ./output
        include: ["*.md"]
    destination:
      hindsight:
        context_prefix: "本地文档"
    steps:
      - convert
```

- [ ] **Step 2: 验证 YAML 配置可用**

Run: `python -m docpipe run --config docpipe.yaml --pipeline local-to-hindsight --dry-run`
Expected: 显示 pipeline 信息，dry-run 不写入文件

- [ ] **Step 3: 提交**

```bash
git add docpipe.yaml
git commit -m "refactor: docpipe.yaml 改写为新配置结构"
```

---

### Task 8: 端到端验证

**Files:**
- 无代码变更

- [ ] **Step 1: 验证 local-to-hindsight pipeline**

Run: `python -m docpipe run --config docpipe.yaml --pipeline local-to-hindsight --dry-run`
Expected: 扫描 output 目录 .md 文件，dry-run 显示处理信息

- [ ] **Step 2: 验证 CLI sources 列表**

Run: `python -m docpipe sources`
Expected: 输出 dingtalk 和 localdrive

- [ ] **Step 3: 运行全部测试**

Run: `python -m pytest tests/test_docpipe.py -v`
Expected: 全部 PASS
