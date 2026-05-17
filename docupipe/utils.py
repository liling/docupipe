from __future__ import annotations

_MIME_MAP = {
    "md": "text/markdown",
    "markdown": "text/markdown",
    "adoc": "text/markdown",
    "txt": "text/plain",
    "csv": "text/csv",
    "html": "text/html",
    "htm": "text/html",
    "json": "application/json",
    "xml": "application/xml",
    "yaml": "application/x-yaml",
    "yml": "application/x-yaml",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "doc": "application/msword",
    "xls": "application/vnd.ms-excel",
    "ppt": "application/vnd.ms-powerpoint",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "svg": "image/svg+xml",
    "emf": "image/x-emf",
    "xmind": "application/octet-stream",
}


def guess_mime_type(extension: str, default: str = "application/octet-stream") -> str:
    if not extension:
        return ""
    return _MIME_MAP.get(extension.lower(), default)
