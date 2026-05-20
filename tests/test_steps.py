from __future__ import annotations

import pytest

from docupipe.models import Bundle, FileItem
from docupipe.steps import STEPS, register_step, get_step
from docupipe.steps.base import Step


class TestStepRegistry:
    def test_convert_step_registered(self):
        assert "convert" in STEPS

    def test_get_step_unknown_raises(self):
        with pytest.raises(ValueError, match="未知的 step"):
            get_step("nonexistent")

    def test_register_and_get(self):
        @register_step("test_step_reg")
        class _TestStep(Step):
            def process(self, bundle):
                return bundle

        assert "test_step_reg" in STEPS
        assert get_step("test_step_reg") is _TestStep
        STEPS.pop("test_step_reg", None)


class TestConvertStep:
    def test_needs_conversion_with_matching_extension(self):
        from docupipe.steps.convert import ConvertStep
        bundle = Bundle(
            files=[FileItem(name="t.pdf", content=b"", content_type="application/pdf", role="main")],
            context={"id": "1", "title": "t", "path": "t.pdf", "extension": "pdf"},
        )
        step = ConvertStep(extension_rules={".pdf": "markitdown"})
        assert step.needs_conversion(bundle) is True

    def test_no_conversion_without_matching_extension(self):
        from docupipe.steps.convert import ConvertStep
        bundle = Bundle(
            files=[FileItem(name="t.txt", content="hello", content_type="text/plain", role="main")],
            context={"id": "1", "title": "t", "path": "t.txt", "extension": "txt"},
        )
        step = ConvertStep(extension_rules={".pdf": "markitdown"})
        assert step.needs_conversion(bundle) is False

    def test_source_rule_skips_conversion(self):
        from docupipe.steps.convert import ConvertStep
        bundle = Bundle(
            files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "t", "path": "t.md", "extension": "md"},
        )
        step = ConvertStep(extension_rules={".md": "source"})
        assert step.needs_conversion(bundle) is False

    def test_process_no_rule_returns_unchanged(self):
        from docupipe.steps.convert import ConvertStep
        bundle = Bundle(
            files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "t", "path": "t.md", "extension": "md"},
        )
        step = ConvertStep(extension_rules={".pdf": "markitdown"})
        result = step.process(bundle)
        assert result.main.content == "hello"


class TestImageDescriptionStep:
    def test_non_text_content_skipped(self):
        from docupipe.steps.image_description import ImageDescriptionStep
        step = ImageDescriptionStep(api_key="k", base_url="http://x", model="m")
        bundle = Bundle(
            files=[FileItem(name="t.pdf", content=b"binary data", content_type="application/pdf", role="main")],
            context={"id": "1", "title": "t", "path": "t.pdf"},
        )
        result = step.process(bundle)
        assert result.main.content == b"binary data"

    def test_no_images_unchanged(self):
        from docupipe.steps.image_description import ImageDescriptionStep
        step = ImageDescriptionStep(api_key="k", base_url="http://x", model="m")
        bundle = Bundle(
            files=[FileItem(name="t.md", content="# Hello\n\nNo images here.", content_type="text/markdown", role="main")],
            context={"id": "1", "title": "t", "path": "t.md"},
        )
        result = step.process(bundle)
        assert result.main.content == "# Hello\n\nNo images here."

    def test_with_image_files_from_bundle(self, monkeypatch):
        from docupipe.steps.image_description import ImageDescriptionStep
        from unittest.mock import MagicMock

        mock_vision_client = MagicMock()
        mock_vision_client.describe.return_value = ("image-1", "图片描述")
        monkeypatch.setattr("docupipe.steps.image_description.OpenAIVisionClient", lambda **kw: mock_vision_client)

        fake_metadata = {"image_1.png": {"description": "图片描述"}}
        def mock_process(markdown, source_context, images_dir=None, image_files=None, progress_callback=None):
            assert "images/image_1.png" in image_files
            assert image_files["images/image_1.png"].content == b"fake-image"
            return ("# 标题\n\n![image_1](images/image_1.png)", fake_metadata)

        step = ImageDescriptionStep(api_key="k", base_url="http://x", model="m")
        step._processor.process = mock_process

        bundle = Bundle(
            files=[
                FileItem(name="test.md", content="# 标题\n\n![原始引用](images/image_1.png)", content_type="text/markdown", role="main"),
                FileItem(name="images/image_1.png", content=b"fake-image", content_type="image/png", role="image"),
            ],
            context={"id": "1", "title": "测试文档", "path": "test.md"},
        )

        result = step.process(bundle)
        assert result.main.content == "# 标题\n\n![image_1](images/image_1.png)"

    def test_image_files_without_path_prefix(self, monkeypatch):
        from docupipe.steps.image_description import ImageDescriptionStep
        from unittest.mock import MagicMock

        mock_vision_client = MagicMock()
        mock_vision_client.describe.return_value = ("image-1", "描述")
        monkeypatch.setattr("docupipe.steps.image_description.OpenAIVisionClient", lambda **kw: mock_vision_client)

        fake_metadata = {"image_1.png": {"description": "描述"}}
        def mock_process(markdown, source_context, images_dir=None, image_files=None, progress_callback=None):
            assert "image_1.png" in image_files
            return ("# 标题\n\n![image_1](image_1.png)", fake_metadata)

        step = ImageDescriptionStep(api_key="k", base_url="http://x", model="m")
        step._processor.process = mock_process

        bundle = Bundle(
            files=[
                FileItem(name="test.md", content="# 标题\n\n![img](image_1.png)", content_type="text/markdown", role="main"),
                FileItem(name="image_1.png", content=b"fake", content_type="image/png", role="image"),
            ],
            context={"id": "1", "title": "测试", "path": "test.md"},
        )

        result = step.process(bundle)
