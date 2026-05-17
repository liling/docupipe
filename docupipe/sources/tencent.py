"""腾讯文档 MCP source

通过 FastMCP Client 连接腾讯文档 MCP 服务，获取文档内容。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import requests

from docupipe.models import Bundle, BundleMeta, FileItem
from docupipe.sources import register_source
from docupipe.sources.base import SourceBase

logger = logging.getLogger(__name__)

_DOC_TYPE_EXT = {
    "word": "docx",
    "sheet": "xlsx",
    "slide": "pptx",
    "doc": "docx",
    "smartcanvas": "docx",
    "smartsheet": "xlsx",
    "mind": "xmind",
    "flowchart": "pdf",
}


class _TencentDocClient:
    """封装腾讯文档 MCP 调用"""

    MCP_URL = "https://docs.qq.com/openapi/mcp"

    def __init__(self, token: str):
        from fastmcp import Client
        from fastmcp.client.auth import BearerAuth

        self._client = Client(self.MCP_URL, auth=BearerAuth(token))

    def _parse_result(self, result) -> dict | list:
        """从 FastMCP call_tool 返回结果中提取 JSON 数据"""
        text = result.content[0].text
        return json.loads(text)

    def _call_tool(self, name: str, arguments: dict | None = None) -> object:
        """同步调用 MCP tool"""
        async def _do():
            async with self._client as c:
                return await c.call_tool(name, arguments)
        return asyncio.run(_do())

    def list_spaces(self, num: int = 0) -> list[dict]:
        """列出知识库空间"""
        result = self._call_tool("query_space_list", {"num": num})
        data = self._parse_result(result)
        if isinstance(data, dict):
            return data.get("spaces", [])
        return data if isinstance(data, list) else []

    def resolve_space_name(self, name: str) -> str | None:
        """根据空间名称解析 space_id"""
        spaces = self.list_spaces()
        for space in spaces:
            if space.get("title") == name:
                space_id = space.get("space_id", "")
                logger.info("空间名称精确匹配: '%s' → %s", name, space_id)
                return space_id
        for space in spaces:
            if name in space.get("title", ""):
                space_id = space.get("space_id", "")
                logger.info("空间名称模糊匹配: '%s' → '%s' (%s)", name, space.get("title"), space_id)
                return space_id
        logger.warning("未找到匹配的空间: '%s'", name)
        return None

    def list_nodes(self, space_id: str, parent_id: str | None = None, num: int = 0) -> dict:
        """列出知识空间节点"""
        args: dict = {"space_id": space_id, "num": num}
        if parent_id:
            args["parent_id"] = parent_id
        result = self._call_tool("query_space_node", args)
        return self._parse_result(result)

    def get_content(self, file_id: str) -> str:
        """获取文档 markdown 内容"""
        result = self._call_tool("get_content", {"file_id": file_id})
        data = self._parse_result(result)
        if isinstance(data, dict):
            return data.get("markdown", data.get("content", ""))
        return str(data)

    def export_file(self, file_id: str) -> str:
        """导出文件，轮询进度直到完成，返回 (file_url, file_name)"""
        # 发起导出
        result = self._call_tool("manage.export_file", {"file_id": file_id})
        data = self._parse_result(result)
        task_id = data.get("task_id", "")
        if not task_id:
            raise RuntimeError(f"export_file 未返回 task_id: {data}")

        # 轮询进度
        for _ in range(60):
            time.sleep(5)
            progress_result = self._call_tool(
                "manage.export_progress",
                {"task_id": task_id},
            )
            progress = self._parse_result(progress_result)
            if progress.get("error"):
                raise RuntimeError(f"导出失败: {progress['error']}")
            if progress.get("progress") == 100:
                file_url = progress.get("file_url", "")
                file_name = progress.get("file_name", "")
                if not file_url:
                    raise RuntimeError(f"导出完成但无下载 URL: {progress}")
                return file_url

        raise SkipBundle(f"导出轮询超时: file_id={file_id}")


@register_source("tencent")
class TencentSource(SourceBase):
    def __init__(
        self,
        space_id: str | None = None,
        space_name: str | None = None,
        parent_id: str | None = None,
        folders: list[str] | None = None,
        include_types: list[str] | None = None,
        fetch_mode: str = "markdown",
        **kwargs,
    ):
        if space_name and space_id:
            logger.warning("同时提供了 space_name 和 space_id，将优先使用 space_name")
        if not space_name and not space_id:
            raise ValueError("必须提供 space_name 或 space_id 参数")

        token = os.environ.get("TENCENT_DOCS_TOKEN", "")
        if not token:
            raise ValueError("环境变量 TENCENT_DOCS_TOKEN 未设置")

        self._client = _TencentDocClient(token)

        if space_name:
            resolved_id = self._client.resolve_space_name(space_name)
            if not resolved_id:
                raise ValueError(f"无法找到空间: '{space_name}'")
            self._space_id = resolved_id
            self._space_name = space_name
        else:
            self._space_id = space_id
            self._space_name = ""
        self._parent_id = parent_id
        self._folders = folders
        self._include_types = set(include_types) if include_types else None
        self._fetch_mode = fetch_mode
        self._client = _TencentDocClient(token)

    def list(self) -> list[BundleMeta]:
        logger.info("列出文档: space_id=%s, folders=%s", self._space_id, self._folders)

        if self._folders:
            nodes = []
            for folder_path in self._folders:
                folder_id = self._resolve_folder_path(folder_path)
                if folder_id:
                    nodes.extend(self._collect_nodes(self._space_id, folder_id, parent_path=folder_path))
                else:
                    logger.warning("跳过无效的文件夹路径: %s", folder_path)
        else:
            nodes = self._collect_nodes(self._space_id, self._parent_id)

        result = []
        for node in nodes:
            node_type = node.get("node_type", "")
            if node_type == "wiki_folder":
                continue

            node_id = node.get("node_id", "")
            title = node.get("title", "未命名")
            doc_type = node.get("doc_type", "")

            if self._include_types is not None and doc_type not in self._include_types:
                continue

            result.append(BundleMeta(
                id=node_id,
                title=title,
                path=node.get("_path", ""),
                hash="",
                extra={
                    "doc_type": doc_type,
                    "node_type": node_type,
                    "has_child": node.get("has_child", False),
                },
            ))

        logger.info("列出文档完成: 共 %d 个文档", len(result))
        return result

    def fetch(self, meta: BundleMeta) -> Bundle:
        file_id = meta.id
        context = dict(meta.extra)

        logger.info("获取文档: id=%s, title=%s, mode=%s", meta.id, meta.title, self._fetch_mode)

        files: list[FileItem] = []

        if self._fetch_mode in ("markdown", "both"):
            markdown = self._client.get_content(file_id)
            files.append(FileItem(
                name=f"{meta.title}.md",
                content=markdown,
                content_type="text/markdown",
                role="main",
            ))

        if self._fetch_mode in ("export", "both"):
            file_url = self._client.export_file(file_id)
            resp = requests.get(file_url, timeout=120)
            resp.raise_for_status()

            ext = _DOC_TYPE_EXT.get(meta.extra.get("doc_type", ""), "docx")
            context["extension"] = ext
            context["_needs_conversion"] = True
            files.append(FileItem(
                name=f"{meta.title}.{ext}",
                content=resp.content,
                content_type=ext,
                role="main" if self._fetch_mode == "export" else "attachment",
            ))

        return Bundle(files=files, context=context)

    def _collect_nodes(self, space_id: str, parent_id: str | None = None, parent_path: str = "") -> list[dict]:
        """递归收集节点，处理分页"""
        all_nodes: list[dict] = []
        num = 0

        while True:
            data = self._client.list_nodes(space_id, parent_id=parent_id, num=num)
            nodes = data.get("children", [])
            has_next = data.get("has_next", False)

            for node in nodes:
                title = node.get("title", "未命名")
                node_id = node.get("node_id", "")
                node_type = node.get("node_type", "")
                current_path = f"{parent_path}/{title}" if parent_path else title

                if node_type == "wiki_folder":
                    if node.get("has_child"):
                        all_nodes.extend(self._collect_nodes(space_id, node_id, current_path))
                    continue

                node["_path"] = current_path
                all_nodes.append(node)

            if not has_next:
                break
            num += len(nodes)

        return all_nodes

    def _resolve_folder_path(self, path: str) -> str | None:
        """将文件夹路径解析为 node_id"""
        segments = [s.strip() for s in path.split("/") if s.strip()]
        if not segments:
            return None

        parent_id = self._parent_id
        for segment in segments:
            data = self._client.list_nodes(self._space_id, parent_id=parent_id)
            nodes = data.get("children", [])
            matched = None
            for node in nodes:
                if node.get("node_type") == "wiki_folder" and node.get("title") == segment:
                    matched = node
                    break
            if not matched:
                logger.warning("未找到文件夹: '%s'", segment)
                return None
            parent_id = matched.get("node_id")

        return parent_id
