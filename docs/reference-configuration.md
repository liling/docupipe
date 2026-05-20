# 配置系统参考

docupipe 使用 YAML 配置文件定义 pipeline 及所有组件参数。仅支持通过 `--config` 传入 YAML 文件启动，不支持纯命令行参数配置。

## 文件结构

配置文件的顶层结构分为全局配置和 pipelines 列表：

```yaml
# 全局默认配置
hindsight:
  api_url: ${HINDSIGHT_API_URL}
  api_key: ${HINDSIGHT_API_KEY}

converters:
  extensions:
    ".pdf": mineru
    ".docx": markitdown

# pipeline 定义列表
pipelines:
  - name: my-pipeline
    source:
      localdrive:
        input_dir: ./input
    destination:
      localdrive:
        output_dir: ./output
    steps: []
```

## 全局配置

全局配置位于顶层，pipeline 级同名配置会通过 deep merge 覆盖全局值。

### hindsight

Hindsight Memory 目的地全局默认值：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `api_url` | string | `${HINDSIGHT_API_URL}` | Hindsight 服务地址 |
| `api_key` | string | `${HINDSIGHT_API_KEY}` | API 密钥 |
| `bank_id` | string | `${HINDSIGHT_BANK_ID}` | 记忆库 ID |
| `context_prefix` | string | null | context 字符串前缀 |
| `document_id_template` | string | null | 自定义 document_id 模板 |
| `context_template` | string | null | 自定义 context 字符串（优先级高于 context_prefix） |
| `extra_tags` | list[string] | null | 附加标签列表 |
| `extra_metadata` | object | null | 附加元数据字典 |

### image_description

图片描述步骤的全局默认值：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `api_key` | string | `${IMAGE_DESCRIPTION_API_KEY}` | OpenAI 兼容 API 密钥 |
| `base_url` | string | `${IMAGE_DESCRIPTION_BASE_URL}` | API 基础地址 |
| `model` | string | `${IMAGE_DESCRIPTION_MODEL:-gpt-4o}` | 模型名称，默认 `gpt-4o` |

### converters

格式转换规则映射，key 为文件扩展名（含点号），value 为 converter 名称或 `"source"`（跳过转换）：

```yaml
converters:
  extensions:
    ".pdf": mineru
    ".docx": markitdown
    ".pptx": markitdown
```

## Pipeline 配置

每个 pipeline 是一个字典，支持以下字段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | string | 必填 | pipeline 名称，用于 --pipeline 参数选择和状态文件命名 |
| `source` | object | 必填 | 数据源配置，key 为 source 名称，value 为参数 |
| `destination` | object | 必填 | 目标配置，key 为 destination 名称，value 为参数 |
| `steps` | array | `[]` | 处理步骤列表，每个元素为 step 名称字符串或 `{name: kwargs}` |
| `mode` | string | `"full"` | 运行模式：`full` / `incremental` / `mirror` |
| `change_detection` | string | null | mirror 模式的变更检测策略：`mtime` / `hash` |
| `post_steps` | array | `[]` | 写入后执行的步骤（如删除源头） |
| `finalize_steps` | array | `[]` | 全部文档处理完毕后的批量步骤 |
| `state_file` | string | null | 自定义状态文件名，不设置则自动生成 |
| `options` | object | `{}` | 额外选项，目前支持 `mirror_delete`（bool，默认 true） |

### Source 配置

每个 pipeline 的 source 配置必须且只能包含一个 type：

```yaml
source:
  localdrive:
    input_dir: ./input
    include: ["*.md"]
```

### Destination 配置

与 source 规则相同，必须且只能包含一个 type：

```yaml
destination:
  hindsight:
    context_prefix: "知识库"
```

Destination 配置支持 `${context.field}` 模板变量，在写入前由 `resolve_context_vars` 自动替换为 Bundle context 中的值。

### Steps 配置

steps 列表中的每个元素可以是：

- 字符串：仅指定 step 名称，使用默认参数
- 字典：key 为 step 名称，value 为参数字典

```yaml
steps:
  - convert                                   # 仅名称
  - convert:                                  # 名称 + 参数
      extension_rules:
        ".docx": markitdown
  - image_description:
      model: gpt-4o
```

## 环境变量插值

配置中任何字符串值都可以通过 `\${VAR}` 或 `\${VAR:-default}` 语法引用环境变量：

| 语法 | 行为 |
|------|------|
| `${API_KEY}` | 必须设置，否则保留原样 |
| `${MODEL:-gpt-4o}` | 未设置时使用 `gpt-4o` |

优先级：variables 脚本值 > 环境变量 > 默认值。

## Variables 脚本

配置中可以包含 `variables` 块，通过执行 Python 代码生成变量：

```yaml
variables:
  script: |
    import datetime
    today = datetime.date.today().isoformat()
    return {'today': today}
```

或从外部文件加载：

```yaml
variables:
  script_file: ./scripts/vars.py
```

`script` 和 `script_file` 同时存在时，优先使用 `script_file`。脚本必须是返回 `dict[str, str]` 的函数体（`def _vars_func():` 会自动包装）。

## Context 模板变量

Destination 配置支持引用 Bundle context 字段，在 pipeline 运行时自动替换：

```yaml
destination:
  localdrive:
    output_dir: ./output
    path_template: "${context.space_name}/${context.path}"
```

内置 context 字段由 Pipeline 注入：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | str | 文档唯一标识 |
| `title` | str | 文档标题 |
| `path` | str | 文档路径 |
| `filename` | str | 文件名 |
| `hash` | str | 内容 SHA-256 哈希 |
| `_source` | str | 来源组件名称 |

## 配置继承（deep merge）

Pipeline 级配置与全局配置自动深度合并，pipeline 级值覆盖全局级：

```yaml
# 全局
hindsight:
  api_url: http://default
  bank_id: default_bank

# pipeline 级只覆盖 bank_id
destination:
  hindsight:
    bank_id: my_bank

# 结果: {api_url: "http://default", bank_id: "my_bank"}
```

## 解析流程

CLI 启动时配置的解析顺序：

1. 读取 YAML 文件
2. 执行 `variables` 脚本（如有）
3. `resolve_env_vars`：递归替换所有 `${VAR}` 和 `${VAR:-default}`
4. 分离全局配置和 pipelines
5. 对每个 pipeline，通过 `parse_component_config` 解析 source/destination 配置（deep merge 全局值）
6. 构建 Pipeline 时传入 resolved config
7. 写入前调用 `resolve_context_vars` 替换 `${context.field}`
