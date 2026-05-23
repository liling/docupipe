# 模板渲染系统重设计

## 背景

当前变量解析使用自制的 `${context.field}` 正则替换，存在两个核心问题：

1. **Bundle 级解析无法处理 per-file 变量**：一个 Bundle 包含多个 FileItem 时（如主文档 + 附件图片），它们可能需要不同的路径/文件名，但当前只有一个 bundle.context。
2. **无表达式能力**：无法做日期格式化、字符串操作、路径提取、条件表达式等。

## 方案

引入 Jinja2 沙箱模式作为模板引擎，解析责任从 Pipeline 下放到 Destination/Step。

### 1. 渲染引擎核心（新增 `docupipe/render.py`）

**核心函数：**

```python
def render_template(value: Any, context: dict) -> Any
```

**Jinja2 Environment 配置：**
- `SandboxedEnvironment` — 禁止执行任意 Python 代码
- `undefined=StrictUndefined` — 变量不存在时抛错，方便排查配置错误
- 语法：`{{ title }}`、`{{ path | basename }}`、`{% if type == 'doc' %}...{% endif %}`

**内置过滤器：**

| 过滤器 | 示例 | 说明 |
|--------|------|------|
| `date_format(fmt)` | `update_time \| date_format('%Y-%m')` | 时间戳/datetime → 格式化字符串 |
| `basename` | `path \| basename` | 取路径中的文件名部分 |
| `extension` | `filename \| extension` | 取扩展名（不含点） |
| `replace(old, new)` | `title \| replace(' ', '-')` | 字符串替换 |
| `default(val)` | `author \| default('unknown')` | Jinja2 内置 `default` 过滤器，替代 `:-` 语法 |

**递归处理：** `render_template` 对 dict/list 递归渲染所有字符串值，与当前 `resolve_context_vars` 行为一致。非字符串值原样返回。

### 2. Context 层级与 per-file 解析

**FileItem 新增 context 字段：**

```python
@dataclass
class FileItem:
    path: str
    content: str | None = None
    context: dict = field(default_factory=dict)  # 新增
```

**Context 合并规则：** 渲染 context = `{**bundle.context, **file.context}`，file 级覆盖 bundle 级。由调用方（Destination/Step）负责合并，`render_template` 本身只接收一个 dict。

**Source 职责：** Source 负责为每个 FileItem 填充各自的 context（如文件名、路径等 per-file 属性）。

### 3. Destination 改造

**当前流程：** Pipeline 统一解析 dest_config → `dest.update_config(resolved)` → `dest.write(bundle)`

**新流程：** Pipeline 传原始 config 给 Destination → Destination 在 `write()` 内部对每个 file 渲染

具体改动：

1. **Pipeline 初始化时传原始 config**：不再调用 `resolve_context_vars`
2. **Destination.write() 内部渲染**：遍历 `bundle.files`，对每个 file 合并 context 后调 `render_template`
3. **`update_config` 语义变化**：从"接收已解析的配置"变为"接收原始配置模板"，Destination 保存模板字符串
4. **`_config_keys` 机制保留**：仍控制哪些字段允许配置，存的是模板而非最终值

**Step 处理：** Step 仍按 bundle 粒度处理（`process` 接收整个 Bundle）。如需渲染能力，自行调用 `render_template`。

### 4. 迁移与清理

**需要变更的文件：**

| 文件 | 变更 |
|------|------|
| `pyproject.toml` | 添加 `jinja2` 依赖 |
| `docupipe/render.py` | 新增，渲染引擎核心 |
| `docupipe/config.py` | 删除 `resolve_context_vars`、`_CONTEXT_PATTERN` |
| `docupipe/models.py` | `FileItem` 加 `context` 字段 |
| `docupipe/pipeline.py` | 删除 `resolve_context_vars` 调用，改传原始 config |
| `docupipe/destinations/base.py` | `update_config` 语义调整为保存模板 |
| `docupipe/destinations/localdrive.py` | `write()` 中用 `render_template` per-file 渲染 `path_template` |
| `docupipe/destinations/hindsight.py` | 同上，渲染 `document_id_template`、`context_template` 等 |
| `docupipe.example.yaml` | `${context.xxx}` → `{{ xxx }}` |
| `examples/*.yaml` | 同上 |
| `tests/test_config.py` | 删除旧测试，新增 `render_template` 测试 |
| `tests/test_localdrive.py` | 更新模板语法 |
| `tests/test_hindsight.py` | 更新模板语法 |

**语法迁移示例：**

```
# 旧语法                          →  新语法
${context.filename}                → {{ filename }}
${context.space_name}/${context.id} → {{ space_name }}/{{ id }}
${context.author:-unknown}         → {{ author | default('unknown') }}
```

**不兼容变更：** 现有 YAML 配置文件需手动更新模板语法。`${VAR}` 环境变量插值不受影响（仍由 `resolve_env_vars` 处理）。
