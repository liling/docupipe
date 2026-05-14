from __future__ import annotations

import json
import subprocess


class WikiClient:
    def _run_dws(self, args: list[str]) -> dict | list:
        cmd = ["dws"] + args + ["--format", "json", "--yes"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(f"dws 命令失败: {' '.join(args)}\n{result.stderr}")
        if not result.stdout.strip():
            return {}
        return json.loads(result.stdout)

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
            items = data.get("items", []) if isinstance(data, dict) else []
            all_items.extend(items)
            page_token = data.get("nextPageToken") if isinstance(data, dict) else None
            if not page_token:
                break
        return all_items

    def get_node_info(self, node_id: str) -> dict:
        return self._run_dws(["doc", "info", "--node", node_id])

    def read_document(self, node_id: str) -> str:
        data = self._run_dws(["doc", "read", "--node", node_id])
        if isinstance(data, dict):
            results = data.get("result", [])
            parts = []
            for block in results:
                if isinstance(block, dict) and block.get("type") == "markdown":
                    parts.append(block.get("content", ""))
            return "\n".join(parts)
        return str(data)

    def download_file(self, node_id: str) -> str:
        data = self._run_dws(["doc", "download", "--node", node_id])
        if isinstance(data, dict):
            return data.get("downloadUrl", "")
        raise RuntimeError(f"下载失败，无法获取 URL: {node_id}")

    def get_space_info(self, space_id: str) -> dict:
        return self._run_dws(["wiki", "space", "get", "--id", space_id])
