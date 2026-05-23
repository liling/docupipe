# 如何配置 Pipeline

## Prerequisites

- 安装了 docupipe
- 了解基本的 YAML 语法

## 步骤

### 1. 创建配置文件

创建 `docupipe.yaml`（默认路径，可通过 `--config` 指定其他位置）：

```yaml
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

### 2. 选择 Source

每个 pipeline 必须有一个 source，支持以下选项：

```yaml
# 本地文件
source:
  localdrive:
    input_dir: ./docs          # 输入目录（必填）
    include: ["*.md", "*.txt"] # 包含模式（可选）
    exclude: ["*.tmp"]         # 排除模式（可选）

# 钉钉知识库（wiki 模式，默认）
source:
  dingtalk:
    space: "产品知识库"           # 知识库名称（与 space_id 二选一）
    # space_id: "kfiwoue83nkxQXyA"
    folders: ["产品规划/解决方案"] # 文件夹路径（可选）
    include_types: [DOCUMENT, ALIDOC]  # 文档类型过滤（可选）

# 钉钉文档（doc 模式，直接操作文件夹，不依赖知识库概念）
source:
  dingtalk:
    mode: doc
    folder_id: "your_folder_id"         # 文件夹 ID（必填）
    folders: ["B1 平台/平台线/02 解决方案"] # 文件夹子路径（可选）
    include_types: [DOCUMENT, ALIDOC]

# 腾讯文档
source:
  tencent:
    space_name: "我的空间"
    fetch_mode: "markdown"     # markdown | export | both
    folders: ["技术文档"]
```

### 3. 选择 Destination

```yaml
# 本地文件
destination:
  localdrive:
    output_dir: ./output
    replace_extension: false   # 是否替换路径原扩展名
    save_sidecar: true         # 是否保存 JSON 元数据
    path_template: "{{ context.space_name }}/{{ context.path }}"  # 自定义路径模板（支持 Jinja2 语法）

# Hindsight Memory
destination:
  hindsight:
    bank_id: ${HINDSIGHT_BANK_ID}
    api_url: ${HINDSIGHT_API_URL}
    context_prefix: "知识库"             # 可选 context 前缀
    # document_id_template: "custom:{{ context.id }}"   # 自定义文档 ID（支持 Jinja2 语法）
    # context_template: "文档：{{ context.title }}"     # 自定义 context（Jinja2 语法，优先级高于 context_prefix）
    # extra_tags: ["生产", "已审核"]                 # 附加标签
    # extra_metadata: {"source": "docupipe"}         # 附加元数据
```

### 4. 配置 Steps

```yaml
# Step 列表，按执行顺序排列
# 字符串形式（使用默认参数）：
steps:
  - convert
  - image_description

# 字典形式（指定参数）：
steps:
  - convert:
      extension_rules:
        ".pdf": mineru
        ".docx": markitdown
  - image_description:
      model: gpt-4o
      concurrency: 3
```

可用步骤：

| Step | 说明 | 推荐位置 |
|------|------|----------|
| `convert` | 格式转换（文件 → Markdown） | 第一个 step |
| `image_description` | AI 图片描述 | 接在 convert 之后 |
| `resolve_attachments` | 解析本地文件引用 | 接在 convert 之后 |
| `s3_upload` | 上传附件到 S3 | 最后执行 |
| `tencent_delete` | 删除已处理的腾讯文档 | 放在 finalize_steps |

### 5. 配置 Post Steps 和 Finalize Steps

`post_steps`：每个文档成功写入后立即执行。
`finalize_steps`：所有文档处理完毕后执行，适合批量操作。

```yaml
steps:
  - convert

post_steps: []
finalize_steps:
  - tencent_delete:
      remove_type: "current"
```

### 6. 设置运行模式和变更检测

```yaml
pipelines:
  - name: sync-pipeline
    mode: mirror                 # full | incremental | mirror
    change_detection: mtime     # mtime | hash（仅 mirror 模式需要）
    options:
      mirror_delete: true       # 是否删除目标中已消失的文档
```

### 7. 使用环境变量

```yaml
# .env 文件
HINDSIGHT_API_URL=http://localhost:8888
HINDSIGHT_API_KEY=sk-xxx

# docupipe.yaml
destination:
  hindsight:
    api_url: ${HINDSIGHT_API_URL}
    api_key: ${HINDSIGHT_API_KEY}
    model: ${MODEL:-gpt-4o}     # 支持默认值
```

### 8. 使用 Variables 脚本

```yaml
variables:
  script: |
    import datetime
    today = datetime.date.today().isoformat()
    return {
        "date_stamp": today,
        "context": f"日报-{today}",
    }

pipelines:
  - name: daily-report
    destination:
      hindsight:
        context_prefix: ${context}
```

Variables 脚本生成的变量在配置中以 `${VAR}` 引用，优先级高于环境变量。
Destination 配置中的 Context 模板渲染使用 Jinja2 `{{ field }}` 语法（见第 3 步中的示例）。

## Verification

```bash
# 执行（dry-run 模式验证配置）
python -m docupipe run --pipeline my-pipeline --dry-run

# 查看可用组件
python -m docupipe sources
python -m docupipe destinations
```

## Troubleshooting

**配置找不到 pipeline**：确认 `pipelines` 列表中的 `name` 字段与 `--pipeline` 参数一致。

**环境变量未替换**：docupipe 自动加载 `.env` 文件。如果变量名不含默认值且环境变量未设置，`${VAR}` 保持原样不报错。

**组件参数无效**：组件 `__init__` 接收的参数名必须与 YAML key 一致。多余的参数会被 `**kwargs` 捕获（如果组件定义了的话）。

**Source list 失败**：钉钉知识库需要 `dws` CLI 已登录认证；腾讯文档需要 `TENCENT_DOCS_TOKEN` 环境变量。
