import os
from unittest.mock import MagicMock, patch

import pytest
from docupipe.models import Bundle, BundleMeta, FileItem


class TestTencentDocClient:
    def test_delete_node_calls_mcp(self):
        from docupipe.sources.tencent import _TencentDocClient

        with patch("docupipe.sources.tencent._TencentDocClient._call_tool") as mock_call:
            mock_call.return_value = MagicMock()
            client = _TencentDocClient("fake-token")
            client.delete_node("space_123", "node_456")
            mock_call.assert_called_once_with("delete_space_node", {
                "space_id": "space_123",
                "node_id": "node_456",
                "remove_type": "current",
            })

    def test_delete_node_with_remove_type_all(self):
        from docupipe.sources.tencent import _TencentDocClient

        with patch("docupipe.sources.tencent._TencentDocClient._call_tool") as mock_call:
            mock_call.return_value = MagicMock()
            client = _TencentDocClient("fake-token")
            client.delete_node("space_123", "node_456", remove_type="all")
            mock_call.assert_called_once_with("delete_space_node", {
                "space_id": "space_123",
                "node_id": "node_456",
                "remove_type": "all",
            })


class TestTencentSourceSpaceId:
    def test_fetch_injects_space_id(self):
        from docupipe.sources.tencent import TencentSource

        with patch("docupipe.sources.tencent._TencentDocClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.get_content.return_value = "# Test"
            MockClient.return_value = mock_instance

            source = TencentSource(space_id="space_123")
            meta = BundleMeta(id="node_1", title="Test", extra={"tencent_doc_type": "doc"})
            bundle = source.fetch(meta)
            assert bundle.context["space_id"] == "space_123"


class TestTencentDeleteStep:
    def _make_bundle(self, node_id="node_1", space_id="space_123"):
        return Bundle(
            files=[FileItem(name="test.md", content="hello", content_type="text/markdown", role="main")],
            context={"id": node_id, "space_id": space_id, "path": "test.md"},
        )

    def test_process_deletes_node(self):
        with patch("docupipe.steps.tencent_delete._TencentDocClient") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance

            from docupipe.steps.tencent_delete import TencentDeleteStep
            step = TencentDeleteStep()
            bundle = self._make_bundle()
            result = step.process(bundle)

            mock_instance.delete_node.assert_called_once_with("space_123", "node_1", "current")
            assert result is bundle

    def test_process_with_remove_type_all(self):
        with patch("docupipe.steps.tencent_delete._TencentDocClient") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance

            from docupipe.steps.tencent_delete import TencentDeleteStep
            step = TencentDeleteStep(remove_type="all")
            bundle = self._make_bundle()
            step.process(bundle)

            mock_instance.delete_node.assert_called_once_with("space_123", "node_1", "all")

    def test_process_logs_warning_on_missing_context(self):
        with patch("docupipe.steps.tencent_delete._TencentDocClient") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance

            from docupipe.steps.tencent_delete import TencentDeleteStep
            step = TencentDeleteStep()
            bundle = Bundle(
                files=[FileItem(name="test.md", content="hello", content_type="text/markdown", role="main")],
                context={"id": "node_1"},
            )
            step.process(bundle)
            mock_instance.delete_node.assert_not_called()

    def test_process_continues_on_delete_failure(self):
        with patch("docupipe.steps.tencent_delete._TencentDocClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.delete_node.side_effect = RuntimeError("API 错误")
            MockClient.return_value = mock_instance

            from docupipe.steps.tencent_delete import TencentDeleteStep
            step = TencentDeleteStep()
            bundle = self._make_bundle()
            result = step.process(bundle)
            assert result is bundle

    def test_raises_without_token(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TENCENT_DOCS_TOKEN", None)
            from docupipe.steps.tencent_delete import TencentDeleteStep
            with pytest.raises(ValueError, match="TENCENT_DOCS_TOKEN"):
                TencentDeleteStep()
