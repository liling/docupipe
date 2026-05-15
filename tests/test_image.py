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
