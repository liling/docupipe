# CLAUDE.md

## 项目概述

`dwsdocs-downloader` 是一个 Python CLI 工具，用于从钉钉知识库读取内容（在线文档和上传文件），
转换为 Markdown 保存到本地，再增量同步到 Hindsight 记忆系统。

## 开发命令

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行全部测试
python -m pytest tests/ -v

# 运行单个测试文件
python -m pytest tests/test_state.py -v

# 运行 CLI
python -m dwsdocs_downloader --help
python -m dwsdocs_downloader download --space SPACE_ID --output-dir ./output
python -m dwsdocs_downloader retain --output-dir ./output
```

## 架构

两层独立流水线：

1. **Download 流水线**：钉钉知识库 → 本地 Markdown（`download` 命令）
   - 递归遍历知识库目录结构，按原目录组织输出
   - 每个文档保存为 `{title}.md` + `{title}.meta.json`
   - 状态文件记录 node_id → content_hash 映射（`output/.state/download_state.json`）

2. **Retain 流水线**：本地 Markdown → Hindsight（`retain` 命令）
   - 扫描所有 `.meta.json` 获取文档元信息
   - 根据 hash 判断是否需要同步（`--sync` 模式）
   - 状态文件记录 node_id → content_hash 映射（`output/.state/retain_state.json`）

| 模块 | 类 | 职责 |
|------|-----|------|
| `config.py` | `Config` | dataclass 配置（当前未使用） |
| `display.py` | `Display` | 进度条和日志输出 |
| `state.py` | `StateManager` + `content_hash` | JSON 状态文件读写、文件 hash 计算 |
| `wiki_client.py` | `WikiClient` | 封装 dws CLI 调用（subprocess → JSON） |
| `converter.py` | `FileConverter` | markitdown 文件转 Markdown |
| `downloader.py` | `Downloader` + `sanitize_filename` | 递归遍历知识库 + 类型分发 + 保存 |
| `retain.py` | `RetainRunner` | 扫描本地 Markdown → Hindsight retain |
| `cli.py` | - | Click CLI 入口 |

CLI 通过 Click 框架组织，支持两个子命令：
- `download`：从钉钉知识库下载内容到本地 Markdown
- `retain`：将本地 Markdown 增量同步到 Hindsight

### 关键行为

- `download --resume`：基于 state 文件跳过已下载的文档
- `retain --resume`：跳过已上传的文档（基于 state 文件）
- `retain --sync`：基于内容 hash 判断是否需要同步（更精确的增量）

## 技术栈

- Python 3.11+
- Click（CLI）、markitdown（文件转 Markdown）、hindsight-client（Hindsight API）
- 运行时依赖：dws CLI（钉钉知识库操作）
- 测试：pytest + unittest.mock

## 环境变量

- `HINDSIGHT_API_URL`、`HINDSIGHT_API_KEY`、`HINDSIGHT_BANK_ID`：Hindsight 服务连接

## 约定

- 提交信息使用中文描述 + `feat:`/`fix:` 前缀
- 输出目录默认 `./output/`
- 状态文件保存在 `{知识库名}/.state/` 下（每个知识库独立）
- document_id 前缀 `wiki:` 区分于 question-downloader 的 `question:`
