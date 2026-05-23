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
python -m docupipe run                                   # 默认 full 模式
python -m docupipe run --config other.yaml               # 指定配置文件
python -m docupipe run --pipeline wiki-to-hs              # 指定 pipeline 名称
python -m docupipe run --mode incremental                 # 只处理新增
python -m docupipe run --mode mirror --change-detection mtime  # 增量同步
python -m docupipe run --resume                           # full 模式断点续传
python -m docupipe run --dry-run                          # 只打印不执行

# 列出可用组件
python -m docupipe sources
python -m docupipe destinations
```

## 架构

插件式 Pipeline 架构，四类可插拔组件，统一使用装饰器注册：

- **Source**（`sources/`）：实现 `list_documents()` + `fetch()` → 从外部系统获取文档
- **Destination**（`destinations/`）：实现 `write()` + `remove()` → 写入目标系统
- **Step**（`steps/`）：实现 `process(doc) → doc` → 文档处理步骤（格式转换、图片描述等）
- **Converter**（`converters/`）：实现 `convert(file_path) → markdown` → 具体的文件格式转换

注册模式：`@register_xxx("name")` 装饰器 + 模块级字典（`SOURCES`/`DESTINATIONS`/`STEPS`/`CONVERTERS`）+ `__init__.py` 中 import 触发注册。

所有组件共享相同注册模式，新增组件只需：实现抽象基类 + 加装饰器 + 在 `__init__.py` 中 import。

## 数据流

```
模式：
  full:        source.list() → 全部处理 → 写状态
  full --resume: 不调 list()，从状态找 pending 继续
  incremental: source.list() → 只处理新增 → 写状态
  mirror:      source.list() → 变更检测(mtime/hash) → 处理变更 + 清理删除

单文档处理流程：
  source.fetch(meta) → Bundle
    → steps 依次处理（convert → image_description → ...）
      → dest.write(bundle)        ← 写入前会用 render_template 解析 dest 配置中的 Jinja2 模板
        → state.mark_done()
          → post_steps（可选，如删除源头）
  全部文档处理完成后：
    → finalize_steps（批量后处理，如腾讯文档删除）
```

## Bundle Context 约定

Source 和 Step 通过 `Bundle.context` 字典传递数据。`models.py` 顶部维护了字段注册表，新增字段必须先查阅该表。
字段命名规则：通用字段用 `snake_case`，Source 特有字段用 `{source}_` 前缀（如 `dingtalk_content_type`、`tencent_doc_type`）。

Destination 的配置支持 `{{ field }}` Jinja2 模板语法，Destination 在 write 时用 `render_template` 解析。
内置过滤器：`date_format`、`basename`、`extension`。变量不存在时用 `| default('xxx')` 提供默认值。

## 配置系统

仅支持 YAML 配置文件方式启动（`--config` 默认值 `docupipe.yaml`）。

配置结构：全局默认值 + `pipelines` 列表。每个 pipeline 定义 `source`、`destination`、`steps`、`mode`、`change_detection`、`post_steps`、`finalize_steps`。
支持环境变量插值：`${VAR}` 和 `${VAR:-default}`。
支持 `variables` 脚本块：通过 `script` 或 `script_file` 执行 Python 函数生成变量，优先级高于环境变量。
组件配置自动与全局默认值 deep merge（pipeline 级覆盖全局级）。

## 状态管理

`StateManager` 为每个 source-dest 组合维护 JSON 状态文件（`{source}_{dest}_state.json`），记录已处理文档 ID 和 hash。
各运行模式通过状态文件实现跳过已处理、增量处理和变更清理等功能。

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
