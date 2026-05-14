# docpipe：通用文档传输 Pipeline 架构设计

## 概述

将 `dwsdocs-downloader`（钉钉文档下载器）重新设计为 `docpipe`——一个通用的文档传输 pipeline 工具。支持从多种文档源获取内容，传输到多种目标系统。

核心思路：Source 和 Destination 各自定义抽象接口，Pipeline 负责编排数据流和状态管理。不做强制中间格式，每个 Source-Destination 组合自行决定转换逻辑。

## 当前范围

- **Source**：钉钉知识库、本地文件夹
- **Destination**：Hindsight、飞书知识库（预留）
- 近期飞书知识库作为 Destination 也是需要的，具体实现细节后续再定

## 数据模型

```python
@dataclass
class DocumentMeta:
    id: str                # 源系统中的唯一 ID
    title: str
    path: str              # 源中的路径（如目录结构）
    hash: str              # 内容 hash，用于增量判断
    extra: dict            # 源特有字段（钉钉的 node_type、update_time 等）

@dataclass
class Document:
    meta: DocumentMeta
    content: str | bytes   # 文档内容
    content_type: str      # "markdown"、"html"、"binary" 等
```

`DocumentMeta.extra` 是源特有字段，不做统一抽象，由 Destination 自行解读。

## Source 接口

```python
class SourceBase(ABC):
    @abstractmethod
    def list_documents(self) -> list[DocumentMeta]:
        """列出所有可获取的文档及其元信息"""

    @abstractmethod
    def fetch(self, doc_meta: DocumentMeta) -> Document:
        """获取单个文档的完整内容"""
```

- `list_documents()` 轻量，只返回元信息，用于增量判断
- `fetch()` 按需获取单个文档，由 Pipeline 决定是否调用

## Destination 接口

```python
class DestinationBase(ABC):
    @abstractmethod
    def write(self, doc: Document) -> str:
        """写入单个文档，返回目标系统中的 ID"""

    @abstractmethod
    def remove(self, doc_id: str) -> None:
        """删除单个文档（用于 sync 模式清理已移除的文档）"""
```

- `remove()` 可选实现——某些目标不支持自动删除，可跳过
- 增量逻辑由 Pipeline 通过状态文件判断，不需要回查目标系统

## Pipeline 编排

```python
class Pipeline:
    def __init__(self, source: SourceBase, dest: DestinationBase, state_dir: Path):
        self.source = source
        self.dest = dest
        self.state = StateManager(state_dir / f"{source.name}_{dest.name}_state.json")

    def run(self, *, resume: bool = False, sync: bool = False):
        docs = self.source.list_documents()

        if resume:
            docs = [d for d in docs if not self.state.is_processed(d.id)]

        for doc_meta in docs:
            if sync and self.state.is_unchanged(doc_meta.id, doc_meta.hash):
                continue

            doc = self.source.fetch(doc_meta)
            self.dest.write(doc)
            self.state.mark_done(doc_meta.id, doc_meta.hash)

        if sync:
            removed = self.state.find_removed([d.id for d in docs])
            for doc_id in removed:
                self.dest.remove(doc_id)
                self.state.mark_removed(doc_id)
```

Pipeline 不关心内容格式，只负责：列出 → 过滤 → 获取 → 写入 → 记录状态。

### 状态文件

每个 Source-Destination 组合各自维护，格式：

```json
{
  "doc_001": { "hash": "abc123" },
  "doc_002": { "hash": "def456" }
}
```

文件按 `{source_name}_{dest_name}_state.json` 命名。

## CLI 和配置文件

### CLI 方式

```bash
# 从钉钉知识库同步到 Hindsight
docpipe run --source dingtalk --dest hindsight --space SPACE_ID

# 从本地文件夹同步到 Hindsight
docpipe run --source local --dest hindsight --input-dir ./docs

# 增量 / 同步模式
docpipe run --source dingtalk --dest hindsight --space SPACE_ID --resume
docpipe run --source dingtalk --dest hindsight --space SPACE_ID --sync

# 列出可用的 source 和 destination
docpipe sources
docpipe destinations
```

### 配置文件方式

```yaml
# docpipe.yaml
pipelines:
  - name: wiki-to-hindsight
    source: dingtalk
    destination: hindsight
    source_config:
      space_id: "xxx"
    dest_config:
      bank_id: "yyy"
      context_prefix: "wiki"
    options:
      resume: true
      sync: true

  - name: local-to-hindsight
    source: local
    destination: hindsight
    source_config:
      input_dir: "./docs"
    dest_config:
      bank_id: "yyy"
```

```bash
# 运行配置文件中的所有 pipeline
docpipe run --config docpipe.yaml

# 运行配置文件中指定的 pipeline
docpipe run --config docpipe.yaml --pipeline wiki-to-hindsight
```

Source/Destination 各自定义自己接受的 `source_config` / `dest_config` 参数。Source 特有参数（如 `space_id`）通过 `source_config` 传递，不污染 CLI 顶层。

## 项目结构

```
docpipe/
├── docpipe/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py               # Click CLI 入口
│   ├── pipeline.py           # Pipeline 编排 + StateManager
│   ├── models.py             # DocumentMeta, Document
│   ├── sources/
│   │   ├── __init__.py       # 注册表：name → class
│   │   ├── base.py           # SourceBase
│   │   ├── dingtalk.py       # 钉钉知识库
│   │   └── local.py          # 本地文件夹
│   ├── destinations/
│   │   ├── __init__.py       # 注册表：name → class
│   │   ├── base.py           # DestinationBase
│   │   ├── hindsight.py      # Hindsight
│   │   └── feishu.py         # 飞书知识库（预留）
│   └── display.py            # 进度条
├── tests/
├── pyproject.toml
└── CLAUDE.md
```

## 注册表机制

```python
# sources/__init__.py
SOURCES: dict[str, type[SourceBase]] = {}

def register_source(name: str):
    def decorator(cls):
        SOURCES[name] = cls
        return cls
    return decorator

# sources/dingtalk.py
@register_source("dingtalk")
class DingtalkSource(SourceBase):
    ...
```

Destination 同理。CLI 通过 `SOURCES[source_name]` 查找并实例化。

## 代码迁移

| 现有模块 | 迁移去向 | 说明 |
|---------|---------|------|
| `wiki_client.py` | `sources/dingtalk.py` | WikiClient 成为 DingtalkSource 的内部实现 |
| `downloader.py` | `sources/dingtalk.py` | 目录遍历逻辑，但不再直接写文件，改为产出 Document |
| `converter.py` | `sources/dingtalk.py` | markitdown 转换逻辑内嵌到 fetch() |
| `retain.py` | `destinations/hindsight.py` | RetainRunner 的逻辑成为 HindsightDestination.write() |
| `state.py` | `pipeline.py` | StateManager 移入 Pipeline |
| `display.py` | `display.py` | 基本不变 |
| `config.py` | 删除 | 配置通过 CLI / YAML 传入 |

## 不做的事

- 飞书 Destination 只预留空文件，不实现
- 不做 pipeline 的并行执行
- 不做 dry-run 以外的执行模式
