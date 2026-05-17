# 运行时上下文模板系统设计

## 概述

在 YAML 配置中支持 `${context.field}` 模板语法，引用 bundle 的运行时上下文（如 space_name、path、title 等）。模板在 pipeline 处理每个 bundle 时解析，解析后的值注入到组件中。路径、标签等参数不再硬编码在程序中，完全由配置控制。

## 模板语法

`${context.field_name}` — `context.` 前缀表示运行时 bundle 上下文变量。

示例：
```yaml
destination:
  localdrive:
    output_dir: /path/to/vault/${context.space_name}
    path_template: ${context.filename}
```

支持 `${context.field:-default}` 默认值语法。

## 两级解析

1. **启动时**：`resolve_env_vars()` 解析 `${VAR}` 和 `${VAR:-default}`。`${context.xxx}` 没有对应环境变量，保留原样。
2. **运行时**：`resolve_context_vars(value, context)` 只处理 `${context.xxx}`，用 bundle.context 的值替换。找不到字段且无默认值时保留原字符串。

## `resolve_context_vars()` 工具函数

在 `config.py` 中新增，与 `resolve_env_vars()` 平行：

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

## Pipeline 集成

### 模板配置保存

Pipeline 在创建组件时，额外保存一份模板配置字典（包含未解析的 `${context.xxx}`）：

```python
dest = get_destination(dest_name)(**dest_kwargs)
dest_template_config = dict(dest_kwargs)  # 保留模板
```

### 运行时注入

在 bundle 处理循环中，调用 `dest.write()` 之前：

```python
resolved = resolve_context_vars(dest_template_config, bundle.context)
dest.update_config(resolved)
dest.write(bundle)
```

### `update_config()` 基类方法

在 `DestinationBase` 和 `StepBase` 上新增：

```python
def update_config(self, config: dict) -> None:
    """用已解析的配置更新组件属性。"""
    for key, value in config.items():
        attr = f"_{key}"
        if hasattr(self, attr):
            setattr(self, attr, value)
```

组件在 `__init__` 中用 `self._xxx` 命名约定存储配置，`update_config` 自动匹配并更新。组件无需重写此方法。

## localdrive 改造

### 去掉硬编码路径逻辑

`_resolve_path()` 去掉 `space_name` 硬编码拼接：

```python
def _resolve_path(self, bundle: Bundle) -> Path:
    context = bundle.context
    rel_path = self._path_template or context["path"]
    # ... 扩展名处理不变 ...
    return self._output_dir / rel_path
```

### 新增 `path_template` 配置项

- 默认值：不设置，使用 `context["path"]`（完整相对路径，保持现有行为）
- 用户可设为 `${context.filename}` 只用文件名
- 用户可设为任意模板组合

### 配置示例

```yaml
# 按年月分目录，只用文件名
destination:
  localdrive:
    output_dir: /vault/公众号文章/${year}/${month}
    path_template: ${context.filename}

# 按空间分目录，保留原始路径结构
destination:
  localdrive:
    output_dir: /vault/${context.space_name}
    # 不设 path_template，默认用 context["path"]
```

## Source 改动：保存 filename

Source 在创建 bundle context 时，同时保存 `filename`（纯文件名，不含文件夹前缀）：

- `path`：完整相对路径（如 `微信公众号文章/文章标题`）
- `filename`：纯文件名（如 `文章标题`）

## 错误处理

| 场景 | 行为 |
|------|------|
| `${context.xxx}` 字段不存在 | 保留原字符串 |
| `${context.xxx:-default}` 字段不存在 | 使用 default |
| 字段值为 None | 保留原字符串 |
| 组件属性不存在 | `update_config` 跳过 |
| 配置中无 `${context.xxx}` | 行为和现在完全一致 |
| `path_template` 未指定 | 使用 `context["path"]` |

## 影响范围

- `docupipe/config.py`：新增 `resolve_context_vars()` 和 `_CONTEXT_PATTERN`
- `docupipe/pipeline.py`：保存模板配置，处理 bundle 时注入
- `docupipe/destinations/base.py`：新增 `update_config()` 方法
- `docupipe/steps/base.py`：新增 `update_config()` 方法
- `docupipe/destinations/localdrive.py`：去掉硬编码路径，新增 `path_template`
- `docupipe/sources/`：各 source 在 context 中增加 `filename` 字段
- `docupipe/cli.py`：保存组件的模板配置传给 Pipeline
- 测试：覆盖模板解析、注入机制、localdrive 改造

## 不做的事

- 不做模板的条件逻辑（if/else）
- 不做模板的字符串操作（substring、replace 等）
- 不改 `resolve_env_vars()` 的现有行为
- 不改 hindsight destination（后续单独处理）
