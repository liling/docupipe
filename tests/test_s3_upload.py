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
        step = _make_step(roles=["image", "attachment"])
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
        step = _make_step(roles=["image", "attachment"])
        result = step.process(Bundle())
        assert result.files == []


class TestS3UploadStepUpload:

    @patch("docpipe.steps.s3_upload.boto3")
    def test_upload_single_image(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        step = _make_step(roles=["image", "attachment"])
        md = "# Title\n\n![photo](images/photo.png)\n"
        bundle = _make_bundle(md, [("photo.png", b"\x89PNG")])

        result = step.process(bundle)

        mock_client.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="attachments/doc1/photo.png",
            Body=b"\x89PNG",
            ContentType="image/png",
        )
        assert len(result.files) == 1
        assert result.files[0].role == "main"
        assert "https://cdn.example.com/attachments/doc1/photo.png" in result.main.content
        assert "images/photo.png" not in result.main.content

    @patch("docpipe.steps.s3_upload.boto3")
    def test_upload_image_without_prefix(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        step = _make_step(roles=["image", "attachment"])
        md = "![photo](photo.png)\n"
        bundle = _make_bundle(md, [("photo.png", b"\x89PNG")])

        result = step.process(bundle)

        assert "https://cdn.example.com/attachments/doc1/photo.png" in result.main.content
        assert len(result.files) == 1

    @patch("docpipe.steps.s3_upload.boto3")
    def test_upload_multiple_images(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        step = _make_step(roles=["image", "attachment"])
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

        step = _make_step(roles=["image", "attachment"])
        md = "[download](images/report.pdf)\n"
        bundle = _make_bundle(md, [("report.pdf", b"%PDF", "attachment")],
                              doc_id="doc2")

        result = step.process(bundle)

        assert "https://cdn.example.com/attachments/doc2/report.pdf" in result.main.content

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


class TestS3UploadStepFallback:

    @patch("docpipe.steps.s3_upload.boto3")
    def test_missing_doc_id_uses_unknown(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        step = _make_step(roles=["image", "attachment"])
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

        step = _make_step(roles=["image", "attachment"])
        md = "![photo](photo.png)\n"
        bundle = _make_bundle(md, [("photo.png", b"\x89PNG")])

        result = step.process(bundle)

        assert len(result.files) == 2
        assert "photo.png" in result.main.content
