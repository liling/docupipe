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
        # FileItem.name 为 "image_1.png"，需要映射两种 key
        image_files: dict[str, FileItem] = {}
        for image_item in bundle.get_by_role("image"):
            image_files[image_item.name] = image_item
            # 添加带 images/ 前缀的映射（与 ConvertStep 输出的 URL 格式对应）
            if "/" not in image_item.name:
                image_files[f"images/{image_item.name}"] = image_item

        source_context = bundle.context.get("source_context", "")

        new_content, image_metadata = self._processor.process(
            content, source_context, image_files=image_files,
        )

        # 更新 main 内容
        main_item.content = new_content

        # 根据 AI 生成的文件名重命名 Bundle 中的图片 FileItem
        for new_filename, meta in image_metadata.items():
            original_url = meta.get("original_url", "")
            original_name = original_url.rsplit("/", 1)[-1] if "/" in original_url else original_url
            for f in bundle.files:
                if f.role == "image" and f.name == original_name:
                    f.name = new_filename
                    break

        # 在 bundle.context 中存储 image_metadata
        bundle.context["image_metadata"] = image_metadata
        logger.info("图片处理完成, 处理了 %d 张图片", len(image_metadata) if image_metadata else 0)

        return bundle
