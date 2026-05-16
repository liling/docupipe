# Bundle 模型设计：统一 Pipeline 数据流

## 背景

当前 pipeline 中 source → step → ... → dest 之间传递的是单个 `Document` 对象，存在以下问题：

1. **附件支持隐式**：内联图片等附件通过 temp path + `meta.extra` 传递，缺乏正式的数据结构
2. **上下文传递黑箱**：step 之间通过 `meta.extra` dict 共享状态，键名约定无约束，容易冲突和误用
3. **组件模型不统一**：source/step/dest 传递的数据类型虽然都是 Document，但语义差异大（source 产出原始内容，step 逐步修改，dest 消费最终结果）
4. **单文档限制**：无法自然表达"主文档 + 附件包"的语义

## 设计目标

- 传递单元从单个 Document 改为 **Bundle（文档包）**，显式包含主文档 + 附件
- 每个文件附带 **role + metadata**，提供文件级元信息
- 用 `bundle.context` 替代 `meta.extra`，给跨 step 通信一个正式的家
- source/step/dest 保持各自角色（数据统一，角色不同），不过度抽象

## 核心数据模型

```python
@dataclass
class FileItem:
    name: str                    # 文件标识，如 "index.md"、"image_001.png"
    content: str | bytes         # 文件内容
    content_type: str = ""       # MIME 类型，如 "text/markdown"、"image/png"
    role: str = "main"           # 语义角色：main / attachment / image / thumbnail 等
    metadata: dict = field(default_factory=dict)  # 文件级扩展信息

@dataclass
class Bundle:
    files: list[FileItem] = field(default_factory=list)
    context: dict = field(default_factory=dict)    # 跨 step 全局上下文

    @property
    def main(self) -> FileItem | None:
        """获取 role=main 的主文件"""
        return next((f for f in self.files if f.role == "main"), None)

    def get_by_role(self, role: str) -> list[FileItem]:
        """按角色筛选文件"""
        return [f for f in self.files if f.role == role]

    def add(self, file: FileItem) -> None:
        self.files.append(file)

    def remove(self, name: str) -> None:
        self.files = [f for f in self.files if f.name != name]

@dataclass
class BundleMeta:
    id: str                      # 文档包唯一标识
    title: str                   # 标题
    hash: str = ""               # 内容哈希
    extra: dict = field(default_factory=dict)
```

**设计决策**：

- `FileItem.role` 是字符串而非枚举，保持扩展性
- `Bundle.context` 替代原来的 `meta.extra`，明确用于跨 step 通信
- `Bundle` 提供便捷方法（`main`、`get_by_role`），但 `files` 列表是真相来源
- `BundleMeta` 用于 `list` 阶段，轻量不含内容

## 组件接口

```python
class SourceBase(ABC):
    name: str = ""

    @abstractmethod
    def list(self) -> list[BundleMeta]:
        """列出可获取的文档包"""

    @abstractmethod
    def fetch(self, meta: BundleMeta) -> Bundle:
        """获取完整文档包"""

class PipelineStep(ABC):
    name: str = ""

    @abstractmethod
    def process(self, bundle: Bundle) -> Bundle:
        """处理文档包，返回处理后的文档包"""

class DestinationBase(ABC):
    name: str = ""

    @abstractmethod
    def write(self, bundle: Bundle) -> str:
        """写入文档包，返回目标系统中的 ID"""

    def remove(self, bundle_id: str) -> None:
        """删除文档包（可选实现）"""
```

三个组件接口签名不变，只是数据类型从 `Document`/`DocumentMeta` 换成 `Bundle`/`BundleMeta`。Source 仍然只产不消费，Dest 仍然只消费不产出。

## Pipeline 执行流程

```
Pipeline.run():
    1. source.list()                    → list[BundleMeta]
    2. 过滤（resume 跳过 / sync 仅变更）
    3. for meta in bundle_metas:
           bundle = source.fetch(meta)   → Bundle
           for step in steps:
               bundle = step.process(bundle)  → Bundle
           dest.write(bundle)
           state.mark_done()
```

### 数据流示例（Wiki 文档 → Hindsight）

```
Source.fetch() → Bundle:
  files: [FileItem("page.html", role="main")]
  context: {source_url: "..."}

ConvertStep.process() → Bundle:
  files: [
    FileItem("page.md", role="main", content_type="text/markdown"),
    FileItem("image_001.png", role="image"),
    FileItem("image_002.png", role="image"),
  ]
  context: {source_url: "...", converted_from: "html"}

ImageDescriptionStep.process() → Bundle:
  files: [
    FileItem("page.md", role="main", content_type="text/markdown"),
    FileItem("image_001.png", role="image", metadata={description: "..."}),
    FileItem("image_002.png", role="image", metadata={description: "..."}),
  ]

Dest.write() → 写入目标系统
```

## 迁移策略

### 删除

- `Document`、`DocumentMeta` 两个类

### Source 改动

| 组件 | 改动 |
|------|------|
| `ListdwsSource` | `list() → list[BundleMeta]`，`fetch(meta) → Bundle`。原来 fetch 返回的 content 放进 `FileItem(role="main")` |

### Step 改动

| 组件 | 改动 |
|------|------|
| `ConvertStep` | `process(bundle)` 中从 `bundle.main` 取主文件，转换后替换 content，提取的图片作为 `FileItem(role="image")` 加入 bundle。删掉 `_temp_file`、`_images_dir` 等 extra 约定 |
| `ImageDescriptionStep` | 从 `bundle.get_by_role("image")` 取图片文件，不再依赖 meta.extra 中的路径。描述结果写入 FileItem.metadata |

### Dest 改动

| 组件 | 改动 |
|------|------|
| `HindsightDest` | `write(bundle)` 从 `bundle.main` 取主内容写入，图片附件按需上传 |

### 不需要改的

- 配置系统（YAML 结构不变，组件名不变）
- 状态管理（StateManager 只关心 BundleMeta.id 和 hash）
- 注册机制（装饰器模式不变）

## 与当前设计的对比

| 维度 | 当前 | 新设计 |
|------|------|--------|
| 传递单元 | 单个 Document | Bundle（文件包） |
| 上下文传递 | `meta.extra` 黑箱 | `bundle.context` 结构化 |
| 附件支持 | 隐式（temp path + extra） | 显式（FileItem 列表） |
| Source 产出 | 单个 content + meta | 可包含主文档 + 内联图片 + 附件 |
| Step 产出 | 原地修改 Document | 可新增/删除 FileItem，修改 content |
| 文件级元信息 | 无 | FileItem.role + FileItem.metadata |
