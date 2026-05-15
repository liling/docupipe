from __future__ import annotations

import base64
import json
import logging
import re

import requests as req

from openai import OpenAI

logger = logging.getLogger(__name__)


class OpenAIVisionClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "gpt-4o",
        timeout: int = 30,
    ):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.timeout = timeout

    def describe(self, image_bytes: bytes, context: str) -> tuple[str, str]:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        prompt = (
            f"这是一篇文档《{context}》中的图片。\n\n"
            "请完成两个任务：\n"
            "1. 生成一个简短的英文文件名（3-5个单词，用连字符连接，如 \"system-architecture-diagram\"）\n"
            "2. 用一句话描述图片内容（中文，适合在文档中作为图片说明）\n\n"
            '请以 JSON 格式返回：\n{"filename": "...", "description": "..."}'
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ],
            max_tokens=300,
            timeout=self.timeout,
        )

        raw = response.choices[0].message.content
        return self._parse_response(raw)

    def _parse_response(self, raw: str) -> tuple[str, str]:
        try:
            data = json.loads(raw)
            return data["filename"], data["description"]
        except (json.JSONDecodeError, KeyError):
            # 尝试从文本中提取 JSON
            match = re.search(r'\{[^}]+\}', raw)
            if match:
                try:
                    data = json.loads(match.group())
                    return data["filename"], data["description"]
                except (json.JSONDecodeError, KeyError):
                    pass
            logger.warning(f"Vision API 返回无法解析: {raw[:200]}")
            return "image-unknown", "图片描述解析失败"


class ImagePostProcessor:
    def __init__(self, vision_client: OpenAIVisionClient, max_image_size: int = 10 * 1024 * 1024):
        self.vision_client = vision_client
        self.max_image_size = max_image_size

    def process(self, markdown: str, source_context: str) -> tuple[str, dict]:
        image_metadata: dict[str, dict] = {}
        pattern = r'!\[([^\]]*)\]\(([^)]+)\)'

        def replace_image(match: re.Match) -> str:
            url = match.group(2).strip().strip('"').strip("'")

            if url.startswith("image://"):
                return match.group(0)

            # 跳过 data: URI（已内联，无需下载）
            if url.startswith("data:"):
                return match.group(0)

            # 跳过相对路径（没有 scheme，无法下载）
            if "://" not in url:
                return match.group(0)

            try:
                resp = req.get(url, timeout=30)
                resp.raise_for_status()
                image_bytes = resp.content

                if len(image_bytes) > self.max_image_size:
                    logger.warning(f"图片过大 ({len(image_bytes)} bytes)，跳过: {url}")
                    return match.group(0)

                filename, description = self.vision_client.describe(image_bytes, source_context)

                full_filename = f"{filename}.png"
                image_metadata[full_filename] = {
                    "original_url": url,
                    "description": description,
                }

                new_alt = filename.replace("-", " ")
                return f"**{new_alt}**：{description}\n\n![{new_alt}](image://{full_filename})"

            except Exception as e:
                logger.warning(f"图片处理失败 {url}: {e}")
                return match.group(0)

        new_markdown = re.sub(pattern, replace_image, markdown)
        return new_markdown, image_metadata
