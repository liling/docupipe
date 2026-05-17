# 腾讯文档 MCP Source 设计

## 目标

为 docupipe 新增 `tencent` source，通过 FastMCP Client 直接连接腾讯文档 MCP 服务，从指定知识库空间获取文档内容。

## 架构

新增 `docupipe/sources/tencent.py`，遵循现有 source 插件架构：
- 继承 `SourceBase`，实现 `list()` 和 `fetch()`
- 使用 `@register_source("tencent")` 装饰器注册
- 在 `sources/__init__.py` 中 import 触发注册

## 依赖

- 新增运行时依赖：`fastmcp`（`pip install fastmcp`）
- 需要环境变量 `TENCENT_DOCS_TOKEN` 提供认证 token

## 核心组件

### `_TencentDocClient`

封装 MCP 客户端，管理连接和工具调用。使用 `fastmcp.Client` + `StreamableHttpTransport` 连接 `https://docs.qq.com/openapi/mcp`，通过 `BearerAuth` 传递 token。对外提供同步方法（内部用 `asyncio.run()` 包装异步 MCP 调用）。

核心调用方式：
```python
from fastmcp import Client
from fastmcp.client.auth import BearerAuth

client = Client("https://docs.qq.com/openapi/mcp", auth=BearerAuth(token))
async with client:
    result = await client.call_tool("query_space_node", {"space_id": "..."})
```

方法：
- `list_nodes(space_id, parent_id=None, num=0)` → 调用 `query_space_node`，返回节点列表和分页信息
- `get_content(file_id)` → 调用 `get_content`，返回文档 markdown 内容
- `export_file(file_id)` → 调用 `manage.export_file` + `manage.export_progress` 轮询，返回文件下载 URL

### `TencentSource`

配置参数（通过 YAML `source` 节传入）：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `space_id` | string | 是 | 知识库空间 ID |
| `parent_id` | string | 否 | 指定空间内某个文件夹作为根 |
| `folders` | list[string] | 否 | 多个子目录路径（与 parent_id 二选一） |
| `include_types` | list[string] | 否 | 过滤文档类型（smartcanvas, word, excel 等） |
| `fetch_mode` | string | 否 | `markdown`（默认）、`export` 或 `both`，控制 fetch 获取方式 |

#### `list()` 逻辑

1. 如果配置了 `folders`，逐个解析路径为 node_id（类似 dingtalk 的 `_resolve_folder_path`）
2. 调用 `query_space_node` 遍历节点树，分页获取（每页 20 条，用 `has_next` + `num` 分页）
3. 跳过 `node_type=wiki_folder` 节点，收集叶子文档节点
4. 递归进入 `has_child=true` 的文件夹
5. 过滤 `include_types`（如果配置了）
6. 返回 `[BundleMeta(id=node_id, title=..., ...)]`

#### `fetch()` 逻辑

两种模式，由配置参数 `fetch_mode` 控制（默认 `markdown`）：

**markdown 模式**：
1. 用 `meta.id`（即 node_id / file_id）调用 `get_content`
2. 返回 `Bundle(files=[FileItem(name=title.md, content=markdown, content_type="text/markdown", role="main")])`

**export 模式**：
1. 调用 `manage.export_file(file_id)` 获取 `task_id`
2. 轮询 `manage.export_progress(task_id)` 直到 `progress=100`
3. 通过临时下载 URL 下载文件内容（docx/xlsx/pptx 等，格式由文档类型自动决定）
4. 返回 `Bundle(files=[FileItem(name=title.docx, content=bytes, content_type=docx, role="main")])`，标记 `_needs_conversion=True` 走 converter 链路

**both 模式**：
1. 同时执行 markdown 和 export 两种获取
2. 返回 `Bundle(files=[FileItem(markdown, role="main"), FileItem(docx, role="attachment")])`，导出文件标记 `_needs_conversion=True`

## 数据流

```
list():
  query_space_node(space_id, parent_id) → 分页遍历 → 递归进入文件夹
    → 收集 node_type != wiki_folder 的节点 → [BundleMeta(id=node_id)]

fetch(meta) — markdown 模式（默认）:
  get_content(file_id=meta.id) → markdown → Bundle(files=[FileItem])

fetch(meta) — export 模式:
  export_file(file_id) → task_id → export_progress 轮询 → 下载 URL → Bundle(files=[FileItem], _needs_conversion=True)
```

## 与钉钉 source 的差异

| 方面 | 钉钉 | 腾讯文档 |
|------|------|---------|
| 调用方式 | subprocess 调用 `dws` CLI | FastMCP Client 直接连接 |
| 内容获取 | 不同类型需区分处理（ALIDOC/下载） | 支持 markdown 和 export 两种模式 |
| HTML 清理 | 需要 `_clean_html_tags` | 不需要 |
| 文件下载 | 部分类型需下载文件后转换 | export 模式支持（docx/xlsx/pptx） |
| 分页 | 50 条/页 | 20 条/页 |

## 配置示例

```yaml
# 默认 markdown 模式
pipelines:
  - name: tencent-to-hs
    source:
      name: tencent
      space_id: "space_xxx"
      folders:
        - "技术文档/API设计"
    destination:
      name: hindsight
      bank_id: "${HINDSIGHT_BANK_ID}"

# export 模式（导出原始格式文件，走 converter 链路）
pipelines:
  - name: tencent-export
    source:
      name: tencent
      space_id: "space_xxx"
      fetch_mode: export
    steps:
      - name: convert
    destination:
      name: localdir
      output_dir: ./output
```

## 错误处理

- Token 缺失或无效：`list()` 初始化时报错，提示配置 `TENCENT_DOCS_TOKEN`
- MCP 连接失败：捕获异常并记录日志
- export 模式轮询超时：设置最大轮询次数（如 60 次 × 5 秒 = 5 分钟），超时抛出 `SkipBundle`
- export 下载 URL 过期：重试一次 export_file → export_progress 流程
