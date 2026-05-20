# docupipe CLI 参考

## 命令总览

所有命令通过 `python -m docupipe` 执行。

| 命令 | 说明 |
|------|------|
| `run` | 执行 pipeline |
| `sources` | 列出可用的 Source |
| `destinations` | 列出可用的 Destination |

## 全局选项

适用于所有命令：

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--state-dir PATH` | `./.state` | 状态文件目录 |
| `--log-level LEVEL` | `INFO` | 日志级别：`DEBUG`, `INFO`, `WARNING`, `ERROR` |

## run 命令

```bash
python -m docupipe run [OPTIONS]
```

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--config PATH` | `docupipe.yaml` | 配置文件路径 |
| `--pipeline NAME` | (全部执行) | 指定 pipeline 名称 |
| `--mode MODE` | (使用配置) | 运行模式：`full`, `incremental`, `mirror` |
| `--resume` | `false` | full 模式断点续传（跳过已处理文档） |
| `--change-detection MODE` | (使用配置) | mirror 模式变更检测：`mtime`, `hash` |
| `--dry-run` | `false` | 只打印不执行 |

## 运行模式说明

### full
处理 source 中的所有文档。已处理过的文档通过状态文件跳过。

### full --resume
不调用 `source.list()`，直接从状态文件中找到 status=pending 的文档继续处理。适用于中断后恢复。

### incremental
调用 `source.list()`，只处理状态文件中不存在的新文档。

### mirror
调用 `source.list()`，对比状态文件：
- 新增/修改的文档 → 处理并写入
- 已删除的文档 → 调用 `destination.remove()` 清理

变更检测策略：
- `mtime`：比较修改时间（需要 source 支持）
- `hash`：比较内容 SHA-256 哈希

## 常用命令组合

```bash
# 首次运行
python -m docupipe run

# 指定配置和 pipeline
python -m docupipe run --config my-pipeline.yaml --pipeline dingtalk-download

# 先试运行查看会处理哪些文档
python -m docupipe run --dry-run

# 中断后续传
python -m docupipe run --resume

# 增量同步
python -m docupipe run --mode incremental

# 镜像同步（mtime 变更检测）
python -m docupipe run --mode mirror --change-detection mtime

# 查看可用组件
python -m docupipe sources
python -m docupipe destinations

# 调试模式
python -m docupipe run --log-level DEBUG --dry-run
```

## 状态文件

位置：`--state-dir` 目录下，文件名格式 `{source}_{dest}_state.json`。

每个文件记录：
- 已处理文档的 ID、hash、处理时间
- pending 状态（用于 resume）

## 退出码

| 退出码 | 说明 |
|--------|------|
| 0 | 成功 |
| 1 | 配置错误或运行时异常 |
