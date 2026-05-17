# tests/test_utils.py
from docupipe.utils import guess_mime_type


def test_known_extensions():
    assert guess_mime_type("pdf") == "application/pdf"
    assert guess_mime_type("md") == "text/markdown"
    assert guess_mime_type("docx") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert guess_mime_type("xlsx") == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert guess_mime_type("pptx") == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    assert guess_mime_type("png") == "image/png"
    assert guess_mime_type("jpg") == "image/jpeg"
    assert guess_mime_type("txt") == "text/plain"
    assert guess_mime_type("html") == "text/html"
    assert guess_mime_type("adoc") == "text/markdown"


def test_unknown_extension_returns_default():
    assert guess_mime_type("xyz") == "application/octet-stream"
    assert guess_mime_type("xyz", default="") == ""
    assert guess_mime_type("") == ""
