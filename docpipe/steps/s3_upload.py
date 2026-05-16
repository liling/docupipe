from __future__ import annotations

import logging
import re

import boto3
from botocore.config import Config as BotoConfig

from docpipe.models import Bundle
from docpipe.steps import register_step
from docpipe.steps.base import PipelineStep

logger = logging.getLogger(__name__)


@register_step("s3_upload")
class S3UploadStep(PipelineStep):
    def __init__(
        self,
        endpoint_url: str = "http://localhost:9000",
        region: str = "us-east-1",
        bucket: str = "",
        access_key: str = "",
        secret_key: str = "",
        prefix: str = "attachments",
        url_prefix: str = "",
        roles: list[str] | None = None,
        id_key: str = "id",
        **kwargs,
    ):
        self._bucket = bucket
        self._prefix = prefix
        self._url_prefix = url_prefix.rstrip("/")
        self._roles = roles or ["image"]
        self._id_key = id_key
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=BotoConfig(signature_version="s3v4"),
        )

    def process(self, bundle: Bundle) -> Bundle:
        main = bundle.main
        if not main or not isinstance(main.content, str):
            return bundle

        doc_id = bundle.context.get(self._id_key)
        if not doc_id:
            logger.warning("s3_upload: context 中未找到 %s，使用 'unknown'", self._id_key)
            doc_id = "unknown"

        attachments = [f for f in bundle.files if f.role in self._roles]
        if not attachments:
            return bundle

        uploaded = []
        for att in attachments:
            key = f"{self._prefix}/{doc_id}/{att.name}"
            url = f"{self._url_prefix}/{key}"
            try:
                put_args = {
                    "Bucket": self._bucket,
                    "Key": key,
                    "Body": att.content,
                }
                if att.content_type:
                    put_args["ContentType"] = att.content_type
                self._client.put_object(**put_args)
            except Exception as e:
                logger.warning("s3_upload: 上传 %s 失败: %s", att.name, e)
                continue

            new_content = self._replace_ref(main.content, att.name, url)
            if new_content != main.content:
                main.content = new_content
                uploaded.append(att.name)
            else:
                logger.info("s3_upload: %s 已上传但未在 markdown 中找到引用，保留在 bundle 中", att.name)

        for name in uploaded:
            bundle.remove(name)

        return bundle

    @staticmethod
    def _replace_ref(content: str, filename: str, url: str) -> str:
        pattern = rf'(?<=\()({re.escape(filename)}|images/{re.escape(filename)})(?=\))'
        return re.sub(pattern, url, content)
