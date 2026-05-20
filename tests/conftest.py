from __future__ import annotations

import hashlib

import pytest

from docupipe.models import Bundle, BundleMeta, FileItem
from docupipe.sources.base import SourceBase
from docupipe.destinations.base import DestinationBase
from docupipe.state import content_hash, bundle_hash


class FakeSource(SourceBase):
    name = "fake"

    def __init__(self, bundles: list[Bundle] | None = None, **kwargs):
        self._bundles = bundles or []

    def list(self) -> list[BundleMeta]:
        return [
            BundleMeta(
                id=b.context.get("id", ""),
                title=b.context.get("title", ""),
                path=b.context.get("path", ""),
                hash=bundle_hash(b),
                extra=b.context.get("extra", {}),
            )
            for b in self._bundles
        ]

    def fetch(self, meta: BundleMeta) -> Bundle:
        for b in self._bundles:
            if b.context.get("id") == meta.id:
                return b
        raise ValueError(f"Bundle not found: {meta.id}")


class FakeDestination(DestinationBase):
    name = "fake"

    def __init__(self, **kwargs):
        self.written: list[Bundle] = []
        self.removed: list[str] = []

    def remove(self, doc_id: str) -> None:
        self.removed.append(doc_id)

    def write(self, bundle: Bundle) -> str:
        self.written.append(bundle)
        return bundle.context.get("id", "")


class FakeSourceWithMeta(SourceBase):
    """支持自定义 list 结果和 mtime 的 FakeSource"""
    name = "fake"

    def __init__(self, metas: list[BundleMeta] | None = None, bundles: dict[str, Bundle] | None = None, **kwargs):
        self._metas = metas or []
        self._bundles = bundles or {}

    def list(self) -> list[BundleMeta]:
        return self._metas

    def fetch(self, meta: BundleMeta) -> Bundle:
        if meta.id in self._bundles:
            return self._bundles[meta.id]
        return _make_bundle(meta.id, meta.title, path=meta.path)

    def supported_change_detection(self) -> list[str]:
        return ["mtime", "hash"]

    def delete(self, doc_id: str) -> None:
        self._metas = [m for m in self._metas if m.id != doc_id]


def _make_bundle(id: str, title: str, content: str = "hello", path: str = "", **extra) -> Bundle:
    return Bundle(
        files=[FileItem(name=f"{title}.md", content=content, content_type="text/markdown", role="main")],
        context={"id": id, "title": title, "path": path or f"{title}.md", **extra},
    )


def _make_meta(id: str, title: str, content: str = "hello", path: str = "",
                mtime: int | None = None, **extra) -> BundleMeta:
    return BundleMeta(
        id=id, title=title, path=path or f"{title}.md",
        hash=content_hash(content),
        extra={"mtime": mtime, **extra} if mtime else extra,
    )
