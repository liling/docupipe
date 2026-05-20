# docupipe YAML 配置参考

## 整体结构

```yaml
# 全局配置（所有 pipeline 共享的默认值）
hindsight:
  api_url: ...
image_description:
  api_key: ...
converters:
  extensions: ...
s3_upload: ...

# Pipeline 列表
pipelines:
  - name: pipeline-name
    source: ...
    destination: ...
    steps: ...
```

## 环境变量插值

语法：`${VAR}` 或 `${VAR:-default}`

```yaml
api_key: ${HINDSIGHT_API_KEY}
model: ${IMAGE_MODEL:-gpt-4o}
```

优先级：variables 脚本生成的值 > 环境变量 > 默认值

## variables 脚本块

通过 Python 脚本动态生成变量：

```yaml
variables:
  script: |
    import os
    return {"BANK_ID": os.getenv("BANK_ID", "default")}
```

或引用外部脚本文件：

```yaml
variables:
  script_file: ./gen_vars.py
```

脚本返回的变量优先级高于环境变量。

## Deep Merge 规则

Pipeline 级配置与全局默认值 deep merge：
- 字典类型：递归合并
- 列表类型：pipeline 级覆盖全局级（不合并）
- 标量类型：pipeline 级覆盖全局级

## Pipeline 配置

```yaml
pipelines:
  - name: string                    # 必填，pipeline 名称
    source:                         # 必填，数据源配置
      <source_type>:
        <params>...
    destination:                    # 必填，目标配置
      <dest_type>:
        <params>...
    steps:                          # 可选，处理步骤列表
      - step_name                   # 无参数的 step
      - step_name:                  # 带参数的 step
          param: value
    mode: full|incremental|mirror   # 可选，运行模式
    change_detection: mtime|hash    # 可选，变更检测策略
    post_steps: [...]               # 可选，每个文档处理完后的步骤
    finalize_steps: [...]           # 可选，全部文档处理完后的批量步骤
```

## 全局配置块

### hindsight

```yaml
hindsight:
  api_url: string       # HindSight API 地址
  api_key: string       # API Key
  bank_id: string       # Bank ID
```

### image_description

```yaml
image_description:
  api_key: string       # OpenAI 兼容 API Key
  base_url: string      # API Base URL
  model: string         # 模型名称
  concurrency: int      # 并发数，默认 1
```

### converters

```yaml
converters:
  extensions:
    ".pdf": mineru
    ".docx": markitdown
    ".pptx": markitdown
    ".xlsx": markitdown
    ".doc": markitdown
    ".xls": markitdown
    ".ppt": markitdown
```

### s3_upload

```yaml
s3_upload:
  endpoint_url: string   # S3 端点，默认 http://localhost:9000
  region: string         # 区域，默认 us-east-1
  bucket: string         # Bucket 名称
  access_key: string     # Access Key
  secret_key: string     # Secret Key
  prefix: string         # Key 前缀，默认 attachments
  url_prefix: string     # 公开 URL 前缀
  roles: [string]        # 上传的文件角色，默认 ["image"]
```

## Destination 的 Context 插值

Destination 配置值支持 `${context.field}` 语法，Pipeline 在 write 前自动解析：

```yaml
destination:
  hindsight:
    document_id_template: "${context._source}:${context.id}"
    context_template: "文档：${context.title}，来自 ${context.space_name}"
```

## 配置模板

### 模板 1：本地文件夹转换

```yaml
converters:
  extensions:
    ".docx": markitdown
    ".pdf": mineru

pipelines:
  - name: local-convert
    source:
      localdrive:
        input_dir: ./input
        include: ["*.docx", "*.pdf"]
    destination:
      localdrive:
        output_dir: ./output
        replace_extension: true
    steps:
      - convert
```

### 模板 2：钉钉知识库 → Hindsight

```yaml
hindsight:
  api_url: ${HINDSIGHT_API_URL}
  api_key: ${HINDSIGHT_API_KEY}
  bank_id: ${HINDSIGHT_BANK_ID}

image_description:
  api_key: ${IMAGE_DESCRIPTION_API_KEY}
  base_url: ${IMAGE_DESCRIPTION_BASE_URL}
  model: ${IMAGE_DESCRIPTION_MODEL:-gpt-4o}

converters:
  extensions:
    ".docx": markitdown
    ".pptx": markitdown
    ".xlsx": markitdown

s3_upload:
  endpoint_url: ${S3_ENDPOINT:-http://localhost:9000}
  bucket: ${S3_BUCKET:-hindsight}
  access_key: ${S3_ACCESS_KEY}
  secret_key: ${S3_SECRET_KEY}
  url_prefix: ${S3_URL_PREFIX}

pipelines:
  - name: dingtalk-to-hindsight
    source:
      dingtalk:
        space: 产品知识库
        folders: ["文件夹路径"]
    destination:
      hindsight:
        context_prefix: "产品知识库"
    steps:
      - convert
      - image_description
      - s3_upload
```

### 模板 3：腾讯文档 → 本地 + S3 上传

```yaml
s3_upload:
  endpoint_url: ${S3_ENDPOINT:-http://localhost:9000}
  bucket: ${S3_BUCKET:-hindsight}
  access_key: ${S3_ACCESS_KEY}
  secret_key: ${S3_SECRET_KEY}
  url_prefix: ${S3_URL_PREFIX}

pipelines:
  - name: tencent-to-s3
    source:
      tencent:
        space_name: "个人空间"
        folders: ["目标文件夹"]
        fetch_mode: markdown
    destination:
      hindsight:
        context_prefix: "腾讯文档"
    steps:
      - resolve_attachments
      - s3_upload
```

### 模板 4：镜像同步

```yaml
pipelines:
  - name: mirror-sync
    source:
      dingtalk:
        space: 知识库名
    destination:
      localdrive:
        output_dir: ./output/sync
    steps:
      - convert
    mode: mirror
    change_detection: mtime
```
