from __future__ import annotations

import base64
import json
import logging
import re

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
