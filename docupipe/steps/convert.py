from __future__ import annotations

import base64
import hashlib
import logging
import re
import tempfile
from pathlib import Path

from docupipe.models import Bundle, FileItem
from docupipe.steps import register_step
from docupipe.steps.base import Step

logger = logging.getLogger(__name__)


def _mime_to_ext(mime: str) -> str:
    mapping = {"png": ".png", "jpeg": ".jpg", "jpg": ".jpg", "gif": ".gif", "webp": ".webp", "x-emf": ".emf"}
    return mapping.get(mime, f".{mime}")


def _replace_extension(name: str, new_ext: str) -> str:
    p = Path(name)
    return f"{p.stem}{new_ext}"


@register_step("convert")
class ConvertStep(Step):
    def __init__(self, extension_rules: dict[str, str] | None = None, **kwargs):
        self._extension_rules = extension_rules or {}

    def needs_conversion(self, bundle: Bundle) -> bool:
        ext = bundle.context.get("extension", "")
        key = f".{ext}" if ext else ""
        rule = self._extension_rules.get(key)
        return rule is not None and rule != "source"

    def process(self, bundle: Bundle) -> Bundle:
        main = bundle.main
        if not main:
            logger.warning("convert step: Bundle 无主文件，跳过转换")
            return bundle

        ext = bundle.context.get("extension", "")
        key = f".{ext}" if ext else ""
        converter_name = self._extension_rules.get(key)

        if not converter_name or converter_name == "source":
            return bundle

        from docupipe.converters import get_converter
        converter_cls = get_converter(converter_name)
        converter = converter_cls()

        # 写临时文件给 converter 使用
        if not isinstance(main.content, bytes):
            logger.warning("convert step: 主文件内容不是 bytes，跳过转换")
            return bundle

        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_file.write(main.content)
            tmp_file.flush()
            temp_path = Path(tmp_file.name)

        try:
            markdown = converter.convert(temp_path)

            # 提取内联图片并创建 FileItem
            if isinstance(markdown, str):
                title = bundle.context.get("title", "")
                prefix = hashlib.sha256(title.encode()).hexdigest()[:10]
                markdown, images = self._extract_inline_images(markdown, prefix)

                # 将图片文件加入 Bundle
                for img in images:
                    bundle.add(img)
                bundle.context["image_prefix"] = "images"

            # 更新主文件内容
            main.content = markdown
            main.content_type = "text/markdown"
            main.name = _replace_extension(main.name, ".md")
        finally:
            temp_path.unlink(missing_ok=True)

        return bundle

    def _extract_inline_images(self, markdown: str, prefix: str = "") -> tuple[str, list[FileItem]]:
        """从 markdown 中提取 data:image base64 内联图片，返回(更新后的markdown, FileItem列表)"""
        if "data:image" not in markdown:
            return markdown, []

        pattern = r'!\[([^\]]*)\]\((data:image/([^;]+);base64,([^)]+))\)'
        counter = 0
        images: list[FileItem] = []

        def replace_inline(match: re.Match) -> str:
            nonlocal counter
            alt = match.group(1)
            mime_type = match.group(3)
            b64_data = match.group(4)

            ext = _mime_to_ext(mime_type)
            counter += 1
            filename = f"image_{counter}{ext}"

            try:
                image_bytes = base64.b64decode(b64_data)
                img_item = FileItem(
                    name=f"images/{prefix}/{filename}",
                    content=image_bytes,
                    content_type=f"image/{mime_type}",
                    role="image"
                )
                images.append(img_item)
            except Exception as e:
                logger.warning("提取内联图片失败: %s", e)
                return match.group(0)

            return f"![{alt}]({img_item.name})"

        new_markdown = re.sub(pattern, replace_inline, markdown)
        return new_markdown, images