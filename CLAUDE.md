# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

`docupipe` 是一个通用文档传输 pipeline 工具，支持从多种文档源获取内容，经过可配置的处理步骤，传输到多种目标系统。采用插件式架构。

## 开发命令

```bash
pip install -e ".[dev]"

# 运行全部测试
python -m pytest tests/ -v

# 运行单个测试文件
python -m pytest tests/test_pipeline.py -v

# 运行 CLI（必须通过 YAML 配置文件启动）
python -m docupipe run                         # 默认读取 docupipe.yaml
python -m docupipe run --config other.yaml     # 指定配置文件
python -m docupipe run --pipeline wiki-to-hs   # 指定 pipeline 名称
```

## 架构

插件式 Pipeline 架构，四类可插拔组件，统一使用装饰器注册：

- **Source**（`sources/`）：实现 `list_documents()` + `fetch()` → 从外部系统获取文档
- **Destination**（`destinations/`）：实现 `write()` + `remove()` → 写入目标系统
- **Step**（`steps/`）：实现 `process(doc) → doc` → 文档处理步骤（格式转换、图片描述等）
- **Converter**（`converters/`）：实现 `convert(file_path) → markdown` → 具体的文件格式转换

注册模式：`@register_source("name")` 装饰器 + 模块级 `SOURCES` 字典 + `__init__.py` 中 import 触发注册。

所有组件共享相同注册模式，新增组件只需：实现抽象基类 + 加装饰器 + 在 `__init__.py` 中 import。

## 数据流

```
source.list_documents() → [DocumentMeta]
  → 过滤（resume 跳过已处理 / sync 仅同步变更）
    → source.fetch(meta) → Document
      → steps 依次处理（convert → image_description → ...）
        → dest.write(doc)
          → state.mark_done()
```

## 配置系统

仅支持 YAML 配置文件方式启动（`--config` 默认值 `docupipe.yaml`）。

配置结构：全局默认值 + `pipelines` 列表。每个 pipeline 定义 `source`、`destination`、`steps`。
支持环境变量插值：`${VAR}` 和 `${VAR:-default}`。
组件配置自动与全局默认值 deep merge（pipeline 级覆盖全局级）。

## 状态管理

`StateManager` 为每个 source-dest 组合维护 JSON 状态文件（`{source}_{dest}_state.json`），记录已处理文档 ID 和 hash。
`--resume` 跳过已处理，`--sync` 仅同步变更并移除源中已删除的文档。

## 技术栈

Python 3.11+ / Click / Rich / PyYAML / markitdown / hindsight-client / OpenAI SDK
运行时依赖：`dws` CLI（钉钉知识库操作，通过 subprocess 调用）
测试：pytest + unittest.mock

## 环境变量

- `HINDSIGHT_API_URL`、`HINDSIGHT_API_KEY`、`HINDSIGHT_BANK_ID`：Hindsight 服务连接
- `IMAGE_DESCRIPTION_API_KEY`、`IMAGE_DESCRIPTION_BASE_URL`、`IMAGE_DESCRIPTION_MODEL`：图片描述

## 约定

- 提交信息使用中文描述 + `feat:`/`fix:` 前缀
- 状态文件保存在 `--state-dir`（默认 `./.state/`）
