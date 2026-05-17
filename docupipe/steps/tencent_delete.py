"""腾讯文档删除 step

放在 finalize_steps 中使用，确保所有文档处理完毕后再执行删除。
"""
from __future__ import annotations

import logging
import os

from docupipe.models import Bundle
from docupipe.sources.tencent import _TencentDocClient
from docupipe.steps import register_step
from docupipe.steps.base import Step

logger = logging.getLogger(__name__)


@register_step("tencent_delete")
class TencentDeleteStep(Step):
    def __init__(self, remove_type: str = "current", **kwargs):
        self._remove_type = remove_type
        token = os.environ.get("TENCENT_DOCS_TOKEN", "")
        if not token:
            raise ValueError("环境变量 TENCENT_DOCS_TOKEN 未设置")
        self._client = _TencentDocClient(token)

    def process(self, bundle: Bundle) -> Bundle:
        space_id = bundle.context.get("space_id", "")
        node_id = bundle.context.get("id", "")
        if not space_id or not node_id:
            logger.warning("缺少 space_id 或 id，跳过删除: id=%s, space_id=%s", node_id, space_id)
            return bundle
        try:
            self._client.delete_node(space_id, node_id, self._remove_type)
            logger.info("已删除腾讯文档: %s (%s)", bundle.context.get("path", node_id), node_id)
        except Exception as e:
            logger.warning("删除腾讯文档失败: %s - %s", node_id, e)
        return bundle
