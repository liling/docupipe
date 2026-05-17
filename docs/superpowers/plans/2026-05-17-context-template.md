# 运行时上下文模板系统实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在配置中支持 `${context.field}` 模板语法，引用 bundle 运行时上下文。Pipeline 在处理每个 bundle 时解析模板并注入到组件。

**Architecture:** 在 `config.py` 新增 `resolve_context_vars()` 函数处理 `${context.xxx}` 模板。在基类上新增 `update_config()` 方法。Pipeline 保存 destination 的模板配置，每次 write() 前解析注入。Localdrive 去掉硬编码 space_name 路径逻辑，新增 `path_template` 配置项。

**Tech Stack:** Python 3.11+ / pytest

---

### Task 1: 新增 `resolve_context_vars()` 函数

**Files:**
- Modify: `docupipe/config.py` — 新增 `_CONTEXT_PATTERN` 和 `resolve_context_vars()`
- Modify: `tests/test_docpipe.py` — 新增 `TestContextInterpolation` 测试类

- [ ] **Step 1: 写失败测试**

在 `tests/test_docpipe.py` 的 `TestEnvInterpolation` 类之后、`TestDeepMerge` 类之前，新增 `TestContextInterpolation` 类：

```python
class TestContextInterpolation:
    def test_simple_field(self):
        from docupipe.config import resolve_context_vars
        result = resolve_context_vars("hello ${context.name}", {"name": "world"})
        assert result == "hello world"

    def test_field_with_slash(self):
        from docupipe.config import resolve_context_vars
        result = resolve_context_vars("/path/${context.space_name}/file", {"space_name": "我的空间"})
        assert result == "/path/我的空间/file"

    def test_multiple_fields(self):
        from docupipe.config import resolve_context_vars
        result = resolve_context_vars("${context.a}/${context.b}", {"a": "x", "b": "y"})
        assert result == "x/y"

    def test_missing_field_keeps_original(self):
        from docupipe.config import resolve_context_vars
        result = resolve_context_vars("${context.missing}", {})
        assert result == "${context.missing}"

    def test_missing_field_with_default(self):
        from docupipe.config import resolve_context_vars
        result = resolve_context_vars("${context.missing:-fallback}", {})
        assert result == "fallback"

    def test_existing_field_overrides_default(self):
        from docupipe.config import resolve_context_vars
        result = resolve_context_vars("${context.name:-default}", {"name": "actual"})
        assert result == "actual"

    def test_none_value_keeps_original(self):
        from docupipe.config import resolve_context_vars
        result = resolve_context_vars("${context.val}", {"val": None})
        assert result == "${context.val}"

    def test_value_converted_to_string(self):
        from docupipe.config import resolve_context_vars
        result = resolve_context_vars("${context.num}", {"num": 42})
        assert result == "42"

    def test_dict_recursive(self):
        from docupipe.config import resolve_context_vars
        config = {"key": "${context.name}", "nested": {"k2": "${context.name}/path"}}
        result = resolve_context_vars(config, {"name": "hello"})
        assert result == {"key": "hello", "nested": {"k2": "hello/path"}}

    def test_list_recursive(self):
        from docupipe.config import resolve_context_vars
        result = resolve_context_vars(["${context.a}", "plain"], {"a": "val"})
        assert result == ["val", "plain"]

    def test_non_string_unchanged(self):
        from docupipe.config import resolve_context_vars
        assert resolve_context_vars(42, {}) == 42
        assert resolve_context_vars(True, {}) is True
        assert resolve_context_vars(None, {}) is None

    def test_no_context_template_unchanged(self):
        from docupipe.config import resolve_context_vars
        assert resolve_context_vars("plain text", {}) == "plain text"
        assert resolve_context_vars("${ENV_VAR}", {}) == "${ENV_VAR}"

    def test_env_var_not_touched(self):
        from docupipe.config import resolve_context_vars
        result = resolve_context_vars("${MY_VAR} ${context.name}", {"name": "x"})
        assert result == "${MY_VAR} x"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestContextInterpolation -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_context_vars'`

- [ ] **Step 3: 实现 `resolve_context_vars()`**

在 `docupipe/config.py` 中，在 `resolve_env_vars()` 函数之后（第 36 行后），新增：

```python
_CONTEXT_PATTERN = re.compile(r"\$\{context\.([^}]+)\}")


def resolve_context_vars(value: Any, context: dict) -> Any:
    """递归替换 ${context.field}，用 bundle context 的值填充。"""

    def _replace(match: re.Match) -> str:
        expr = match.group(1)
        if ":-" in expr:
            field, default = expr.split(":-", 1)
            return str(context.get(field.strip(), default))
        val = context.get(expr.strip())
        return str(val) if val is not None else match.group(0)

    if isinstance(value, str):
        return _CONTEXT_PATTERN.sub(_replace, value)
    if isinstance(value, dict):
        return {k: resolve_context_vars(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_context_vars(v, context) for v in value]
    return value
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestContextInterpolation -v`
Expected: 全部 PASS

- [ ] **Step 5: 运行全部测试确认无回归**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add docupipe/config.py tests/test_docpipe.py
git commit -m "feat: 新增 resolve_context_vars() 支持运行时上下文模板"
```

---

### Task 2: 基类新增 `update_config()` 方法

**Files:**
- Modify: `docupipe/destinations/base.py` — 新增 `update_config()` 方法
- Modify: `docupipe/steps/base.py` — 新增 `update_config()` 方法
- Modify: `tests/test_docpipe.py` — 新增测试

- [ ] **Step 1: 写失败测试**

在 `tests/test_docpipe.py` 的 `TestStepRegistry` 类之前，新增 `TestUpdateConfig` 类：

```python
class TestUpdateConfig:
    def test_destination_update_config(self):
        from docupipe.destinations.localdrive import LocalDriveDestination
        dest = LocalDriveDestination(output_dir="/old")
        dest.update_config({"output_dir": "/new"})
        assert str(dest._output_dir) == "/new"

    def test_update_config_skips_unknown_keys(self):
        from docupipe.destinations.localdrive import LocalDriveDestination
        dest = LocalDriveDestination(output_dir="/old")
        dest.update_config({"output_dir": "/new", "unknown_key": "value"})
        assert str(dest._output_dir) == "/new"
        assert not hasattr(dest, "_unknown_key")

    def test_update_config_no_attr_noop(self):
        from docupipe.destinations.localdrive import LocalDriveDestination
        dest = LocalDriveDestination(output_dir="/old")
        dest.update_config({"nonexistent": "value"})
        assert str(dest._output_dir) == "/old"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestUpdateConfig -v`
Expected: FAIL — `AttributeError: 'LocalDriveDestination' object has no attribute 'update_config'`

- [ ] **Step 3: 在 `DestinationBase` 新增 `update_config()`**

在 `docupipe/destinations/base.py` 的 `DestinationBase` 类中，`write` 方法之后新增：

```python
    def update_config(self, config: dict) -> None:
        """用已解析的配置更新组件属性。"""
        for key, value in config.items():
            attr = f"_{key}"
            if hasattr(self, attr):
                setattr(self, attr, value)
```

- [ ] **Step 4: 在 `StepBase` 新增同样的 `update_config()`**

在 `docupipe/steps/base.py` 的 `PipelineStep` 类中，`process` 方法之后新增同样的方法：

```python
    def update_config(self, config: dict) -> None:
        """用已解析的配置更新组件属性。"""
        for key, value in config.items():
            attr = f"_{key}"
            if hasattr(self, attr):
                setattr(self, attr, value)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestUpdateConfig -v`
Expected: 全部 PASS

- [ ] **Step 6: 运行全部测试确认无回归**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add docupipe/destinations/base.py docupipe/steps/base.py tests/test_docpipe.py
git commit -m "feat: DestinationBase/StepBase 新增 update_config() 方法"
```

---

### Task 3: Pipeline 集成 — 模板解析与注入

**Files:**
- Modify: `docupipe/pipeline.py` — 接收 dest_config，write 前解析注入，设置 filename
- Modify: `docupipe/cli.py` — 传递 dest_kwargs 给 Pipeline

- [ ] **Step 1: 改造 `Pipeline.__init__()`**

在 `docupipe/pipeline.py` 中，修改 `Pipeline.__init__()` 签名，新增 `dest_config` 参数。

将当前代码（第 83-95 行）：

```python
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
        self._steps = steps
```

替换为：

```python
class Pipeline:
    def __init__(
        self,
        source: SourceBase,
        dest: DestinationBase,
        state_dir: Path,
        display: Display | None = None,
        steps: list | None = None,
        dest_config: dict | None = None,
    ):
        self.source = source
        self.dest = dest
        self.state = StateManager(state_dir / f"{source.name}_{dest.name}_state.json")
        self._display = display or Display()
        self._steps = steps
        self._dest_config = dest_config
```

- [ ] **Step 2: 在 bundle 处理循环中添加 context 模板解析和 filename**

在 `docupipe/pipeline.py` 中：

a) 在文件顶部添加 import（第 8 行后）：

```python
from docupipe.config import resolve_context_vars
```

b) 在 bundle 处理循环中，设置通用上下文时增加 `filename`。将第 119-123 行：

```python
                # 设置 Bundle 的通用上下文字段
                bundle.context["id"] = meta.id
                bundle.context["title"] = meta.title
                bundle.context["path"] = meta.path
                bundle.context["_source"] = self.source.name
```

替换为：

```python
                # 设置 Bundle 的通用上下文字段
                bundle.context["id"] = meta.id
                bundle.context["title"] = meta.title
                bundle.context["path"] = meta.path
                bundle.context["filename"] = Path(meta.path).name if meta.path else ""
                bundle.context["_source"] = self.source.name
```

c) 在 `self.dest.write(bundle)` 之前（第 144 行前），插入模板解析：

```python
                if dry_run:
                    self._display.result("info", f"[dry-run] {_display_path}")
                else:
                    # 解析 destination 配置中的 ${context.xxx} 模板
                    if self._dest_config:
                        resolved = resolve_context_vars(self._dest_config, bundle.context)
                        self.dest.update_config(resolved)
                    self.dest.write(bundle)
```

- [ ] **Step 3: 在 CLI 中传递 dest_config**

在 `docupipe/cli.py` 中，修改 Pipeline 创建（第 100-102 行）：

将：
```python
            pipeline = Pipeline(source, dest, ctx.obj["state_dir"],
                                display=Display(), steps=steps)
```

替换为：
```python
            pipeline = Pipeline(source, dest, ctx.obj["state_dir"],
                                display=Display(), steps=steps,
                                dest_config=dest_kwargs)
```

注意：`dest_kwargs` 在第 77 行定义，包含 `${context.xxx}` 模板（启动时 `resolve_env_vars` 不处理 `context.` 前缀）。

- [ ] **Step 4: 运行全部测试确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add docupipe/pipeline.py docupipe/cli.py
git commit -m "feat: Pipeline 集成运行时上下文模板解析与注入"
```

---

### Task 4: Localdrive 改造 — 去掉硬编码路径，新增 path_template

**Files:**
- Modify: `docupipe/destinations/localdrive.py` — 新增 `path_template` 参数，简化 `_resolve_path()`
- Modify: `tests/test_docpipe.py` — 更新/新增测试

- [ ] **Step 1: 修改 `__init__` 新增 `path_template` 参数**

在 `docupipe/destinations/localdrive.py` 中，将第 13-16 行：

```python
    def __init__(self, output_dir: str, replace_extension: bool = False, save_sidecar: bool = True, **kwargs):
        self._output_dir = Path(output_dir)
        self._replace_extension = replace_extension
        self._save_sidecar = save_sidecar
```

替换为：

```python
    def __init__(self, output_dir: str, replace_extension: bool = False, save_sidecar: bool = True, path_template: str | None = None, **kwargs):
        self._output_dir = Path(output_dir)
        self._replace_extension = replace_extension
        self._save_sidecar = save_sidecar
        self._path_template = path_template
```

- [ ] **Step 2: 简化 `_resolve_path()` 去掉 space_name 硬编码**

将第 80-102 行的 `_resolve_path` 方法：

```python
    def _resolve_path(self, bundle: Bundle) -> Path:
        """从 Bundle context 解析输出路径"""
        context = bundle.context
        space_name = context.get("space_name", "")
        rel_path = context["path"]

        # 追加或替换扩展名
        main_file = bundle.main
        if main_file:
            ext = self._content_type_to_ext(main_file.content_type)
        else:
            ext = ""
        if ext and not rel_path.endswith(ext):
            if self._replace_extension:
                stem = Path(rel_path).stem
                parent = str(Path(rel_path).parent)
                rel_path = f"{parent}/{stem}{ext}" if parent != "." else f"{stem}{ext}"
            else:
                rel_path = rel_path + ext

        if space_name:
            return self._output_dir / space_name / rel_path
        return self._output_dir / rel_path
```

替换为：

```python
    def _resolve_path(self, bundle: Bundle) -> Path:
        """从 Bundle context 解析输出路径"""
        context = bundle.context
        rel_path = self._path_template or context["path"]

        # 追加或替换扩展名
        main_file = bundle.main
        if main_file:
            ext = self._content_type_to_ext(main_file.content_type)
        else:
            ext = ""
        if ext and not rel_path.endswith(ext):
            if self._replace_extension:
                stem = Path(rel_path).stem
                parent = str(Path(rel_path).parent)
                rel_path = f"{parent}/{stem}{ext}" if parent != "." else f"{stem}{ext}"
            else:
                rel_path = rel_path + ext

        return self._output_dir / rel_path
```

- [ ] **Step 3: 新增测试**

在 `tests/test_docpipe.py` 中 `TestUpdateConfig` 类之后新增 `TestLocalDrivePathTemplate` 类：

```python
class TestLocalDrivePathTemplate:
    def test_default_uses_context_path(self, tmp_path):
        from docupipe.destinations.localdrive import LocalDriveDestination
        dest = LocalDriveDestination(output_dir=str(tmp_path))
        bundle = Bundle(
            files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "t", "path": "folder/doc", "extension": "md"},
        )
        path = dest._resolve_path(bundle)
        assert path == tmp_path / "folder" / "doc.md"

    def test_path_template_overrides_context_path(self, tmp_path):
        from docupipe.destinations.localdrive import LocalDriveDestination
        dest = LocalDriveDestination(output_dir=str(tmp_path), path_template="custom/name")
        bundle = Bundle(
            files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "t", "path": "folder/doc", "extension": "md"},
        )
        path = dest._resolve_path(bundle)
        assert path == tmp_path / "custom" / "name.md"

    def test_no_space_name_prefix(self, tmp_path):
        from docupipe.destinations.localdrive import LocalDriveDestination
        dest = LocalDriveDestination(output_dir=str(tmp_path))
        bundle = Bundle(
            files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "t", "path": "doc", "extension": "md", "space_name": "我的空间"},
        )
        path = dest._resolve_path(bundle)
        assert path == tmp_path / "doc.md"
        assert "我的空间" not in str(path)

    def test_path_template_with_context_filename_via_update_config(self, tmp_path):
        from docupipe.destinations.localdrive import LocalDriveDestination
        dest = LocalDriveDestination(output_dir=str(tmp_path), path_template="${context.filename}")
        bundle = Bundle(
            files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "t", "path": "folder/doc", "filename": "doc", "extension": "md"},
        )
        # 模拟 pipeline 的 update_config
        from docupipe.config import resolve_context_vars
        resolved = resolve_context_vars({"path_template": dest._path_template}, bundle.context)
        dest.update_config(resolved)
        path = dest._resolve_path(bundle)
        assert path == tmp_path / "doc.md"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestLocalDrivePathTemplate -v`
Expected: 全部 PASS

- [ ] **Step 5: 运行全部测试确认无回归**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add docupipe/destinations/localdrive.py tests/test_docpipe.py
git commit -m "feat: localdrive 去掉 space_name 硬编码，新增 path_template"
```

---

### Task 5: 更新示例配置

**Files:**
- Modify: `examples/tencent-docs-to-obsidian.yaml`

- [ ] **Step 1: 更新示例配置**

将 `examples/tencent-docs-to-obsidian.yaml` 的 destination 部分改为：

```yaml
    destination:
      localdrive:
        output_dir: output/obsidian-vault/公众号文章/${year}/${month}
        path_template: ${context.filename}
        replace_extension: true
        save_sidecar: false
```

- [ ] **Step 2: 端到端验证**

```bash
cat > /tmp/test_context.yaml << 'EOF'
variables:
  script: |
    from datetime import date
    today = date.today()
    return {"year": str(today.year), "month": f"{today.month:02d}"}

pipelines:
  - name: test
    source:
      tencent:
        space_name: "个人空间"
        folders: ["微信公众号文章"]
        fetch_mode: markdown
    destination:
      localdrive:
        output_dir: /tmp/test_output/${context.space_name}/${year}/${month}
        path_template: ${context.filename}
        replace_extension: true
        save_sidecar: false
    steps: []
EOF
python -m docupipe run --config /tmp/test_context.yaml --dry-run 2>&1 | head -10
```

Expected: 不报错（dry-run 模式，或者因缺少 token 报错但不是模板/配置错误）。

- [ ] **Step 3: 提交**

```bash
git add examples/tencent-docs-to-obsidian.yaml
git commit -m "feat: 示例配置使用 context 模板和 path_template"
```
