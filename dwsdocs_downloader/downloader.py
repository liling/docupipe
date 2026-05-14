from __future__ import annotations

import json
import tempfile
from pathlib import Path

import requests

from dwsdocs_downloader.converter import FileConverter
from dwsdocs_downloader.display import Display
from dwsdocs_downloader.state import StateManager, content_hash
from dwsdocs_downloader.wiki_client import WikiClient

_UNSAFE_CHARS = ('/', '\\', ':', '*', '?', '"', '<', '>', '|')


def sanitize_filename(name: str) -> str:
    for ch in _UNSAFE_CHARS:
        name = name.replace(ch, '_')
    name = name.strip()
    if not name or name == '.':
        return "未命名"
    if name.upper() in ('CON', 'PRN', 'AUX', 'NUL', 'COM1', 'LPT1'):
        return f"_{name}"
    return name


class Downloader:
    def __init__(self, client: WikiClient, output_dir: Path, display: Display | None = None):
        self._client = client
        self._output_dir = Path(output_dir)
        self._display = display or Display()
        self._converter = FileConverter()
        self._state = StateManager(self._output_dir / ".state", "download")

    def download(self, space_id: str, folder_id: str | None = None, resume: bool = False) -> None:
        space_info = self._client.get_space_info(space_id)
        space_name = sanitize_filename(space_info.get("name", space_id))
        space_dir = self._output_dir / space_name

        existing_hashes = self._state.load() if resume else {}

        self._display.start("下载知识库", 0)
        self._walk(space_dir, space_id, folder_id, existing_hashes, resume)
        self._display.stop()
        self._display.print_summary()

    def _walk(
        self,
        parent_dir: Path,
        workspace_id: str,
        folder_id: str | None,
        existing_hashes: dict[str, str],
        resume: bool,
    ) -> None:
        nodes = self._client.list_nodes(workspace_id, folder_id)
        for node in nodes:
            node_id = node.get("nodeId", "")
            title = node.get("title", "未命名")
            node_type = node.get("nodeType", "")

            if node_type == "folder":
                child_dir = parent_dir / sanitize_filename(title)
                child_dir.mkdir(parents=True, exist_ok=True)
                if node.get("hasChildren"):
                    self._walk(child_dir, workspace_id, node_id, existing_hashes, resume)
                continue

            if resume and node_id in existing_hashes:
                md_path = parent_dir / f"{sanitize_filename(title)}.md"
                meta_path = parent_dir / f"{sanitize_filename(title)}.meta.json"
                if md_path.exists() and meta_path.exists():
                    self._display.log("DEBUG", f"跳过已有: {title}")
                    continue

            self._download_node(parent_dir, node, node_id, title)

    def _download_node(self, parent_dir: Path, node: dict, node_id: str, title: str) -> None:
        safe_name = sanitize_filename(title)

        content_type = node.get("contentType", "")
        extension = node.get("extension", "")
        if not content_type:
            info = self._client.get_node_info(node_id)
            content_type = info.get("contentType", "")
            extension = info.get("extension", "")

        try:
            if content_type == "ALIDOC" and extension == "adoc":
                markdown = self._client.read_document(node_id)
            else:
                markdown = self._download_and_convert(node_id, extension)

            self._save_document(parent_dir, safe_name, node_id, markdown, content_type, extension)
            self._display.result("success", f"{safe_name}")
        except Exception as e:
            self._display.result("error", f"{safe_name}: {e}")

    def _download_and_convert(self, node_id: str, extension: str) -> str:
        download_url = self._client.download_file(node_id)
        resp = requests.get(download_url, timeout=120)
        resp.raise_for_status()

        suffix = f".{extension}" if extension else ".bin"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = Path(tmp.name)

        try:
            converter = FileConverter()
            result = converter.convert(tmp_path)
            return result.markdown
        finally:
            tmp_path.unlink(missing_ok=True)

    def _save_document(
        self,
        parent_dir: Path,
        safe_name: str,
        node_id: str,
        markdown: str,
        content_type: str,
        extension: str,
    ) -> None:
        parent_dir.mkdir(parents=True, exist_ok=True)
        md_path = parent_dir / f"{safe_name}.md"
        md_path.write_text(markdown, encoding="utf-8")

        meta = {
            "nodeId": node_id,
            "title": safe_name,
            "contentType": content_type,
            "extension": extension,
        }
        meta_path = parent_dir / f"{safe_name}.meta.json"
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
