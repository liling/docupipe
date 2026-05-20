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
    bank_id: string                 # 可选，回退顺序：此处 > 全局配置 > $HINDSIGHT_BANK_ID
    api_url: string                 # 可选，回退顺序：此处 > 全局配置 > $HINDSIGHT_API_URL
    api_key: string                 # 可选，回退顺序：此处 > 全局配置 > $HINDSIGHT_API_KEY
    context_prefix: string          # 可选，回退到 $HINDSIGHT_CONTEXT 环境变量
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
