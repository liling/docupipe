# docupipe CLI Skill 设计

## 目标

为 `docupipe` CLI 工具创建一个 Superpowers 格式的 skill，让 AI agent（Claude Code / Copilot CLI / Gemini CLI）能够：
- 根据用户需求生成正确的 YAML 配置
- 执行 pipeline 并监控进度
- 查询状态、排查错误
- 修改配置并重新执行

## 方案

主 skill + references/ 目录。主 skill 提供触发规则、核心运维流程和检查清单；详细参考资料按需查阅。

## 文件结构

```
.claude/skills/docupipe/
├── docupipe.md                    # 主 skill 文件
└── references/
    ├── cli-reference.md           # CLI 命令和选项
    ├── config-reference.md        # YAML 配置格式 + 常用模板
    └── components.md              # 可用组件详情
```

## 主 Skill（docupipe.md）

### 元数据

```yaml
name: docupipe
description: 管理 docupipe 文档传输 pipeline —— 配置生成、执行监控、状态查询、排错修复。当用户需要传输/处理/同步文档、配置 docupipe pipeline、或提到"文档pipeline"时使用。
```

### 触发规则

- 关键词：文档传输、文档处理、docupipe、pipeline、导入文档到 Hindsight、钉钉文档同步、腾讯文档同步、文档转换、增量同步、镜像同步
- 斜杠命令：`/docupipe`

### Agent 行为流程

**场景 1：用户描述新需求**
1. 确认 source 和 destination 类型
2. 查阅 `references/components.md` 获取组件配置参数
3. 生成 YAML 配置文件
4. 向用户展示配置并确认
5. 执行 `python -m docupipe run --config <file> --dry-run` 验证
6. 确认无误后正式执行

**场景 2：用户要求执行已有配置**
1. 读取并展示当前配置
2. 确认 pipeline 名称和模式
3. 执行并监控输出

**场景 3：查看处理状态**
1. 读取 `.state/` 目录下的 JSON 状态文件
2. 汇报已处理/待处理/失败数量

**场景 4：排错**
1. 分析错误信息，定位问题类别（配置/网络/权限/组件）
2. 查阅 `references/components.md` 确认正确配置格式
3. 提出修复方案，用户确认后修改

**场景 5：增量/镜像模式**
1. 确认 `--mode`（incremental/mirror）和 `--change-detection`（mtime/hash）
2. 执行

### 关键约束

- 执行前必须让用户确认 YAML 配置
- 修改配置前先读取当前配置，不覆盖未修改的部分
- 操作状态文件前先备份
- 不自动执行 `--dry-run`，除非用户要求或作为调试步骤
- 配置中涉及的环境变量使用 `${VAR}` 语法，不硬编码值
- 使用 `references/` 下的参考文档获取准确的组件参数，不要凭记忆编造

## 参考文档

### cli-reference.md

内容：
- `python -m docupipe run` 的完整选项表
- `python -m docupipe sources` / `destinations` 列表命令
- 各运行模式的说明（full/incremental/mirror + resume）
- 输出格式和常见组合示例

### config-reference.md

内容：
- 完整 YAML 结构（全局配置 + pipelines 列表）
- 环境变量插值语法（`${VAR}`, `${VAR:-default}`）
- `variables` 脚本块的用法
- deep merge 规则
- 常用配置模板（从少到多）：
  1. 本地文件夹 → 本地输出
  2. 钉钉知识库 → Hindsight
  3. 腾讯文档 → 本地 + S3 上传
  4. 镜像同步（带变更检测）

### components.md

内容：每个已注册组件的详细信息：
- Sources: `localdrive`, `dingtalk`, `tencent` — 参数、默认值、行为说明
- Destinations: `localdrive`, `hindsight` — 参数、默认值、行为说明
- Steps: `convert`, `image_description`, `resolve_attachments`, `s3_upload`, `tencent_delete` — 参数、默认值、行为说明
- Converters: `markitdown`, `mineru` — 用途和行为

所有内容从项目代码中提取，确保准确。

## 实现步骤

1. 创建 `.claude/skills/docupipe/` 目录和 `references/` 子目录
2. 编写 `references/cli-reference.md`（从 cli.py 和 pipeline.py 提取）
3. 编写 `references/config-reference.md`（从代码和已有配置提取）
4. 编写 `references/components.md`（从各组件源码提取）
5. 编写主 skill `docupipe.md`
6. 测试：在 Claude Code 中加载 skill 验证触发和内容准确性
