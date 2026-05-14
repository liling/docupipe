from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from dwsdocs_downloader.display import Display
from dwsdocs_downloader.state import StateManager, content_hash


class RetainRunner:
    def __init__(self, output_dir: Path | str, display: Display | None = None):
        self._output_dir = Path(output_dir)
        self._display = display or Display()
        self._state = StateManager(self._output_dir / ".state", "retain")

    def scan_documents(self) -> list[dict]:
        docs: list[dict] = []
        for meta_path in sorted(self._output_dir.rglob("*.meta.json")):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                node_id = meta.get("nodeId", "")
                if not node_id:
                    continue
                md_name = meta_path.name.replace(".meta.json", ".md")
                md_path = meta_path.parent / md_name
                if not md_path.exists():
                    continue
                relative = md_path.relative_to(self._output_dir)
                docs.append({
                    "node_id": node_id,
                    "title": meta.get("title", ""),
                    "content_type": meta.get("contentType", ""),
                    "extension": meta.get("extension", ""),
                    "md_path": md_path,
                    "relative_path": str(relative),
                    "folder_parts": relative.parts[:-1],
                })
            except (json.JSONDecodeError, OSError, ValueError):
                continue
        return docs

    def scan_documents_sync(self) -> tuple[list[dict], int]:
        stored_hashes = self._state.load()
        all_docs = self.scan_documents()
        changed: list[dict] = []
        skipped = 0
        for doc in all_docs:
            current_hash = content_hash(doc["md_path"])
            if stored_hashes.get(doc["node_id"]) == current_hash:
                skipped += 1
            else:
                changed.append(doc)
        return changed, skipped

    def build_retain_item(self, doc: dict, context_prefix: str | None = None) -> dict:
        md_content = doc["md_path"].read_text(encoding="utf-8")
        current_hash = content_hash(doc["md_path"])

        folder_parts = doc.get("folder_parts", ())
        space_name = folder_parts[0] if folder_parts else ""
        path_tags = [f"path:{part}" for part in folder_parts]
        tags = ["dingtalk", "wiki"] + ([f"space:{space_name}"] if space_name else []) + path_tags

        # 可配置的 context
        if context_prefix:
            # 使用自定义 context
            context = context_prefix
        else:
            # 默认 context 格式：钉钉知识库文档：标题，来自 知识库名/路径
            folder_display = "/".join(folder_parts[1:]) if len(folder_parts) > 1 else ""
            if folder_display:
                context = f"钉钉知识库文档：{doc['title']}，来自 {space_name}/{folder_display} 知识库"
            elif space_name:
                context = f"钉钉知识库文档：{doc['title']}，来自 {space_name} 知识库"
            else:
                context = f"钉钉知识库文档：{doc['title']}"

        return {
            "content": md_content,
            "document_id": f"dingtalk:wiki:{doc['node_id']}",
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "context": context,
            "tags": tags,
            "metadata": {
                "nodeId": doc["node_id"],
                "title": doc["title"],
                "contentType": doc["content_type"],
                "extension": doc["extension"],
                "relative_path": doc["relative_path"],
                "content_hash": current_hash,
            },
        }

    def run(
        self,
        client,
        bank_id: str,
        resume: bool = False,
        sync: bool = False,
        dry_run: bool = False,
        context_prefix: str | None = None,
    ) -> None:
        if sync:
            docs, skipped = self.scan_documents_sync()
            if skipped:
                self._display.log("INFO", f"{skipped} 个文档无变化，跳过")
        elif resume:
            stored = self._state.load()
            all_docs = self.scan_documents()
            docs = [d for d in all_docs if d["node_id"] not in stored]
        else:
            docs = self.scan_documents()

        if not docs:
            self._display.log("INFO", "没有需要同步的文档")
            return

        self._display.start("同步到 Hindsight", len(docs))

        uploaded = 0
        for doc in docs:
            title = doc["title"]
            try:
                item = self.build_retain_item(doc, context_prefix=context_prefix)
                if dry_run:
                    self._display.result("info", f"[dry-run] {title} tags={item['tags']}")
                else:
                    client.retain_batch(bank_id, items=[item], retain_async=True)
                    self._display.result("success", f"{title}")
                self._state.save({**self._state.load(), doc["node_id"]: item["metadata"]["content_hash"]})
                uploaded += 1
            except Exception as e:
                self._display.result("error", f"{title}: {e}")
                self._display.add_failure()

        self._display.stop()
        self._display.print_summary()
