from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

import requests as req

from openai import AsyncOpenAI, OpenAI

if TYPE_CHECKING:
    from docpipe.models import FileItem

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_TYPES: set[str] = {"png", "jpeg", "jpg", "gif", "webp", "bmp"}
MIN_IMAGE_DIM = 10


class OpenAIVisionClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "gpt-4o",
        timeout: int = 30,
    ):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.async_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
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

    async def a_describe(self, image_bytes: bytes, context: str) -> tuple[str, str]:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        prompt = (
            f"这是一篇文档《{context}》中的图片。\n\n"
            "请完成两个任务：\n"
            "1. 生成一个简短的英文文件名（3-5个单词，用连字符连接，如 \"system-architecture-diagram\"）\n"
            "2. 用一句话描述图片内容（中文，适合在文档中作为图片说明）\n\n"
            '请以 JSON 格式返回：\n{"filename": "...", "description": "..."}'
        )

        response = await self.async_client.chat.completions.create(
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
            match = re.search(r'\{[^}]+\}', raw)
            if match:
                try:
                    data = json.loads(match.group())
                    return data["filename"], data["description"]
                except (json.JSONDecodeError, KeyError):
                    pass
            logger.warning("Vision API 返回无法解析: %s", raw[:200])
            return "image-unknown", "图片描述解析失败"


def validate_image(image_bytes: bytes) -> bytes | None:
    """验证图片是否可处理：检查格式和尺寸。返回有效图片字节或 None。"""
    if not image_bytes:
        return None

    image_bytes = _ensure_supported_format(image_bytes)
    if image_bytes is None:
        return None

    if not _check_image_size(image_bytes):
        return None

    return image_bytes


def _ensure_supported_format(image_bytes: bytes) -> bytes | None:
    """将不支持格式的图片转为 PNG，不可转换则返回 None。"""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        fmt = (img.format or "").lower()
        if fmt in ("png", "jpeg", "jpg", "gif", "bmp", "webp"):
            return image_bytes
        # 尝试转换为 PNG
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        logger.debug("图片格式 %s 转为 PNG, %d -> %d bytes", fmt, len(image_bytes), len(buf.getvalue()))
        return buf.getvalue()
    except ImportError:
        # 没有 PIL，只检查简单 magic bytes
        if image_bytes[:8] == b'\x89PNG\r\n\x1a\n' or image_bytes[:2] == b'\xff\xd8':
            return image_bytes
        return None
    except Exception as e:
        logger.debug("无法识别图片格式: %s", e)
        return None


def _check_image_size(image_bytes: bytes) -> bool:
    """检查图片像素尺寸，宽或高小于 MIN_IMAGE_DIM 则跳过。"""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        if w < MIN_IMAGE_DIM or h < MIN_IMAGE_DIM:
            logger.debug("图片尺寸过小 (%dx%d)，跳过", w, h)
            return False
    except ImportError:
        pass
    except Exception:
        pass
    return True


class ImagePostProcessor:
    def __init__(self, vision_client: OpenAIVisionClient, max_image_size: int = 10 * 1024 * 1024,
                 concurrency: int = 1):
        self.vision_client = vision_client
        self.max_image_size = max_image_size
        self.concurrency = concurrency

    def _resolve_image_bytes(self, url: str, image_files: dict[str, FileItem] | None,
                             images_dir: str | None) -> bytes | None:
        if image_files and url in image_files:
            file_item = image_files[url]
            if isinstance(file_item.content, bytes):
                return file_item.content
            return base64.b64decode(file_item.content)
        if url.startswith("data:"):
            return self._decode_data_uri(url)
        if "://" in url:
            resp = req.get(url, timeout=30)
            resp.raise_for_status()
            return resp.content
        if images_dir:
            local_path = Path(images_dir) / url
            if local_path.is_file():
                return local_path.read_bytes()
        return None

    def process(self, markdown: str, source_context: str, images_dir: str | None = None,
                image_files: dict[str, FileItem] | None = None,
                progress_callback=None) -> tuple[str, dict]:
        image_metadata: dict[str, dict] = {}
        pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        all_matches = list(re.finditer(pattern, markdown))

        if not all_matches:
            return markdown, {}

        # Phase 1: Collect — resolve image bytes for each match
        processable: list[tuple[int, re.Match, bytes]] = []
        for i, match in enumerate(all_matches):
            url = match.group(2).strip().strip('"').strip("'").strip()
            if url.startswith("image://"):
                continue
            try:
                image_bytes = self._resolve_image_bytes(url, image_files, images_dir)
                if not image_bytes or len(image_bytes) > self.max_image_size:
                    continue
                image_bytes = validate_image(image_bytes)
                if image_bytes is None:
                    logger.debug("图片不满足处理条件，保留原引用: %s", url[:80])
                    continue
                processable.append((i, match, image_bytes))
            except Exception as e:
                logger.warning("图片加载失败 %s: %s", url[:80], e)

        total = len(processable)
        if total == 0:
            return markdown, {}

        # Phase 2: Describe
        image_bytes_list = [img_bytes for _, _, img_bytes in processable]
        if self.concurrency > 1:
            results = asyncio.run(self._run_concurrent(image_bytes_list, source_context))
        else:
            results = self._run_sync(image_bytes_list, source_context)

        # Phase 3: Build replacements and metadata
        replacements: dict[int, str] = {}
        for (idx, match, _), (filename, description) in zip(processable, results):
            if filename is None:
                continue
            url = match.group(2).strip().strip('"').strip("'").strip()
            original_ext = PurePosixPath(url).suffix or ".png"
            full_filename = f"{filename}{original_ext}"
            image_metadata[full_filename] = {
                "original_url": url[:200],
                "description": description,
            }
            if "/" in url:
                new_url = f"{url.rsplit('/', 1)[0]}/{full_filename}"
            else:
                new_url = full_filename
            replacements[idx] = f"![{description}]({new_url})"

        # Phase 4: Progress callback
        if progress_callback and total > 0:
            done = sum(1 for r in results if r[0] is not None)
            progress_callback(f"image_description ({done}/{total})")

        # Phase 5: Rebuild markdown
        parts: list[str] = []
        last_end = 0
        for i, match in enumerate(all_matches):
            parts.append(markdown[last_end:match.start()])
            if i in replacements:
                parts.append(replacements[i])
            else:
                parts.append(match.group(0))
            last_end = match.end()
        parts.append(markdown[last_end:])

        return "".join(parts), image_metadata

    def _run_sync(self, image_bytes_list: list[bytes], source_context: str) -> list[tuple[str | None, str | None]]:
        results: list[tuple[str | None, str | None]] = []
        for img_bytes in image_bytes_list:
            try:
                filename, description = self.vision_client.describe(img_bytes, source_context)
                results.append((filename, description))
            except Exception as e:
                logger.warning("图片描述失败: %s", e)
                results.append((None, None))
        return results

    async def _run_concurrent(self, image_bytes_list: list[bytes], source_context: str) -> list[tuple[str | None, str | None]]:
        sem = asyncio.Semaphore(self.concurrency)

        async def describe_one(img_bytes: bytes) -> tuple[str | None, str | None]:
            async with sem:
                try:
                    return await self.vision_client.a_describe(img_bytes, source_context)
                except Exception as e:
                    logger.warning("图片描述失败: %s", e)
                    return (None, None)

        return await asyncio.gather(*[describe_one(b) for b in image_bytes_list])

    @staticmethod
    def _decode_data_uri(uri: str) -> bytes:
        match = re.match(r'data:[^;]+;base64,(.+)', uri)
        if not match:
            raise ValueError(f"无法解析 data URI: {uri[:50]}")
        return base64.b64decode(match.group(1))
