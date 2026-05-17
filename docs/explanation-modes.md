# 运行模式设计

## 问题

文档传输 pipeline 需要覆盖多种使用场景：首次全量同步、增量处理新增文档、持续镜像同步（包括删除已消失的文档）、以及中断后恢复。每种场景对状态管理的需求不同。

## Full 模式：首次全量同步

```
source.list() → 全部标记 pending → 逐个处理 → 逐个标记 done
```

full 模式是最直接的"处理全部"模式。它适合首次运行或需要重新处理所有文档的场景。

**resume 变体**：当 pipeline 处理到第 N 个文档时中断（网络故障、进程被杀等），重新运行时 `--resume` 跳过已处理文档，只处理 pending 状态的文档。这避免了调用 `source.list()`——因为 list 可能很慢（网络请求分页）或者可能产生不同的结果。

## Incremental 模式：增量处理

```
source.list() → 只在状态中不存在的 → 处理 → 标记 done
```

incremental 模式的处理逻辑最简单：全量列举，只处理新增的。它适合"源只增不减"的场景，比如从钉钉知识库不断拉取新文档。不会处理已存在文档的变更，也不会删除已消失的文档。

## Mirror 模式：双向同步

```
source.list() → 检测变更 → 处理变更 → 删除源中已消失的文档
```

mirror 模式是最完整的同步模式。它处理三种情况：
1. **新增文档**：状态中不存在 → 处理
2. **已变更文档**：mtime 或 hash 变化 → 重新处理
3. **已删除文档**：在源中消失 → 从目标删除

### 变更检测策略

| 策略 | 原理 | 适用场景 |
|------|------|----------|
| `mtime` | 比较文件的修改时间戳 | 文件内容可能不变但 mtime 变化（如 touch）不重新处理 |
| `hash` | 比较文件内容的 SHA-256 | 需要精确检测内容变更，但每次比较都需要获取全部文件内容 |

mtime 策略依赖 Source 报告每个文档的修改时间。hash 策略在获取内容后计算 hash，因此对同一个文件每次 mirror 都需要 fetch 完整内容。

### 删除控制

`mirror_delete: false` 可以关闭自动删除功能，让 pipeline 做"只增不改"的单向同步。

## 状态驱动设计

所有模式都围绕状态文件设计：

```
状态文件 = {doc_id → {status, hash, path, mtime, ...}}
```

| 模式 | 写状态 | 读状态 |
|------|--------|--------|
| full | 起始 mark_pending，完成 mark_done | 否 |
| full + resume | 同上 | 读取 pending 列表 |
| incremental | 完成时 mark_done | 读取 done 集合 |
| mirror | 完成时 mark_done（含 mtime/hash） | 读取 done + mtime/hash 比对 |

## 选择指南

| 场景 | 推荐模式 |
|------|----------|
| 首次全量同步 | `full` |
| 中断后恢复 | `full --resume` |
| 定期拉取新文档 | `incremental` |
| 持续镜像同步（含删除） | `mirror --change-detection mtime` |
| 精确内容变更检测 | `mirror --change-detection hash` |
| 仅测试不执行 | `--dry-run`（可搭配任意模式） |
