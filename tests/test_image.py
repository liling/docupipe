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


from docpipe.image import ImagePostProcessor


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


def _mock_get(url, **kwargs):
    mock_resp = MagicMock()
    mock_resp.content = b"fake-image-data"
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


class TestImagePostProcessor:
    def test_process_replaces_image_refs(self, monkeypatch):
        monkeypatch.setattr("docpipe.image.req.get", _mock_get)
        monkeypatch.setattr("docpipe.image.validate_image", lambda b: b)
        vision = _FakeVisionClient(results={
            "default": ("architecture-diagram", "展示微服务三层架构"),
        })
        processor = ImagePostProcessor(vision_client=vision)

        markdown = '![imag.png](https://example.com/test.png)'
        result, metadata = processor.process(markdown, "测试文档")

        assert "**architecture diagram**：展示微服务三层架构" in result
        assert "image://architecture-diagram.png" in result
        assert "architecture-diagram.png" in metadata
        assert metadata["architecture-diagram.png"]["original_url"] == "https://example.com/test.png"
        assert metadata["architecture-diagram.png"]["description"] == "展示微服务三层架构"

    def test_process_keeps_original_on_failure(self):
        vision = _FakeVisionClient()
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

    def test_process_multiple_images(self, monkeypatch):
        monkeypatch.setattr("docpipe.image.req.get", _mock_get)
        monkeypatch.setattr("docpipe.image.validate_image", lambda b: b)
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


class TestDingtalkSourceImageIntegration:
    def test_fetch_with_image_description_enabled(self, monkeypatch):
        from docpipe.sources.dingtalk import DingtalkSource

        vision = _FakeVisionClient(results={
            "default": ("architecture-diagram", "展示系统架构"),
        })

        monkeypatch.setattr("docpipe.image.req.get", _mock_get)
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


class TestEnvironmentVariableDefaults:
    def test_dingtalk_source_uses_env_vars(self, monkeypatch):
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
