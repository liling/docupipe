# Hindsight Destination 可配置参数设计

## 背景

Hindsight destination 的 `_build_retain_item` 方法中，`document_id`、`tags`、`metadata`、`context` 的生成逻辑全部硬编码。用户需要通过 YAML 配置文件控制这些参数的取值。

## 方案

复用现有的 `dest_config` + `resolve_context_vars` + `update_config` 机制，在 `destination.hindsight` 下增加 4 个可选配置字段。

## 配置结构

```yaml
destination:
  hindsight:
    # 现有字段
    context_prefix: "产品知识库"

    # 新增字段（全部可选）
    document_id_template: "${context.space_name}/${context.path}"
    context_template: "来自${context.space_name}的${context.title}"
    extra_tags:
      - "custom:${context.space_name}"
    extra_metadata:
      author: "${context.author:-unknown}"
```

- 4 个字段全部可选，不配则保持现有行为
- 所有字符串值支持 `${context.xxx}` 和 `${context.xxx:-default}` 语法
- `extra_tags`（列表）追加到自动生成的 tags 上
- `extra_metadata`（字典）追加到自动生成的 metadata 上
- `document_id_template` 和 `context_template` 如果配置了，替换现有自动生成逻辑

## 实现方式

### HindsightDestination.__init__

增加 4 个参数，以 `self._xxx` 私有属性形式存储，与 `update_config` 的 `self._{key}` 查找机制一致：

```python
def __init__(
    self,
    bank_id: str | None = None,
    api_url: str | None = None,
    api_key: str | None = None,
    context_prefix: str | None = None,
    document_id_template: str | None = None,
    context_template: str | None = None,
    extra_tags: list | None = None,
    extra_metadata: dict | None = None,
    **kwargs,
):
    # ... 现有初始化 ...
    self._document_id_template = document_id_template
    self._context_template = context_template
    self._extra_tags = extra_tags
    self._extra_metadata = extra_metadata
```

### _build_retain_item 修改

**document_id：** 如果 `_document_id_template` 存在，用它替换默认的 `{source_name}:{id}` 格式。

**context：** 优先级：`_context_template` > `context_prefix` > 自动生成。如果 `_context_template` 存在，用它替换现有逻辑。

**tags：** 保持现有自动生成逻辑，如果 `_extra_tags` 存在，将解析后的列表追加。

**metadata：** 保持现有自动生成逻辑，如果 `_extra_metadata` 存在，将解析后的字典 merge 进去。

### resolve_context_vars 时机

无需修改。Pipeline 在 `write()` 前调用 `resolve_context_vars(self._dest_config, bundle.context)`，递归处理 dict/list/string，结果通过 `update_config` 设置到 destination 实例。新增的 4 个字段已被完整解析为具体值，`_build_retain_item` 直接使用即可。

## 影响范围

- `docupipe/destinations/hindsight.py`：修改 `__init__` 和 `_build_retain_item`
- `docupipe.yaml` / `docupipe.example.yaml`：可选的配置示例
- 无架构变更，无新增依赖
