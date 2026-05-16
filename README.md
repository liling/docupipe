# docpipe

通用文档传输 pipeline 工具，支持从多种文档源获取内容，经过可配置的处理步骤，传输到多种目标系统。

## 为什么需要 docpipe？

在智能化时代，文档管理面临着诸多挑战：

- **格式转换**：不同系统间的文档格式不兼容
- **内容迁移**：知识库搬迁、系统切换时的批量文档迁移
- **智能处理**：为知识图谱、检索系统准备标准化的文档内容
- **位置搬家**：文档在不同存储系统间的传输

docpipe 为解决这些问题提供了一个通用的、可扩展的框架。

## 核心特性

- **插件式架构**：Source、Destination、Step、Converter 四类可插拔组件
- **YAML 配置**：声明式配置，支持环境变量插值
- **状态管理**：支持断点续传和增量同步
- **多种文档源**：支持钉钉知识库、本地文件系统等
- **多种目标系统**：支持本地文件、HindSight Memory 等
- **格式转换**：集成 markitdown、MinerU 等转换引擎
- **智能处理**：支持图片描述等 AI 处理步骤

## 安装

```bash
# 克隆项目
git clone <repository-url>
cd docpipe

# 安装依赖（推荐使用 uv）
pip install uv
uv pip install -e ".[dev]"

# 如需处理 PDF 文件，安装 MinerU 依赖
uv pip install -e ".[mineru]"

# 或安装所有可选依赖
uv pip install -e ".[all]"

# 或使用 pip
pip install -e ".[dev]"
pip install -e ".[mineru]"  # PDF 支持
```

### 环境变量

创建 `.env` 文件：

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

## 快速开始

### 1. 创建配置文件

复制示例配置并根据需要修改：

```bash
cp docpipe.example.yaml docpipe.yaml
```

### 2. 运行 pipeline

```bash
# 运行默认配置文件
python -m docpipe run

# 指定配置文件
python -m docpipe run --config custom.yaml

# 运行特定 pipeline
python -m docpipe run --pipeline dingtalk-download
```

## 使用场景

### 场景 1：从钉钉知识库下载文档到本地

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

### 环境变量插值

支持 `${VAR}` 和 `${VAR:-default}` 语法：

```yaml
api_key: ${API_KEY}                          # 必须设置
model: ${MODEL:-gpt-4o}                      # 默认值
base_url: ${BASE_URL:-http://localhost:8080} # 默认值
```

## 可用组件

### Source（数据源）

- `dingtalk`：钉钉知识库
- `localdrive`：本地文件系统

### Destination（目标）

- `localdrive`：本地文件系统
- `hindsight`：HindSight Memory

### Step（处理步骤）

- `convert`：文档格式转换
- `image_description`：图片描述生成

### Converter（转换器）

- `markitdown`：支持常见办公文档
- `mineru`：高质量 PDF 转换

## 命令行参数

```bash
# 运行 pipeline
python -m docpipe run [OPTIONS]

选项：
  --config PATH              配置文件路径（默认：docpipe.yaml）
  --pipeline NAME            指定 pipeline 名称
  --resume                   跳过已处理的文档
  --sync                     仅同步有变化的文档
  --dry-run                  只打印不执行
  --state-dir PATH           状态文件目录（默认：./.state）
  --log-level LEVEL          日志级别（DEBUG/INFO/WARNING/ERROR）

# 列出可用组件
python -m docpipe sources       # 列出所有 Source
python -m docpipe destinations  # 列出所有 Destination
```

## 状态管理

docpipe 为每个 source-dest 组合维护状态文件（`{source}_{dest}_state.json`），记录：

- 已处理的文档 ID
- 文档哈希值（用于变更检测）

### 运行模式

- **默认模式**：处理所有文档
- **--resume**：跳过已处理的文档
- **--sync**：仅同步有变化的文档，删除源中已移除的文档

## 开发

### 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行单个测试文件
python -m pytest tests/test_pipeline.py -v
```

### 添加新组件

所有组件使用装饰器注册，添加新组件只需三步：

1. **实现抽象基类**
2. **添加装饰器**：`@register_source("name")`
3. **在 __init__.py 中 import**

示例：

```python
# sources/custom.py
from docpipe.sources.base import BaseSource
from docpipe.sources import register_source

@register_source("custom")
class CustomSource(BaseSource):
    def list_documents(self):
        # 实现文档列表逻辑
        pass

    def fetch(self, meta):
        # 实现文档获取逻辑
        pass
```

## 架构

```
source.list_documents() → [DocumentMeta]
  → 过滤（resume 跳过已处理 / sync 仅同步变更）
    → source.fetch(meta) → Document
      → steps 依次处理（convert → image_description → ...）
        → dest.write(doc)
          → state.mark_done()
```

## 依赖

- Python 3.11+
- Click（CLI 框架）
- Rich（终端输出）
- PyYAML（配置解析）
- markitdown（文档转换）
- hindsight-client（HindSight Memory 客户端）
- OpenAI SDK（图片描述）

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
