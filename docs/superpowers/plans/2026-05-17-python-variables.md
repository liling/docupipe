# Python 变量系统实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 YAML 配置中新增 `variables` 块，支持通过 Python 脚本动态定义变量，用于配置插值 `${var_name}`，优先级高于环境变量。

**Architecture:** 在 `config.py` 中新增 `execute_variables_script()` 函数执行 Python 脚本获取变量字典，改造 `resolve_env_vars()` 接受可选的 variables dict 参数（Python 变量优先于环境变量）。在 `cli.py` 启动流程中插入脚本执行步骤。

**Tech Stack:** Python 3.11+ / pytest

---

### Task 1: 新增 `execute_variables_script()` 函数

**Files:**
- Modify: `docupipe/config.py:1-28`
- Modify: `tests/test_docpipe.py:593`（在 `TestEnvInterpolation` 类之后新增测试类）

- [ ] **Step 1: 写失败测试 — 内嵌脚本返回 dict**

在 `tests/test_docpipe.py` 的 `TestEnvInterpolation` 类之后、`TestDeepMerge` 类之前，新增 `TestExecuteVariablesScript` 类：

```python
class TestExecuteVariablesScript:
    def test_inline_script_returns_dict(self):
        from docupipe.config import execute_variables_script
        raw = {"variables": {"script": "return {'today': '2026-01-01'}"}}
        result = execute_variables_script(raw)
        assert result == {"today": "2026-01-01"}

    def test_inline_script_with_import(self):
        import datetime
        from docupipe.config import execute_variables_script
        raw = {"variables": {"script": "import datetime\nreturn {'day': datetime.date(2026, 1, 1).isoformat()}"}}
        result = execute_variables_script(raw)
        assert result == {"day": "2026-01-01"}

    def test_script_file_reads_external_file(self, tmp_path):
        from docupipe.config import execute_variables_script
        script = tmp_path / "vars.py"
        script.write_text("return {'key': 'from_file'}\n", encoding="utf-8")
        raw = {"variables": {"script_file": str(script)}}
        result = execute_variables_script(raw)
        assert result == {"key": "from_file"}

    def test_script_file_not_found_raises(self):
        from docupipe.config import execute_variables_script
        raw = {"variables": {"script_file": "/nonexistent/vars.py"}}
        with pytest.raises(FileNotFoundError, match="script_file"):
            execute_variables_script(raw)

    def test_returns_non_dict_raises(self):
        from docupipe.config import execute_variables_script
        raw = {"variables": {"script": "return 'not a dict'"}}
        with pytest.raises(TypeError, match="dict"):
            execute_variables_script(raw)

    def test_non_string_key_raises(self):
        from docupipe.config import execute_variables_script
        raw = {"variables": {"script": "return {1: 'value'}"}}
        with pytest.raises(TypeError, match="key.*字符串"):
            execute_variables_script(raw)

    def test_value_converted_to_string(self):
        from docupipe.config import execute_variables_script
        raw = {"variables": {"script": "return {'num': 42, 'flag': True}"}}
        result = execute_variables_script(raw)
        assert result == {"num": "42", "flag": "True"}

    def test_empty_dict_returns_empty(self):
        from docupipe.config import execute_variables_script
        raw = {"variables": {"script": "return {}"}}
        result = execute_variables_script(raw)
        assert result == {}

    def test_no_variables_block_returns_empty(self):
        from docupipe.config import execute_variables_script
        assert execute_variables_script({}) == {}
        assert execute_variables_script({"pipelines": []}) == {}

    def test_no_script_or_file_returns_empty(self):
        from docupipe.config import execute_variables_script
        raw = {"variables": {}}
        assert execute_variables_script(raw) == {}

    def test_both_script_and_file_prefers_file(self, tmp_path):
        from docupipe.config import execute_variables_script
        script = tmp_path / "vars.py"
        script.write_text("return {'source': 'file'}\n", encoding="utf-8")
        raw = {"variables": {"script": "return {'source': 'inline'}", "script_file": str(script)}}
        result = execute_variables_script(raw)
        assert result == {"source": "file"}

    def test_script_exception_propagates(self):
        from docupipe.config import execute_variables_script
        raw = {"variables": {"script": "raise ValueError('boom')"}}
        with pytest.raises(ValueError, match="boom"):
            execute_variables_script(raw)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestExecuteVariablesScript -v`
Expected: FAIL — `ImportError: cannot import name 'execute_variables_script'`

- [ ] **Step 3: 实现 `execute_variables_script()`**

在 `docupipe/config.py` 中，在 `_replace_env` 函数之后（第 28 行后），新增：

```python
def execute_variables_script(raw_config: dict) -> dict[str, str]:
    """执行配置中的 variables 脚本，返回变量字典。"""
    vars_block = raw_config.get("variables")
    if not vars_block:
        return {}

    script_file = vars_block.get("script_file")
    script_inline = vars_block.get("script")

    if script_file and script_inline:
        import logging
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
```

同时在文件顶部 `import re` 后新增 `from pathlib import Path`：

```python
import os
import re
from pathlib import Path
from typing import Any
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestExecuteVariablesScript -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add docupipe/config.py tests/test_docpipe.py
git commit -m "feat: 新增 execute_variables_script() 支持从 Python 脚本获取变量"
```

---

### Task 2: 改造 `resolve_env_vars()` 支持 Python 变量优先级

**Files:**
- Modify: `docupipe/config.py:10-28`
- Modify: `tests/test_docpipe.py:593`

- [ ] **Step 1: 写失败测试 — Python 变量覆盖环境变量**

在 `TestEnvInterpolation` 类中新增以下测试方法（在 `test_resolve_non_string_unchanged` 之后）：

```python
    def test_resolve_python_vars_override_env(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "from_env")
        from docupipe.config import resolve_env_vars
        result = resolve_env_vars("${MY_KEY}", variables={"MY_KEY": "from_python"})
        assert result == "from_python"

    def test_resolve_python_vars_without_env(self):
        from docupipe.config import resolve_env_vars
        result = resolve_env_vars("${MY_VAR}", variables={"MY_VAR": "python_value"})
        assert result == "python_value"

    def test_resolve_python_vars_with_default(self):
        from docupipe.config import resolve_env_vars
        result = resolve_env_vars("${MISSING:-fallback}", variables={"MISSING": "from_python"})
        assert result == "from_python"

    def test_resolve_python_vars_fallback_to_env(self, monkeypatch):
        monkeypatch.setenv("ENV_ONLY", "env_val")
        from docupipe.config import resolve_env_vars
        result = resolve_env_vars("${ENV_ONLY}", variables={"OTHER": "val"})
        assert result == "env_val"

    def test_resolve_python_vars_in_dict(self):
        from docupipe.config import resolve_env_vars
        config = {"key": "${my_var}", "nested": {"k2": "${my_var}/path"}}
        result = resolve_env_vars(config, variables={"my_var": "hello"})
        assert result == {"key": "hello", "nested": {"k2": "hello/path"}}

    def test_resolve_no_variables_same_behavior(self, monkeypatch):
        monkeypatch.setenv("KEY", "val")
        from docupipe.config import resolve_env_vars
        assert resolve_env_vars("${KEY}") == "val"
        assert resolve_env_vars("${MISSING}") == "${MISSING}"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestEnvInterpolation::test_resolve_python_vars_override_env -v`
Expected: FAIL — `TypeError` (函数不接受 `variables` 参数)

- [ ] **Step 3: 改造 `resolve_env_vars()` 和 `_replace_env()`**

替换 `docupipe/config.py` 中第 10-27 行的 `resolve_env_vars` 和 `_replace_env` 函数为：

```python
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
        return val if val is not None else match.group(0)

    if isinstance(value, str):
        return _ENV_PATTERN.sub(_replace, value)
    if isinstance(value, dict):
        return {k: resolve_env_vars(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_env_vars(v, variables) for v in value]
    return value
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestEnvInterpolation -v`
Expected: 全部 PASS（包括旧测试和新测试）

- [ ] **Step 5: 运行全部测试确认无回归**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add docupipe/config.py tests/test_docpipe.py
git commit -m "feat: resolve_env_vars 支持 Python 变量优先级"
```

---

### Task 3: 集成到 CLI 启动流程

**Files:**
- Modify: `docupipe/cli.py:47-61`

- [ ] **Step 1: 改造 `_run_from_config()` 中的启动流程**

替换 `docupipe/cli.py` 第 50 行和第 57-60 行。先更新 import（第 50 行）：

```python
    from docupipe.config import deep_merge, execute_variables_script, parse_component_config, resolve_env_vars
```

然后替换第 57-60 行（`raw = ...` 到 `extension_rules = ...`）：

```python
    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    variables = execute_variables_script(raw)
    config = resolve_env_vars(raw, variables)

    global_config = {k: v for k, v in config.items() if k not in ("pipelines", "variables")}
    converters_config = global_config.pop("converters", global_config.pop("type_rules", {}))
    extension_rules = converters_config.get("extensions", {})
```

关键变更：
- 新增 `execute_variables_script(raw)` 获取 Python 变量
- `resolve_env_vars(raw, variables)` 传入变量 dict
- `global_config` 过滤中排除 `"variables"` key

- [ ] **Step 2: 运行全部测试确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 3: 手动集成测试**

创建临时配置文件验证端到端流程：

```bash
cat > /tmp/test_vars.yaml << 'EOF'
variables:
  script: |
    return {"greeting": "hello", "port": "8080"}

pipelines: []
EOF
python -m docupipe run --config /tmp/test_vars.yaml --pipeline nonexistent 2>&1 | head -5
```

Expected: 输出 "未找到 pipeline: nonexistent"（说明配置解析成功，变量脚本执行无误），无变量相关报错。

- [ ] **Step 4: 提交**

```bash
git add docupipe/cli.py
git commit -m "feat: CLI 启动时执行 variables 脚本并传入插值系统"
```
