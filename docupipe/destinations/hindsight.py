from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from docupipe.destinations import register_destination
from docupipe.destinations.base import DestinationBase
from docupipe.models import Bundle, FileItem
from docupipe.render import render_template


@register_destination("hindsight")
class HindsightDestination(DestinationBase):
    _config_keys = {"context_prefix", "document_id_template", "context_template", "extra_tags", "extra_metadata"}

    def __init__(
        self,
        bank_id: str | None = None,
        api_url: str | None = None,
        api_key: str | None = None,
        context_prefix: str | None = None,
        document_id_template: str | None = None,
        context_template: str | None = None,
        extra_tags: list | None = None,
        extra_metadata: dict | None = None,
        **kwargs,
    ):
        self.bank_id = bank_id or os.environ.get("HINDSIGHT_BANK_ID", "")
        self.api_url = api_url or os.environ.get("HINDSIGHT_API_URL", "")
        self.api_key = api_key or os.environ.get("HINDSIGHT_API_KEY", "")
        self._context_prefix = context_prefix or os.environ.get("HINDSIGHT_CONTEXT", "")
        self._document_id_template = document_id_template
        self._context_template = context_template
        self._extra_tags = extra_tags
        self._extra_metadata = extra_metadata
        self._client = None

    def _get_client(self):
        if self._client is None:
            from hindsight_client import Hindsight
            self._client = Hindsight(base_url=self.api_url, api_key=self.api_key or None)
            self._client.__enter__()
        return self._client

    def write(self, bundle: Bundle) -> str:
        client = self._get_client()
        main_files = bundle.get_by_role("main")

        if len(main_files) <= 1:
            item = self._build_retain_item(bundle)
            client.retain_batch(self.bank_id, items=[item], retain_async=True)
            return item["document_id"]

        first_id = None
        for file_item in main_files:
            item = self._build_retain_item(bundle, file_item=file_item)
            client.retain_batch(self.bank_id, items=[item], retain_async=True)
            if first_id is None:
                first_id = item["document_id"]

        return first_id or ""

    def remove(self, bundle_id: str) -> None:
        raise NotImplementedError("Hindsight 不支持删除文档")

    def close(self) -> None:
        if self._client is not None:
            self._client.__exit__(None, None, None)
            self._client = None

    def _build_retain_item(self, bundle: Bundle, *, file_item: FileItem | None = None) -> dict:
        target_file = file_item or bundle.main
        if not target_file:
            raise ValueError("Bundle must have a main file")

        context = dict(bundle.context)
        if target_file.context:
            context.update(target_file.context)

        content = target_file.content if isinstance(target_file.content, str) else target_file.content.decode("utf-8")

        # 从 path 构建标签
        space_name = context.get("space_name", "")
        path_parts = Path(context["path"]).parts
        path_tags = [f"path:{part}" for part in path_parts[1:]] if len(path_parts) > 1 else []
        tags = ([f"space:{space_name}"] if space_name else []) + path_tags

        # 追加额外标签
        if self._extra_tags:
            tags.extend(render_template(self._extra_tags, context))

        # context
        if self._context_template:
            context_str = render_template(self._context_template, context)
        elif self._context_prefix:
            context_str = self._context_prefix
        else:
            folder_display = "/".join(path_parts[1:]) if len(path_parts) > 1 else ""
            if folder_display:
                context_str = f"文档：{context['title']}，来自 {space_name}/{folder_display}"
            elif space_name:
                context_str = f"文档：{context['title']}，来自 {space_name}"
            else:
                context_str = f"文档：{context['title']}"

        # timestamp
        update_time = context.get("mtime")
        if update_time:
            tz = timezone(timedelta(hours=8))
            dt = datetime.fromtimestamp(update_time / 1000, tz=tz)
            timestamp = dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        else:
            timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")

        # document_id
        if self._document_id_template:
            document_id = render_template(self._document_id_template, context)
        else:
            source_name = context.get("_source", "local")
            document_id = f"{source_name}:{context['id']}"
        if file_item is not None:
            document_id = f"{document_id}:{file_item.name}"

        item = {
            "content": content,
            "document_id": document_id,
            "timestamp": timestamp,
            "context": context_str,
            "tags": tags,
            "metadata": {
                **{k: str(v) if not isinstance(v, str) else v for k, v in context.items()},
                "content_type": context.get("dingtalk_content_type", ""),
                "relative_path": context["path"],
                "full_path": f"{context.get('space_name', '')}/{context['path']}" if context.get("space_name") else context["path"],
                "content_hash": context["hash"],
                "update_time": str(update_time) if update_time else "",
            },
        }

        if self._extra_metadata:
            item["metadata"].update(render_template(self._extra_metadata, context))

        return item
