# 控制台界面重写设计

## 目标

重写 `docpipe/display.py` 的 Display 类，用 Rich Live + Progress 替换纯 `print()` 输出，实现实时刷新的状态面板，展示 Pipeline 标题、进度条、统计、当前任务等信息。

参考项目：`../xzs/question_downloader/display.py` 的 Rich Live 实现。

## 布局

运行时界面分两个区域：

```
┌─────────────────────────────────────────────┐
│                                             │
│  ✅ 产品需求文档 v2.1                       │  ← 结果日志（向上滚动）
│  ✅ 技术架构设计.md                         │     通过 Live.console.print 输出
│  ⏭️ 会议纪要-0112 (无变化)                 │     自动出现在面板上方
│  ❌ 旧版文档.doc: 不支持的格式              │
│  ✅ 钉钉项目周报-2024Q3.md                  │
│                                             │
├─────────────────────────────────────────────┤
│  Pipeline: dingtalk → hindsight             │  ← 行1: Pipeline 标题
│  ⠋ ████████████████░░░░░░░░ 25/40 剩余 1:32│  ← 行2: 进度条
│  ✅ 23  ⏭️ 2  ❌ 1                          │  ← 行3: 统计
│  ⏳ 正在处理: 前端组件规范.md               │  ← 行4+: 当前任务（可扩展多行）
└─────────────────────────────────────────────┘
```

完成后输出汇总表格：

```
Pipeline: dingtalk → hindsight 完成!
┌──────┬──────┬──────┬──────┬──────────┐
│ 总数 │ 成功 │ 跳过 │ 失败 │ 耗时     │
├──────┼──────┼──────┼──────┼──────────┤
│  40  │  36  │   3  │   1  │ 3分20秒  │
└──────┴──────┴──────┴──────┴──────────┘
```

## Display 类设计

### 属性

```python
class Display:
    _console: Console
    _is_tty: bool
    _live: Live | None
    _progress: Progress | None
    _progress_task_id: TaskID | None
    _lock: threading.Lock
    _current_tasks: list[str]        # 当前正在处理的任务名，支持多行扩展

    total: int
    completed: int
    skipped: int
    failed: int

    _title: str
    _start_time: float
```

### 接口

保持与 pipeline.py 的调用点兼容，新增当前任务管理：

| 方法 | 说明 |
|------|------|
| `start(title, total)` | 启动 Live + Progress，记录标题和总数 |
| `stop()` | 停止 Live |
| `result(status, message)` | 输出结果行（✅/⏭️/❌），通过 `Live.console.print` 输出到面板上方 |
| `add_failure()` | `failed += 1`，推进进度条 |
| `set_current(label)` | 设置当前任务（追加到 `_current_tasks`） |
| `clear_current(label)` | 清除当前任务（从 `_current_tasks` 移除） |
| `print_summary()` | 结束后打印 Rich Table 汇总 |

### 统计计数

`result()` 方法根据 status 更新计数：
- `"success"` → `self.completed += 1`，推进进度条
- `"skip"` → `self.skipped += 1`，推进进度条
- `"error"` → 不在此计数（由 `add_failure()` 负责）
- `"info"` → 不计数

### 渲染

`_build_renderable()` 返回 `Group(progress, stats_text, current_tasks_text)`：

- **Progress**：`SpinnerColumn + TextColumn("{task.description}") + BarColumn(40) + TaskProgressColumn + TimeRemainingColumn`
  - `task.description` 设为 Pipeline 标题，标题和进度条合在同一个 Progress 组件
- **统计行**：`Text` 对象，格式 `✅ {completed}  ⏭️ {skipped}  ❌ {failed}`
- **当前任务行**：遍历 `_current_tasks`，每项生成 `⏳ {label}`

### 非 TTY 降级

`_is_tty = sys.stdout.isatty()`。非交互式终端（管道、CI）时：
- 不启动 Live 和 Progress
- `result()` 回退到 `print()`
- `set_current()` / `clear_current()` 不操作

### 线程安全

所有修改共享状态（`_current_tasks`、计数器、Progress）的操作通过 `_lock` 保护。

## pipeline.py 适配

改动最小化，仅新增当前任务提示：

```python
# fetch 前设置当前任务
self._display.set_current(doc_meta.title)
try:
    doc = self.source.fetch(doc_meta)
    # ... 原有逻辑不变
finally:
    self._display.clear_current(doc_meta.title)
```

其余调用点（`start`、`result`、`add_failure`、`stop`、`print_summary`）无需改动。

## 依赖变更

- **新增**：`rich` 加入 pyproject.toml 运行时依赖
- **移除**：`tqdm`（已声明但未使用）

## 文件变更清单

| 文件 | 变更 |
|------|------|
| `docpipe/display.py` | 完全重写 |
| `docpipe/pipeline.py` | 新增 `set_current` / `clear_current` 调用 |
| `pyproject.toml` | 依赖变更（+rich, -tqdm） |
