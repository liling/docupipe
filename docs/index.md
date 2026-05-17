# docupipe 文档

docupipe 是一个通用文档传输 pipeline 工具，支持从多种文档源获取内容，经过可配置的处理步骤，传输到多种目标系统。

## 文档结构

### 教程

| 文档 | 说明 |
|------|------|
| [快速入门](tutorial-quick-start.md) | 从钉钉知识库同步文档到 Hindsight Memory |

### 操作指南

| 文档 | 说明 |
|------|------|
| [如何配置 Pipeline](howto-configure.md) | 选择 Source/Destination/Step，设置模式和环境变量 |
| [如何添加新组件](howto-add-component.md) | 三步添加自定义组件 |

### 参考

| 文档 | 说明 |
|------|------|
| [配置系统参考](reference-configuration.md) | YAML 配置格式、环境变量插值、variables 脚本 |
| [API 参考](reference-api.md) | Pipeline、StateManager、Models、CLI、Bundle Context |
| [组件 API 参考](reference-components.md) | Source/Destination/Step/Converter 全部参数和行为 |

### 解释

| 文档 | 说明 |
|------|------|
| [架构设计](explanation-architecture.md) | 插件式架构设计原理和权衡 |
| [运行模式设计](explanation-modes.md) | full/incremental/mirror 模式的适用场景 |

## 快速链接

- [README.md](../README.md) — 项目概览和安装指南
- [AGENTS.md](../AGENTS.md) — 开发指南和命令参考
- [配置示例](../docupipe.example.yaml) — 完整配置示例
