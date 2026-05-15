from __future__ import annotations

import json
import logging
import re
import tempfile
from pathlib import Path

import requests

from docpipe.models import Document, DocumentMeta

logger = logging.getLogger(__name__)
from docpipe.sources import register_source
from docpipe.sources.base import SourceBase


class _WikiClient:
    def _run_dws(self, args: list[str]) -> dict | list:
        import subprocess
        cmd = ["dws"] + args + ["--format", "json", "--yes", "--timeout", "300"]
        logger.debug("执行 dws 命令: %s", " ".join(args))
        result = subprocess.run(cmd, capture_output=True, timeout=300)
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
        page_count = 0
        while True:
            page_count += 1
            args = ["doc", "list", "--workspace", workspace_id, "--page-size", "50"]
            if folder_id:
                args += ["--folder", folder_id]
            if page_token:
                args += ["--page-token", page_token]
            data = self._run_dws(args)
            items = data.get("nodes", []) if isinstance(data, dict) else []
            all_items.extend(items)
            logger.debug("列出节点: 第 %d 页, 获取 %d 条", page_count, len(items))
            page_token = data.get("nextPageToken") if isinstance(data, dict) else None
            if not page_token:
                break
        logger.info("列出节点完成: 工作区=%s, 文件夹=%s, 共 %d 页, %d 个节点",
                     workspace_id, folder_id or "(根)", page_count, len(all_items))
        return all_items

    def read_document(self, node_id: str) -> str:
        logger.debug("读取文档: node_id=%s", node_id)
        data = self._run_dws(["doc", "read", "--node", node_id])
        if isinstance(data, dict):
            content = data.get("markdown", "")
            logger.debug("读取文档完成: node_id=%s, 长度=%d", node_id, len(content))
            return content
        return str(data)

    def download_file(self, node_id: str) -> str:
        logger.debug("下载文件: node_id=%s", node_id)
        data = self._run_dws(["doc", "download", "--node", node_id])
        if isinstance(data, dict):
            url = data.get("resourceUrl", "") or data.get("downloadUrl", "")
            logger.debug("下载文件完成: node_id=%s, URL 长度=%d", node_id, len(url))
            return url
        raise RuntimeError(f"下载失败，无法获取 URL: {node_id}")

    def get_space_info(self, space_id: str) -> dict:
        return self._run_dws(["wiki", "space", "get", "--id", space_id])

    def get_node_info(self, node_id: str) -> dict:
        data = self._run_dws(["doc", "info", "--node", node_id])
        return data if isinstance(data, dict) else {}


@register_source("dingtalk")
class DingtalkSource(SourceBase):
    def __init__(self, space_id: str, folder_id: str | None = None, **kwargs):
        self._space_id = space_id
        self._folder_id = folder_id
        self._client = _WikiClient()
        self._space_name = ""
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
        if not self._space_name:
            try:
                space_info = self._client.get_space_info(self._space_id)
                self._space_name = space_info.get("name", self._space_id)
            except Exception:
                self._space_name = self._space_id
        logger.info("列出文档: 知识库=%s, 文件夹=%s", self._space_name, self._folder_id or "(根目录)")
        nodes = self._collect_nodes(self._space_id, self._folder_id)
        result = []
        _UNSUPPORTED_EXTENSIONS = {"axls", "amindmap", "aform", "abitable"}
        for node in nodes:
            node_type = node.get("nodeType", "")
            if node_type == "folder":
                continue
            extension = node.get("extension", "")
            if extension in _UNSUPPORTED_EXTENSIONS:
                logger.debug("跳过不支持的钉钉类型: %s (extension=%s)", node.get("name", ""), extension)
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
        logger.info("列出文档完成: 共 %d 个文档", len(result))
        return result

    def fetch(self, doc_meta: DocumentMeta) -> Document:
        content_type = doc_meta.extra.get("contentType", "")
        extension = doc_meta.extra.get("extension", "")
        node_id = doc_meta.id

        logger.info("获取文档: id=%s, title=%s, type=%s, ext=%s", doc_meta.id, doc_meta.title, content_type, extension or "(空)")

        extra = dict(doc_meta.extra)

        if content_type == "ALIDOC" or extension == "adoc":
            # doc list 不返回 extension，用 doc info 补全
            if not extension:
                info = self._client.get_node_info(node_id)
                extension = info.get("extension", "")
                extra["extension"] = extension
                logger.debug("doc info 补全 extension: %s → %s", doc_meta.title, extension or "(空)")

            _UNSUPPORTED = {"axls", "amindmap", "aform", "abitable"}
            if extension in _UNSUPPORTED:
                from docpipe.models import SkipDocument
                raise SkipDocument(f"不支持的钉钉类型: extension={extension}")

            markdown = self._client.read_document(node_id)
            markdown = self._clean_html_tags(markdown)
        else:
            tmp_path = self._download_to_temp(node_id, extension)
            extra["_temp_file"] = str(tmp_path)
            extra["_needs_conversion"] = True
            markdown = ""

        if markdown and self._image_processor:
            source_context = f"{doc_meta.title} - {doc_meta.path}"
            logger.debug("处理文档中的图片: %s", doc_meta.title)
            markdown, image_metadata = self._image_processor.process(markdown, source_context)
            extra["image_metadata"] = image_metadata
            logger.info("图片处理完成: %s, 处理了 %d 张图片", doc_meta.title, len(image_metadata) if image_metadata else 0)

        return Document(
            meta=DocumentMeta(
                id=doc_meta.id,
                title=doc_meta.title,
                path=doc_meta.path,
                hash="",
                extra=extra,
            ),
            content=markdown,
            content_type="markdown",
        )

    def _collect_nodes(self, space_id: str, folder_id: str | None, parent_path: str = "") -> list[dict]:
        folder_label = parent_path or "(根)"
        logger.debug("收集节点: %s/%s", self._space_name, folder_label)
        nodes = self._client.list_nodes(space_id, folder_id)
        result = []
        folder_count = 0
        doc_count = 0
        for node in nodes:
            title = node.get("name", "未命名")
            node_id = node.get("nodeId", "")
            node_type = node.get("nodeType", "")
            current_path = f"{parent_path}/{title}" if parent_path else title

            if node_type == "folder":
                folder_count += 1
                if node.get("hasChildren"):
                    result.extend(self._collect_nodes(space_id, node_id, current_path))
            else:
                doc_count += 1
                node["_path"] = current_path
                result.append(node)
        logger.debug("收集节点完成: 文件夹=%d, 文档=%d", folder_count, doc_count)
        return result

    def _download_to_temp(self, node_id: str, extension: str) -> Path:
        logger.debug("下载文件: node_id=%s, extension=%s", node_id, extension)
        download_url = self._client.download_file(node_id)
        resp = requests.get(download_url, timeout=120)
        resp.raise_for_status()
        logger.debug("文件下载成功: node_id=%s, 大小=%d bytes", node_id, len(resp.content))

        suffix = f".{extension}" if extension else ".bin"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(resp.content)
            return Path(tmp.name)

    @staticmethod
    def _clean_html_tags(markdown: str) -> str:
        """清理钉钉文档导出 Markdown 中残留的内联 HTML 标签"""
        # <span style="...">text</span> → text
        markdown = re.sub(r'</?span[^>]*>', '', markdown)
        # <font ...>text</font> → text
        markdown = re.sub(r'</?font[^>]*>', '', markdown)
        # <div ...>...</div> → 内容（保留换行）
        markdown = re.sub(r'<div[^>]*>', '\n', markdown)
        markdown = re.sub(r'</div>', '', markdown)
        # <br>, <br/> → 换行
        markdown = re.sub(r'<br\s*/?>', '\n', markdown)
        # <u>text</u> → text（下划线在 Markdown 中不常用）
        markdown = re.sub(r'</?u>', '', markdown)
        # <strong>text</strong> → **text**
        markdown = re.sub(r'<strong[^>]*>(.*?)</strong>', r'*\1*', markdown, flags=re.DOTALL)
        # <em>text</em> → *text*
        markdown = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', markdown, flags=re.DOTALL)
        # <p>text</p> → text（保留段落）
        markdown = re.sub(r'<p[^>]*>', '', markdown)
        markdown = re.sub(r'</p>', '\n', markdown)
        # 清理多余空行
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        return markdown.strip()
