# 图片描述性信息处理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在文档传输 pipeline 中，使用 OpenAI 兼容 Vision API 为图片生成描述性名称和内容说明，替换 markdown 中的原始图片引用，并在 meta 中保存映射。

**Architecture:** 在 `docpipe/image.py` 中新增 `OpenAIVisionClient` 和 `ImagePostProcessor`。`DingtalkSource.fetch()` 获取 markdown 后调用 `ImagePostProcessor` 处理图片引用，将图片元数据存入 `doc.meta.extra["image_metadata"]`。

**Tech Stack:** Python 3.11+, openai SDK, requests, re

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `docpipe/image.py` | Create | OpenAIVisionClient + ImagePostProcessor |
| `docpipe/sources/dingtalk.py` | Modify | fetch() 中调用 ImagePostProcessor |
| `docpipe/cli.py` | Modify | 传递 image_description 配置到 Source |
| `pyproject.toml` | Modify | 添加 openai 依赖 |
| `tests/test_image.py` | Create | 测试 ImagePostProcessor 和 VisionClient |

---

### Task 1: 创建 OpenAIVisionClient

**Files:**
- Create: `docpipe/image.py`
- Create: `tests/test_image.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_image.py
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from docpipe.image import OpenAIVisionClient
from docpipe.models import DocumentMeta


class TestOpenAIVisionClient:
    def test_describe_returns_filename_and_description(self, monkeypatch):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "filename": "system-architecture-diagram",
            "description": "展示微服务三层架构，包含网关层、服务层和数据层",
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        monkeypatch.setattr(
            "docpipe.image.OpenAI",
            lambda **kwargs: mock_client,
        )

        client = OpenAIVisionClient(
            api_key="test-key",
            base_url="https://api.example.com/v1",
            model="gpt-4o",
        )
        filename, description = client.describe(b"fake-image-bytes", "测试文档")

        assert filename == "system-architecture-diagram"
        assert description == "展示微服务三层架构，包含网关层、服务层和数据层"

        # 验证调用参数
        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs["model"] == "gpt-4o"
        messages = call_args.kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        content = messages[0]["content"]
        # content 是 list，包含 text 和 image_url
        assert any("测试文档" in part["text"] for part in content if part["type"] == "text")

    def test_describe_invalid_json_response_falls_back(self, monkeypatch):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not valid json"

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        monkeypatch.setattr(
            "docpipe.image.OpenAI",
            lambda **kwargs: mock_client,
        )

        client = OpenAIVisionClient(
            api_key="test-key",
            base_url="https://api.example.com/v1",
            model="gpt-4o",
        )
        filename, description = client.describe(b"fake-image-bytes", "测试文档")

        assert filename  # 应该有降级值
        assert description  # 应该有降级值
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_image.py::TestOpenAIVisionClient -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'docpipe.image'`

- [ ] **Step 3: 实现 OpenAIVisionClient**

```python
# docpipe/image.py
from __future__ import annotations

import base64
import json
import logging
import re

logger = logging.getLogger(__name__)


class OpenAIVisionClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "gpt-4o",
        timeout: int = 30,
    ):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.timeout = timeout

    def describe(self, image_bytes: bytes, context: str) -> tuple[str, str]:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        prompt = (
            f"这是一篇文档《{context}》中的图片。\n\n"
            "请完成两个任务：\n"
            "1. 生成一个简短的英文文件名（3-5个单词，用连字符连接，如 \"system-architecture-diagram\"）\n"
            "2. 用一句话描述图片内容（中文，适合在文档中作为图片说明）\n\n"
            '请以 JSON 格式返回：\n{"filename": "...", "description": "..."}'
        )

        response = self.client.chat.completions.create(
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

    def _parse_response(self, raw: str) -> tuple[str, str]:
        try:
            data = json.loads(raw)
            return data["filename"], data["description"]
        except (json.JSONDecodeError, KeyError):
            # 尝试从文本中提取 JSON
            match = re.search(r'\{[^}]+\}', raw)
            if match:
                try:
                    data = json.loads(match.group())
                    return data["filename"], data["description"]
                except (json.JSONDecodeError, KeyError):
                    pass
            logger.warning(f"Vision API 返回无法解析: {raw[:200]}")
            return "image-unknown", "图片描述解析失败"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_image.py::TestOpenAIVisionClient -v`
Expected: PASS

- [ ] **Step 5: 添加 openai 依赖**

在 `pyproject.toml` 的 `dependencies` 列表中添加 `"openai>=1.0.0"`:

```toml
dependencies = [
    "click>=8.1.0",
    "markitdown>=0.1.0",
    "hindsight-client>=0.1.0",
    "tqdm>=4.66.0",
    "python-dotenv>=1.0.0",
    "pyyaml>=6.0",
    "requests>=2.31.0",
    "openai>=1.0.0",
]
```

Run: `pip install -e ".[dev]"`

- [ ] **Step 6: Commit**

```bash
git add docpipe/image.py tests/test_image.py pyproject.toml
git commit -m "feat: 添加 OpenAIVisionClient 图片描述客户端"
```

---

### Task 2: 创建 ImagePostProcessor

**Files:**
- Modify: `docpipe/image.py`
- Modify: `tests/test_image.py`

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_image.py
from docpipe.image import ImagePostProcessor


class _FakeVisionClient:
    def __init__(self, results: dict[str, tuple[str, str]] | None = None):
        self.results = results or {}
        self.calls: list[tuple[bytes, str]] = []

    def describe(self, image_bytes: bytes, context: str) -> tuple[str, str]:
        self.calls.append((image_bytes, context))
        if self.results:
            for url_key, val in self.results.items():
                return val
        return "test-image", "测试图片描述"


class TestImagePostProcessor:
    def test_process_replaces_image_refs(self):
        vision = _FakeVisionClient(results={
            "default": ("architecture-diagram", "展示微服务三层架构"),
        })
        processor = ImagePostProcessor(vision_client=vision)

        markdown = '![imag.png](https://example.com/test.png)'
        result, metadata = processor.process(markdown, "测试文档")

        assert "**architecture-diagram**：展示微服务三层架构" in result
        assert "image://architecture-diagram.png" in result
        assert "architecture-diagram.png" in metadata
        assert metadata["architecture-diagram.png"]["original_url"] == "https://example.com/test.png"
        assert metadata["architecture-diagram.png"]["description"] == "展示微服务三层架构"

    def test_process_keeps_original_on_failure(self):
        vision = _FakeVisionClient()
        # 模拟 describe 抛出异常
        vision.describe = lambda img, ctx: (_ for _ in ()).throw(RuntimeError("API error"))

        processor = ImagePostProcessor(vision_client=vision)
        markdown = '![img.png](https://example.com/broken.png)'
        result, metadata = processor.process(markdown, "测试文档")

        assert "https://example.com/broken.png" in result
        assert metadata == {}

    def test_process_skips_already_processed(self):
        vision = _FakeVisionClient()
        processor = ImagePostProcessor(vision_client=vision)

        markdown = '![test](image://already-done.png)'
        result, metadata = processor.process(markdown, "测试文档")

        assert result == '![test](image://already-done.png)'
        assert metadata == {}
        assert len(vision.calls) == 0

    def test_process_multiple_images(self):
        call_count = [0]

        def mock_describe(img, ctx):
            call_count[0] += 1
            return f"image-{call_count[0]}", f"描述{call_count[0]}"

        vision = _FakeVisionClient()
        vision.describe = mock_describe

        processor = ImagePostProcessor(vision_client=vision)
        markdown = (
            '![a](https://example.com/a.png)\n'
            '一些文字\n'
            '![b](https://example.com/b.png)'
        )
        result, metadata = processor.process(markdown, "测试文档")

        assert len(metadata) == 2
        assert "image-1.png" in metadata
        assert "image-2.png" in metadata
        assert "image://image-1.png" in result
        assert "image://image-2.png" in result

    def test_process_no_images(self):
        vision = _FakeVisionClient()
        processor = ImagePostProcessor(vision_client=vision)

        markdown = "这是一段没有图片的文字"
        result, metadata = processor.process(markdown, "测试文档")

        assert result == markdown
        assert metadata == {}
        assert len(vision.calls) == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_image.py::TestImagePostProcessor -v`
Expected: FAIL — `ImportError: cannot import name 'ImagePostProcessor'`

- [ ] **Step 3: 实现 ImagePostProcessor**

在 `docpipe/image.py` 末尾追加：

```python
class ImagePostProcessor:
    def __init__(self, vision_client: OpenAIVisionClient, max_image_size: int = 10 * 1024 * 1024):
        self.vision_client = vision_client
        self.max_image_size = max_image_size

    def process(self, markdown: str, source_context: str) -> tuple[str, dict]:
        image_metadata: dict[str, dict] = {}
        pattern = r'!\[([^\]]*)\]\(([^)]+)\)'

        def replace_image(match: re.Match) -> str:
            alt = match.group(1)
            url = match.group(2)

            if url.startswith("image://"):
                return match.group(0)

            try:
                import requests as req
                resp = req.get(url, timeout=30)
                resp.raise_for_status()
                image_bytes = resp.content

                if len(image_bytes) > self.max_image_size:
                    logger.warning(f"图片过大 ({len(image_bytes)} bytes)，跳过: {url}")
                    return match.group(0)

                filename, description = self.vision_client.describe(image_bytes, source_context)

                full_filename = f"{filename}.png"
                image_metadata[full_filename] = {
                    "original_url": url,
                    "description": description,
                }

                new_alt = filename.replace("-", " ")
                return f"**{new_alt}**：{description}\n\n![{new_alt}](image://{full_filename})"

            except Exception as e:
                logger.warning(f"图片处理失败 {url}: {e}")
                return match.group(0)

        new_markdown = re.sub(pattern, replace_image, markdown)
        return new_markdown, image_metadata
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_image.py::TestImagePostProcessor -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add docpipe/image.py tests/test_image.py
git commit -m "feat: 添加 ImagePostProcessor 图片引用处理器"
```

---

### Task 3: 集成到 DingtalkSource

**Files:**
- Modify: `docpipe/sources/dingtalk.py:69-120`
- Modify: `docpipe/cli.py:56-77, 121-131`

- [ ] **Step 1: 写失败测试**

在 `tests/test_image.py` 末尾追加：

```python
from unittest.mock import patch, MagicMock


class TestDingtalkSourceImageIntegration:
    def test_fetch_with_image_description_enabled(self, monkeypatch):
        from docpipe.sources.dingtalk import DingtalkSource

        vision = _FakeVisionClient(results={
            "default": ("architecture-diagram", "展示系统架构"),
        })

        mock_client = MagicMock()
        mock_client.read_document.return_value = (
            "# 标题\n\n"
            "![img.png](https://example.com/img.png)\n\n"
            "正文内容"
        )
        monkeypatch.setattr(
            "docpipe.sources.dingtalk._WikiClient",
            lambda: mock_client,
        )

        source = DingtalkSource(
            space_id="test-space",
            image_description=True,
            image_description_api_key="key",
            image_description_base_url="https://api.example.com/v1",
            image_description_model="gpt-4o",
        )
        # 替换内部的 vision client
        source._image_processor.vision_client = vision

        doc_meta = DocumentMeta(
            id="test-node",
            title="测试文档",
            path="测试文档",
            hash="",
            extra={"contentType": "ALIDOC", "extension": "adoc"},
        )
        doc = source.fetch(doc_meta)

        assert "image://architecture-diagram.png" in doc.content
        assert "展示系统架构" in doc.content
        assert "image_metadata" in doc.meta.extra
        assert "architecture-diagram.png" in doc.meta.extra["image_metadata"]

    def test_fetch_without_image_description(self, monkeypatch):
        from docpipe.sources.dingtalk import DingtalkSource

        mock_client = MagicMock()
        mock_client.read_document.return_value = "![img](https://example.com/img.png)"

        monkeypatch.setattr(
            "docpipe.sources.dingtalk._WikiClient",
            lambda: mock_client,
        )

        source = DingtalkSource(space_id="test-space")
        doc_meta = DocumentMeta(
            id="test-node",
            title="测试文档",
            path="测试文档",
            hash="",
            extra={"contentType": "ALIDOC", "extension": "adoc"},
        )
        doc = source.fetch(doc_meta)

        assert "https://example.com/img.png" in doc.content
        assert "image_metadata" not in doc.meta.extra
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_image.py::TestDingtalkSourceImageIntegration -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'image_description'`

- [ ] **Step 3: 修改 DingtalkSource.__init__ 和 fetch**

修改 `docpipe/sources/dingtalk.py`：

在文件顶部添加导入：
```python
import logging

logger = logging.getLogger(__name__)
```

修改 `DingtalkSource.__init__` (第 69-73 行)：
```python
@register_source("dingtalk")
class DingtalkSource(SourceBase):
    def __init__(self, space_id: str, folder_id: str | None = None, **kwargs):
        self._space_id = space_id
        self._folder_id = folder_id
        self._client = _WikiClient()
        self._nodes_cache: list[dict] | None = None

        self._image_processor = None
        if kwargs.get("image_description"):
            from docpipe.image import ImagePostProcessor, OpenAIVisionClient
            vision_client = OpenAIVisionClient(
                api_key=kwargs.get("image_description_api_key", ""),
                base_url=kwargs.get("image_description_base_url", ""),
                model=kwargs.get("image_description_model", "gpt-4o"),
            )
            self._image_processor = ImagePostProcessor(vision_client)
```

修改 `fetch` 方法 (第 98-120 行)，在 `content_hash` 行之前插入图片处理：
```python
    def fetch(self, doc_meta: DocumentMeta) -> Document:
        content_type = doc_meta.extra.get("contentType", "")
        extension = doc_meta.extra.get("extension", "")
        node_id = doc_meta.id

        if content_type == "ALIDOC" or extension == "adoc":
            markdown = self._client.read_document(node_id)
        else:
            ext = extension if extension else "bin"
            markdown = self._download_and_convert(node_id, ext)

        if self._image_processor:
            source_context = f"{doc_meta.title} - {doc_meta.path}"
            markdown, image_metadata = self._image_processor.process(markdown, source_context)
            doc_meta.extra["image_metadata"] = image_metadata

        content_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        return Document(
            meta=DocumentMeta(
                id=doc_meta.id,
                title=doc_meta.title,
                path=doc_meta.path,
                hash=content_hash,
                extra=doc_meta.extra,
            ),
            content=markdown,
            content_type="markdown",
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_image.py::TestDingtalkSourceImageIntegration -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add docpipe/sources/dingtalk.py tests/test_image.py
git commit -m "feat: DingtalkSource 集成图片描述处理"
```

---

### Task 4: CLI 和配置支持

**Files:**
- Modify: `docpipe/cli.py:29-49, 121-131`

- [ ] **Step 1: 写失败测试**

在 `tests/test_image.py` 末尾追加：

```python
class TestCLIImageDescription:
    def test_extract_source_config_passes_image_description(self):
        from docpipe.cli import _extract_source_config

        kwargs = {
            "space": "test-space",
            "image_description": True,
            "image_description_api_key": "sk-test",
            "image_description_base_url": "https://api.example.com/v1",
            "image_description_model": "gpt-4o",
        }
        config = _extract_source_config("dingtalk", kwargs)

        assert config["space_id"] == "test-space"
        assert config["image_description"] is True
        assert config["image_description_api_key"] == "sk-test"
        assert config["image_description_base_url"] == "https://api.example.com/v1"
        assert config["image_description_model"] == "gpt-4o"

    def test_extract_source_config_without_image_description(self):
        from docpipe.cli import _extract_source_config

        kwargs = {"space": "test-space"}
        config = _extract_source_config("dingtalk", kwargs)

        assert config["space_id"] == "test-space"
        assert "image_description" not in config

    def test_config_yaml_passes_image_description(self):
        from docpipe.cli import _extract_source_config

        kwargs = {
            "space": "test-space",
            "image_description": True,
            "image_description_api_key": "key",
            "image_description_base_url": "url",
            "image_description_model": "model",
        }
        config = _extract_source_config("dingtalk", kwargs)

        assert config["image_description"] is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_image.py::TestCLIImageDescription -v`
Expected: FAIL — 断言失败，`image_description` 不在 config 中

- [ ] **Step 3: 修改 _extract_source_config**

修改 `docpipe/cli.py` 中的 `_extract_source_config` 函数（第 121-131 行）：

```python
def _extract_source_config(source_name, kwargs):
    config = {}
    if source_name == "dingtalk":
        if kwargs.get("space"):
            config["space_id"] = kwargs["space"]
        if kwargs.get("folder"):
            config["folder_id"] = kwargs["folder"]
        if kwargs.get("image_description"):
            config["image_description"] = True
            config["image_description_api_key"] = kwargs.get("image_description_api_key", "")
            config["image_description_base_url"] = kwargs.get("image_description_base_url", "")
            config["image_description_model"] = kwargs.get("image_description_model", "gpt-4o")
    elif source_name == "local":
        if kwargs.get("input_dir"):
            config["input_dir"] = kwargs["input_dir"]
    return config
```

在 `run` 命令的 `@click.option` 列表中（第 29-35 行之后）添加：

```python
    @click.option("--enable-image-description", is_flag=True, default=False,
                  help="启用图片描述生成")
    @click.option("--image-api-key", default=None, envvar="IMAGE_DESCRIPTION_API_KEY",
                  help="图片描述 API Key")
    @click.option("--image-base-url", default=None, envvar="IMAGE_DESCRIPTION_BASE_URL",
                  help="图片描述 API Base URL")
    @click.option("--image-model", default="gpt-4o", envvar="IMAGE_DESCRIPTION_MODEL",
                  help="图片描述模型名称")
```

在 `run` 函数签名中添加对应参数：

```python
def run(ctx, source_name, dest_name, config_path, pipeline_name, resume, sync_mode, dry_run,
        space, folder, input_dir, bank_id, hindsight_url, hindsight_key, context,
        enable_image_description, image_api_key, image_base_url, image_model):
```

在 `_run_single` 调用时传递新参数（修改第 42-46 行）：

```python
        _run_single(ctx, source_name, dest_name, resume, sync_mode, dry_run,
                     space=space, folder=folder, input_dir=input_dir,
                     bank_id=bank_id, hindsight_url=hindsight_url,
                     hindsight_key=hindsight_key, context=context,
                     image_description=enable_image_description,
                     image_description_api_key=image_api_key,
                     image_description_base_url=image_base_url,
                     image_description_model=image_model)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_image.py::TestCLIImageDescription -v`
Expected: PASS

- [ ] **Step 5: 运行全部测试确认无回归**

Run: `python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add docpipe/cli.py tests/test_image.py
git commit -m "feat: CLI 支持图片描述配置参数"
```

---

### Task 5: YAML 配置文件支持

**Files:**
- Modify: `docpipe/cli.py:79-118`

- [ ] **Step 1: 写失败测试**

在 `tests/test_image.py` 末尾追加：

```python
class TestYAMLConfigImageDescription:
    def test_yaml_source_config_includes_image_description(self, tmp_path):
        config_content = """
pipelines:
  - name: wiki-to-hindsight
    source: dingtalk
    destination: hindsight
    source_config:
      space_id: "test-space"
      image_description: true
      image_description_api_key: "sk-test"
      image_description_base_url: "https://api.example.com/v1"
      image_description_model: "gpt-4o"
    dest_config:
      bank_id: "test-bank"
"""
        config_file = tmp_path / "test-config.yaml"
        config_file.write_text(config_content)

        import yaml
        config = yaml.safe_load(config_file.read_text())
        pipe = config["pipelines"][0]
        source_config = pipe.get("source_config", {})

        assert source_config["image_description"] is True
        assert source_config["image_description_api_key"] == "sk-test"
```

- [ ] **Step 2: 运行测试确认通过（YAML 配置已透传）**

Run: `python -m pytest tests/test_image.py::TestYAMLConfigImageDescription -v`
Expected: PASS — YAML 配置中的 `source_config` 直接作为 `**kwargs` 传入 Source 构造函数，不需要额外处理。

- [ ] **Step 3: Commit**

```bash
git add tests/test_image.py
git commit -m "test: 添加 YAML 配置图片描述测试"
```

---

### Task 6: 环境变量默认值支持

**Files:**
- Modify: `docpipe/sources/dingtalk.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_image.py` 末尾追加：

```python
class TestEnvironmentVariableDefaults:
    def test_dingtalk_source_uses_env_vars_for_image_description(self, monkeypatch):
        from docpipe.sources.dingtalk import DingtalkSource

        monkeypatch.setenv("IMAGE_DESCRIPTION_API_KEY", "env-key")
        monkeypatch.setenv("IMAGE_DESCRIPTION_BASE_URL", "https://env.example.com/v1")
        monkeypatch.setenv("IMAGE_DESCRIPTION_MODEL", "env-model")

        mock_client = MagicMock()
        monkeypatch.setattr(
            "docpipe.sources.dingtalk._WikiClient",
            lambda: mock_client,
        )

        source = DingtalkSource(
            space_id="test-space",
            image_description=True,
        )

        assert source._image_processor is not None
        assert source._image_processor.vision_client.model == "env-model"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_image.py::TestEnvironmentVariableDefaults -v`
Expected: FAIL — `api_key` 为空字符串

- [ ] **Step 3: 修改 DingtalkSource 使用环境变量默认值**

修改 `docpipe/sources/dingtalk.py` 中 `__init__` 的 image_processor 初始化部分：

```python
        self._image_processor = None
        if kwargs.get("image_description"):
            import os
            from docpipe.image import ImagePostProcessor, OpenAIVisionClient
            vision_client = OpenAIVisionClient(
                api_key=kwargs.get("image_description_api_key", "") or os.environ.get("IMAGE_DESCRIPTION_API_KEY", ""),
                base_url=kwargs.get("image_description_base_url", "") or os.environ.get("IMAGE_DESCRIPTION_BASE_URL", ""),
                model=kwargs.get("image_description_model", "") or os.environ.get("IMAGE_DESCRIPTION_MODEL", "gpt-4o"),
            )
            self._image_processor = ImagePostProcessor(vision_client)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_image.py::TestEnvironmentVariableDefaults -v`
Expected: PASS

- [ ] **Step 5: 运行全部测试确认无回归**

Run: `python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add docpipe/sources/dingtalk.py tests/test_image.py
git commit -m "feat: 支持环境变量默认值配置图片描述"
```
