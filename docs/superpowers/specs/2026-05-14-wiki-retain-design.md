# 钉钉知识库同步到 Hindsight 设计文档

## 概述

`docpipe`（原名 dwsdocs-downloader）是一个独立 CLI 工具，用于从钉钉知识库读取内容（在线文档和上传文件），转换为 Markdown 保存到本地，再增量同步到 Hindsight 记忆系统。

项目路径：`~/src/ai/docpipe`

## 核心流程

两步走，与 question-downloader 模式一致：

1. **download**：从钉钉知识库读取内容 → 转 Markdown → 镜像保存到本地
2. **retain**：扫描本地 Markdown → 增量同步到 Hindsight

## CLI 命令

```
dwsdocs-downloader download --space SPACE_ID [--folder FOLDER_ID] --output-dir ./output [--resume]
dwsdocs-downloader retain --output-dir ./output --bank-id BANK_ID [--resume] [--sync] [--dry-run]
```

### download 命令

| 参数 | 必填 | 说明 |
|------|------|------|
| `--space` | 是 | 知识库 ID |
| `--folder` | 否 | 指定文件夹 ID，不传则从知识库根目录开始 |
| `--output-dir` | 否 | 本地输出目录，默认 `./output` |
| `--resume` | 否 | 跳过已下载的文档 |

**流程**：

1. `dws doc list --workspace SPACE --folder FOLDER --format json` 递归遍历节点树
2. 对每个节点调用 `dws doc info --node ID --format json` 获取类型
3. 根据类型分发：
   - **adoc 在线文档**：`dws doc read --node ID` → 直接保存为 `.md`
   - **文件类型**（pdf/docx/xlsx 等）：`dws doc download --node ID` 下载到临时目录 → `markitdown` 转 Markdown → 保存
4. 为每个文档写 `meta.json` sidecar（nodeId、标题、类型、修改时间、来源路径）
5. 目录结构镜像知识库：`output/{space_name}/{folder_path}/{doc_title}.md`

### retain 命令

| 参数 | 必填 | 说明 |
|------|------|------|
| `--output-dir` | 否 | 已下载的数据目录，默认 `./output` |
| `--bank-id` | 否 | Hindsight Bank ID，默认读 `HINDSIGHT_BANK_ID` 环境变量 |
| `--hindsight-url` | 否 | Hindsight API URL，默认读 `HINDSIGHT_API_URL` |
| `--hindsight-key` | 否 | Hindsight API Key，默认读 `HINDSIGHT_API_KEY` |
| `--resume` | 否 | 跳过已上传的文档 |
| `--sync` | 否 | 仅同步有变化的文档（hash 对比） |
| `--dry-run` | 否 | 只打印不执行 |

**流程**：

1. 扫描 `output/` 下所有 `.md` 文件及对应的 `meta.json`
2. 计算每个文档的 content_hash，对比本地状态决定是否需要同步
3. 调用 `Hindsight.retain_batch()` 上传，document_id 为 `wiki:{nodeId}`
4. retain 数据结构：
   - `content`：Markdown 正文
   - `document_id`：`wiki:{nodeId}`
   - `timestamp`：文档修改时间
   - `context`：文件来源描述
   - `tags`：`source:wiki`、知识库名称、文件夹路径层级
   - `metadata`：nodeId、标题、原始类型、来源路径、content_hash

## 项目结构

```
docpipe/
├── pyproject.toml
├── CLAUDE.md
├── dwsdocs_downloader/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py              # Click CLI: download / retain
│   ├── config.py            # 配置管理
│   ├── wiki_client.py       # 封装 dws CLI 调用
│   ├── converter.py         # markitdown 文件转 Markdown
│   ├── downloader.py        # 知识库下载编排
│   ├── retain.py            # 同步到 Hindsight
│   ├── display.py           # 进度/日志展示
│   └── state.py             # 同步状态管理（断点续传）
└── tests/
```

### 模块职责

| 模块 | 职责 |
|------|------|
| `cli.py` | Click 命令组，`download` 和 `retain` 两个子命令 |
| `config.py` | dataclass 配置，环境变量读取 |
| `wiki_client.py` | 封装 `dws` CLI 的 subprocess 调用，返回解析后的 JSON |
| `converter.py` | 调用 `markitdown` 将下载的文件转为 Markdown |
| `downloader.py` | 编排递归遍历、类型分发、下载保存 |
| `retain.py` | 扫描本地 Markdown，构建 retain 数据，调用 Hindsight |
| `display.py` | 进度条和日志输出 |
| `state.py` | JSON 文件持久化的状态管理（已处理 nodeId → hash） |

## 增量同步机制

- `download` 和 `retain` 各自维护状态文件（`download_state.json` 和 `retain_state.json`）
- 状态文件记录：已处理文档的 nodeId → content_hash 映射
- `--sync` 模式对比 hash，仅处理变化的文档
- `--resume` 模式跳过状态中已存在的 nodeId

## Cron 定时同步

```cron
# 每 4 小时同步一次
0 */4 * * * cd ~/src/ai/docpipe && dwsdocs-downloader download --resume --space XXX && dwsdocs-downloader retain --sync
```

## 依赖

| 包 | 用途 |
|-----|------|
| `markitdown[all]` | 微软的文件转 Markdown 库 |
| `hindsight-client` | Hindsight API 客户端 |
| `click` | CLI 框架 |
| `dws`（运行时） | 钉钉知识库 CLI，通过 subprocess 调用 |

## 与现有系统的关系

- 与 `question-downloader` 同级独立项目，不共享代码
- 复用同一个 Hindsight bank，document_id 用前缀区分：`wiki:{nodeId}` vs `question:{qid}`
- 不影响现有工单 retain 流程
