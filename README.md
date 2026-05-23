# docupipe

通用文档传输与处理工具，支持从多种文档源获取内容，经过可配置的处理步骤，传输到多种目标系统。设计受 KETTLE 启发，将文档及其附件作为一个原子包（Bundle），在管道中整体传输、逐步加工。

## 为什么需要 docupipe？

在智能化时代，文档管理面临着诸多挑战：

- **格式转换**：不同系统间的文档格式不兼容
- **内容迁移**：知识库搬迁、系统切换时的批量文档迁移
- **智能处理**：为知识图谱、检索系统准备标准化的文档内容
- **位置搬家**：文档在不同存储系统间的传输

docupipe 为解决这些问题提供了一个通用的、可扩展的框架。

## 核心特性

- **插件式架构**：Source、Destination、Step、Converter 四类可插拔组件
- **YAML 配置**：声明式配置，支持环境变量插值
- **状态管理**：支持断点续传和增量同步
- **多种文档源**：支持钉钉知识库、本地文件系统等
- **多种目标系统**：支持本地文件、HindSight Memory 等
- **格式转换**：集成 markitdown、MinerU 等转换引擎
- **智能处理**：支持图片描述等 AI 处理步骤

## 安装

### 通过 pip 安装（推荐）

```bash
pip install docupipe
```

如需处理内含图片的 PDF（需 OCR 识别），安装可选依赖：

```bash
pip install "docupipe[mineru]"
```

### 通过源代码安装

```bash
# 克隆项目
git clone https://github.com/liling/docupipe.git
cd docupipe

# 安装依赖（推荐使用 uv）
pip install uv
uv pip install -e ".[dev]"

# 如需处理内含图片的 PDF（需 OCR 识别），安装 MinerU 依赖
uv pip install -e ".[mineru]"

# 或安装所有可选依赖
uv pip install -e ".[all]"

# 或使用 pip
pip install -e ".[dev]"
pip install -e ".[mineru]"  # PDF 支持
```

## 快速开始

以下示例使用本地文件作为数据源和目标，无需任何外部依赖。

### 1. 准备配置文件

创建 `docupipe.yaml`：

```yaml
pipelines:
  - name: quick-start
    source:
      localdrive:
        input_dir: ./input
        include: ["*.md"]
    destination:
      localdrive:
        output_dir: ./output
    steps: []
```

### 2. 准备测试文件

```bash
mkdir -p input output
echo "你好，docupipe！" > input/hello.md
```

### 3. 运行 pipeline

```bash
python -m docupipe run
```

查看输出：

```bash
cat output/hello.md
```

## 命令行参数

```bash
python -m docupipe run [OPTIONS]

选项：
  --config PATH              配置文件路径（默认：docupipe.yaml）
  --pipeline NAME            指定 pipeline 名称
  --mode MODE                运行模式（full/incremental/mirror）
  --resume                   full 模式断点续传
  --change-detection STRATEGY  变更检测策略（mtime/hash，仅 mirror 模式）
  --dry-run                  只打印不执行
  --state-dir PATH           状态文件目录（默认：./.state）
  --log-level LEVEL          日志级别（DEBUG/INFO/WARNING/ERROR）

# 列出可用组件
python -m docupipe sources       # 列出所有 Source
python -m docupipe destinations  # 列出所有 Destination
python -m docupipe plugins       # 列出所有已加载的插件
```

## 配置说明

### 全局配置

```yaml
# HindSight Memory 配置
hindsight:
  api_url: ${HINDSIGHT_API_URL}
  api_key: ${HINDSIGHT_API_KEY}
  bank_id: ${HINDSIGHT_BANK_ID}

# 图片描述配置
image_description:
  api_key: ${IMAGE_DESCRIPTION_API_KEY}
  base_url: ${IMAGE_DESCRIPTION_BASE_URL}
  model: ${IMAGE_DESCRIPTION_MODEL:-gpt-4o}

# 文件类型转换规则
converters:
  extensions:
    ".pdf": mineru
    ".docx": markitdown
    ".pptx": markitdown
```

### Pipeline 配置

每个 pipeline 包含：

- `source`：数据源配置
- `destination`：目标配置
- `steps`：处理步骤列表
- `options`：可选配置（resume、sync 等）

### 环境变量

创建 `.env` 文件（仅在使用 HindSight Memory 或图片描述时需要）：

```bash
# HindSight Memory 配置
HINDSIGHT_API_URL=http://localhost:8888
HINDSIGHT_API_KEY=your_api_key
HINDSIGHT_BANK_ID=your_bank_id

# 图片描述 API 配置
IMAGE_DESCRIPTION_API_KEY=your_api_key
IMAGE_DESCRIPTION_BASE_URL=http://localhost:8002/v1
IMAGE_DESCRIPTION_MODEL=gpt-4o
```

### 环境变量插值

支持 `${VAR}` 和 `${VAR:-default}` 语法：

```yaml
api_key: ${API_KEY}                          # 必须设置
model: ${MODEL:-gpt-4o}                      # 默认值
base_url: ${BASE_URL:-http://localhost:8080} # 默认值
```

## 使用场景

### 场景 1：从钉钉知识库下载文档到本地

使用钉钉知识库前，需安装 `dws`（钉钉官方 CLI）并完成认证：

```bash
# 安装 dws（macOS / Linux）
curl -fsSL https://raw.githubusercontent.com/DingTalk-Real-AI/dingtalk-workspace-cli/main/scripts/install.sh | sh

# 或通过 npm 安装
npm install -g dingtalk-workspace-cli

# 认证（浏览器扫码）
dws auth login

# 无头环境使用设备流
dws auth login --device
```

> 如果组织未开启 CLI 访问权限，扫码后可按提示向管理员申请。管理员在钉钉开放平台 → "CLI 访问管理" 中开启即可。

配置 pipeline：

```yaml
pipelines:
  - name: dingtalk-download
    source:
      dingtalk:
        # 支持使用知识库名称（程序自动查询 ID）
        space: "产品知识库"
        # 或者直接使用 space_id
        # space_id: "kfiwoue83nkxQXyA"
        folders: ["产品规划物料"]
        include_types: [DOCUMENT, ALIDOC]
    destination:
      localdrive:
        output_dir: ./output/dingtalk
    steps: []
```

```mermaid
flowchart LR
    A[钉钉知识库] --> B[下载文档]
    B --> C[本地目录]
```

### 场景 2：本地文档格式转换

```yaml
pipelines:
  - name: convert-docs
    source:
      localdrive:
        input_dir: ./output/dingtalk
        include: ["*.docx"]
    destination:
      localdrive:
        output_dir: ./output/markdown
    steps:
      - convert          # 转换为 markdown
      - image_description # 为图片添加描述
```

```mermaid
flowchart LR
    A[本地 .docx] --> B[格式转换]
    B --> C[图片描述]
    C --> D[本地 .md]
```

### 场景 3：本地文档写入 HindSight Memory

```yaml
pipelines:
  - name: to-hindsight
    source:
      localdrive:
        input_dir: ./output/markdown
        include: ["*.md"]
    destination:
      hindsight:
        context_prefix: "产品知识库"
    steps: []
```

```mermaid
flowchart LR
    A[本地 .md] --> B[上传到记忆库]
    B --> C[HindSight]
```

### 场景 4：ALL IN ONE

```yaml
pipelines:
  - name: full-pipeline
    source:
      dingtalk:
        space: "产品知识库"
    destination:
      hindsight:
        context_prefix: "知识库"
    steps:
      - convert
      - image_description
```

```mermaid
flowchart LR
    A[钉钉文档] --> B[格式转换]
    B --> C[图片描述]
    C --> D[HindSight]
```

## 可用组件

### Source（数据源）

- `dingtalk`：钉钉知识库（wiki/doc 双模式）
- `localdrive`：本地文件系统
- `tencent`：腾讯文档（MCP 协议）

### Destination（目标）

- `localdrive`：本地文件系统
- `hindsight`：HindSight Memory

### Step（处理步骤）

- `convert`：文档格式转换（调用 Converter）
- `image_description`：AI 图片描述
- `excel_structured`：Excel → 结构化 Markdown 表格
- `resolve_attachments`：解析 Markdown 中引用的本地文件
- `s3_upload`：上传附件到 S3 兼容存储
- `tencent_delete`：删除已处理的腾讯文档（放 finalize_steps）

### Converter（转换器）

- `markitdown`：支持常见办公文档
- `mineru`：高质量 PDF 转换（支持 OCR）

## 插件系统

docupipe 支持通过插件扩展 Source、Destination、Step、Converter 四类组件，无需修改核心代码。

### 加载方式

插件通过两阶段加载：

- **阶段 1（import 时）**：自动扫描已安装包的 `docupipe.plugins` entry_points，通过 `pip install` 安装的插件在此阶段生效
- **阶段 2（运行时）**：加载 YAML 配置中 `plugin_dirs` 指定的目录和约定目录 `~/.docupipe/plugins/`，支持 `.py` 文件或包含 `__init__.py` 的包

### 配置方式

在 YAML 配置的顶层添加 `plugin_dirs`：

```yaml
plugin_dirs:
  - ./my-plugins           # 相对于 CWD 的目录
  - ~/team-plugins         # 用户目录下的目录

pipelines:
  - name: with-plugins
    source:
      custom_source: {}    # 插件注册的 source
    ...
```

### 编写插件

插件 `.py` 文件使用标准装饰器注册组件：

```python
# my-plugins/custom_source.py
from docupipe.models import Bundle, BundleMeta
from docupipe.sources import register_source
from docupipe.sources.base import SourceBase

@register_source("custom_source")
class CustomSource(SourceBase):
    def list(self) -> list[BundleMeta]:
        ...
    def fetch(self, meta: BundleMeta) -> Bundle:
        ...
```

支持 `.py` 文件和包含 `__init__.py` 的包两种形式。以 `_` 开头的文件被自动跳过。

### 发布为 pip 包

在插件的 `pyproject.toml` 中注册 entry_point：

```toml
[project.entry-points."docupipe.plugins"]
my_plugin = "my_plugin:register"
```

`register` 函数内部调用 `register_source`/`register_destination`/`register_step`/`register_converter` 注册组件。

### 冲突检测

同名组件注册时抛出 `ValueError`，错误信息显示冲突双方的来源（如 `built-in` 与 `file:/path/to/plugin.py`），便于定位。

### CLI 查看

```bash
# 查看所有已加载的插件及其注册的组件
python -m docupipe plugins

# 查看组件时显示来源（built-in 或 plugin）
python -m docupipe sources
python -m docupipe destinations
```

## 状态管理

docupipe 为每个 source-dest 组合维护状态文件（`{source}_{dest}_state.json`），记录：

- 已处理的文档 ID
- 文档哈希值（用于变更检测）

### 运行模式

- **full**：调用 `source.list()` 获取全部文档，逐个处理
- **full + --resume**：不调 list()，从状态文件找 pending 继续处理
- **incremental**：全量列举，只处理新增文档
- **mirror**：检测变更（mtime/hash） + 清理已删除的文档

## 架构

```
source.list() → [BundleMeta]
  → 过滤（resume 跳过已处理 / incremental 仅新增 / mirror 检测变更）
    → source.fetch(meta) → Bundle
      → steps 依次处理（convert → image_description → ...）
        → dest.write(bundle)
          → state.mark_done()
            → post_steps（可选，如删除源头）
全部文档完成后：
  → finalize_steps（批量后处理，如腾讯文档删除）
```

## 开发

### 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行单个测试文件
python -m pytest tests/test_pipeline.py -v
```

### 添加内置组件

所有组件使用装饰器注册，添加内置组件只需三步：

1. **实现抽象基类**
2. **添加装饰器**：`@register_source("name")`
3. **在 `__init__.py` 中 import**

示例（Source）：

```python
# sources/custom.py
from docupipe.models import Bundle, BundleMeta
from docupipe.sources import register_source
from docupipe.sources.base import SourceBase

@register_source("custom")
class CustomSource(SourceBase):
    def list(self) -> list[BundleMeta]:
        ...
    def fetch(self, meta: BundleMeta) -> Bundle:
        ...
```

### 添加外部插件

外部插件使用相同的装饰器，但无需修改核心代码。参见上方「插件系统」章节。

详细文档参见 [如何添加新组件](docs/howto-add-component.md)。

## 文档

详细文档请参见 [docs/](docs/index.md) 目录：

| 类型 | 文档 |
|------|------|
| 📖 教程 | [快速入门](docs/tutorial-quick-start.md) — 从钉钉知识库同步到 Hindsight Memory |
| 📋 操作指南 | [配置 Pipeline](docs/howto-configure.md)、[添加新组件](docs/howto-add-component.md) |
| 📚 参考 | [配置系统](docs/reference-configuration.md)、[API 参考](docs/reference-api.md)、[组件 API](docs/reference-components.md) |
| 💡 解释 | [架构设计](docs/explanation-architecture.md)、[运行模式](docs/explanation-modes.md) |

## 依赖

- Python 3.11+
- Click（CLI 框架）
- Rich（终端输出）
- PyYAML（配置解析）
- markitdown（文档转换）
- MinerU（内含图片的 PDF OCR 转换）
- hindsight-client（HindSight Memory 客户端）
- OpenAI SDK（图片描述）

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
