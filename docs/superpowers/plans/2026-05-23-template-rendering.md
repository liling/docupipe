# 模板渲染系统重设计 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 Jinja2 沙箱模式替代自制的 `${context.field}` 正则替换，支持 per-file 变量解析和表达式能力。

**Architecture:** 新增 `render.py` 提供 `render_template(value, context)` 函数，Pipeline 不再统一解析模板，改为 Destination/Step 在内部按需渲染。`FileItem` 新增 `context` 字段支持 per-file 变量。

**Tech Stack:** Jinja2 SandboxedEnvironment + StrictUndefined

---

### Task 1: 添加 jinja2 依赖

**Files:**
- Modify: `pyproject.toml:23-36`

- [ ] **Step 1: 添加依赖**

在 `pyproject.toml` 的 `dependencies` 列表中添加 `jinja2`:

```toml
dependencies = [
    "click>=8.1.0",
    "markitdown[all]>=0.1.0",
    "hindsight-client>=0.1.0",
    "rich>=13.0.0",
    "python-dotenv>=1.0.0",
    "pyyaml>=6.0",
    "requests>=2.31.0",
    "openai>=1.0.0",
    "boto3>=1.28.0",
    "fastmcp>=2.0.0",
    "cryptography>=42.0.0",
    "openpyxl>=3.1.0",
    "python-pptx>=1.0.0",
    "jinja2>=3.1.0",
]
```

- [ ] **Step 2: 安装依赖**

Run: `cd /Users/liling/src/ai/docpipe && pip install -e ".[dev]"`

- [ ] **Step 3: 验证安装**

Run: `python -c "from jinja2.sandbox import SandboxedEnvironment; print('OK')"`
Expected: `OK`

---

### Task 2: 创建 render.py（TDD）

**Files:**
- Create: `docupipe/render.py`
- Create: `tests/test_render.py`

- [ ] **Step 1: 编写测试 `tests/test_render.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from docupipe.render import render_template


class TestSimpleVariable:
    def test_single_variable(self):
        assert render_template("hello {{ name }}", {"name": "world"}) == "hello world"

    def test_multiple_variables(self):
        assert render_template("{{ a }}/{{ b }}", {"a": "x", "b": "y"}) == "x/y"

    def test_unicode_value(self):
        assert render_template("/path/{{ space_name }}/file", {"space_name": "我的空间"}) == "/path/我的空间/file"


class TestStrictUndefined:
    def test_missing_variable_raises(self):
        with pytest.raises(Exception):
            render_template("{{ missing }}", {})

    def test_default_filter(self):
        assert render_template("{{ author | default('unknown') }}", {}) == "unknown"

    def test_default_filter_not_used_when_present(self):
        assert render_template("{{ author | default('unknown') }}", {"author": "张三"}) == "张三"


class TestFilters:
    def test_date_format_from_timestamp_ms(self):
        ts = datetime(2026, 3, 15, 10, 30, 0, tzinfo=timezone(timedelta(hours=8))).timestamp() * 1000
        result = render_template("{{ ts | date_format('%Y-%m') }}", {"ts": ts})
        assert result == "2026-03"

    def test_date_format_from_datetime(self):
        dt = datetime(2026, 5, 1)
        result = render_template("{{ dt | date_format('%Y/%m/%d') }}", {"dt": dt})
        assert result == "2026/05/01"

    def test_basename(self):
        assert render_template("{{ p | basename }}", {"p": "folder/sub/doc.md"}) == "doc.md"

    def test_extension(self):
        assert render_template("{{ f | extension }}", {"f": "report.pdf"}) == "pdf"

    def test_extension_no_dot(self):
        assert render_template("{{ f | extension }}", {"f": "README"}) == ""

    def test_replace(self):
        assert render_template("{{ title | replace(' ', '-') }}", {"title": "hello world"}) == "hello-world"


class TestRecursiveRendering:
    def test_dict_recursive(self):
        config = {"key": "{{ name }}", "nested": {"k2": "{{ name }}/path"}}
        result = render_template(config, {"name": "hello"})
        assert result == {"key": "hello", "nested": {"k2": "hello/path"}}

    def test_list_recursive(self):
        assert render_template(["{{ a }}", "plain"], {"a": "val"}) == ["val", "plain"]

    def test_non_string_passthrough(self):
        assert render_template(42, {}) == 42
        assert render_template(True, {}) is True
        assert render_template(None, {}) is None


class TestConditional:
    def test_if_true(self):
        tpl = "{% if type == 'doc' %}{{ title }}{% else %}{{ filename }}{% endif %}"
        assert render_template(tpl, {"type": "doc", "title": "My Doc", "filename": "f.md"}) == "My Doc"

    def test_if_false(self):
        tpl = "{% if type == 'doc' %}{{ title }}{% else %}{{ filename }}{% endif %}"
        assert render_template(tpl, {"type": "sheet", "title": "My Doc", "filename": "f.xlsx"}) == "f.xlsx"


class TestNoJinjaSyntax:
    def test_plain_string_unchanged(self):
        assert render_template("plain text", {}) == "plain text"

    def test_env_var_syntax_unchanged(self):
        assert render_template("${MY_VAR}", {}) == "${MY_VAR}"

    def test_mixed_env_and_jinja(self):
        assert render_template("${MY_VAR} {{ name }}", {"name": "x"}) == "${MY_VAR} x"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'docupipe.render'`

- [ ] **Step 3: 实现 `docupipe/render.py`**

```python
from __future__ import annotations

from datetime import date, datetime
from pathlib import PurePosixPath
from typing import Any

from jinja2 import BaseLoader, StrictUndefined
from jinja2.sandbox import SandboxedEnvironment


def _date_format(value: Any, fmt: str = "%Y-%m-%d") -> str:
    if isinstance(value, (int, float)):
        value = datetime.fromtimestamp(value / 1000)
    elif isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, (datetime, date)):
        return value.strftime(fmt)
    return str(value)


def _basename(value: Any) -> str:
    return PurePosixPath(str(value)).name


def _extension(value: Any) -> str:
    name = PurePosixPath(str(value)).name
    if "." in name:
        return name.rsplit(".", 1)[1]
    return ""


_env = SandboxedEnvironment(
    loader=BaseLoader(),
    undefined=StrictUndefined,
    autoescape=False,
)
_env.filters["date_format"] = _date_format
_env.filters["basename"] = _basename
_env.filters["extension"] = _extension


def render_template(value: Any, context: dict) -> Any:
    """使用 Jinja2 渲染模板字符串。对 dict/list 递归处理。"""
    if isinstance(value, str):
        tpl = _env.from_string(value)
        return tpl.render(**context)
    if isinstance(value, dict):
        return {k: render_template(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [render_template(v, context) for v in value]
    return value
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_render.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add docupipe/render.py tests/test_render.py
git commit -m "feat: 添加 Jinja2 沙箱模板渲染引擎"
```

---

### Task 3: FileItem 新增 context 字段

**Files:**
- Modify: `docupipe/models.py:46-51`

- [ ] **Step 1: 修改 FileItem dataclass**

在 `docupipe/models.py` 的 `FileItem` 中添加 `context` 字段：

```python
@dataclass
class FileItem:
    name: str
    content: str | bytes
    content_type: str = ""
    role: str = "main"
    context: dict = field(default_factory=dict)
```

- [ ] **Step 2: 验证现有测试仍然通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS（新增字段有默认值，向后兼容）

- [ ] **Step 3: 提交**

```bash
git add docupipe/models.py
git commit -m "feat: FileItem 新增 context 字段支持 per-file 变量"
```

---

### Task 4: 迁移 Pipeline 和 Destination 到新模板系统

这是核心迁移任务，需同时修改多个文件以确保系统一致。

**Files:**
- Modify: `docupipe/config.py` — 删除 `resolve_context_vars`、`_CONTEXT_PATTERN`，清理 `resolve_env_vars`
- Modify: `docupipe/pipeline.py` — 删除 `resolve_context_vars` 调用，移除 `dest_config`
- Modify: `docupipe/runner.py` — 移除 `dest_config` 传递
- Modify: `docupipe/destinations/base.py` — 更新 docstring
- Modify: `docupipe/destinations/localdrive.py` — 用 `render_template` 内部渲染
- Modify: `docupipe/destinations/hindsight.py` — 用 `render_template` 内部渲染

- [ ] **Step 1: 修改 `docupipe/config.py`**

删除 `_CONTEXT_PATTERN` 和 `resolve_context_vars`（第 49-69 行），以及 `resolve_env_vars` 中第 22-24 行的 `context.` 跳过逻辑。修改后完整文件：

```python
from __future__ import annotations

import copy
import logging
import os
import re
from pathlib import Path
from typing import Any

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


logger = logging.getLogger(__name__)


def resolve_env_vars(value: Any, variables: dict[str, str] | None = None) -> Any:
    """递归替换 ${VAR}，优先级：variables dict > 环境变量 > 默认值"""
    vars_dict = variables or {}

    def _replace(match: re.Match) -> str:
        expr = match.group(1)
        if ":-" in expr:
            var, default = expr.split(":-", 1)
            var = var.strip()
            if var in vars_dict:
                return vars_dict[var]
            return os.environ.get(var, default)
        var = expr.strip()
        if var in vars_dict:
            return vars_dict[var]
        val = os.environ.get(var)
        if val is None:
            logger.warning("环境变量未设置: '%s'，将保留原始值", var)
            return match.group(0)
        return val

    if isinstance(value, str):
        return _ENV_PATTERN.sub(_replace, value)
    if isinstance(value, dict):
        return {k: resolve_env_vars(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_env_vars(v, variables) for v in value]
    return value


def execute_variables_script(raw_config: dict) -> dict[str, str]:
    """执行配置中的 variables 脚本，返回变量字典。"""
    vars_block = raw_config.get("variables")
    if not vars_block:
        return {}

    script_file = vars_block.get("script_file")
    script_inline = vars_block.get("script")

    if script_file and script_inline:
        logging.getLogger(__name__).warning("variables 同时指定了 script 和 script_file，使用 script_file")

    if script_file:
        path = Path(script_file)
        if not path.is_file():
            raise FileNotFoundError(f"variables script_file 不存在: {script_file}")
        source = path.read_text(encoding="utf-8")
    elif script_inline:
        source = script_inline
    else:
        return {}

    func_lines = ["def _vars_func():"]
    for line in source.splitlines():
        func_lines.append("    " + line if line.strip() else "")
    func_source = "\n".join(func_lines)

    namespace: dict = {}
    exec(func_source, namespace)
    result = namespace["_vars_func"]()

    if not isinstance(result, dict):
        raise TypeError(f"variables 脚本必须返回 dict，实际返回了 {type(result).__name__}")

    variables: dict[str, str] = {}
    for k, v in result.items():
        if not isinstance(k, str):
            raise TypeError(f"variables 脚本返回的 key 必须是字符串，实际为 {type(k).__name__}: {k}")
        variables[k] = str(v)

    return variables


def deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典，override 覆盖 base，不修改 base"""
    result = copy.deepcopy(base)
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

    global_comp = global_config.get(type_name, {})
    if global_comp:
        config = deep_merge(global_comp, config)

    return type_name, config
```

- [ ] **Step 2: 修改 `docupipe/pipeline.py`**

1. 删除第 6 行 `from docupipe.config import resolve_context_vars` 导入
2. 从 `__init__` 参数中移除 `dest_config: dict | None = None`
3. 删除 `self._dest_config = dest_config`
4. 在 `_process_document` 中删除 `if self._dest_config:` 块（第 212-214 行）

`__init__` 修改后：

```python
def __init__(
    self,
    source: SourceBase,
    dest: DestinationBase,
    state_dir: Path,
    pipeline_name: str = "",
    display: Display | None = None,
    steps: list | None = None,
    post_steps: list | None = None,
    finalize_steps: list | None = None,
    state_file: str | None = None,
    mode: str = "full",
    change_detection: str | None = None,
    mirror_delete: bool = True,
):
    self.source = source
    self.dest = dest
    self._pipeline_name = pipeline_name
    if state_file:
        self.state = StateManager(state_dir / state_file)
    else:
        name = pipeline_name or f"{source.name}_{dest.name}"
        self.state = StateManager(state_dir / f"{name}_state.json")
    self._display = display or Display()
    self._steps = steps
    self._post_steps = post_steps or []
    self._finalize_steps = finalize_steps or []
    self._mode = mode
    self._change_detection = change_detection
    self._mirror_delete = mirror_delete
```

`_process_document` 中替换第 209-215 行（`if dry_run:` ... `self.dest.write(bundle)` 块）：

```python
if dry_run:
    self._display.result("info", f"[dry-run] {_display_path}")
else:
    self.dest.write(bundle)
    self._display.result("success", _display_path)
```

- [ ] **Step 3: 修改 `docupipe/runner.py`**

删除第 84 行的 `dest_config=dest_kwargs,` 参数。修改后 Pipeline 构造：

```python
pipeline = Pipeline(
    source, dest, state_dir,
    pipeline_name=pipe_name,
    display=Display(),
    steps=steps,
    post_steps=post_steps,
    finalize_steps=finalize_steps,
    state_file=pipe_config.get("state_file"),
    mode=effective_mode,
    change_detection=effective_cd,
    mirror_delete=options.get("mirror_delete", True),
)
```

- [ ] **Step 4: 修改 `docupipe/destinations/base.py`**

仅更新 `update_config` 的 docstring：

```python
def update_config(self, config: dict) -> None:
    """更新组件配置属性。只更新 _config_keys 中声明的字段。"""
    for key in self._config_keys:
        if key in config:
            setattr(self, f"_{key}", config[key])
```

- [ ] **Step 5: 修改 `docupipe/destinations/localdrive.py`**

1. 添加导入：`from docupipe.render import render_template`
2. 修改 `_resolve_path` 方法，用 `render_template` 渲染 `path_template`，并合并 file context：

```python
def _resolve_path(self, bundle: Bundle) -> Path:
    """从 Bundle context 解析输出路径"""
    context = dict(bundle.context)
    main_file = bundle.main
    if main_file and main_file.context:
        context.update(main_file.context)

    if self._path_template:
        rel_path = render_template(self._path_template, context)
    else:
        rel_path = context["path"]

    ext = ""
    ctx_ext = context.get("extension")
    if ctx_ext:
        ext = f".{ctx_ext}"
    elif bundle.main:
        ext = self._content_type_to_ext(bundle.main.content_type)
    if ext and not rel_path.endswith(ext):
        if self._replace_extension:
            stem = Path(rel_path).stem
            parent = str(Path(rel_path).parent)
            rel_path = f"{parent}/{stem}{ext}" if parent != "." else f"{stem}{ext}"
        else:
            rel_path = rel_path + ext

    return Path(self._output_dir) / rel_path
```

- [ ] **Step 6: 修改 `docupipe/destinations/hindsight.py`**

1. 添加导入：`from docupipe.render import render_template`
2. 修改 `_build_retain_item` 方法，添加 file context 合并和 `render_template` 调用：

```python
def _build_retain_item(self, bundle: Bundle, *, file_item: FileItem | None = None) -> dict:
    target_file = file_item or bundle.main
    if not target_file:
        raise ValueError("Bundle must have a main file")

    context = dict(bundle.context)
    if target_file.context:
        context.update(target_file.context)

    content = target_file.content if isinstance(target_file.content, str) else target_file.content.decode("utf-8")

    # 从 path 构建标签
    space_name = context.get("space_name", "")
    path_parts = Path(context["path"]).parts
    path_tags = [f"path:{part}" for part in path_parts[1:]] if len(path_parts) > 1 else []
    tags = ([f"space:{space_name}"] if space_name else []) + path_tags

    # 追加额外标签
    if self._extra_tags:
        tags.extend(render_template(self._extra_tags, context))

    # context
    if self._context_template:
        context_str = render_template(self._context_template, context)
    elif self._context_prefix:
        context_str = self._context_prefix
    else:
        folder_display = "/".join(path_parts[1:]) if len(path_parts) > 1 else ""
        if folder_display:
            context_str = f"文档：{context['title']}，来自 {space_name}/{folder_display}"
        elif space_name:
            context_str = f"文档：{context['title']}，来自 {space_name}"
        else:
            context_str = f"文档：{context['title']}"

    # timestamp
    update_time = context.get("mtime")
    if update_time:
        tz = timezone(timedelta(hours=8))
        dt = datetime.fromtimestamp(update_time / 1000, tz=tz)
        timestamp = dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    else:
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")

    # document_id
    if self._document_id_template:
        document_id = render_template(self._document_id_template, context)
    else:
        source_name = context.get("_source", "local")
        document_id = f"{source_name}:{context['id']}"
    if file_item is not None:
        document_id = f"{document_id}:{file_item.name}"

    item = {
        "content": content,
        "document_id": document_id,
        "timestamp": timestamp,
        "context": context_str,
        "tags": tags,
        "metadata": {
            **{k: str(v) if not isinstance(v, str) else v for k, v in context.items()},
            "content_type": context.get("dingtalk_content_type", ""),
            "relative_path": context["path"],
            "full_path": f"{context.get('space_name', '')}/{context['path']}" if context.get("space_name") else context["path"],
            "content_hash": context["hash"],
            "update_time": str(update_time) if update_time else "",
        },
    }

    if self._extra_metadata:
        item["metadata"].update(render_template(self._extra_metadata, context))

    return item
```

- [ ] **Step 7: 提交**

```bash
git add docupipe/config.py docupipe/pipeline.py docupipe/runner.py docupipe/destinations/base.py docupipe/destinations/localdrive.py docupipe/destinations/hindsight.py
git commit -m "refactor: 迁移到 Jinja2 模板渲染，移除 resolve_context_vars"
```

---

### Task 5: 更新测试文件

**Files:**
- Modify: `tests/test_config.py`
- Modify: `tests/test_hindsight.py`
- Modify: `tests/test_localdrive.py`

- [ ] **Step 1: 更新 `tests/test_config.py`**

1. 删除 `resolve_context_vars` 导入
2. 删除整个 `TestContextInterpolation` 类（第 71-125 行）
3. `TestUpdateConfig` 保持不变

修改后导入部分：

```python
from docupipe.config import (
    resolve_env_vars,
    execute_variables_script, deep_merge, parse_component_config,
)
```

- [ ] **Step 2: 更新 `tests/test_hindsight.py`**

1. 删除第 5 行 `from docupipe.config import resolve_context_vars`
2. 更新所有使用 `${context.xxx}` 语法的测试：

`test_template_document_id`：
```python
def test_template_document_id(self):
    dest = _make_dest(template="{{ space_name }}/{{ id }}")
    item = dest._build_retain_item(_make_bundle())
    assert item["document_id"] == "space1/doc1"
```

`test_context_template_overrides_prefix`：
```python
def test_context_template_overrides_prefix(self):
    dest = _make_dest(context_template="来自{{ space_name }}", context_prefix="产品知识库")
    item = dest._build_retain_item(_make_bundle())
    assert item["context"] == "来自space1"
```

`test_extra_tags_appended`：
```python
def test_extra_tags_appended(self):
    dest = _make_dest(extra_tags=["custom:{{ space_name }}", "env:prod"])
    item = dest._build_retain_item(_make_bundle())
    assert "space:space1" in item["tags"]
    assert "custom:space1" in item["tags"]
    assert "env:prod" in item["tags"]
```

`test_extra_metadata_merged`：
```python
def test_extra_metadata_merged(self):
    dest = _make_dest(extra_metadata={"author": "{{ author | default('unknown') }}", "version": "1.0"})
    item = dest._build_retain_item(_make_bundle(author="张三"))
    assert item["metadata"]["title"] == "测试"
    assert item["metadata"]["author"] == "张三"
    assert item["metadata"]["version"] == "1.0"
```

`test_extra_metadata_overwrites_existing`：
```python
def test_extra_metadata_overwrites_existing(self):
    dest = _make_dest(extra_metadata={"title": "自定义标题"})
    item = dest._build_retain_item(_make_bundle())
    assert item["metadata"]["title"] == "自定义标题"
```

`test_multi_file_with_template_appends_filename`：
```python
def test_multi_file_with_template_appends_filename(self):
    dest = _make_dest(template="{{ space_name }}/{{ id }}")
    bundle = _make_bundle()
    bundle.files.append(FileItem(name="t_Sheet2.md", content="sheet2 data", content_type="text/markdown", role="main"))
    item = dest._build_retain_item(bundle, file_item=bundle.files[1])
    assert item["document_id"] == "space1/doc1:t_Sheet2.md"
```

- [ ] **Step 3: 更新 `tests/test_localdrive.py`**

将 `test_path_template_with_context_filename_via_update_config`（第 288-298 行）替换为：

```python
def test_path_template_with_context_variable(self, tmp_path):
    dest = LocalDriveDestination(output_dir=str(tmp_path), path_template="{{ filename }}")
    bundle = Bundle(
        files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
        context={"id": "1", "title": "t", "path": "folder/doc", "filename": "doc", "extension": "md"},
    )
    path = dest._resolve_path(bundle)
    assert path == tmp_path / "doc.md"
```

- [ ] **Step 4: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add tests/test_config.py tests/test_hindsight.py tests/test_localdrive.py
git commit -m "test: 更新测试用例到 Jinja2 模板语法"
```

---

### Task 6: 更新 YAML 配置文件

**Files:**
- Modify: `docupipe.example.yaml`
- Modify: `examples/tencent-docs-to-obsidian.yaml`
- Modify: `examples/dingtalk-wiki-to-hindsight.yaml`

- [ ] **Step 1: 更新 `docupipe.example.yaml`**

将注释中的模板语法示例从 `${context.xxx}` 改为 `{{ xxx }}`：

```yaml
        # 可选高级配置（支持 {{ xxx }} Jinja2 模板）
        # document_id_template: "{{ space_name }}/{{ path }}"
        # context_template: "来自{{ space_name }}的{{ title }}"
        # extra_tags:
        #   - "custom:{{ space_name }}"
        # extra_metadata:
        #   author: "{{ author | default('unknown') }}"
```

- [ ] **Step 2: 更新 `examples/tencent-docs-to-obsidian.yaml`**

第 46 行：
```yaml
        path_template: "{{ filename }}"
```

- [ ] **Step 3: 更新 `examples/dingtalk-wiki-to-hindsight.yaml`**

第 73 行和第 116 行：
```yaml
        context_template: "{{ space_name }} {{ title }}"
```

- [ ] **Step 4: 提交**

```bash
git add docupipe.example.yaml examples/tencent-docs-to-obsidian.yaml examples/dingtalk-wiki-to-hindsight.yaml
git commit -m "docs: 更新配置文件模板语法到 Jinja2"
```

---

### Task 7: 更新 CLAUDE.md 文档

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: 更新 Bundle Context 约定部分**

将 `Destination 的配置支持 ${context.field} 插值，Pipeline 在 write 前自动调用 resolve_context_vars 解析` 改为：

```
Destination 的配置支持 `{{ field }}` Jinja2 模板语法，Destination 在 write 时用 `render_template` 解析。
内置过滤器：`date_format`、`basename`、`extension`。变量不存在时用 `| default('xxx')` 提供默认值。
```

- [ ] **Step 2: 提交**

```bash
git add CLAUDE.md
git commit -m "docs: 更新 CLAUDE.md 模板语法说明"
```
