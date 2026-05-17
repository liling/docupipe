# API 参考

## Pipeline

核心执行引擎，驱动整个文档传输流程。

```python
from docupipe.pipeline import Pipeline

pipeline = Pipeline(
    source,              # SourceBase 实例
    dest,                # DestinationBase 实例
    state_dir,           # Path — 状态文件目录
    pipeline_name="",    # str — pipeline 名称，用于状态文件命名
    display=None,        # Display — Rich 进度显示
    steps=None,          # list[Step] — 处理步骤
    post_steps=None,     # list[Step] — 写入后执行步骤
    finalize_steps=None, # list[Step] — 全部完成后的批量步骤
    dest_config=None,    # dict — destination 原始配置（含 ${context.field} 模板）
    state_file=None,     # str — 自定义状态文件名
    mode="full",         # str — "full"|"incremental"|"mirror"
    change_detection=None,# str — "mtime"|"hash"
    mirror_delete=True,  # bool — mirror 模式是否删除目标中已移除的文档
)

pipeline.run(mode=None, resume=False, change_detection=None, dry_run=False)
```

`Pipeline.run()` 参数覆盖构造函数中的同名参数。

### 运行模式

| 模式 | 行为 | 状态使用 |
|------|------|----------|
| `full` | 调用 `source.list()` 获取全部文档，逐个处理 | 标记为 pending → done |
| `full` + resume=True | 不调 list()，从状态文件找 pending 继续 | 读取 pending |
| `incremental` | 调用 list()，只处理状态文件中不存在的文档 | 只处理新文档 |
| `mirror` + change_detection | 调用 list()，检测变更 + 清理已删除的文档 | 跳过不变，删除消失 |

### StateManager

状态管理，以 JSON 文件持久化文档处理状态。

```python
from docupipe.pipeline import StateManager

sm = StateManager(path)  # path: Path — 状态文件路径
```

**方法：**

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `load()` | — | `dict[str, dict]` | 加载(缓存)状态文件 |
| `save(entries=None)` | `dict[str, dict]` | — | 保存状态到磁盘 |
| `is_processed(doc_id)` | `doc_id: str` | `bool` | 是否已处理 |
| `is_unchanged(doc_id, hash)` | `doc_id, hash: str` | `bool` | hash 是否一致 |
| `is_mtime_unchanged(doc_id, mtime)` | `doc_id: str, mtime: int` | `bool` | mtime 是否一致 |
| `mark_pending(items)` | `list[tuple[id, path, title, extra]]` | — | 标记为待处理 |
| `mark_done(doc_id, hash, path, mtime, source_hash)` | — | — | 标记为已完成 |
| `is_source_unchanged(doc_id, hash)` | `doc_id, hash: str` | `bool` | source_hash 是否一致 |
| `get_path(doc_id)` | `doc_id: str` | `str` | 获取存储的路径 |
| `get_mtime(doc_id)` | `doc_id: str` | `int \| None` | 获取存储的 mtime |
| `find_pending()` | — | `list[tuple]` | 返回待处理条目 |
| `find_removed(current_ids)` | `list[str]` | `list[str]` | 找出已消失的 ID |
| `mark_removed(doc_id)` | `doc_id: str` | — | 删除状态条目 |

状态文件条目格式：

```json
{
  "doc_id": {
    "status": "done",
    "hash": "sha256hex",
    "path": "relative/path",
    "mtime": 1713571200000,
    "source_hash": "sha256hex"
  }
}
```

旧格式 `{id: hash}` 自动兼容，加载时转为 `{"hash": hash, "path": "", "status": "done"}`。

### 工具函数

```python
from docupipe.pipeline import content_hash, bundle_hash

content_hash(content: str | bytes) -> str   # SHA-256 十六进制字符串
bundle_hash(bundle: Bundle) -> str           # 取 Bundle.main.content 的 hash
```

## Models

### Bundle

文档包，包含一组文件和上下文元数据。

```python
from docupipe.models import Bundle

bundle = Bundle(
    files=[],    # list[FileItem] — 文件列表
    context={},  # dict — 上下文数据，在 source、step、destination 间传递
)

bundle.main           # FileItem | None — role="main" 的文件
bundle.get_by_role(role)  # list[FileItem] — 按 role 筛选
bundle.add(file)      # 添加文件，冲突时自动重命名（image.png → image_1.png）
bundle.remove(name)   # 按名称删除文件
```

### FileItem

```python
from docupipe.models import FileItem

FileItem(
    name="doc.md",              # str — 文件名（可含路径前缀）
    content="hello",            # str | bytes — 文件内容
    content_type="text/markdown", # str — MIME 类型（可选）
    role="main",                # str — "main" | "image" | "attachment"
)
```

### BundleMeta

Source 的 `list()` 返回的文档元数据：

```python
from docupipe.models import BundleMeta

BundleMeta(
    id="node_id",    # str — 唯一标识
    title="标题",     # str — 文档标题
    path="路径",      # str — 相对路径
    hash="",          # str — 内容哈希
    extra={},         # dict — 扩展信息，传递给 fetch()
)
```

### SkipBundle

Source 在 `fetch()` 中抛出此异常表示该文档应被跳过，不中断 pipeline 运行。

```python
from docupipe.models import SkipBundle

raise SkipBundle("不支持的文档类型")
```

## CLI

```bash
python -m docupipe run [OPTIONS]
```

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--config` | string | `docupipe.yaml` | 配置文件路径 |
| `--pipeline` | string | null | 指定运行的 pipeline 名称 |
| `--mode` | `full\|incremental\|mirror` | null | 覆盖配置文件中的 mode |
| `--resume` | flag | false | full 模式下断点续传 |
| `--change-detection` | `mtime\|hash` | null | 覆盖 mirror 模式的变更检测策略 |
| `--dry-run` | flag | false | 只打印不执行 |
| `--state-dir` | string | `./.state` | 状态文件目录 |
| `--log-level` | `DEBUG\|INFO\|WARNING\|ERROR` | `INFO` | 日志级别 |

列出可用组件：

```bash
python -m docupipe sources       # 列出所有 Source
python -m docupipe destinations  # 列出所有 Destination
```

## Bundle Context 字段注册表

Source 和 Step 通过 `Bundle.context` 字典传递数据。新增字段必须先查阅此表。

### Pipeline 注入字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | str | 文档唯一标识 |
| `title` | str | 文档标题 |
| `path` | str | 文档路径 |
| `filename` | str | 文件名 |
| `_source` | str | 来源名称 |
| `hash` | str | 内容 SHA-256 哈希 |
| `_step_progress` | callable | 进度回调（step 执行期间临时存在） |

### 通用字段（多个 Source 共用）

| 字段 | 类型 | 说明 | 写入方 | 读取方 |
|------|------|------|--------|--------|
| `extension` | str | 文件扩展名，不含点号 | Source | ConvertStep |
| `space_name` | str | 知识库/空间名称 | 钉钉/腾讯 Source | Destination |
| `absolute_path` | str | 本地文件绝对路径 | LocalDrive Source | ResolveAttachmentsStep |
| `image_metadata` | dict | 图片描述 AI 处理结果 | ImageDescriptionStep | — |

### Source 特有字段

| 字段 | 类型 | 说明 | 写入方 |
|------|------|------|--------|
| `dingtalk_content_type` | str | 钉钉文档类型枚举（ALIDOC/DOCUMENT） | DingtalkSource |
| `dingtalk_update_time` | int | 钉钉文档更新时间戳（毫秒） | DingtalkSource |
| `dingtalk_node_type` | str | 钉钉节点类型 | DingtalkSource |
| `tencent_doc_type` | str | 腾讯文档类型枚举 | TencentSource |
| `tencent_node_type` | str | 腾讯节点类型 | TencentSource |
| `tencent_has_child` | bool | 腾讯节点是否有子节点 | TencentSource |
