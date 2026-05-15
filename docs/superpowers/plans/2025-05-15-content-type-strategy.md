# ContentTypeStrategy 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现两级文档类型策略：ContentTypeStrategy (contentType → action) + TypeRuleResolver (extension → converter)，将钉钉文档类型决策绑定到 pipeline 配置上。

**Architecture:** Pipeline 层新增 ContentTypeStrategy，先根据钉钉 contentType（DOCUMENT/ALIDOC/ARCHIVE/IMAGE/OTHER）决定处理动作（convert/skip/source/download），convert 动作再由 TypeRuleResolver 根据扩展名选择 converter。DingtalkSource 移除硬编码过滤列表，ALIDOC 子类型处理整合到 fetch 内部。

**Tech Stack:** Python 3.11+, pytest, Click, PyYAML

---

### Task 1: ContentTypeStrategy 类及测试

**Files:**
- Modify: `docpipe/pipeline.py` (在 `StateManager` 类之后、`content_hash` 函数之前添加)
- Modify: `tests/test_docpipe.py` (添加 `TestContentTypeStrategy` 类)

- [ ] **Step 1: 写测试**

在 `tests/test_docpipe.py` 中，`TestContentHash` 类之后、`TestPipeline` 类之前添加：

```python
class TestContentTypeStrategy:
    def test_resolve_known_type(self):
        from docpipe.pipeline import ContentTypeStrategy
        strategy = ContentTypeStrategy({"DOCUMENT": "convert", "ALIDOC": "source"})
        assert strategy.resolve("DOCUMENT") == "convert"
        assert strategy.resolve("ALIDOC") == "source"

    def test_resolve_unknown_returns_none(self):
        from docpipe.pipeline import ContentTypeStrategy
        strategy = ContentTypeStrategy({"DOCUMENT": "convert"})
        assert strategy.resolve("UNKNOWN") is None

    def test_empty_rules(self):
        from docpipe.pipeline import ContentTypeStrategy
        strategy = ContentTypeStrategy()
        assert strategy.resolve("DOCUMENT") is None

    def test_all_actions(self):
        from docpipe.pipeline import ContentTypeStrategy
        strategy = ContentTypeStrategy({
            "DOCUMENT": "convert",
            "ALIDOC": "source",
            "ARCHIVE": "skip",
            "IMAGE": "download",
        })
        assert strategy.resolve("DOCUMENT") == "convert"
        assert strategy.resolve("ALIDOC") == "source"
        assert strategy.resolve("ARCHIVE") == "skip"
        assert strategy.resolve("IMAGE") == "download"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestContentTypeStrategy -v`
Expected: FAIL (ImportError: cannot import name 'ContentTypeStrategy')

- [ ] **Step 3: 实现 ContentTypeStrategy**

在 `docpipe/pipeline.py` 第 55 行（`StateManager` 类结束之后、`content_hash` 函数之前）添加：

```python
class ContentTypeStrategy:
    """钉钉 contentType 到处理动作的映射"""

    def __init__(self, rules: dict[str, str] | None = None):
        self._rules = rules or {}

    def resolve(self, content_type: str) -> str | None:
        return self._rules.get(content_type)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestContentTypeStrategy -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add docpipe/pipeline.py tests/test_docpipe.py
git commit -m "feat: 添加 ContentTypeStrategy 类及测试"
```

---

### Task 2: Pipeline 两级类型解析

**Files:**
- Modify: `docpipe/pipeline.py:63-76` (Pipeline.__init__)
- Modify: `docpipe/pipeline.py:100-115` (Pipeline.run 类型过滤逻辑)
- Modify: `tests/test_docpipe.py` (添加 TestPipelineContentTypeStrategy 类)

- [ ] **Step 1: 写测试**

在 `tests/test_docpipe.py` 中，`TestPipeline` 类之后、`TestRegistration` 类之前添加。需要在文件顶部 import 中添加 `ContentTypeStrategy`：

```python
from docpipe.pipeline import Pipeline, StateManager, content_hash, ContentTypeStrategy
```

测试类：

```python
class TestPipelineContentTypeStrategy:
    def test_skip_archives(self, tmp_path):
        """ContentTypeStrategy 返回 skip 时跳过"""
        docs = [_make_doc("1", "A", contentType="ARCHIVE")]
        source = FakeSource(docs)
        dest = FakeDestination()
        strategy = ContentTypeStrategy({"ARCHIVE": "skip", "DOCUMENT": "convert"})
        pipeline = Pipeline(source, dest, tmp_path, content_type_strategy=strategy)
        pipeline.run()
        assert len(dest.written) == 0

    def test_no_rule_skips(self, tmp_path):
        """ContentTypeStrategy 无规则时跳过"""
        docs = [_make_doc("1", "A", contentType="OTHER")]
        source = FakeSource(docs)
        dest = FakeDestination()
        strategy = ContentTypeStrategy({"DOCUMENT": "convert"})
        pipeline = Pipeline(source, dest, tmp_path, content_type_strategy=strategy)
        pipeline.run()
        assert len(dest.written) == 0

    def test_source_action_processes(self, tmp_path):
        """ContentTypeStrategy 返回 source 时走 Source 原生处理"""
        docs = [_make_doc("1", "A", contentType="ALIDOC")]
        source = FakeSource(docs)
        dest = FakeDestination()
        strategy = ContentTypeStrategy({"ALIDOC": "source"})
        pipeline = Pipeline(source, dest, tmp_path, content_type_strategy=strategy)
        pipeline.run()
        assert len(dest.written) == 1

    def test_convert_with_resolver(self, tmp_path):
        """convert 动作委托给 TypeRuleResolver 二次分发"""
        docs = [_make_doc("1", "A", contentType="DOCUMENT", extension="pdf")]
        source = FakeSource(docs)
        dest = FakeDestination()
        strategy = ContentTypeStrategy({"DOCUMENT": "convert"})
        resolver = TypeRuleResolver(extension_rules={".pdf": "markitdown"})
        pipeline = Pipeline(source, dest, tmp_path,
                            content_type_strategy=strategy, type_resolver=resolver)
        pipeline.run()
        assert len(dest.written) == 1

    def test_convert_no_converter_skips(self, tmp_path):
        """convert 但无匹配 converter 时跳过"""
        docs = [_make_doc("1", "A", contentType="DOCUMENT", extension="exe")]
        source = FakeSource(docs)
        dest = FakeDestination()
        strategy = ContentTypeStrategy({"DOCUMENT": "convert"})
        resolver = TypeRuleResolver(extension_rules={".pdf": "markitdown"})
        pipeline = Pipeline(source, dest, tmp_path,
                            content_type_strategy=strategy, type_resolver=resolver)
        pipeline.run()
        assert len(dest.written) == 0

    def test_convert_without_resolver_processes(self, tmp_path):
        """convert 但无 resolver 时仍处理（不转换）"""
        docs = [_make_doc("1", "A", contentType="DOCUMENT")]
        source = FakeSource(docs)
        dest = FakeDestination()
        strategy = ContentTypeStrategy({"DOCUMENT": "convert"})
        pipeline = Pipeline(source, dest, tmp_path, content_type_strategy=strategy)
        pipeline.run()
        assert len(dest.written) == 1

    def test_download_action_processes(self, tmp_path):
        """download 动作正常处理"""
        docs = [_make_doc("1", "A", contentType="IMAGE")]
        source = FakeSource(docs)
        dest = FakeDestination()
        strategy = ContentTypeStrategy({"IMAGE": "download"})
        pipeline = Pipeline(source, dest, tmp_path, content_type_strategy=strategy)
        pipeline.run()
        assert len(dest.written) == 1

    def test_no_strategy_uses_old_resolver(self, tmp_path):
        """无 ContentTypeStrategy 时走原有 TypeRuleResolver 逻辑（向后兼容）"""
        docs = [_make_doc("1", "A", extension="pdf")]
        source = FakeSource(docs)
        dest = FakeDestination()
        resolver = TypeRuleResolver(extension_rules={".pdf": "markitdown"})
        pipeline = Pipeline(source, dest, tmp_path, type_resolver=resolver)
        pipeline.run()
        assert len(dest.written) == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestPipelineContentTypeStrategy -v`
Expected: FAIL (Pipeline 不接受 content_type_strategy 参数)

- [ ] **Step 3: 修改 Pipeline.__init__ 添加 content_type_strategy 参数**

修改 `docpipe/pipeline.py` 中 `Pipeline.__init__`（第 63-76 行）：

```python
class Pipeline:
    def __init__(
        self,
        source: SourceBase,
        dest: DestinationBase,
        state_dir: Path,
        display: Display | None = None,
        type_resolver=None,
        content_type_strategy: ContentTypeStrategy | None = None,
    ):
        self.source = source
        self.dest = dest
        self.state = StateManager(state_dir / f"{source.name}_{dest.name}_state.json")
        self._display = display or Display()
        self._type_resolver = type_resolver
        self._content_type_strategy = content_type_strategy
```

- [ ] **Step 4: 修改 Pipeline.run() 两级类型解析逻辑**

替换 `docpipe/pipeline.py` 第 100-115 行（类型规则过滤部分）为：

```python
            # 类型策略过滤
            if self._content_type_strategy:
                # 第一级：ContentTypeStrategy
                content_type = doc_meta.extra.get("contentType", "")
                action = self._content_type_strategy.resolve(content_type)
                if action is None or action == "skip":
                    ct_label = content_type or "未知类型"
                    self._display.result("skip", f"{doc_meta.path} [contentType={ct_label}, action={action or '无规则'}]")
                    continue
                if action in ("source", "download"):
                    converter_name = None
                elif action == "convert":
                    # 第二级：TypeRuleResolver（仅 convert 动作）
                    if self._type_resolver:
                        converter_name = self._resolve_type(doc_meta)
                        ext_info = doc_meta.extra.get("extension", "") or ""
                        ext_label = f".{ext_info}" if ext_info else "未知扩展名"
                        if converter_name is None:
                            self._display.result("skip", f"{doc_meta.path} [contentType={content_type}, 无匹配 converter: {ext_label}]")
                            continue
                        if converter_name == "skip":
                            self._display.result("skip", f"{doc_meta.path} [contentType={content_type}, converter 跳过: {ext_label}]")
                            continue
                        if converter_name == "source":
                            converter_name = None
                    else:
                        converter_name = None
            elif self._type_resolver:
                # 向后兼容：无 ContentTypeStrategy 时走原有逻辑
                converter_name = self._resolve_type(doc_meta)
                ext_info = doc_meta.extra.get("extension", "") or ""
                type_info = doc_meta.extra.get("contentType", "") or ""
                type_label = f".{ext_info}" if ext_info else type_info or "未知类型"
                if converter_name is None:
                    self._display.result("skip", f"{doc_meta.path} [无处理规则: {type_label}]")
                    continue
                if converter_name == "skip":
                    self._display.result("skip", f"{doc_meta.path} [跳过: {type_label}]")
                    continue
                if converter_name == "source":
                    converter_name = None
            else:
                converter_name = None
```

- [ ] **Step 5: 运行全部 Pipeline 相关测试**

Run: `python -m pytest tests/test_docpipe.py::TestPipelineContentTypeStrategy tests/test_docpipe.py::TestPipeline tests/test_docpipe.py::TestPipelineTypeRules -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add docpipe/pipeline.py tests/test_docpipe.py
git commit -m "feat: Pipeline 支持两级类型解析（ContentTypeStrategy + TypeRuleResolver）"
```

---

### Task 3: DingtalkSource ALIDOC handler 清理

**Files:**
- Modify: `docpipe/sources/dingtalk.py:100-133` (list_documents 移除硬编码过滤)
- Modify: `docpipe/sources/dingtalk.py:136-165` (fetch 中 ALIDOC handler 常量提升)

- [ ] **Step 1: 移除 list_documents 中的硬编码过滤**

替换 `docpipe/sources/dingtalk.py` 第 110 行：

```python
        _UNSUPPORTED_EXTENSIONS = {"axls", "amindmap", "aform", "abitable", "able"}
```

以及第 116-118 行：

```python
            if extension in _UNSUPPORTED_EXTENSIONS:
                logger.debug("跳过不支持的钉钉类型: %s (extension=%s)", node.get("name", ""), extension)
                continue
```

删除这三行。`list_documents` 不再过滤 ALIDOC 子类型，改由 Pipeline 的 ContentTypeStrategy 和 fetch 内的 ALIDOC handler 处理。

- [ ] **Step 2: 将 fetch 中的 ALIDOC 子类型常量提升为模块级**

在 `docpipe/sources/dingtalk.py` 文件顶部（`logger` 定义之后，`_WikiClient` 类之前）添加：

```python
_ALIDOC_UNSUPPORTED = frozenset({"axls", "amindmap", "aform", "abitable", "able"})
```

然后替换 `fetch` 方法中第 153-156 行：

```python
            _UNSUPPORTED = {"axls", "amindmap", "aform", "abitable", "able"}
            if extension in _UNSUPPORTED:
                from docpipe.models import SkipDocument
                raise SkipDocument(f"不支持的钉钉类型: extension={extension}")
```

为：

```python
            if extension in _ALIDOC_UNSUPPORTED:
                raise SkipDocument(f"ALIDOC 子类型暂不支持: extension={extension}")
```

（`SkipDocument` 已在文件顶部通过 `from docpipe.models import Document, DocumentMeta` 间接可用——需要确认 import。当前文件第 11 行已有 `from docpipe.models import Document, DocumentMeta`，需添加 `SkipDocument`。）

同时修改第 11 行的 import：

```python
from docpipe.models import Document, DocumentMeta, SkipDocument
```

- [ ] **Step 3: 运行全部测试确认无回归**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
git add docpipe/sources/dingtalk.py
git commit -m "refactor: DingtalkSource 移除硬编码过滤，ALIDOC 子类型处理统一到 handler"
```

---

### Task 4: CLI 配置解析更新

**Files:**
- Modify: `docpipe/cli.py:102-150` (_run_from_config 函数)

- [ ] **Step 1: 修改 _run_from_config 支持 content_type_rules 和 converters**

替换 `docpipe/cli.py` 中的 `_run_from_config` 函数（第 102-150 行）为：

```python
def _run_from_config(ctx, config_path, pipeline_name, resume, sync_mode, dry_run):
    import yaml

    from docpipe.converters.resolver import TypeRuleResolver
    from docpipe.destinations import get_destination
    from docpipe.display import Display
    from docpipe.pipeline import ContentTypeStrategy, Pipeline
    from docpipe.sources import get_source

    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))

    # 兼容旧配置：converters 优先，fallback 到 type_rules
    converters = config.get("converters", config.get("type_rules", {}))
    resolver = TypeRuleResolver(
        extension_rules=converters.get("extensions", {}),
        mime_rules=converters.get("mime_types", {}),
    )

    pipelines = config.get("pipelines", [])

    if pipeline_name:
        pipelines = [p for p in pipelines if p.get("name") == pipeline_name]
        if not pipelines:
            click.echo(f"未找到 pipeline: {pipeline_name}")
            raise SystemExit(1)

    for pipe_config in pipelines:
        # content_type_rules: pipeline 级别优先，fallback 到全局
        ct_rules = pipe_config.get("content_type_rules", config.get("content_type_rules"))
        strategy = ContentTypeStrategy(ct_rules) if ct_rules else None

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
                                display=Display(),
                                type_resolver=resolver,
                                content_type_strategy=strategy)
            pipeline.run(
                resume=resume or options.get("resume", False),
                sync=sync_mode or options.get("sync", False),
                dry_run=dry_run,
            )
        finally:
            if hasattr(dest, "close"):
                dest.close()
```

- [ ] **Step 2: 更新 docpipe.yaml 配置文件**

替换 `docpipe.yaml` 为新格式：

```yaml
content_type_rules:
  DOCUMENT: convert
  ALIDOC: source
  ARCHIVE: skip
  IMAGE: skip
  OTHER: skip

converters:
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

- [ ] **Step 3: 运行全部测试确认无回归**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 4: 验证 CLI 帮助正常**

Run: `python -m docpipe run --help`
Expected: 正常显示帮助信息

- [ ] **Step 5: 提交**

```bash
git add docpipe/cli.py docpipe.yaml
git commit -m "feat: CLI 支持 content_type_rules 和 converters 配置解析"
```

---

### Task 5: 端到端验证

- [ ] **Step 1: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS，包括新增的 TestContentTypeStrategy 和 TestPipelineContentTypeStrategy

- [ ] **Step 2: 验证向后兼容**

用旧格式配置（`type_rules` + `mime_types`）仍能正常运行。确认 `converters` 和 `type_rules` 两种配置键名都能被识别。

Run: `python -m docpipe run --config docpipe.yaml --pipeline shujuxian-to-hindsight --dry-run`
Expected: 正常运行，dry-run 模式输出文档列表

- [ ] **Step 3: 最终提交**

```bash
git add -A
git commit -m "feat: ContentTypeStrategy 两级文档类型策略实现完成"
```
