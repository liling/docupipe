# Image Description 并发处理设计

## 背景

`image_description` step 对文档中的每张图片串行调用 Vision API，是整个 pipeline 的性能瓶颈。一篇文档含 10 张图片时，耗时可达到 30-60 秒。

## 目标

单文档内多张图片并发调用 Vision API，通过 YAML 配置控制并发度。

## 方案

使用 `asyncio` + `Semaphore`，`AsyncOpenAI` 客户端并发调用 Vision API。

## 改动范围

### `docpipe/image.py`

**`OpenAIVisionClient`：**

- 构造函数同时创建 `OpenAI`（同步）和 `AsyncOpenAI`（异步）客户端
- 新增 `async a_describe()` 方法，逻辑与 `describe()` 一致，使用 `AsyncOpenAI`
- 保留原有 `describe()` 同步方法不变

**`ImagePostProcessor`：**

- 构造函数新增 `concurrency` 参数，默认 1
- `process()` 方法改造为两阶段：
  1. `_collect_images()`：用 `re.finditer` 收集所有匹配项，读取图片字节，过滤无效图片，返回待处理列表
  2. 当 `concurrency > 1` 时，`asyncio.run(_describe_concurrent())` 并发处理；当 `concurrency == 1` 时，走原有同步逻辑
- `_describe_concurrent()`：`asyncio.gather` + `Semaphore(concurrency)` 并发调用 `a_describe()`
- 失败单张图片不影响其他，保留原始引用（与当前行为一致）
- 进度显示：并发完成后统一回调一次 `progress_callback(f"image_description ({done}/{total})")`

### `docpipe/steps/image_description.py`

- 构造函数接收 `concurrency` 参数，传递给 `ImagePostProcessor`
- `process()` 无需处理 async 桥接，由 `ImagePostProcessor` 内部处理

### 不改动的文件

- `pipeline.py`、`display.py`、`models.py` — 不变
- `OpenAIVisionClient.describe()` 同步方法 — 保留
- `validate_image()` 等辅助函数 — 不变

## YAML 配置

```yaml
steps:
  - image_description:
      api_key: ${IMAGE_DESCRIPTION_API_KEY}
      base_url: ${IMAGE_DESCRIPTION_BASE_URL}
      model: ${IMAGE_DESCRIPTION_MODEL}
      concurrency: 4    # 可选，默认 1（串行）
```

- `concurrency` 不配置或为 1 时，行为与当前完全一致
- 推荐值 4-8，取决于 API rate limit

## 错误处理

每张图片的 `a_describe()` 用 `try/except` 包裹，失败返回 None。组装替换结果时遇到 None 保留原始图片引用。单个失败不阻塞其他图片处理。

## 进度显示

并发完成后统一更新一次进度计数，格式为 `image_description ({done}/{total})`。不再逐张更新。

## 兼容性

- `concurrency` 默认为 1，不改变任何现有行为
- 不配置时无 asyncio 开销
- 同步 `describe()` 方法保留，不影响其他调用方
