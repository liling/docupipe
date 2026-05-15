# CLAUDE.md

## 项目概述

`docpipe` 是一个通用文档传输 pipeline 工具，支持从多种文档源获取内容，传输到多种目标系统。
采用插件式架构：Source 和 Destination 各自定义抽象接口，Pipeline 负责编排和状态管理。

## 开发命令

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行全部测试
python -m pytest tests/ -v

# 运行 CLI
python -m docpipe --help
python -m docpipe run --source dingtalk --dest hindsight --space SPACE_ID
python -m docpipe run --source local --dest hindsight --input-dir ./docs
python -m docpipe run --config docpipe.yaml
```

## 架构

插件式 Pipeline 架构：

- **Source**（文档源）：实现 `list_documents()` 和 `fetch()` 接口
- **Destination**（目标系统）：实现 `write()` 和 `remove()` 接口
- **Pipeline**：编排 Source → Destination 数据流 + 状态管理

```
docpipe/
├── models.py             # DocumentMeta, Document 数据模型
├── pipeline.py           # Pipeline 编排 + StateManager
├── cli.py                # Click CLI 入口
├── display.py            # 进度条和日志输出
├── sources/
│   ├── base.py           # SourceBase 抽象基类
│   ├── dingtalk.py       # 钉钉知识库 Source
│   └── local.py          # 本地文件夹 Source
├── destinations/
│   ├── base.py           # DestinationBase 抽象基类
│   ├── hindsight.py      # Hindsight Destination
│   └── feishu.py         # 飞书知识库（预留）
```

### 注册表机制

Source 和 Destination 通过装饰器注册：
```python
@register_source("dingtalk")
class DingtalkSource(SourceBase): ...
```

### CLI 用法

```bash
# CLI 参数方式
docpipe run --source dingtalk --dest hindsight --space SPACE_ID --resume

# YAML 配置文件方式
docpipe run --config docpipe.yaml --pipeline wiki-to-hindsight
```

### 状态管理

每个 Source-Destination 组合各自维护状态文件：`{source_name}_{dest_name}_state.json`
支持 `--resume`（跳过已处理）和 `--sync`（仅同步有变化 + 移除已删除）模式。

## 技术栈

- Python 3.11+
- Click（CLI）、markitdown（文件转 Markdown）、hindsight-client（Hindsight API）
- 运行时依赖：dws CLI（钉钉知识库操作）
- 测试：pytest + unittest.mock

## 环境变量

- `HINDSIGHT_API_URL`、`HINDSIGHT_API_KEY`、`HINDSIGHT_BANK_ID`：Hindsight 服务连接

## 约定

- 提交信息使用中文描述 + `feat:`/`fix:` 前缀
- 状态文件保存在 `--state-dir` 目录下（默认 `./.state/`）
- 新增 Source/Destination 只需实现接口 + 加注册装饰器
