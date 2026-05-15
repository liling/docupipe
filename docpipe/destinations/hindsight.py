from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from docpipe.destinations import register_destination
from docpipe.destinations.base import DestinationBase
from docpipe.models import Document


@register_destination("hindsight")
class HindsightDestination(DestinationBase):
    def __init__(
        self,
        bank_id: str | None = None,
        api_url: str | None = None,
        api_key: str | None = None,
        context_prefix: str | None = None,
        **kwargs,
    ):
        self.bank_id = bank_id or os.environ.get("HINDSIGHT_BANK_ID", "")
        self.api_url = api_url or os.environ.get("HINDSIGHT_API_URL", "")
        self.api_key = api_key or os.environ.get("HINDSIGHT_API_KEY", "")
        self.context_prefix = context_prefix or os.environ.get("HINDSIGHT_CONTEXT", "")
        self._client = None

    def _get_client(self):
        if self._client is None:
            from hindsight_client import Hindsight
            self._client = Hindsight(base_url=self.api_url, api_key=self.api_key or None)
            self._client.__enter__()
        return self._client

    def write(self, doc: Document) -> str:
        item = self._build_retain_item(doc)
        client = self._get_client()
        client.retain_batch(self.bank_id, items=[item], retain_async=True)
        return item["document_id"]

    def remove(self, doc_id: str) -> None:
        raise NotImplementedError("Hindsight 不支持删除文档")

    def close(self) -> None:
        if self._client is not None:
            self._client.__exit__(None, None, None)
            self._client = None

    def _build_retain_item(self, doc: Document) -> dict:
        meta = doc.meta
        content = doc.content if isinstance(doc.content, str) else doc.content.decode("utf-8")

        # 从 path 构建标签
        path_parts = Path(meta.path).parts
        space_name = path_parts[0] if path_parts else ""
        path_tags = [f"path:{part}" for part in path_parts[1:]]
        tags = ([f"space:{space_name}"] if space_name else []) + path_tags

        # context
        if self.context_prefix:
            context = self.context_prefix
        else:
            folder_display = "/".join(path_parts[1:]) if len(path_parts) > 1 else ""
            if folder_display:
                context = f"文档：{meta.title}，来自 {space_name}/{folder_display}"
            elif space_name:
                context = f"文档：{meta.title}，来自 {space_name}"
            else:
                context = f"文档：{meta.title}"

        # timestamp
        update_time = meta.extra.get("updateTime")
        if update_time:
            tz = timezone(timedelta(hours=8))
            dt = datetime.fromtimestamp(update_time / 1000, tz=tz)
            timestamp = dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        else:
            timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")

        # document_id 前缀
        source_name = meta.extra.get("_source", "local")
        document_id = f"{source_name}:{meta.id}"

        return {
            "content": content,
            "document_id": document_id,
            "timestamp": timestamp,
            "context": context,
            "tags": tags,
            "metadata": {
                "id": meta.id,
                "title": meta.title,
                "contentType": meta.extra.get("contentType", ""),
                "extension": meta.extra.get("extension", ""),
                "space_name": meta.extra.get("space_name", ""),
                "relative_path": meta.path,
                "full_path": f"{meta.extra.get('space_name', '')}/{meta.path}" if meta.extra.get("space_name") else meta.path,
                "content_hash": meta.hash,
                "updateTime": str(update_time) if update_time else None,
            },
        }
