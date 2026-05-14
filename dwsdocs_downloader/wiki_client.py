from __future__ import annotations

import json
import subprocess


class WikiClient:
    def _run_dws(self, args: list[str]) -> dict | list:
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

    def get_node_info(self, node_id: str) -> dict:
        return self._run_dws(["doc", "info", "--node", node_id])

    def read_document(self, node_id: str) -> str:
        data = self._run_dws(["doc", "read", "--node", node_id])
        if isinstance(data, dict):
            # 直接返回 markdown 字段
            return data.get("markdown", "")
        return str(data)

    def download_file(self, node_id: str) -> str:
        data = self._run_dws(["doc", "download", "--node", node_id])
        if isinstance(data, dict):
            # 优先使用 resourceUrl，其次 downloadUrl
            return data.get("resourceUrl", "") or data.get("downloadUrl", "")
        raise RuntimeError(f"下载失败，无法获取 URL: {node_id}")

    def get_space_info(self, space_id: str) -> dict:
        return self._run_dws(["wiki", "space", "get", "--id", space_id])
