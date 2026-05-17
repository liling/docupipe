# Pipeline 运行模式与增量同步设计

日期：2026-05-17

## 背景

当前 pipeline 只有 `--resume`（断点续传）和 `--sync`（同步）两个选项，语义模糊且功能有限：

- `--resume` 混淆了"断点续传"和"只处理新增"两种意图
- `--sync` 的 hash 比对对 tencent/dingtalk source 不生效（`meta.hash` 为空）
- 缺少"处理完删除源头"的中转站场景支持
- 缺少可靠的变更检测机制

## 设计

### 运行模式

用 `--mode` 替换 `--resume` / `--sync`，删除旧参数。

| 模式 | 配置 | CLI | 调 list() | 读状态 | 写状态 |
|---|---|---|---|---|---|
| full | `mode: full` | `--mode full`（默认） | 是 | 否 | 是 |
| full + resume | — | `--resume` | 否 | 是（找未完成的） | 是 |
| incremental | `mode: incremental` | `--mode incremental` | 是 | 是（比对新增） | 是 |
| mirror | `mode: mirror` | `--mode mirror` | 是 | 是（比对变更+删除） | 是 |

- `--resume` 是 CLI 级别的控制参数，不属于 pipeline 配置。仅在 `full` 模式下有效。
- `--dry-run` 保持不变。

**各模式行为：**

**full**：列出所有文档，全部处理。写入状态供后续 resume 或 incremental 使用。

**full --resume**：不调 list()，从状态文件中找到未完成的文档继续处理。适合大批量中断后恢复。

**incremental**：调 list() 拿最新列表，和状态文件比对，只处理状态中不存在的文档。适合定期拉取新增内容。

**mirror**：调 list() 拿最新列表，用变更检测策略判断每个文档是否需要重新处理，并检测源头已删除的文档。适合持续同步。

### 变更检测

mirror 模式需要指定变更检测策略：

```yaml
mode: mirror
change_detection: mtime  # mtime | hash
```

**策略：**

- **mtime**：比较文档修改时间。source 在 `list()` 时提供 mtime，pipeline 存入状态文件。下次运行时比对，mtime 相同则跳过。不 fetch 内容。
- **hash**：fetch 内容后计算 SHA-256 hash，和状态文件中存储的 hash 比对。相同则跳过后续 steps 和 write。代价是需要 fetch。

**Source 声明能力：**

Source 基类增加 `supported_change_detection()` 方法，返回支持的策略列表。Pipeline 启动时校验，source 不支持则报错退出。

| Source | mtime | hash |
|---|---|---|
| localdrive | 支持（`st_mtime`） | 支持 |
| dingtalk | 支持（`updateTime`） | 支持 |
| tencent | 不支持 | 支持 |

**mtime 格式约定：** 统一为毫秒级 Unix 时间戳（int）。各 source 在 `list()` 时自行转换。

**新增/删除检测** 不受策略影响：

- 新增：ID 不在状态文件中 → 处理
- 删除：ID 在状态文件中但不在当前 list() 列表中 → 执行清理

### 状态文件

**命名：** 默认 `{pipeline_name}_state.json`，可在 pipeline 配置中通过 `state_file` 自定义。

**格式：** 增加 `status` 和 `mtime` 字段：

```json
{
  "doc_id_done": {
    "status": "done",
    "hash": "sha256...",
    "mtime": 1713571200000,
    "path": "文档/标题"
  },
  "doc_id_pending": {
    "status": "pending",
    "path": "文档/标题",
    "title": "标题",
    "fetch_extra": {"dingtalk_content_type": "ALIDOC", "extension": "adoc"}
  }
}
```

- `status`：`"done"` 或 `"pending"`。full 模式在 list() 后将所有文档标记为 pending，处理成功后更新为 done。resume 时从状态文件找 pending 的继续处理。
- `hash`：pipeline 在 fetch + steps 完成后计算写入。仅 status=done 时存在。
- `mtime`：source 在 `list()` 时提供，pipeline 存入状态。只在 `change_detection: mtime` 时写入。
- `path`：文档路径，用于日志和删除时显示。
- `title`：文档标题，pending 条目保存，用于 resume 时重建 BundleMeta。
- `fetch_extra`：source 特有的元数据，pending 条目保存，用于 resume 时重建 BundleMeta 传给 fetch()。

`incremental` 和 `mirror` 模式不使用 pending 状态，处理完直接写 done。

### Post Step

Post step 是 pipeline 成功处理单个文档后执行的动作，注册机制和 step 一致（装饰器 + 基类）。

**执行时机：** `dest.write()` + `state.mark_done()` 都成功之后。任何一步失败都不执行。

**配置方式：** 和 steps 保持一致，使用注册名列表：

```yaml
pipelines:
  - name: inbox
    mode: incremental
    source:
      tencent:
        space_name: "个人空间"
    destination:
      localdrive:
        output_dir: ./output
    steps: []
    post_steps:
      - tencent_doc_delete

  - name: sync-wiki
    mode: mirror
    change_detection: mtime
    source:
      dingtalk:
        space: 平台产品知识库
    destination:
      hindsight:
        context_prefix: "平台产品知识库"
    steps:
      - convert
      - s3_upload
```

**具体 post step 由需求决定，可以是：**

- `tencent_doc_delete`：从腾讯文档删除
- `dingtalk_doc_delete`：从钉钉知识库删除
- `localdrive_archive`：本地文件归档（移动到 archive 目录）
- `localdrive_delete`：本地文件删除

**Mirror 模式的目标侧删除** 不通过 post step 实现，而是 mirror 模式的内置逻辑：所有文档处理完后，比对当前 list() 的 ID 集合与状态文件，对差集执行目标删除。可配置是否开启。

### Source 接口变更

Source 基类增加：

```python
class SourceBase:
    def supported_change_detection(self) -> list[str]:
        """返回支持的变更检测策略，如 ['mtime', 'hash']"""
        return []

    def delete(self, doc_id: str) -> None:
        """删除指定文档（可选实现）"""
        raise NotImplementedError
```

Source 的 `list()` 返回的 `BundleMeta.extra` 中应包含 `mtime`（毫秒级 Unix 时间戳），如果 source 支持mtime 检测。

### CLI 变更

删除 `--resume` 和 `--sync` 参数。新增：

```
--mode {full,incremental,mirror}   运行模式（默认 full）
--resume                           full 模式下断点续传
--change-detection {mtime,hash}    mirror 模式的变更检测策略（覆盖配置）
--dry-run                          试跑（保持不变）
```

配置文件中的 `mode` 和 `change_detection` 可被 CLI 参数覆盖。

### 配置结构

```yaml
# 全局默认值
pipelines:
  - name: <pipeline名>
    mode: full | incremental | mirror    # 运行模式
    change_detection: mtime | hash       # mirror 模式的变更检测策略
    source:
      <source_type>:
        ...
    destination:
      <dest_type>:
        ...
    steps:
      - <step_name>
    post_steps:                          # 可选
      - <post_step_name>
    state_file: custom_state.json        # 可选，默认 {pipeline_name}_state.json
    options:                             # 可选
      mirror_delete: true                # mirror 模式是否删除目标侧（默认 true）
```

## 不做的事

- 不做向后兼容（`--resume` / `--sync` 直接删除）
- 不做 `id` 变更检测策略（等价于 incremental，无意义）
- 不做 post step 的字典形式配置（暂不需要 step 参数）
- 不做跨 pipeline 的状态共享
