from __future__ import annotations

import hashlib
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

_CONVERTIBLE_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt",
    ".html", ".htm", ".csv", ".json", ".xml", ".txt", ".md",
    ".rtf", ".odt", ".ods",
}

_SKIP_CONTENT_TYPES = {"AXLS"}


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
                     workspace_id, folder_id or "(根目录)", page_count, len(all_items))
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
        logger.info("列出文档: space_id=%s, folder_id=%s", self._space_id, self._folder_id or "(根目录)")
        nodes = self._collect_nodes(self._space_id, self._folder_id)
        result = []
        skipped_count = 0
        for node in nodes:
            node_type = node.get("nodeType", "")
            if node_type == "folder":
                continue
            content_type = node.get("contentType", "")
            extension = node.get("extension", "")
            # 跳过钉钉表格等无法处理的类型
            if content_type in _SKIP_CONTENT_TYPES or extension == "axls":
                logger.debug("跳过不支持的类型: %s (contentType=%s, extension=%s)",
                             node.get("name", "未命名"), content_type, extension)
                skipped_count += 1
                continue
            # 跳过不可转换的文件类型（非 adoc 且扩展名不在支持列表中）
            if content_type != "ALIDOC" and extension != "adoc":
                ext_lower = f".{extension}" if extension else ""
                if ext_lower and ext_lower not in _CONVERTIBLE_EXTENSIONS:
                    logger.debug("跳过不可转换的文件: %s (extension=%s)", node.get("name", "未命名"), extension)
                    skipped_count += 1
                    continue
            node_id = node.get("nodeId", "")
            title = node.get("name", "未命名")
            result.append(DocumentMeta(
                id=node_id,
                title=title,
                path=node.get("_path", ""),
                hash="",
                extra={
                    "contentType": content_type,
                    "extension": extension,
                    "updateTime": node.get("updateTime"),
                    "nodeType": node_type,
                },
            ))
        logger.info("列出文档完成: 共 %d 个文档, 跳过 %d 个", len(result), skipped_count)
        return result

    def fetch(self, doc_meta: DocumentMeta) -> Document:
        content_type = doc_meta.extra.get("contentType", "")
        extension = doc_meta.extra.get("extension", "")
        node_id = doc_meta.id

        logger.info("获取文档: id=%s, title=%s, type=%s", doc_meta.id, doc_meta.title, content_type)

        if content_type == "ALIDOC" or extension == "adoc":
            markdown = self._client.read_document(node_id)
        else:
            ext = extension if extension else "bin"
            markdown = self._download_and_convert(node_id, ext)

        markdown = self._clean_html_tags(markdown)

        if self._image_processor:
            source_context = f"{doc_meta.title} - {doc_meta.path}"
            logger.debug("处理文档中的图片: %s", doc_meta.title)
            markdown, image_metadata = self._image_processor.process(markdown, source_context)
            doc_meta.extra["image_metadata"] = image_metadata
            logger.info("图片处理完成: %s, 处理了 %d 张图片", doc_meta.title, len(image_metadata) if image_metadata else 0)

        content_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        logger.debug("文档获取完成: id=%s, 内容长度=%d, hash=%s...", doc_meta.id, len(markdown), content_hash[:12])
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
        logger.debug("收集节点: space_id=%s, folder_id=%s, path=%s", space_id, folder_id or "(根)", parent_path or "(根)")
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

    def _download_and_convert(self, node_id: str, extension: str) -> str:
        logger.debug("下载并转换文件: node_id=%s, extension=%s", node_id, extension)
        download_url = self._client.download_file(node_id)
        resp = requests.get(download_url, timeout=120)
        resp.raise_for_status()
        logger.debug("文件下载成功: node_id=%s, 大小=%d bytes", node_id, len(resp.content))

        suffix = f".{extension}" if extension else ".bin"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = Path(tmp.name)

        try:
            from markitdown import MarkItDown
            md = MarkItDown()
            result = md.convert(str(tmp_path))
            logger.debug("文件转换完成: node_id=%s, Markdown 长度=%d", node_id, len(result.markdown))
            return result.markdown
        finally:
            tmp_path.unlink(missing_ok=True)

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
