"""测试钉钉 space 名称解析功能"""
from unittest.mock import MagicMock, patch

import pytest

from docupipe.sources.dingtalk import DingtalkSource, _WikiClient


class TestSpaceResolution:
    """测试 space 名称到 ID 的解析"""

    @patch.object(_WikiClient, '_run_dws')
    def test_resolve_space_name_exact_match(self, mock_run_dws):
        mock_run_dws.return_value = {
            "wikiSpaces": [
                {"name": "平台产品知识库", "workspaceId": "nb9XJB7qpnkxQXyA"},
                {"name": "数据线-知识库", "workspaceId": "nb9XJVyNJv2LaXyA"},
            ]
        }

        client = _WikiClient()
        result = client.resolve_space_name("平台产品知识库")

        assert result == "nb9XJB7qpnkxQXyA"
        mock_run_dws.assert_called_once()

    @patch.object(_WikiClient, '_run_dws')
    def test_resolve_space_name_fuzzy_match(self, mock_run_dws):
        mock_run_dws.return_value = {
            "wikiSpaces": [
                {"name": "平台产品知识库", "workspaceId": "nb9XJB7qpnkxQXyA"},
                {"name": "数据线-知识库", "workspaceId": "nb9XJVyNJv2LaXyA"},
            ]
        }

        client = _WikiClient()
        result = client.resolve_space_name("平台产品")

        assert result == "nb9XJB7qpnkxQXyA"

    @patch.object(_WikiClient, '_run_dws')
    def test_resolve_space_name_not_found(self, mock_run_dws):
        mock_run_dws.return_value = {
            "wikiSpaces": [
                {"name": "平台产品知识库", "workspaceId": "nb9XJB7qpnkxQXyA"},
            ]
        }

        client = _WikiClient()
        result = client.resolve_space_name("不存在的知识库")

        assert result is None

    @patch.object(_WikiClient, 'resolve_space_name')
    def test_dingtalk_source_with_space_name(self, mock_resolve):
        mock_resolve.return_value = "nb9XJB7qpnkxQXyA"

        source = DingtalkSource(space="平台产品知识库")

        assert source._space_id == "nb9XJB7qpnkxQXyA"
        assert source._space_name == "平台产品知识库"
        mock_resolve.assert_called_once_with("平台产品知识库")

    def test_dingtalk_source_with_space_id(self):
        source = DingtalkSource(space_id="nb9XJB7qpnkxQXyA")

        assert source._space_id == "nb9XJB7qpnkxQXyA"
        assert source._space_name == ""

    def test_dingtalk_source_without_space_or_id(self):
        with pytest.raises(ValueError, match="必须提供 space 或 space_id"):
            DingtalkSource()

    @patch.object(_WikiClient, 'resolve_space_name')
    def test_dingtalk_source_space_not_found(self, mock_resolve):
        mock_resolve.return_value = None

        with pytest.raises(ValueError, match="无法找到知识库"):
            DingtalkSource(space="不存在的知识库")
