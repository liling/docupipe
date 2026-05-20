# docupipe CLI Skill 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建 Superpowers 格式的 skill，让 AI agent 能完整运维 docupipe CLI（配置生成、执行、监控、排错）。

**Architecture:** 主 skill 文件 + references/ 参考文档目录。主 skill 提供触发规则和运维流程清单；references/ 提供精确的 CLI/配置/组件参考，按需查阅。

**Tech Stack:** Markdown（Superpowers skill 格式）

---

### Task 1: 创建目录结构

**Files:**
- Create: `.claude/skills/docupipe/references/` (directory)

- [ ] **Step 1: 创建目录**

```bash
mkdir -p .claude/skills/docupipe/references
```

- [ ] **Step 2: 验证目录存在**

```bash
ls -la .claude/skills/docupipe/
```

Expected: 显示 `references/` 目录

---

### Task 2: 编写 CLI 参考文档

**Files:**
- Create: `.claude/skills/docupipe/references/cli-reference.md`

从 `docupipe/cli.py` 提取的完整 CLI 参考。

- [ ] **Step 1: 创建文件**

写入以下内容：

```markdown
# docupipe CLI 参考

## 命令总览

所有命令通过 `python -m docupipe` 执行。

| 命令 | 说明 |
|------|------|
| `run` | 执行 pipeline |
| `sources` | 列出可用的 Source |
| `destinations` | 列出可用的 Destination |

## 全局选项

适用于所有命令：

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--state-dir PATH` | `./.state` | 状态文件目录 |
| `--log-level LEVEL` | `INFO` | 日志级别：`DEBUG`, `INFO`, `WARNING`, `ERROR` |

## run 命令

```bash
python -m docupipe run [OPTIONS]
```

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--config PATH` | `docupipe.yaml` | 配置文件路径 |
| `--pipeline NAME` | (全部执行) | 指定 pipeline 名称 |
| `--mode MODE` | (使用配置) | 运行模式：`full`, `incremental`, `mirror` |
| `--resume` | `false` | full 模式断点续传（跳过已处理文档） |
| `--change-detection MODE` | (使用配置) | mirror 模式变更检测：`mtime`, `hash` |
| `--dry-run` | `false` | 只打印不执行 |

## 运行模式说明

### full
处理 source 中的所有文档。已处理过的文档通过状态文件跳过。

### full --resume
不调用 `source.list()`，直接从状态文件中找到 status=pending 的文档继续处理。适用于中断后恢复。

### incremental
调用 `source.list()`，只处理状态文件中不存在的新文档。

### mirror
调用 `source.list()`，对比状态文件：
- 新增/修改的文档 → 处理并写入
- 已删除的文档 → 调用 `destination.remove()` 清理

变更检测策略：
- `mtime`：比较修改时间（需要 source 支持）
- `hash`：比较内容 SHA-256 哈希

## 常用命令组合

```bash
# 首次运行
python -m docupipe run

# 指定配置和 pipeline
python -m docupipe run --config my-pipeline.yaml --pipeline dingtalk-download

# 先试运行查看会处理哪些文档
python -m docupipe run --dry-run

# 中断后续传
python -m docupipe run --resume

# 增量同步
python -m docupipe run --mode incremental

# 镜像同步（mtime 变更检测）
python -m docupipe run --mode mirror --change-detection mtime

# 查看可用组件
python -m docupipe sources
python -m docupipe destinations

# 调试模式
python -m docupipe run --log-level DEBUG --dry-run
```

## 状态文件

位置：`--state-dir` 目录下，文件名格式 `{source}_{dest}_state.json`。

每个文件记录：
- 已处理文档的 ID、hash、处理时间
- pending 状态（用于 resume）

## 退出码

| 退出码 | 说明 |
|--------|------|
| 0 | 成功 |
| 1 | 配置错误或运行时异常 |
```

- [ ] **Step 2: 验证文件内容正确**

```bash
wc -l .claude/skills/docupipe/references/cli-reference.md
```

Expected: 约 100 行

---

### Task 3: 编写配置参考文档

**Files:**
- Create: `.claude/skills/docupipe/references/config-reference.md`

- [ ] **Step 1: 创建文件**

写入以下内容：

```markdown
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

### 模板 3：腾讯文档 → 本地导出

```yaml
pipelines:
  - name: tencent-export
    source:
      tencent:
        space_name: "个人空间"
        folders: ["目标文件夹"]
        fetch_mode: export
    destination:
      localdrive:
        output_dir: ./output/tencent
    steps: []
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
```

- [ ] **Step 2: 验证文件**

```bash
wc -l .claude/skills/docupipe/references/config-reference.md
```

Expected: 约 180 行

---

### Task 4: 编写组件参考文档

**Files:**
- Create: `.claude/skills/docupipe/references/components.md`

- [ ] **Step 1: 创建文件**

写入以下内容：

```markdown
# docupipe 组件参考

## Sources

### localdrive

从本地文件系统读取文件。

```yaml
source:
  localdrive:
    input_dir: ./input          # 必填，输入目录
    include: ["*.md", "*.docx"] # 可选，包含的文件 glob 模式
    exclude: ["*.tmp"]          # 可选，排除的文件 glob 模式
```

行为：
- 自动跳过隐藏文件和目录（`.` 开头）
- 自动跳过无扩展名文件
- 文本文件按 UTF-8 读取，二进制文件按 bytes 读取
- 支持 sidecar JSON 文件（同目录下 `filename.json`）提供额外元数据

Context 字段：
| 字段 | 类型 | 说明 |
|------|------|------|
| `extension` | str | 文件扩展名（不含点） |
| `absolute_path` | str | 文件绝对路径 |
| `size` | int | 文件大小（字节） |
| `mtime` | int | 修改时间（毫秒） |

变更检测：支持 `mtime` 和 `hash`

---

### dingtalk

从钉钉知识库获取文档。需要 `dws` CLI 工具。

**Wiki 模式（默认）：**

```yaml
source:
  dingtalk:
    space: 知识库名称            # space 或 space_id 二选一
    space_id: "xxx"             # 直接指定知识库 ID
    folders: ["路径/子路径"]     # 可选，按路径过滤
    folder_id: "xxx"            # 可选，直接指定文件夹 ID
    include_types: [DOCUMENT, ALIDOC]  # 可选，文档类型过滤
    mode: wiki                  # 默认值
```

**Doc 模式：**

```yaml
source:
  dingtalk:
    mode: doc
    folder_id: "xxx"            # 必填，根文件夹 ID
    folders: ["路径/子路径"]     # 可选，路径过滤
    include_types: [DOCUMENT]   # 可选，类型过滤
```

行为：
- ALIDOC 文档自动转换为 Markdown
- 不支持的 ALIDOC 子类型：axls、amindmap、aform、abitable、able
- 非 ALIDOC 类型回退到文件下载
- HTML 标签会从 Markdown 输出中清理

Context 字段：
| 字段 | 类型 | 说明 |
|------|------|------|
| `dingtalk_content_type` | str | 文档类型枚举 |
| `dingtalk_extension` | str | 原始扩展名 |
| `dingtalk_update_time` | int | 更新时间戳（毫秒） |
| `dingtalk_node_type` | str | 节点类型 |
| `space_name` | str | 知识库名称 |

变更检测：支持 `mtime` 和 `hash`

---

### tencent

从腾讯文档获取文档。需要 `TENCENT_DOCS_TOKEN` 环境变量和 `fastmcp` 包。

```yaml
source:
  tencent:
    space_name: "空间名称"      # space_name 或 space_id 二选一
    space_id: "xxx"             # 直接指定空间 ID
    folders: ["文件夹/子文件夹"] # 可选，路径过滤
    parent_id: "xxx"            # 可选，父节点 ID
    include_types: [document, sheet]  # 可选，类型过滤
    fetch_mode: markdown        # markdown | export | both
```

fetch_mode 说明：
- `markdown`：仅返回 Markdown 内容
- `export`：仅返回导出文件（docx/xlsx/pptx 等）
- `both`：同时返回 Markdown 和导出文件

导出文件类型映射：word/doc/smartcanvas → docx, sheet/smartsheet → xlsx, slide → pptx, mind → xmind, flowchart → pdf

Context 字段：
| 字段 | 类型 | 说明 |
|------|------|------|
| `tencent_doc_type` | str | 文档类型枚举 |
| `tencent_node_type` | str | 节点类型 |
| `tencent_has_child` | bool | 是否有子节点 |
| `space_id` | str | 空间 ID（删除操作需要） |

变更检测：支持 `hash`

## Destinations

### localdrive

写入本地文件系统。

```yaml
destination:
  localdrive:
    output_dir: ./output            # 必填，输出目录
    replace_extension: false        # 替换扩展名为 .md
    save_sidecar: true              # 保存 .json sidecar 元数据
    path_template: null             # 可选，输出路径模板
```

行为：
- 自动创建父目录
- 如果 sidecar 存在且内容 hash 相同，跳过写入
- sidecar JSON 包含：id, title, content_type, extension, space_name, relative_path, full_path, content_hash

---

### hindsight

推送到 Hindsight Memory 服务。需要 `hindsight_client` 包。

```yaml
destination:
  hindsight:
    bank_id: ${HINDSIGHT_BANK_ID}       # 可选，默认从全局配置继承
    api_url: ${HINDSIGHT_API_URL}       # 可选，默认从全局配置继承
    api_key: ${HINDSIGHT_API_KEY}       # 可选，默认从全局配置继承
    context_prefix: "知识库名"           # 可选，context 前缀
    document_id_template: "..."         # 可选，文档 ID 模板
    context_template: "..."             # 可选，context 模板
    extra_tags: ["tag1"]                # 可选，额外标签
    extra_metadata: {key: val}          # 可选，额外元数据
```

默认行为（无模板时）：
- document_id: `{source_name}:{doc_id}`
- context: `"文档：{title}，来自 {space_name}/{folder_path}"`
- tags: `["space:{space_name}", "path:folder1", "path:folder2", ...]`

模板支持 `${context.field}` 插值。

注意：`remove()` 操作不支持（会抛出 NotImplementedError）。

## Steps

### convert

使用配置的 converter 将文档转换为 Markdown。

```yaml
steps:
  - convert                        # 使用全局 converter 配置
  - convert:                       # 或覆盖扩展名规则
      extension_rules:
        ".pdf": mineru
```

行为：
- 旧格式（.doc/.ppt/.xls）自动用 LibreOffice 转为现代格式
- 提取 Markdown 中的 base64 内联图片为独立文件
- 转换后设置 `extension = "md"`

---

### image_description

使用 AI 视觉模型为 Markdown 中的图片生成描述。

```yaml
steps:
  - image_description              # 使用全局 image_description 配置
```

配置从全局 `image_description` 块读取：
- `api_key`：API Key
- `base_url`：API Base URL
- `model`：模型名称，默认 `gpt-4o`
- `concurrency`：并发数，默认 `1`

行为：
- 处理 bundle 中所有 role=image 的文件
- 用 AI 生成图片描述，替换 Markdown 中的图片引用
- 重命名图片文件为 AI 生成的文件名

---

### resolve_attachments

解析 Markdown 中的本地文件引用，将文件添加到 bundle。

```yaml
steps:
  - resolve_attachments
```

无额外配置参数。

行为：
- 查找 Markdown 中所有 `![alt](path)` 和 `[text](path)` 引用
- 跳过外部 URL（http/https、# 锚点、data:、mailto:）
- 需要 `bundle.context["absolute_path"]` 来解析相对路径
- 图片扩展名：png/jpg/jpeg/gif/webp/svg/bmp/ico/emf → role=image
- 其他文件 → role=attachment

---

### s3_upload

将 bundle 文件上传到 S3 兼容存储，更新 Markdown 中的引用。

```yaml
steps:
  - s3_upload                      # 使用全局 s3_upload 配置
```

配置从全局 `s3_upload` 块读取：
- `endpoint_url`：S3 端点，默认 `http://localhost:9000`
- `region`：区域，默认 `us-east-1`
- `bucket`：Bucket 名称
- `access_key`：Access Key
- `secret_key`：Secret Key
- `prefix`：Key 前缀，默认 `attachments`
- `url_prefix`：公开 URL 前缀
- `roles`：上传的文件角色，默认 `["image"]`

行为：
- 上传路径：`{prefix}/{sha256_hash}/{filename}`
- 上传后更新 Markdown 引用并从 bundle 中移除文件

---

### tencent_delete

处理完成后删除腾讯文档源文件。

```yaml
finalize_steps:
  - tencent_delete
  # 或指定删除类型：
  - tencent_delete:
      remove_type: trash    # trash（移到回收站）或 current（直接删除）
```

注意：应在 `finalize_steps` 中使用，确保所有处理完成后再删除。

## Converters

### markitdown

使用 Microsoft MarkItDown 库转换文档。支持 docx/pptx/xlsx 等常见格式。

### mineru

使用 MinerU 解析 PDF。支持 OCR，针对中文优化。用于 PDF 转 Markdown。
```

- [ ] **Step 2: 验证文件**

```bash
wc -l .claude/skills/docupipe/references/components.md
```

Expected: 约 200 行

---

### Task 5: 编写主 Skill 文件

**Files:**
- Create: `.claude/skills/docupipe/docupipe.md`

- [ ] **Step 1: 创建文件**

写入以下内容：

```markdown
---
name: docupipe
description: 管理 docupipe 文档传输 pipeline —— 配置生成、执行监控、状态查询、排错修复。当用户需要传输/处理/同步文档、配置 docupipe pipeline、或提到"文档pipeline"时使用。
---

# docupipe CLI Skill

通用文档传输 pipeline 工具。支持从多种文档源获取内容，经过可配置的处理步骤，传输到多种目标系统。

## 何时使用

当用户提到以下场景时触发本 skill：
- 文档传输、文档处理、文档同步、文档转换
- docupipe、pipeline
- 导入文档到 Hindsight
- 钉钉文档/知识库同步
- 腾讯文档同步/导出
- 本地文件批量转换

也支持用户输入 `/docupipe` 直接触发。

## 参考文档

查阅以下文件获取准确的配置参数和组件详情（不要凭记忆编造参数）：
- `references/cli-reference.md` — CLI 命令和选项
- `references/config-reference.md` — YAML 配置格式和模板
- `references/components.md` — 所有可用组件的详细配置

## Agent 操作流程

### 场景 1：新需求（配置生成 + 执行）

1. **确认需求**：确定 source 类型、destination 类型、需要的处理步骤
2. **查阅参考文档**：读取 `references/components.md` 确认组件参数
3. **生成配置**：按照 `references/config-reference.md` 中的模板生成 YAML
4. **用户确认**：展示完整配置，等用户批准
5. **试运行**：`python -m docupipe run --config <file> --dry-run`
6. **正式执行**：`python -m docupipe run --config <file>`

### 场景 2：执行已有配置

1. **读取配置**：读取 YAML 文件
2. **确认参数**：pipeline 名称、模式（full/incremental/mirror）
3. **执行**：`python -m docupipe run --config <file> [--pipeline NAME]`
4. **监控输出**：关注错误信息

### 场景 3：查看状态

1. **列出状态文件**：`ls .state/` 或 `ls <state-dir>/`
2. **读取状态**：查看 JSON 文件中的处理记录
3. **汇报**：已处理/待处理/失败数量

### 场景 4：排错

1. **分析错误**：根据错误信息定位类别：
   - 配置错误（YAML 语法、缺少必填参数、组件名拼写）
   - 网络错误（API 连接、超时）
   - 权限错误（API Key、文件读写）
   - 组件错误（converter 依赖缺失、dws CLI 不可用）
2. **查阅参考文档**：确认正确的配置格式和参数
3. **提出修复方案**：用户确认后修改配置或环境

### 场景 5：增量/镜像模式

1. **确认模式**：`--mode incremental` 或 `--mode mirror`
2. **确认变更检测**（mirror 模式）：`--change-detection mtime` 或 `hash`
3. **执行**

## 关键约束

- **执行前确认**：必须让用户确认 YAML 配置后才能执行
- **读取优先**：修改配置前先读取当前配置，不覆盖未修改部分
- **环境变量**：配置中使用 `${VAR}` 语法，不硬编码密钥
- **查文档不编造**：组件参数以 `references/` 下的文档为准
- **状态文件安全**：操作前先备份 `.state/` 文件
- **dry-run 调试**：不自动添加 `--dry-run`，仅在用户要求或调试时使用

## 常见问题

**Q: 如何查看有哪些可用组件？**
```bash
python -m docupipe sources
python -m docupipe destinations
```

**Q: 中断后如何恢复？**
```bash
python -m docupipe run --resume
```

**Q: 如何只处理新增文档？**
```bash
python -m docupipe run --mode incremental
```

**Q: 如何同步删除操作？**
```bash
python -m docupipe run --mode mirror --change-detection mtime
```
```

- [ ] **Step 2: 验证文件**

```bash
wc -l .claude/skills/docupipe/docupipe.md
```

Expected: 约 100 行

---

### Task 6: 验证 Skill 加载

- [ ] **Step 1: 检查文件结构**

```bash
find .claude/skills/docupipe -type f | sort
```

Expected:
```
.claude/skills/docupipe/docupipe.md
.claude/skills/docupipe/references/cli-reference.md
.claude/skills/docupipe/references/components.md
.claude/skills/docupipe/references/config-reference.md
```

- [ ] **Step 2: 提交代码**

```bash
git add .claude/skills/
git commit -m "feat: 添加 docupipe CLI skill（Superpowers 格式）"
```

- [ ] **Step 3: 在新会话中测试**

开启新的 Claude Code 会话，输入 `/docupipe` 验证 skill 能被正确触发。或提到"帮我配置一个文档 pipeline"验证关键词触发。
