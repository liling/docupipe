# S3 Upload Step 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `s3_upload` 步骤，将 markdown 附件上传到 S3 兼容存储，替换 markdown 中的引用 URL，并从 bundle 中移除已上传文件。

**Architecture:** 单一步骤类 `S3UploadStep`，在 `process()` 中完成附件上传、URL 替换、bundle 清理。使用 boto3 作为 S3 SDK，支持自定义 endpoint 兼容 rustfs 等存储。

**Tech Stack:** Python 3.11+ / boto3 / pytest + unittest.mock

---

### Task 1: 添加 boto3 依赖

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 添加 boto3 到项目依赖**

在 `pyproject.toml` 的 `dependencies` 列表中添加 `boto3`：

```toml
dependencies = [
    "click>=8.1.0",
    "markitdown>=0.1.0",
    "hindsight-client>=0.1.0",
    "rich>=13.0.0",
    "python-dotenv>=1.0.0",
    "pyyaml>=6.0",
    "requests>=2.31.0",
    "openai>=1.0.0",
    "boto3>=1.28.0",
]
```

- [ ] **Step 2: 安装依赖**

Run: `pip install -e ".[dev]"`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat: 添加 boto3 依赖"
```

---

### Task 2: 实现 S3UploadStep

**Files:**
- Create: `docpipe/steps/s3_upload.py`

- [ ] **Step 1: 编写测试**

创建 `tests/test_s3_upload.py`：

```python
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call

from docpipe.models import Bundle, FileItem
from docpipe.steps.s3_upload import S3UploadStep


def _make_bundle(md_content: str, images: list[tuple] | None = None, doc_id: str = "doc1"):
    files = [FileItem(name="doc.md", content=md_content, content_type="text/markdown", role="main")]
    for item in (images or []):
        name, data = item[0], item[1]
        role = item[2] if len(item) > 2 else "image"
        files.append(FileItem(name=name, content=data, content_type="image/png", role=role))
    return Bundle(files=files, context={"id": doc_id})


def _make_step(**overrides):
    defaults = {
        "endpoint_url": "http://localhost:9000",
        "region": "us-east-1",
        "bucket": "test-bucket",
        "access_key": "test-ak",
        "secret_key": "test-sk",
        "prefix": "attachments",
        "url_prefix": "https://cdn.example.com",
        "roles": ["image"],
        "id_key": "id",
    }
    defaults.update(overrides)
    return S3UploadStep(**defaults)


class TestS3UploadStepNoOp:

    def test_non_markdown_main_skipped(self):
        step = _make_step()
        bundle = Bundle(files=[
            FileItem(name="doc.docx", content=b"\x00\x01", role="main"),
        ])
        with patch("docpipe.steps.s3_upload.boto3") as mock_boto3:
            result = step.process(bundle)
        assert len(result.files) == 1

    def test_no_matching_roles_skipped(self):
        step = _make_step(roles=["image"])
        bundle = Bundle(files=[
            FileItem(name="doc.md", content="hello", role="main"),
            FileItem(name="data.csv", content=b"a,b", role="attachment"),
        ])
        result = step.process(bundle)
        assert len(result.files) == 2

    def test_empty_bundle(self):
        step = _make_step()
        result = step.process(Bundle())
        assert result.files == []


class TestS3UploadStepUpload:

    @patch("docpipe.steps.s3_upload.boto3")
    def test_upload_single_image(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        step = _make_step()
        md = "# Title\n\n![photo](images/photo.png)\n"
        bundle = _make_bundle(md, [("photo.png", b"\x89PNG")])

        result = step.process(bundle)

        mock_client.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="attachments/doc1/photo.png",
            Body=b"\x89PNG",
        )
        assert len(result.files) == 1
        assert result.files[0].role == "main"
        assert "https://cdn.example.com/attachments/doc1/photo.png" in result.main.content
        assert "images/photo.png" not in result.main.content

    @patch("docpipe.steps.s3_upload.boto3")
    def test_upload_image_without_prefix(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        step = _make_step()
        md = "![photo](photo.png)\n"
        bundle = _make_bundle(md, [("photo.png", b"\x89PNG")])

        result = step.process(bundle)

        assert "https://cdn.example.com/attachments/doc1/photo.png" in result.main.content
        assert len(result.files) == 1

    @patch("docpipe.steps.s3_upload.boto3")
    def test_upload_multiple_images(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        step = _make_step()
        md = "![a](images/a.png)\n![b](images/b.png)\n"
        bundle = _make_bundle(md, [("a.png", b"aaa"), ("b.png", b"bbb")])

        result = step.process(bundle)

        assert mock_client.put_object.call_count == 2
        assert len(result.files) == 1
        assert "attachments/doc1/a.png" in result.main.content
        assert "attachments/doc1/b.png" in result.main.content

    @patch("docpipe.steps.s3_upload.boto3")
    def test_link_reference_replaced(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        step = _make_step()
        md = "[download](images/report.pdf)\n"
        bundle = _make_bundle(md, [("report.pdf", b"%PDF", "attachment")],
                              doc_id="doc2")

        result = step.process(bundle)

        assert "https://cdn.example.com/attachments/doc2/report.pdf" in result.main.content


class TestS3UploadStepFallback:

    @patch("docpipe.steps.s3_upload.boto3")
    def test_missing_doc_id_uses_unknown(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        step = _make_step()
        md = "![photo](photo.png)\n"
        files = [
            FileItem(name="doc.md", content=md, role="main"),
            FileItem(name="photo.png", content=b"\x89PNG", role="image"),
        ]
        bundle = Bundle(files=files, context={})

        result = step.process(bundle)

        mock_client.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="attachments/unknown/photo.png",
            Body=b"\x89PNG",
        )

    @patch("docpipe.steps.s3_upload.boto3")
    def test_upload_failure_skips_file(self, mock_boto3):
        mock_client = MagicMock()
        mock_client.put_object.side_effect = Exception("network error")
        mock_boto3.client.return_value = mock_client

        step = _make_step()
        md = "![photo](photo.png)\n"
        bundle = _make_bundle(md, [("photo.png", b"\x89PNG")])

        result = step.process(bundle)

        # File kept, URL not replaced
        assert len(result.files) == 2
        assert "photo.png" in result.main.content
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_s3_upload.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'docpipe.steps.s3_upload'`

- [ ] **Step 3: 实现 S3UploadStep**

创建 `docpipe/steps/s3_upload.py`：

```python
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
                self._client.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=att.content,
                )
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
```

- [ ] **Step 4: 注册 step**

在 `docpipe/steps/__init__.py` 末尾添加 import：

```python
import docpipe.steps.s3_upload  # noqa: F401, E402
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_s3_upload.py -v`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add docpipe/steps/s3_upload.py docpipe/steps/__init__.py tests/test_s3_upload.py
git commit -m "feat: 实现 s3_upload 步骤"
```

---

### Task 3: 集成测试验证

**Files:**
- Test: `tests/test_s3_upload.py`

- [ ] **Step 1: 补充自定义 roles 配置测试**

在 `tests/test_s3_upload.py` 的 `TestS3UploadStepUpload` 类中添加：

```python
    @patch("docpipe.steps.s3_upload.boto3")
    def test_custom_roles(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        step = _make_step(roles=["attachment"])
        md = "[file](data.csv)\n"
        files = [
            FileItem(name="doc.md", content=md, role="main"),
            FileItem(name="data.csv", content=b"a,b", role="attachment"),
        ]
        bundle = Bundle(files=files, context={"id": "doc1"})

        result = step.process(bundle)

        assert len(result.files) == 1
        assert "https://cdn.example.com/attachments/doc1/data.csv" in result.main.content
```

- [ ] **Step 2: 运行全部测试确认无回归**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_s3_upload.py
git commit -m "test: 补充 s3_upload 自定义 roles 测试"
```
