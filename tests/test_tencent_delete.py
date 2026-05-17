from unittest.mock import MagicMock, patch

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
