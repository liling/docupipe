# 组件 API 参考

docupipe 包含四类可插拔组件：Source、Destination、Step、Converter。所有组件通过装饰器注册，在 `__init__.py` 中 import 触发注册。

## Source（数据源）

所有 Source 继承 `SourceBase`：

```python
from docupipe.sources.base import SourceBase

class SourceBase(ABC):
    name: str = ""

    @abstractmethod
    def list(self) -> list[BundleMeta]:
        """列出所有可获取的文档元数据"""

    @abstractmethod
    def fetch(self, meta: BundleMeta) -> Bundle:
        """获取单个文档的完整内容"""

    def supported_change_detection(self) -> list[str]:
        """返回支持的变更检测策略，默认 []"""
        return []

    def delete(self, doc_id: str) -> None:
        """删除源头文档（可选实现）"""
        raise NotImplementedError
```

### localdrive

本地文件系统 Source。`list()` 递归遍历目录，`fetch()` 按扩展名自动区分文本/二进制读取。

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `input_dir` | str | 必填 | 输入目录 |
| `include` | list[str] | null | glob 包含模式（不设置则包含全部） |
| `exclude` | list[str] | null | glob 排除模式 |

**行为：**
- 跳过以点开头的目录和文件（`.` 前缀视为隐藏）
- 跳过无扩展名的文件
- 跳过 `.json` 文件（如果同名的无扩展名主文件存在——这是 sidecar 过滤）
- `list()` 返回的 `BundleMeta.id` 默认使用文件内容的 SHA-256；如果同名 `.json` sidecar 文件存在且包含 `id` 字段，则优先使用 sidecar 中的 ID
- 从 sidecar 中读取 `title`、`content_type`、`extension`、`dingtalk_extension`、`space_name` 等字段注入到 `extra`
- `supported_change_detection()` 返回 `["mtime", "hash"]`
- `context` 写入 `extension`、`absolute_path`、`size`、`mtime`

### dingtalk

钉钉知识库 Source。通过命令行工具 `dws`（dingtalk-workspace-cli）操作。

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `space` | str | 与 space_id 二选一 | 知识库名称（自动解析 ID，仅 wiki 模式） |
| `space_id` | str | 与 space 二选一 | 知识库 workspace ID（仅 wiki 模式） |
| `folders` | list[str] | null | 文件夹路径列表（如 `["产品规划/解决方案"]`） |
| `folder_id` | str | null | 单个文件夹 ID |
| `include_types` | list[str] | null | 文档类型白名单（如 `ALIDOC`、`DOCUMENT`） |
| `mode` | `"wiki"\|"doc"` | `"wiki"` | 操作模式 |

**模式说明：**

| 模式 | 说明 | 必需参数 |
|------|------|----------|
| `wiki` | 操作知识库（默认），使用 `dws doc list --workspace` API | `space` 或 `space_id` |
| `doc` | 操作指定文件夹下的文档，不依赖知识库概念。`space_name` 为空字符串 | `folder_id` |

**行为：**
- `list()` 递归遍历指定文件夹，收集文档节点
- ALIDOC 类型通过 `dws doc read` 获取 Markdown 内容
- DOCUMENT 类型通过 `dws doc download` 获取下载 URL 后下载文件
- ALIDOC 子类型 `axls`、`amindmap`、`aform`、`abitable`、`able` 不支持，抛出 `SkipBundle`
- 导出 Markdown 会清理残留的内联 HTML 标签
- `supported_change_detection()` 返回 `["mtime", "hash"]`
- `context` 写入 `dingtalk_content_type`、`dingtalk_update_time`、`dingtalk_node_type`、`dingtalk_extension`、`space_name`、`mtime`

### tencent

腾讯文档 Source。通过 FastMCP Client 连接腾讯文档 MCP 服务。

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `space_name` | str | 与 space_id 二选一 | 空间名称（自动解析 ID） |
| `space_id` | str | 与 space_name 二选一 | 空间 ID |
| `folders` | list[str] | null | 文件夹路径列表 |
| `parent_id` | str | null | 父节点 ID |
| `include_types` | list[str] | null | 文档类型白名单 |
| `fetch_mode` | `"markdown"\|"export"\|"both"` | `"markdown"` | 获取方式 |

**行为：**
- 需要环境变量 `TENCENT_DOCS_TOKEN`
- `fetch_mode` 控制获取策略：
  - `markdown`：通过 MCP `get_content` 获取 Markdown
  - `export`：通过 `manage.export_file` 导出为 Office 格式（轮询等待完成）
  - `both`：同时获取 Markdown 和导出文件
- 导出完成后自动轮询进度，最多等待 5 分钟（60 次 × 5 秒）
- 文档类型到扩展名的映射：

| 类型 | 扩展名 |
|------|--------|
| `word`/`doc`/`smartcanvas` | `.docx` |
| `sheet`/`smartsheet` | `.xlsx` |
| `slide` | `.pptx` |
| `mind` | `.xmind` |
| `flowchart` | `.pdf` |

- `supported_change_detection()` 返回 `["hash"]`

## Destination（目标）

所有 Destination 继承 `DestinationBase`：

```python
class DestinationBase(ABC):
    name: str = ""

    @abstractmethod
    def write(self, bundle: Bundle) -> str:
        """写入文档包，返回目标系统 ID"""

    def remove(self, bundle_id: str) -> None:
        """删除文档（可选实现）"""
        raise NotImplementedError

    def update_config(self, config: dict) -> None:
        """用已解析的配置更新组件属性（去除 ${context.field} 模板后）"""
```

### localdrive

写入本地文件系统。

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `output_dir` | str | 必填 | 输出目录 |
| `replace_extension` | bool | false | 是否替换路径扩展名（追加 .md 等） |
| `save_sidecar` | bool | true | 是否保存 JSON 元数据 sidecar 文件 |
| `path_template` | str | null | 自定义输出路径模板 |

**行为：**
- 输出路径由 `path_template` 或 `context.path` 决定，结合 content_type 自动追加/替换扩展名
- Bundle 中的非主文件（role != "main"）写入到主文件同目录
- 文件已存在且 hash 一致则跳过写入
- sidecar JSON 包含：`id`、`title`、`content_type`、`extension`、`space_name`、`relative_path`、`content_hash`
- `remove()` 使用 `remove_by_path(file_path)` 删除文件及 sidecar（非标准 `remove(doc_id)` 模式）

### hindsight

写入 Hindsight Memory 服务。

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `bank_id` | str | `${HINDSIGHT_BANK_ID}` | 记忆库 ID |
| `api_url` | str | `${HINDSIGHT_API_URL}` | 服务地址 |
| `api_key` | str | `${HINDSIGHT_API_KEY}` | API 密钥 |
| `context_prefix` | str | null | context 字符串前缀 |
| `document_id_template` | str | null | 自定义 document_id 模板字符串 |
| `context_template` | str | null | 自定义 context 字符串模板（优先级高于 context_prefix） |
| `extra_tags` | list[str] | null | 附加标签列表，追加到自动生成的 space:/path: 标签之后 |
| `extra_metadata` | dict | null | 附加元数据字典，合并到 metadata 对象中 |

**行为：**
- 使用 hindsight_client SDK，通过 `retain_batch(..., retain_async=True)` 异步写入
- `document_id` 默认格式：`{source}:{id}`（如 `dingtalk:node123`）；设置 `document_id_template` 可自定义
- 路径自动拆分为 `space:` 和 `path:` 标签
- context 字符串优先级：`context_template` > `context_prefix` > 标题+路径自动构建
- `extra_tags` 追加到自动生成的标签列表末尾；`extra_metadata` 合并到 `metadata` 对象中
- 时间戳优先使用 `mtime`（context 中的通用修改时间戳，毫秒），否则使用当前时间
- 不支持 `remove()`
- 需要调用 `close()` 释放 hindsight 连接（CLI 自动处理）

## Step（处理步骤）

所有 Step 继承 `Step`：

```python
class Step(ABC):
    name: str = ""

    @abstractmethod
    def process(self, bundle: Bundle) -> Bundle:
        """处理文档包，返回处理后的文档包"""

    def update_config(self, config: dict) -> None:
        """用已解析的配置更新组件属性"""
```

### convert

文档格式转换。根据配置的 extension → converter 映射自动转换文件格式。

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `extension_rules` | dict | `{}` | `{".ext": "converter_name"}` 映射 |

**行为：**
- 从 `bundle.context.extension` 读取文件扩展名，匹配 `extension_rules`
- value 为 `"source"` 时跳过转换
- 主文件内容必须是 bytes，写入临时文件后调用 converter
- 提取 Markdown 中的 `data:image` base64 内联图片，转换为 FileItem 加入 bundle
- 图片文件路径格式：`images/{title_hash}/{filename}`
- 主文件名扩展名替换为 `.md`，content_type 设为 `text/markdown`

### image_description

AI 图片描述。调用 OpenAI 兼容的 Vision API 为 bundle 中的图片生成描述。

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `api_key` | string | "" | 调用时从配置传入 |
| `base_url` | string | "" | API 基础 URL |
| `model` | string | `gpt-4o` | 视觉模型名称 |
| `concurrency` | int | 1 | 并发数（>1 时使用 asyncio） |

**行为：**
- 解析 Markdown 中的图片引用，提取图片文件内容
- 跳过 `image://` 前缀的虚拟引用
- 图片大小超过 10MB 跳过
- 使用 `OpenAIVisionClient` 调用 API，返回 JSON `{filename, description}`
- 自动将图片文件名替换为 AI 生成的英文文件名
- Markdown 中的图片 alt text 替换为 AI 生成的中文描述
- 结果写入 `bundle.context.image_metadata`
- 图片格式检查：支持 png/jpeg/gif/webp/bmp，其他格式尝试转换为 PNG（需 PIL）
- 图片尺寸小于 10×10 像素跳过

### excel_structured

将 Excel 文件按 Sheet 结构化提取为独立 Markdown 表格文件。放在 `convert` step 之前，对 `.xlsx` 文件预处理。

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `fill_merged` | bool | `true` | 是否将合并单元格的值填充到所有合并区域单元格 |
| `skip_hidden` | bool | `true` | 是否跳过隐藏行和隐藏列 |
| `skip_empty` | bool | `true` | 是否跳过全空行 |

**行为：**
- 仅处理 `extension` 为 `xlsx` 的文件（非 xlsx 原样返回）
- 每个 Sheet 输出为独立的 Markdown 表格 FileItem，文件名为 `{stem}_{sheet_name}.md`
- 合并单元格自动填充左上角值到整个区域（`fill_merged=true`）
- 隐藏行/列自动跳过（`skip_hidden=true`）
- 全空行自动跳过（`skip_empty=true`）
- 处理后将 `bundle.context.extension` 设为 `md`，后续 `convert` step 会跳过

### resolve_attachments

解析本地文件引用，将 Markdown 中引用的本地文件作为 FileItem 加入 bundle。

**行为：**
- 读取 `bundle.context.absolute_path` 获取文件所在目录
- 解析 Markdown 中的 `[text](path)` 引用
- 跳过外部 URL（`http://`、`https://`、`data:`、`#`、`mailto:`）
- 文件类型自动判断：图片扩展名 → role `"image"`，其他 → role `"attachment"`

### s3_upload

将 bundle 中的附件（图片等）上传到 S3 兼容的对象存储。

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `endpoint_url` | string | `http://localhost:9000` | S3 端点 |
| `region` | string | `us-east-1` | 区域 |
| `bucket` | string | "" | bucket 名称 |
| `prefix` | string | `attachments` | 对象 key 前缀 |
| `url_prefix` | string | "" | 生成的 URL 前缀 |
| `roles` | list[string] | `["image"]` | 要上传的 role 类型 |

**行为：**
- 使用 boto3 客户端执行 `put_object`
- 对象 key 格式：`{prefix}/{sha256hash}/{filename}`
- 上传后在 Markdown 中将本地引用替换为 S3 URL
- 已替换的文件从 bundle 中移除

### tencent_delete

腾讯文档删除步骤。放在 `finalize_steps` 中使用，确保所有文档处理完后再删除源头。

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `remove_type` | string | `"current"` | 删除类型 |

**行为：**
- 需要环境变量 `TENCENT_DOCS_TOKEN`
- 从 `bundle.context` 读取 `space_id` 和 `id`
- 调用腾讯文档 MCP `delete_space_node`

## Converter（格式转换器）

所有 Converter 继承 `ConverterBase`：

```python
class ConverterBase(ABC):
    name: str = ""

    @abstractmethod
    def convert(self, file_path: Path) -> str:
        """将文件转换为 Markdown 文本"""
```

### markitdown

使用 `markitdown` 库转换常见办公文档。支持 `.docx`、`.pptx`、`.xlsx`、`.pdf`（文本型）等格式。转换时保留 `data:` URI 图片引用。

### mineru

使用 MinerU 引擎转换 PDF（特别是内含图片的扫描件 PDF），支持 OCR 识别。

**行为：**
- 输出 Markdown 格式
- 使用 pipeline 后端，自动解析方法
- 语言设置为中文
- 输出到临时目录，查找生成的 `.md` 文件
- 依赖项：`pip install "docupipe[mineru]"`
