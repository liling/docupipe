from __future__ import annotations

import logging

from docpipe.image import ImagePostProcessor, OpenAIVisionClient
from docpipe.models import Bundle, FileItem
from docpipe.steps import register_step
from docpipe.steps.base import PipelineStep

logger = logging.getLogger(__name__)


@register_step("image_description")
class ImageDescriptionStep(PipelineStep):
    def __init__(self, api_key: str = "", base_url: str = "", model: str = "gpt-4o", **kwargs):
        vision_client = OpenAIVisionClient(api_key=api_key, base_url=base_url, model=model)
        self._processor = ImagePostProcessor(vision_client)

    def process(self, bundle: Bundle) -> Bundle:
        main_item = bundle.main
        if not main_item:
            return bundle

        content = main_item.content
        if not isinstance(content, str):
            return bundle

        if "![" not in content:
            return bundle

        # 从 bundle 获取图片文件，构建 image_files 映射
        # ConvertStep 创建的引用格式为 "images/image_1.png"
        # 我们需要同时映射 "images/image_1.png" 和 "image_1.png"
        image_files: dict[str, FileItem] = {}
        for image_item in bundle.get_by_role("image"):
            image_files[image_item.name] = image_item
            # 如果文件名包含路径前缀，添加不带前缀的映射作为后备
            if "/" in image_item.name:
                short_name = image_item.name.split("/")[-1]
                image_files[short_name] = image_item

        source_context = bundle.context.get("source_context", "")

        new_content, image_metadata = self._processor.process(
            content, source_context, image_files=image_files,
        )

        # 更新 main 内容
        main_item.content = new_content

        # 在 bundle.context 中存储 image_metadata
        bundle.context["image_metadata"] = image_metadata
        logger.info("图片处理完成, 处理了 %d 张图片", len(image_metadata) if image_metadata else 0)

        return bundle
