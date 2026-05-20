---
name: docupipe
description: 管理 docupipe 文档传输 pipeline —— 配置生成、执行监控、状态查询、排错修复。当用户需要传输/处理/同步文档、配置 docupipe pipeline、或提到"文档pipeline"时使用。
---

# docupipe CLI Skill

通用文档传输 pipeline 工具。支持从多种文档源获取内容，经过可配置的处理步骤，传输到多种目标系统。

## 何时使用

当用户提到以下场景时触发本 skill：
- 文档传输、文档处理、文档同步、文档转换
- docupipe、pipeline
- 导入文档到 Hindsight
- 钉钉文档/知识库同步
- 腾讯文档同步/导出
- 本地文件批量转换

也支持用户输入 `/docupipe` 直接触发。

## 参考文档

查阅以下文件获取准确的配置参数和组件详情（不要凭记忆编造参数）：
- `references/cli-reference.md` — CLI 命令和选项
- `references/config-reference.md` — YAML 配置格式和模板
- `references/components.md` — 所有可用组件的详细配置

## Agent 操作流程

### 场景 1：新需求（配置生成 + 执行）

1. **确认需求**：确定 source 类型、destination 类型、需要的处理步骤
2. **查阅参考文档**：读取 `references/components.md` 确认组件参数
3. **生成配置**：按照 `references/config-reference.md` 中的模板生成 YAML
4. **用户确认**：展示完整配置，等用户批准
5. **试运行**：`python -m docupipe run --config <file> --dry-run`
6. **正式执行**：`python -m docupipe run --config <file>`

### 场景 2：执行已有配置

1. **读取配置**：读取 YAML 文件
2. **确认参数**：pipeline 名称、模式（full/incremental/mirror）
3. **执行**：`python -m docupipe run --config <file> [--pipeline NAME]`
4. **监控输出**：关注错误信息

### 场景 3：查看状态

1. **列出状态文件**：`ls .state/` 或 `ls <state-dir>/`
2. **读取状态**：查看 JSON 文件中的处理记录
3. **汇报**：已处理/待处理/失败数量

### 场景 4：排错

1. **分析错误**：根据错误信息定位类别：
   - 配置错误（YAML 语法、缺少必填参数、组件名拼写）
   - 网络错误（API 连接、超时）
   - 权限错误（API Key、文件读写）
   - 组件错误（converter 依赖缺失、dws CLI 不可用）
2. **查阅参考文档**：确认正确的配置格式和参数
3. **提出修复方案**：用户确认后修改配置或环境

### 场景 5：增量/镜像模式

1. **确认模式**：`--mode incremental` 或 `--mode mirror`
2. **确认变更检测**（mirror 模式）：`--change-detection mtime` 或 `hash`
3. **执行**

## 关键约束

- **执行前确认**：必须让用户确认 YAML 配置后才能执行
- **读取优先**：修改配置前先读取当前配置，不覆盖未修改部分
- **环境变量**：配置中使用 `${VAR}` 语法，不硬编码密钥
- **查文档不编造**：组件参数以 `references/` 下的文档为准
- **状态文件安全**：操作前先备份 `.state/` 文件
- **dry-run 调试**：不自动添加 `--dry-run`，仅在用户要求或调试时使用

## 常见问题

**Q: 如何查看有哪些可用组件？**
```bash
python -m docupipe sources
python -m docupipe destinations
```

**Q: 中断后如何恢复？**
```bash
python -m docupipe run --resume
```

**Q: 如何只处理新增文档？**
```bash
python -m docupipe run --mode incremental
```

**Q: 如何同步删除操作？**
```bash
python -m docupipe run --mode mirror --change-detection mtime
```
