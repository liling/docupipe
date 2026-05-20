from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import requests

from docupipe.models import Bundle, BundleMeta, FileItem, SkipBundle
from docupipe.utils import guess_mime_type

logger = logging.getLogger(__name__)

_ALIDOC_UNSUPPORTED = frozenset({"axls", "amindmap", "aform", "abitable", "able"})

from docupipe.sources import register_source
from docupipe.sources.base import SourceBase


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

    def list_spaces(self) -> list[dict]:
        """列出所有知识库"""
        data = self._run_dws(["wiki", "space", "list"])
        if isinstance(data, dict):
            return data.get("wikiSpaces", [])
        return data if isinstance(data, list) else []

    def resolve_space_name(self, space_name: str) -> str | None:
        """根据知识库名称解析 workspace ID"""
        spaces = self.list_spaces()
        # 精确匹配
        for space in spaces:
            if space.get("name") == space_name:
                space_id = space.get("workspaceId")
                logger.info("知识库名称匹配: '%s' → %s", space_name, space_id)
                return space_id
        # 模糊匹配（包含关键词）
        for space in spaces:
            if space_name in space.get("name", ""):
                space_id = space.get("workspaceId")
                matched_name = space.get("name")
                logger.info("知识库名称模糊匹配: '%s' → '%s' (%s)", space_name, matched_name, space_id)
                return space_id
        logger.warning("未找到匹配的知识库: '%s'", space_name)
        return None

    def list_nodes(self, workspace_id: str, folder_id: str | None = None, folder_name: str = "", workspace_name: str = "") -> list[dict]:
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
        logger.info("列出节点完成: %s/%s, 共 %d 页, %d 个节点",
                     workspace_name or workspace_id, folder_name or "(根)", page_count, len(all_items))
        return all_items

    def list_nodes_by_folder(self, folder_id: str, folder_name: str = "") -> list[dict]:
        """列出指定文件夹下的节点（用于 doc 模式）"""
        all_items: list[dict] = []
        page_token: str | None = None
        page_count = 0
        while True:
            page_count += 1
            args = ["doc", "list", "--folder", folder_id, "--page-size", "50"]
            if page_token:
                args += ["--page-token", page_token]
            data = self._run_dws(args)
            items = data.get("nodes", []) if isinstance(data, dict) else []
            all_items.extend(items)
            logger.debug("列出节点: 第 %d 页, 获取 %d 条", page_count, len(items))
            page_token = data.get("nextPageToken") if isinstance(data, dict) else None
            if not page_token:
                break
        logger.info("列出节点完成: %s, 共 %d 页, %d 个节点", folder_name or folder_id, page_count, len(all_items))
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
    def __init__(self, space: str | None = None, space_id: str | None = None,
                 folder_id: str | None = None, folders: list[str] | None = None,
                 include_types: list[str] | None = None, mode: str = "wiki",
                 **kwargs):
        self._mode = mode
        if mode == "doc":
            if not folder_id:
                raise ValueError("doc 模式必须提供 folder_id 参数")
            self._doc_folder_id = folder_id
            self._folders = folders
            self._include_types = set(include_types) if include_types else None
            self._client = _WikiClient()
            return

        if mode != "wiki":
            raise ValueError(f"不支持的 mode: {mode}，可选值: wiki, doc")

        self._client = _WikiClient()

        if space and space_id:
            logger.warning("同时提供了 space 和 space_id，将优先使用 space")
        if space:
            resolved_id = self._client.resolve_space_name(space)
            if not resolved_id:
                raise ValueError(f"无法找到知识库: '{space}'")
            self._space_id = resolved_id
            self._space_name = space
        elif space_id:
            self._space_id = space_id
            self._space_name = ""
        else:
            raise ValueError("wiki 模式必须提供 space 或 space_id 参数")

        self._folder_id = folder_id
        self._folders = folders
        self._include_types = set(include_types) if include_types else None

    def supported_change_detection(self) -> list[str]:
        return ["mtime", "hash"]

    def list(self) -> list[BundleMeta]:
        if self._mode == "doc":
            return self._list_doc_mode()

        # --- wiki 模式 ---
        # 如果通过 space_id 传入且没有名称，尝试获取名称
        if not self._space_name:
            try:
                space_info = self._client.get_space_info(self._space_id)
                self._space_name = space_info.get("name", self._space_id)
            except Exception as e:
                logger.warning("获取知识库名称失败: %s, 使用 ID 作为名称: %s", e, self._space_id)
                self._space_name = self._space_id
        logger.info("列出文档: 知识库=%s, 文件夹=%s", self._space_name, self._folders or self._folder_id or "(根目录)")
        if self._folders:
            nodes = []
            for folder_path in self._folders:
                folder_id = self._resolve_folder_path(folder_path)
                if folder_id:
                    nodes.extend(self._collect_nodes(self._space_id, folder_id, parent_path=folder_path))
                else:
                    logger.warning("跳过无效的文件夹路径: %s", folder_path)
        else:
            nodes = self._collect_nodes(self._space_id, self._folder_id)
        result = []
        for node in nodes:
            node_type = node.get("nodeType", "")
            if node_type == "folder":
                continue
            node_id = node.get("nodeId", "")
            title = node.get("name", "未命名")
            content_type = node.get("contentType", "")
            if self._include_types is not None and content_type not in self._include_types:
                continue
            extension = node.get("extension", "")

            # doc list 不返回 DOCUMENT 类型的扩展名，用 doc info 补全
            if content_type == "DOCUMENT" and not extension:
                info = self._client.get_node_info(node_id)
                extension = info.get("extension", "")
                logger.debug("doc info 补全 extension: %s → %s", title, extension or "(空)")

            result.append(BundleMeta(
                id=node_id,
                title=title,
                path=node.get("_path", ""),
                hash="",
                extra={
                    "dingtalk_content_type": content_type,
                    "extension": extension,
                    "dingtalk_extension": extension,
                    "dingtalk_update_time": node.get("updateTime"),
                    "dingtalk_node_type": node_type,
                    "space_name": self._space_name,
                    "mtime": node.get("updateTime"),
                },
            ))
        logger.info("列出文档完成: 共 %d 个文档", len(result))
        return result

    def fetch(self, meta: BundleMeta) -> Bundle:
        content_type = meta.extra.get("dingtalk_content_type", "")
        extension = meta.extra.get("extension", "")
        node_id = meta.id

        logger.info("获取文档: id=%s, title=%s, type=%s, ext=%s", meta.id, meta.title, content_type, extension or "(空)")

        context = dict(meta.extra)

        if content_type == "ALIDOC" or extension == "adoc":
            # doc list 不返回 extension，用 doc info 补全
            if not extension:
                info = self._client.get_node_info(node_id)
                extension = info.get("extension", "")
                context["extension"] = extension
                logger.debug("doc info 补全 extension: %s → %s", meta.title, extension or "(空)")

            if extension in _ALIDOC_UNSUPPORTED:
                raise SkipBundle(f"ALIDOC 子类型暂不支持: extension={extension}")

            markdown = self._client.read_document(node_id)
            markdown = self._clean_html_tags(markdown)

            context["extension"] = "md"

            return Bundle(
                files=[FileItem(
                    name=f"{meta.title}.md",
                    content=markdown,
                    content_type="text/markdown",
                    role="main",
                )],
                context=context,
            )
        else:
            logger.debug("下载文件内容: node_id=%s, extension=%s", node_id, extension)
            download_url = self._client.download_file(node_id)
            resp = requests.get(download_url, timeout=120)
            resp.raise_for_status()
            content = resp.content
            logger.debug("文件下载成功: node_id=%s, 大小=%d bytes", node_id, len(content))

            filename = f"{meta.title}.{extension}" if extension else meta.title
            return Bundle(
                files=[FileItem(
                    name=filename,
                    content=content,
                    content_type=guess_mime_type(extension),
                    role="main",
                )],
                context=context,
            )

    def _list_doc_mode(self) -> list[BundleMeta]:
        """doc 模式：从指定文件夹递归列出文档"""
        if self._folders:
            logger.info("列出文档: folder=%s, 路径=%s", self._doc_folder_id, self._folders)
            all_nodes = []
            for folder_path in self._folders:
                folder_id = self._resolve_doc_folder_path(folder_path)
                if folder_id:
                    all_nodes.extend(self._collect_doc_nodes(folder_id, parent_path=folder_path))
                else:
                    logger.warning("跳过无效的文件夹路径: %s", folder_path)
            nodes = all_nodes
        else:
            logger.info("列出文档: folder=%s", self._doc_folder_id)
            nodes = self._collect_doc_nodes(self._doc_folder_id)
        result = []
        for node in nodes:
            node_type = node.get("nodeType", "")
            if node_type == "folder":
                continue
            node_id = node.get("nodeId", "")
            title = node.get("name", "未命名")
            content_type = node.get("contentType", "")
            if self._include_types is not None and content_type not in self._include_types:
                continue
            extension = node.get("extension", "")

            if content_type == "DOCUMENT" and not extension:
                info = self._client.get_node_info(node_id)
                extension = info.get("extension", "")
                logger.debug("doc info 补全 extension: %s → %s", title, extension or "(空)")

            result.append(BundleMeta(
                id=node_id,
                title=title,
                path=node.get("_path", ""),
                hash="",
                extra={
                    "dingtalk_content_type": content_type,
                    "extension": extension,
                    "dingtalk_extension": extension,
                    "dingtalk_update_time": node.get("updateTime"),
                    "dingtalk_node_type": node_type,
                    "space_name": "",
                    "mtime": node.get("updateTime"),
                },
            ))
        logger.info("列出文档完成: 共 %d 个文档", len(result))
        return result

    def _collect_doc_nodes(self, folder_id: str, parent_path: str = "") -> list[dict]:
        """doc 模式：递归收集文件夹下的所有文档节点"""
        logger.debug("收集 doc 节点: %s", parent_path or folder_id)
        nodes = self._client.list_nodes_by_folder(folder_id, folder_name=parent_path or folder_id)
        result = []
        for node in nodes:
            title = node.get("name", "未命名")
            node_id = node.get("nodeId", "")
            node_type = node.get("nodeType", "")
            current_path = f"{parent_path}/{title}" if parent_path else title

            if node_type == "folder":
                if node.get("hasChildren"):
                    result.extend(self._collect_doc_nodes(node_id, current_path))
            else:
                node["_path"] = current_path
                result.append(node)
        return result

    def _resolve_doc_folder_path(self, path: str) -> str | None:
        """在 doc 模式下，将文件夹路径（如 'B1 平台产品/平台线/02 解决方案'）解析为 folder ID"""
        segments = [s.strip() for s in path.split("/") if s.strip()]
        if not segments:
            return self._doc_folder_id

        parent_id = self._doc_folder_id
        resolved = ""
        for segment in segments:
            nodes = self._client.list_nodes_by_folder(parent_id, folder_name=resolved or self._doc_folder_id)
            matched = None
            for node in nodes:
                if node.get("nodeType") == "folder" and node.get("name") == segment:
                    matched = node
                    break
            if not matched:
                logger.warning("未找到文件夹: '%s' (在 %s 下)", segment, resolved or "根目录")
                return None
            parent_id = matched.get("nodeId")
            resolved = f"{resolved}/{segment}" if resolved else segment

        return parent_id

    def _resolve_folder_path(self, path: str) -> str | None:
        """将文件夹路径（如 '产品规划物料/解决方案'）解析为 folder ID"""
        segments = [s.strip() for s in path.split("/") if s.strip()]
        if not segments:
            return None

        parent_id = None
        resolved = ""
        for segment in segments:
            folder_label = resolved or "(根)"
            nodes = self._client.list_nodes(self._space_id, parent_id,
                                            folder_name=folder_label, workspace_name=self._space_name)
            matched = None
            for node in nodes:
                if node.get("nodeType") == "folder" and node.get("name") == segment:
                    matched = node
                    break
            if not matched:
                logger.warning("未找到文件夹: '%s' (在 %s 下)", segment, resolved or "根目录")
                return None
            parent_id = matched.get("nodeId")
            resolved = f"{resolved}/{segment}" if resolved else segment

        return parent_id

    def _collect_nodes(self, space_id: str, folder_id: str | None, parent_path: str = "") -> list[dict]:
        folder_label = parent_path or "(根)"
        logger.debug("收集节点: %s/%s", self._space_name, folder_label)
        nodes = self._client.list_nodes(space_id, folder_id, folder_name=folder_label, workspace_name=self._space_name)
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
