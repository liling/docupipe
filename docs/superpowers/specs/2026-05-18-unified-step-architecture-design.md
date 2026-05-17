# 统一 Step 架构 + 腾讯文档删除 FinalizeStep

## 背景

当前项目有两套独立的 step 机制：

- `PipelineStep`（`steps/base.py`）— source→dest 之间执行
- `PostStep`（`post_steps/base.py`）— dest 之后执行

两者接口完全相同：`process(bundle) -> Bundle`。区别仅在 pipeline 调用时机的不同。

同时需要新增"Pipeline 结束后批量执行"的能力（用于从腾讯文档删除已处理的文档）。如果再新建一个基类，就会出现三个接口相同但名字不同的类。

## 设计原则

**Step 本质相同，区别只在 pipeline 中的位置。**

- 所有 step 共享同一个基类和注册表
- Pipeline 通过配置中的位置（`steps` / `post_steps` / `finalize_steps`）决定调用时机
- Step 不需要知道 pipeline 生命周期，只负责 `process(bundle)`

## 改动概览

### 1. 统一 Step 基类

合并 `PipelineStep` 和 `PostStep` 为一个 `Step` 基类，放在 `steps/base.py`：

```python
class Step(ABC):
    name: str = ""

    @abstractmethod
    def process(self, bundle: Bundle) -> Bundle:
        """处理文档包"""

    def update_config(self, config: dict) -> None:
        """用配置更新组件属性（可选）"""
        for key, value in config.items():
            attr = f"_{key}"
            if hasattr(self, attr):
                setattr(self, attr, value)
```

### 2. 统一注册表

`steps/__init__.py` 中保留一个 `STEPS` 字典 + `@register_step()` 装饰器。
所有 step（包括原来的 post_step）都注册到这里。

### 3. Pipeline 三个执行位置

配置示例：

```yaml
pipelines:
  - source: tencent
    destination: hindsight
    steps:                    # source → dest 之间，逐文档
      - convert
      - image_description
    post_steps:               # dest 之后，逐文档
      - notify
    finalize_steps:           # pipeline 结束后，对成功 bundle 逐个执行
      - tencent_delete:
          remove_type: current
```

执行逻辑：

| 位置 | 调用时机 | 方法 |
|------|---------|------|
| `steps` | source.fetch() 之后、dest.write() 之前，逐文档 | `step.process(bundle)` |
| `post_steps` | dest.write() 成功之后，逐文档 | `step.process(bundle)` |
| `finalize_steps` | 所有文档处理完毕后，对收集的成功 bundle 逐个执行 | `step.process(bundle)` |

Pipeline 在处理过程中收集成功的 bundle，在各 run 模式结束后对 `finalize_steps` 逐个调用 `process(bundle)`。

### 4. TencentDeleteStep

放在 `steps/tencent_delete.py`，用 `@register_step("tencent_delete")` 注册。

**配置项**：
- `remove_type`：`current`（默认，仅删当前节点）或 `all`（递归删子节点）

**实现**：
- `process(bundle)`：从 `bundle.context` 取 `id`（node_id）和 `space_id`，调用 `_TencentDocClient.delete_space_node()`
- 删除失败时 `logger.warning`，不抛异常，继续下一个

**依赖**：
- 复用 `_TencentDocClient`（从 `sources/tencent.py` 导入或提取为公共模块）
- 从 `TENCENT_DOCS_TOKEN` 环境变量认证

### 5. TencentSource 改动

`fetch()` 中向 `bundle.context` 注入 `space_id`（`delete_space_node` API 需要此参数）。

### 6. CLI 改动

- `finalize_steps` 加载方式与 `steps` 相同（`{name: config}` 格式）
- 三个列表都从统一的 `STEPS` 注册表查找
- 传入 Pipeline 构造函数

### 7. 文件结构

移除 `post_steps/` 目录。所有 step 实现统一放在 `steps/` 下。

迁移后的 `steps/` 目录：
```
steps/
  __init__.py       # 统一注册表
  base.py           # Step 基类
  convert.py
  image_description.py
  s3_upload.py
  resolve_attachments.py
  tencent_delete.py  # 新增
```

### 8. 向后兼容

- `post_steps/base.py` 中的 `PostStep` 删除
- `post_steps/__init__.py` 中的注册机制删除
- `PipelineStep` 改名为 `Step`
- 所有现有 step 的 import 路径更新

## 不在范围内

- 空文件夹清理（后续迭代）
- 回收站功能（API 不支持）
- `finalize()` 方法（不需要，pipeline 对 finalize_steps 同样调用 `process()`）
