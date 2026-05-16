"""测试钉钉 space 名称解析功能"""
import unittest
from unittest.mock import MagicMock, patch

from docupipe.sources.dingtalk import DingtalkSource, _WikiClient


class TestSpaceResolution(unittest.TestCase):
    """测试 space 名称到 ID 的解析"""

    @patch.object(_WikiClient, '_run_dws')
    def test_resolve_space_name_exact_match(self, mock_run_dws):
        """测试精确匹配知识库名称"""
        mock_run_dws.return_value = {
            "wikiSpaces": [
                {"name": "平台产品知识库", "workspaceId": "nb9XJB7qpnkxQXyA"},
                {"name": "数据线-知识库", "workspaceId": "nb9XJVyNJv2LaXyA"},
            ]
        }

        client = _WikiClient()
        result = client.resolve_space_name("平台产品知识库")

        self.assertEqual(result, "nb9XJB7qpnkxQXyA")
        mock_run_dws.assert_called_once()

    @patch.object(_WikiClient, '_run_dws')
    def test_resolve_space_name_fuzzy_match(self, mock_run_dws):
        """测试模糊匹配知识库名称"""
        mock_run_dws.return_value = {
            "wikiSpaces": [
                {"name": "平台产品知识库", "workspaceId": "nb9XJB7qpnkxQXyA"},
                {"name": "数据线-知识库", "workspaceId": "nb9XJVyNJv2LaXyA"},
            ]
        }

        client = _WikiClient()
        result = client.resolve_space_name("平台产品")

        self.assertEqual(result, "nb9XJB7qpnkxQXyA")

    @patch.object(_WikiClient, '_run_dws')
    def test_resolve_space_name_not_found(self, mock_run_dws):
        """测试找不到匹配的知识库"""
        mock_run_dws.return_value = {
            "wikiSpaces": [
                {"name": "平台产品知识库", "workspaceId": "nb9XJB7qpnkxQXyA"},
            ]
        }

        client = _WikiClient()
        result = client.resolve_space_name("不存在的知识库")

        self.assertIsNone(result)

    @patch.object(_WikiClient, 'resolve_space_name')
    def test_dingtalk_source_with_space_name(self, mock_resolve):
        """测试使用 space 名称初始化 DingtalkSource"""
        mock_resolve.return_value = "nb9XJB7qpnkxQXyA"

        source = DingtalkSource(space="平台产品知识库")

        self.assertEqual(source._space_id, "nb9XJB7qpnkxQXyA")
        self.assertEqual(source._space_name, "平台产品知识库")
        mock_resolve.assert_called_once_with("平台产品知识库")

    def test_dingtalk_source_with_space_id(self):
        """测试使用 space_id 初始化 DingtalkSource"""
        source = DingtalkSource(space_id="nb9XJB7qpnkxQXyA")

        self.assertEqual(source._space_id, "nb9XJB7qpnkxQXyA")
        self.assertEqual(source._space_name, "")

    def test_dingtalk_source_without_space_or_id(self):
        """测试不提供 space 或 space_id 时抛出错误"""
        with self.assertRaises(ValueError) as context:
            DingtalkSource()

        self.assertIn("必须提供 space 或 space_id", str(context.exception))

    @patch.object(_WikiClient, 'resolve_space_name')
    def test_dingtalk_source_space_not_found(self, mock_resolve):
        """测试 space 名称找不到时抛出错误"""
        mock_resolve.return_value = None

        with self.assertRaises(ValueError) as context:
            DingtalkSource(space="不存在的知识库")

        self.assertIn("无法找到知识库", str(context.exception))


if __name__ == '__main__':
    unittest.main()
