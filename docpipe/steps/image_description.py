from __future__ import annotations

import logging

from docpipe.image import ImagePostProcessor, OpenAIVisionClient
from docpipe.models import Document
from docpipe.steps import register_step
from docpipe.steps.base import PipelineStep

logger = logging.getLogger(__name__)


@register_step("image_description")
class ImageDescriptionStep(PipelineStep):
    def __init__(self, api_key: str = "", base_url: str = "", model: str = "gpt-4o", **kwargs):
        vision_client = OpenAIVisionClient(api_key=api_key, base_url=base_url, model=model)
        self._processor = ImagePostProcessor(vision_client)

    def process(self, doc: Document) -> Document:
        if not isinstance(doc.content, str):
            return doc

        if "![" not in doc.content:
            return doc

        images_dir = doc.meta.extra.get("_images_dir")
        source_context = f"{doc.meta.title} - {doc.meta.path}"
        new_content, image_metadata = self._processor.process(
            doc.content, source_context, images_dir=images_dir,
        )

        doc.content = new_content
        doc.meta.extra["image_metadata"] = image_metadata
        logger.info("图片处理完成: %s, 处理了 %d 张图片", doc.meta.title, len(image_metadata) if image_metadata else 0)

        return doc
