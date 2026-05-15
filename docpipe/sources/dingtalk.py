from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from pathlib import Path

import requests

from docpipe.models import Document, DocumentMeta

logger = logging.getLogger(__name__)
from docpipe.sources import register_source
from docpipe.sources.base import SourceBase

_CONVERTIBLE_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt",
    ".html", ".htm", ".csv", ".json", ".xml", ".txt", ".md",
    ".rtf", ".odt", ".ods",
}


class _WikiClient:
    def _run_dws(self, args: list[str]) -> dict | list:
        import subprocess
        cmd = ["dws"] + args + ["--format", "json", "--yes"]
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
            raise RuntimeError(f"dws 命令失败: {' '.join(args)}\n{stderr}")
        stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
        if not stdout.strip():
            return {}
        return json.loads(stdout)

    def list_nodes(self, workspace_id: str, folder_id: str | None = None) -> list[dict]:
        all_items: list[dict] = []
        page_token: str | None = None
        while True:
            args = ["doc", "list", "--workspace", workspace_id, "--page-size", "50"]
            if folder_id:
                args += ["--folder", folder_id]
            if page_token:
                args += ["--page-token", page_token]
            data = self._run_dws(args)
            items = data.get("nodes", []) if isinstance(data, dict) else []
            all_items.extend(items)
            page_token = data.get("nextPageToken") if isinstance(data, dict) else None
            if not page_token:
                break
        return all_items

    def read_document(self, node_id: str) -> str:
        data = self._run_dws(["doc", "read", "--node", node_id])
        if isinstance(data, dict):
            return data.get("markdown", "")
        return str(data)

    def download_file(self, node_id: str) -> str:
        data = self._run_dws(["doc", "download", "--node", node_id])
        if isinstance(data, dict):
            return data.get("resourceUrl", "") or data.get("downloadUrl", "")
        raise RuntimeError(f"下载失败，无法获取 URL: {node_id}")

    def get_space_info(self, space_id: str) -> dict:
        return self._run_dws(["wiki", "space", "get", "--id", space_id])


@register_source("dingtalk")
class DingtalkSource(SourceBase):
    def __init__(self, space_id: str, folder_id: str | None = None, **kwargs):
        self._space_id = space_id
        self._folder_id = folder_id
        self._client = _WikiClient()
        self._nodes_cache: list[dict] | None = None

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

    def list_documents(self) -> list[DocumentMeta]:
        nodes = self._collect_nodes(self._space_id, self._folder_id)
        result = []
        for node in nodes:
            node_type = node.get("nodeType", "")
            if node_type == "folder":
                continue
            node_id = node.get("nodeId", "")
            title = node.get("name", "未命名")
            result.append(DocumentMeta(
                id=node_id,
                title=title,
                path=node.get("_path", ""),
                hash="",
                extra={
                    "contentType": node.get("contentType", ""),
                    "extension": node.get("extension", ""),
                    "updateTime": node.get("updateTime"),
                    "nodeType": node_type,
                },
            ))
        return result

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

    def _collect_nodes(self, space_id: str, folder_id: str | None, parent_path: str = "") -> list[dict]:
        nodes = self._client.list_nodes(space_id, folder_id)
        result = []
        for node in nodes:
            title = node.get("name", "未命名")
            node_id = node.get("nodeId", "")
            node_type = node.get("nodeType", "")
            current_path = f"{parent_path}/{title}" if parent_path else title

            if node_type == "folder":
                if node.get("hasChildren"):
                    result.extend(self._collect_nodes(space_id, node_id, current_path))
            else:
                node["_path"] = current_path
                result.append(node)
        return result

    def _download_and_convert(self, node_id: str, extension: str) -> str:
        download_url = self._client.download_file(node_id)
        resp = requests.get(download_url, timeout=120)
        resp.raise_for_status()

        suffix = f".{extension}" if extension else ".bin"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = Path(tmp.name)

        try:
            from markitdown import MarkItDown
            md = MarkItDown()
            result = md.convert(str(tmp_path))
            return result.markdown
        finally:
            tmp_path.unlink(missing_ok=True)
