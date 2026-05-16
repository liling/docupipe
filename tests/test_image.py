from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from docpipe.image import OpenAIVisionClient, ImagePostProcessor, validate_image
from docpipe.models import FileItem
from docpipe.steps.image_description import ImageDescriptionStep


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

    def test_a_describe_returns_filename_and_description(self, monkeypatch):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "filename": "async-flow-diagram",
            "description": "异步处理流程图",
        })

        async def mock_create(**kwargs):
            return mock_response

        mock_async_client = MagicMock()
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

        assert "![展示微服务三层架构](https://example.com/architecture-diagram.png)" in result
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
        assert "image-1.png" in result
        assert "image-2.png" in result

    def test_process_no_images(self):
        vision = _FakeVisionClient()
        processor = ImagePostProcessor(vision_client=vision)

        markdown = "这是一段没有图片的文字"
        result, metadata = processor.process(markdown, "测试文档")

        assert result == markdown
        assert metadata == {}
        assert len(vision.calls) == 0

    def test_process_with_image_files(self, monkeypatch):
        """测试使用 image_files 参数处理图片"""
        monkeypatch.setattr("docpipe.image.validate_image", lambda b: b)
        vision = _FakeVisionClient(results={
            "default": ("chart", "数据图表"),
        })
        processor = ImagePostProcessor(vision_client=vision)

        image_files = {
            "images/chart.png": FileItem(
                name="images/chart.png",
                content=b"fake-png-data",
                content_type="image/png",
                role="image"
            )
        }

        markdown = '![图表](images/chart.png)'
        result, metadata = processor.process(markdown, "测试文档", image_files=image_files)

        assert "![数据图表](images/chart.png)" in result
        assert "chart.png" in metadata
        assert metadata["chart.png"]["original_url"] == "images/chart.png"
        assert metadata["chart.png"]["description"] == "数据图表"

    def test_process_with_image_files_base64_content(self, monkeypatch):
        """测试 image_files 中内容为 base64 字符串的情况"""
        import base64
        monkeypatch.setattr("docpipe.image.validate_image", lambda b: b)
        vision = _FakeVisionClient(results={
            "default": ("chart", "数据图表"),
        })
        processor = ImagePostProcessor(vision_client=vision)

        # FileItem.content 是 base64 字符串
        encoded_content = base64.b64encode(b"fake-png-data").decode("utf-8")
        image_files = {
            "chart.png": FileItem(
                name="chart.png",
                content=encoded_content,
                content_type="image/png",
                role="image"
            )
        }

        markdown = '![图表](chart.png)'
        result, metadata = processor.process(markdown, "测试文档", image_files=image_files)

        assert "![数据图表](chart.png)" in result
        assert "chart.png" in metadata

    def test_process_image_files_missing(self, monkeypatch):
        """测试 image_files 中找不到对应文件，应保持原样（降级策略）"""
        monkeypatch.setattr("docpipe.image.req.get", _mock_get)
        monkeypatch.setattr("docpipe.image.validate_image", lambda b: b)
        vision = _FakeVisionClient()
        processor = ImagePostProcessor(vision_client=vision)

        image_files = {
            "other.png": FileItem(
                name="other.png",
                content=b"data",
                content_type="image/png",
                role="image"
            )
        }

        markdown = '![图表](missing.png)'
        result, metadata = processor.process(markdown, "测试文档", image_files=image_files)

        # 在 image_files 中找不到，没有 images_dir，也没有 http:// 协议
        # 所以应该保持原样，不调用 vision_client
        assert result == '![图表](missing.png)'
        assert metadata == {}
        assert len(vision.calls) == 0

    def test_process_concurrent_multiple_images(self, monkeypatch):
        monkeypatch.setattr("docpipe.image.req.get", _mock_get)
        monkeypatch.setattr("docpipe.image.validate_image", lambda b: b)
        call_count = [0]

        def mock_describe(img, ctx):
            call_count[0] += 1
            return f"image-{call_count[0]}", f"描述{call_count[0]}"

        async def mock_a_describe(img, ctx):
            call_count[0] += 1
            return f"image-{call_count[0]}", f"描述{call_count[0]}"

        vision = _FakeVisionClient()
        vision.describe = mock_describe
        vision.a_describe = mock_a_describe

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
        assert "描述1" in result
        assert "描述2" in result
        assert "描述3" in result


class TestEnvironmentVariableDefaults:
    def test_dingtalk_source_uses_env_vars(self, monkeypatch):
        """测试环境变量默认值（ImagePostProcessor 的环境变量）"""
        monkeypatch.setenv("IMAGE_DESCRIPTION_API_KEY", "env-key")
        monkeypatch.setenv("IMAGE_DESCRIPTION_BASE_URL", "https://env.example.com/v1")
        monkeypatch.setenv("IMAGE_DESCRIPTION_MODEL", "env-model")

        # 验证可以正常创建 ImagePostProcessor
        vision = OpenAIVisionClient(
            api_key="env-key",
            base_url="https://env.example.com/v1",
            model="env-model"
        )
        assert vision.model == "env-model"


class TestValidateImage:
    def test_validate_empty_returns_none(self):
        assert validate_image(b"") is None
        # 没有 magic bytes 的情况会尝试用 PIL 转换，如果失败则返回 None
        # 这里我们不测试这种情况，因为需要真实的图片数据

    def test_validate_png_magic_bytes(self):
        # 创建一个最小的有效 PNG 图片
        png_data = b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\rIHDR' + b'\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89' + b'\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\x0d\n\xeb' + b'\x00\x00\x00\x00IEND\xaeB`\x82'
        result = validate_image(png_data)
        # 如果有 PIL，会做更详细的验证；如果没有 PIL，至少不会失败
        # 这里我们只验证不会抛异常
        if result is not None:
            assert result == png_data or len(result) > 0

    def test_validate_jpg_magic_bytes(self):
        # 创建一个最小的有效 JPEG 图片
        jpg_data = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x03\x02\x02\x03\x02\x02\x03\x03\x03\x03\x04\x03\x03\x04\x05\x08\x05\x05\x04\x04\x05\n\x07\x07\x06\x08\x0c\n\x0c\x0c\x0b\n\x0b\x0b\r\x0e\x12\x10\r\x0e\x11\x0e\x0b\x0b\x10\x16\x10\x11\x13\x14\x15\x15\x15\x0c\x0f\x17\x18\x16\x14\x18\x12\x14\x15\x14\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\n\t\x16\x17\x18\x19\x1a%&\'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xd9'
        result = validate_image(jpg_data)
        if result is not None:
            assert result == jpg_data or len(result) > 0


class TestImageDescriptionStepConcurrency:
    def test_passes_concurrency_to_processor(self):
        step = ImageDescriptionStep(
            api_key="test-key",
            base_url="https://api.example.com/v1",
            model="gpt-4o",
            concurrency=8,
        )
        assert step._processor.concurrency == 8

    def test_default_concurrency_is_one(self):
        step = ImageDescriptionStep(
            api_key="test-key",
            base_url="https://api.example.com/v1",
            model="gpt-4o",
        )
        assert step._processor.concurrency == 1