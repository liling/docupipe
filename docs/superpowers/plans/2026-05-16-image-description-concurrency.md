# Image Description 并发处理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 单文档内多张图片并发调用 Vision API，通过 YAML 配置控制并发度。

**Architecture:** 在 `OpenAIVisionClient` 新增 `async a_describe()` 方法。`ImagePostProcessor.process()` 重构为 collect-then-process-then-replace 三阶段模式，concurrency>1 时走 asyncio 路径，concurrency==1 时走同步路径。

**Tech Stack:** asyncio, asyncio.Semaphore, openai.AsyncOpenAI

---

### Task 1: Add `a_describe` to `OpenAIVisionClient`

**Files:**
- Modify: `docpipe/image.py:1-18` (imports + `__init__`)
- Modify: `docpipe/image.py:24-34` (`OpenAIVisionClient.__init__`)
- Modify: `docpipe/image.py:36-65` (add `a_describe` method after `describe`)
- Test: `tests/test_image.py`

- [ ] **Step 1: Write the failing test**

Add the following test to `tests/test_image.py`, inside `TestOpenAIVisionClient` class:

```python
import asyncio

# (add at top of file if not already imported)

def test_a_describe_returns_filename_and_description(self, monkeypatch):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({
        "filename": "async-flow-diagram",
        "description": "异步处理流程图",
    })

    mock_async_client = MagicMock()
    mock_async_client.chat.completions.create = asyncio.coroutine(lambda **kwargs: mock_response)()

    # We need a proper async mock
    async def mock_create(**kwargs):
        return mock_response

    mock_async_client.chat.completions.create = mock_create

    monkeypatch.setattr(
        "docpipe.image.AsyncOpenAI",
        lambda **kwargs: mock_async_client,
    )

    client = OpenAIVisionClient(
        api_key="test-key",
        base_url="https://api.example.com/v1",
        model="gpt-4o",
    )
    filename, description = asyncio.run(client.a_describe(b"fake-image-bytes", "测试文档"))

    assert filename == "async-flow-diagram"
    assert description == "异步处理流程图"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_image.py::TestOpenAIVisionClient::test_a_describe_returns_filename_and_description -v`
Expected: FAIL with `ImportError: cannot import name 'AsyncOpenAI'` or `AttributeError`

- [ ] **Step 3: Write minimal implementation**

In `docpipe/image.py`, add import at line 13:

```python
from openai import AsyncOpenAI
```

Change `OpenAIVisionClient.__init__` (currently lines 25-34) to also create an async client:

```python
class OpenAIVisionClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "gpt-4o",
        timeout: int = 30,
    ):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.async_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.timeout = timeout
```

Add `a_describe` method after `describe` (after line 65):

```python
    async def a_describe(self, image_bytes: bytes, context: str) -> tuple[str, str]:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        prompt = (
            f"这是一篇文档《{context}》中的图片。\n\n"
            "请完成两个任务：\n"
            "1. 生成一个简短的英文文件名（3-5个单词，用连字符连接，如 \"system-architecture-diagram\"）\n"
            "2. 用一句话描述图片内容（中文，适合在文档中作为图片说明）\n\n"
            '请以 JSON 格式返回：\n{"filename": "...", "description": "..."}'
        )

        response = await self.async_client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ],
            max_tokens=300,
            timeout=self.timeout,
        )

        raw = response.choices[0].message.content
        return self._parse_response(raw)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_image.py::TestOpenAIVisionClient::test_a_describe_returns_filename_and_description -v`
Expected: PASS

- [ ] **Step 5: Run all image tests to verify no regressions**

Run: `python -m pytest tests/test_image.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add docpipe/image.py tests/test_image.py
git commit -m "feat: 为 OpenAIVisionClient 新增 async a_describe 方法"
```

---

### Task 2: Refactor `ImagePostProcessor.process()` to collect-then-replace pattern

This is a structural refactor. Behavior must remain identical for `concurrency=1` (default).

**Files:**
- Modify: `docpipe/image.py:137-230` (`ImagePostProcessor`)

- [ ] **Step 1: Add `concurrency` parameter to `ImagePostProcessor.__init__`**

Change `ImagePostProcessor.__init__` (currently line 138) to:

```python
class ImagePostProcessor:
    def __init__(self, vision_client: OpenAIVisionClient, max_image_size: int = 10 * 1024 * 1024, concurrency: int = 1):
        self.vision_client = vision_client
        self.max_image_size = max_image_size
        self.concurrency = concurrency
```

- [ ] **Step 2: Add `_resolve_image_bytes` method**

Add after `__init__`, before `process`:

```python
    def _resolve_image_bytes(self, url: str, image_files: dict[str, FileItem] | None,
                             images_dir: str | None) -> bytes | None:
        if image_files and url in image_files:
            file_item = image_files[url]
            if isinstance(file_item.content, bytes):
                return file_item.content
            return base64.b64decode(file_item.content)
        if url.startswith("data:"):
            return self._decode_data_uri(url)
        if "://" in url:
            resp = req.get(url, timeout=30)
            resp.raise_for_status()
            return resp.content
        if images_dir:
            local_path = Path(images_dir) / url
            if local_path.is_file():
                return local_path.read_bytes()
        return None
```

- [ ] **Step 3: Rewrite `process()` method**

Replace the entire `process()` method with:

```python
    def process(self, markdown: str, source_context: str, images_dir: str | None = None,
                image_files: dict[str, FileItem] | None = None,
                progress_callback=None) -> tuple[str, dict]:
        image_metadata: dict[str, dict] = {}
        pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        all_matches = list(re.finditer(pattern, markdown))

        if not all_matches:
            return markdown, {}

        # Phase 1: Collect — resolve image bytes for each match
        processable: list[tuple[int, re.Match, bytes]] = []
        for i, match in enumerate(all_matches):
            url = match.group(2).strip().strip('"').strip("'").strip()
            if url.startswith("image://"):
                continue
            try:
                image_bytes = self._resolve_image_bytes(url, image_files, images_dir)
                if not image_bytes or len(image_bytes) > self.max_image_size:
                    continue
                image_bytes = validate_image(image_bytes)
                if image_bytes is None:
                    logger.debug("图片不满足处理条件，保留原引用: %s", url[:80])
                    continue
                processable.append((i, match, image_bytes))
            except Exception as e:
                logger.warning("图片加载失败 %s: %s", url[:80], e)

        total = len(processable)
        if total == 0:
            return markdown, {}

        # Phase 2: Describe
        image_bytes_list = [img_bytes for _, _, img_bytes in processable]
        if self.concurrency > 1:
            results = asyncio.run(self._run_concurrent(image_bytes_list, source_context))
        else:
            results = self._run_sync(image_bytes_list, source_context)

        # Phase 3: Build replacements and metadata
        replacements: dict[int, str] = {}
        for (idx, match, _), (filename, description) in zip(processable, results):
            if filename is None:
                continue
            url = match.group(2).strip().strip('"').strip("'").strip()
            original_ext = PurePosixPath(url).suffix or ".png"
            full_filename = f"{filename}{original_ext}"
            image_metadata[full_filename] = {
                "original_url": url[:200],
                "description": description,
            }
            if "/" in url:
                new_url = f"{url.rsplit('/', 1)[0]}/{full_filename}"
            else:
                new_url = full_filename
            replacements[idx] = f"![{description}]({new_url})"

        # Phase 4: Progress callback
        if progress_callback and total > 0:
            done = sum(1 for r in results if r[0] is not None)
            progress_callback(f"image_description ({done}/{total})")

        # Phase 5: Rebuild markdown
        parts: list[str] = []
        last_end = 0
        for i, match in enumerate(all_matches):
            parts.append(markdown[last_end:match.start()])
            if i in replacements:
                parts.append(replacements[i])
            else:
                parts.append(match.group(0))
            last_end = match.end()
        parts.append(markdown[last_end:])

        return "".join(parts), image_metadata
```

- [ ] **Step 4: Add `_run_sync` method**

Add after `process()`:

```python
    def _run_sync(self, image_bytes_list: list[bytes], source_context: str) -> list[tuple[str | None, str | None]]:
        results: list[tuple[str | None, str | None]] = []
        for img_bytes in image_bytes_list:
            try:
                filename, description = self.vision_client.describe(img_bytes, source_context)
                results.append((filename, description))
            except Exception as e:
                logger.warning("图片描述失败: %s", e)
                results.append((None, None))
        return results
```

- [ ] **Step 5: Add `_run_concurrent` method (stub for now)**

Add after `_run_sync`:

```python
    async def _run_concurrent(self, image_bytes_list: list[bytes], source_context: str) -> list[tuple[str | None, str | None]]:
        sem = asyncio.Semaphore(self.concurrency)

        async def describe_one(img_bytes: bytes) -> tuple[str | None, str | None]:
            async with sem:
                try:
                    return await self.vision_client.a_describe(img_bytes, source_context)
                except Exception as e:
                    logger.warning("图片描述失败: %s", e)
                    return (None, None)

        return await asyncio.gather(*[describe_one(b) for b in image_bytes_list])
```

- [ ] **Step 6: Add `asyncio` import**

Add `import asyncio` to the imports at the top of `docpipe/image.py` (after `import base64`).

- [ ] **Step 7: Run all existing tests**

Run: `python -m pytest tests/test_image.py -v`
Expected: All PASS (behavior unchanged with default concurrency=1)

- [ ] **Step 8: Commit**

```bash
git add docpipe/image.py
git commit -m "refactor: 重构 ImagePostProcessor.process() 为 collect-then-replace 模式"
```

---

### Task 3: Add test for concurrent processing

**Files:**
- Modify: `tests/test_image.py`

- [ ] **Step 1: Add `a_describe` to `_FakeVisionClient`**

In `tests/test_image.py`, replace the `_FakeVisionClient` class (lines 73-83) with:

```python
class _FakeVisionClient:
    def __init__(self, results: dict[str, tuple[str, str]] | None = None):
        self.results = results or {}
        self.calls: list[tuple[bytes, str]] = []

    def describe(self, image_bytes: bytes, context: str) -> tuple[str, str]:
        self.calls.append((image_bytes, context))
        if self.results:
            for _, val in self.results.items():
                return val
        return "test-image", "测试图片描述"

    async def a_describe(self, image_bytes: bytes, context: str) -> tuple[str, str]:
        self.calls.append((image_bytes, context))
        if self.results:
            for _, val in self.results.items():
                return val
        return "test-image", "测试图片描述"
```

- [ ] **Step 2: Write test for concurrent processing**

Add to `TestImagePostProcessor` class:

```python
    def test_process_concurrent_multiple_images(self, monkeypatch):
        monkeypatch.setattr("docpipe.image.req.get", _mock_get)
        monkeypatch.setattr("docpipe.image.validate_image", lambda b: b)
        call_order: list[int] = []

        def mock_describe(img, ctx):
            idx = len(call_order)
            call_order.append(idx)
            return f"image-{idx + 1}", f"描述{idx + 1}"

        vision = _FakeVisionClient()
        vision.describe = mock_describe
        vision.a_describe = lambda img, ctx: self._coro_return(mock_describe(img, ctx))

        processor = ImagePostProcessor(vision_client=vision, concurrency=4)
        markdown = (
            '![a](https://example.com/a.png)\n'
            '文字\n'
            '![b](https://example.com/b.png)\n'
            '文字\n'
            '![c](https://example.com/c.png)'
        )
        result, metadata = processor.process(markdown, "测试文档")

        assert len(metadata) == 3
        assert "image-1.png" in metadata
        assert "image-2.png" in metadata
        assert "image-3.png" in metadata
        # 验证所有图片都被替换到正确位置
        assert "描述1" in result
        assert "描述2" in result
        assert "描述3" in result

    @staticmethod
    async def _coro_return(value):
        return value
```

- [ ] **Step 3: Run the new test**

Run: `python -m pytest tests/test_image.py::TestImagePostProcessor::test_process_concurrent_multiple_images -v`
Expected: PASS

- [ ] **Step 4: Run all image tests**

Run: `python -m pytest tests/test_image.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_image.py
git commit -m "test: 添加 ImagePostProcessor 并发处理测试"
```

---

### Task 4: Wire up `concurrency` in `ImageDescriptionStep`

**Files:**
- Modify: `docpipe/steps/image_description.py:14-17`
- Test: `tests/test_image.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_image.py` (at module level, after imports):

```python
class TestImageDescriptionStepConcurrency:
    def test_passes_concurrency_to_processor(self, monkeypatch):
        monkeypatch.setattr("docpipe.image.validate_image", lambda b: b)

        step = ImageDescriptionStep(
            api_key="test-key",
            base_url="https://api.example.com/v1",
            model="gpt-4o",
            concurrency=8,
        )
        assert step._processor.concurrency == 8

    def test_default_concurrency_is_one(self, monkeypatch):
        step = ImageDescriptionStep(
            api_key="test-key",
            base_url="https://api.example.com/v1",
            model="gpt-4o",
        )
        assert step._processor.concurrency == 1
```

Add import at top of `tests/test_image.py`:

```python
from docpipe.steps.image_description import ImageDescriptionStep
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_image.py::TestImageDescriptionStepConcurrency -v`
Expected: FAIL — `ImageDescriptionStep.__init__` doesn't accept `concurrency`

- [ ] **Step 3: Implement**

Change `docpipe/steps/image_description.py` constructor (lines 15-17) to:

```python
@register_step("image_description")
class ImageDescriptionStep(PipelineStep):
    def __init__(self, api_key: str = "", base_url: str = "", model: str = "gpt-4o",
                 concurrency: int = 1, **kwargs):
        vision_client = OpenAIVisionClient(api_key=api_key, base_url=base_url, model=model)
        self._processor = ImagePostProcessor(vision_client, concurrency=concurrency)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_image.py::TestImageDescriptionStepConcurrency -v`
Expected: PASS

- [ ] **Step 5: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add docpipe/steps/image_description.py tests/test_image.py
git commit -m "feat: ImageDescriptionStep 支持 concurrency 配置项"
```
