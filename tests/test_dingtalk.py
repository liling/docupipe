from __future__ import annotations

import pytest

from docupipe.sources.dingtalk import DingtalkSource, _WikiClient


class TestWikiClientListNodesByFolder:
    def test_calls_doc_list_with_folder(self, monkeypatch):
        captured = {}
        def mock_run_dws(self, args):
            captured["args"] = args
            return {"nodes": [{"nodeId": "abc", "name": "doc1", "nodeType": "doc"}]}
        monkeypatch.setattr(_WikiClient, "_run_dws", mock_run_dws)
        client = _WikiClient()
        result = client.list_nodes_by_folder("folder123")
        assert captured["args"] == ["doc", "list", "--folder", "folder123", "--page-size", "50"]
        assert len(result) == 1
        assert result[0]["nodeId"] == "abc"

    def test_pagination(self, monkeypatch):
        call_count = 0
        def mock_run_dws(self, args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"nodes": [{"nodeId": "a"}], "nextPageToken": "tok1"}
            return {"nodes": [{"nodeId": "b"}]}
        monkeypatch.setattr(_WikiClient, "_run_dws", mock_run_dws)
        client = _WikiClient()
        result = client.list_nodes_by_folder("f1")
        assert len(result) == 2
        assert call_count == 2


class TestDingtalkSourceDocMode:
    def test_doc_mode_requires_folder_id(self):
        with pytest.raises(ValueError, match="folder_id"):
            DingtalkSource(mode="doc")

    def test_doc_mode_stores_folder_id(self, monkeypatch):
        source = DingtalkSource(mode="doc", folder_id="test_folder_id")
        assert source._mode == "doc"
        assert source._doc_folder_id == "test_folder_id"

    def test_wiki_mode_default(self, monkeypatch):
        monkeypatch.setattr("docupipe.sources.dingtalk._WikiClient.resolve_space_name", lambda self, x: "ws1")
        source = DingtalkSource(space="测试")
        assert source._mode == "wiki"

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="mode"):
            DingtalkSource(mode="invalid", folder_id="f1")


class TestDingtalkSourceDocList:
    def _mock_list_nodes_by_folder(self, monkeypatch, folder_nodes, node_info=None):
        def mock_list(self, folder_id, folder_name=""):
            return folder_nodes.get(folder_id, [])

        def mock_get_node_info(self, node_id):
            return node_info or {"extension": ""}

        monkeypatch.setattr(_WikiClient, "list_nodes_by_folder", mock_list)
        monkeypatch.setattr(_WikiClient, "get_node_info", mock_get_node_info)

    def test_doc_mode_list_collects_files(self, monkeypatch):
        nodes = {
            "f1": [
                {"nodeId": "doc1", "name": "文档1", "nodeType": "doc",
                 "contentType": "DOCUMENT", "extension": "", "updateTime": 1000},
                {"nodeId": "doc2", "name": "文档2.docx", "nodeType": "doc",
                 "contentType": "DOCUMENT", "extension": "docx", "updateTime": 2000},
            ]
        }
        self._mock_list_nodes_by_folder(monkeypatch, nodes)
        source = DingtalkSource(mode="doc", folder_id="f1")
        result = source.list()
        assert len(result) == 2
        assert result[0].id == "doc1"
        assert result[1].id == "doc2"

    def test_doc_mode_list_recursive_folders(self, monkeypatch):
        nodes = {
            "root": [
                {"nodeId": "sub1", "name": "子文件夹", "nodeType": "folder", "hasChildren": True},
                {"nodeId": "doc1", "name": "根文件.txt", "nodeType": "doc",
                 "contentType": "FILE", "extension": "txt", "updateTime": 1000},
            ],
            "sub1": [
                {"nodeId": "doc2", "name": "子文件.pdf", "nodeType": "doc",
                 "contentType": "FILE", "extension": "pdf", "updateTime": 2000},
            ]
        }
        self._mock_list_nodes_by_folder(monkeypatch, nodes)
        source = DingtalkSource(mode="doc", folder_id="root")
        result = source.list()
        assert len(result) == 2
        paths = [r.path for r in result]
        assert "根文件.txt" in paths
        assert "子文件夹/子文件.pdf" in paths

    def test_doc_mode_list_no_space_name(self, monkeypatch):
        nodes = {
            "f1": [
                {"nodeId": "doc1", "name": "文档", "nodeType": "doc",
                 "contentType": "DOCUMENT", "extension": "", "updateTime": 1000},
            ]
        }
        self._mock_list_nodes_by_folder(monkeypatch, nodes)
        source = DingtalkSource(mode="doc", folder_id="f1")
        result = source.list()
        assert result[0].extra["space_name"] == ""

    def test_doc_mode_list_skip_folders(self, monkeypatch):
        nodes = {
            "f1": [
                {"nodeId": "empty", "name": "空文件夹", "nodeType": "folder", "hasChildren": False},
            ]
        }
        self._mock_list_nodes_by_folder(monkeypatch, nodes)
        source = DingtalkSource(mode="doc", folder_id="f1")
        result = source.list()
        assert len(result) == 0


class TestSourceChangeDetection:
    def test_localdrive_supports_mtime_and_hash(self, tmp_path):
        from docupipe.sources.localdrive import LocalDriveSource
        (tmp_path / "test.md").write_text("hello")
        source = LocalDriveSource(input_dir=str(tmp_path))
        assert sorted(source.supported_change_detection()) == ["hash", "mtime"]

    def test_localdrive_list_provides_mtime(self, tmp_path):
        from docupipe.sources.localdrive import LocalDriveSource
        (tmp_path / "test.md").write_text("hello")
        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        assert len(metas) == 1
        assert metas[0].extra.get("mtime") is not None
        assert isinstance(metas[0].extra["mtime"], int)

    def test_dingtalk_supports_mtime_and_hash(self):
        assert "mtime" in DingtalkSource.supported_change_detection(DingtalkSource)
        assert "hash" in DingtalkSource.supported_change_detection(DingtalkSource)

    def test_tencent_supports_hash_only(self):
        from docupipe.sources.tencent import TencentSource
        assert sorted(TencentSource.supported_change_detection(TencentSource)) == ["hash"]
