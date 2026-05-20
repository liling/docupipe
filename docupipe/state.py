from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from docupipe.models import Bundle


logger = logging.getLogger(__name__)


def content_hash(content: str | bytes) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def bundle_hash(bundle: Bundle) -> str:
    if bundle.main is None:
        if not bundle.files:
            return ""
        combined = "".join(
            str(f.content) if isinstance(f.content, str) else f.content.hex()
            for f in bundle.files
        )
        return content_hash(combined)
    return content_hash(bundle.main.content)


class StateManager:
    def __init__(self, path: Path):
        self._path = path
        self._cache: dict[str, dict] | None = None
        self._dirty = False

    def load(self) -> dict[str, dict]:
        if self._cache is not None:
            return self._cache
        if not self._path.exists():
            self._cache = {}
            return self._cache
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._cache = {}
            return self._cache
        result = {}
        for k, v in raw.items():
            if isinstance(v, str):
                result[k] = {"hash": v, "path": "", "status": "done"}
            else:
                result[k] = v
        self._cache = result
        return self._cache

    def save(self, entries: dict[str, dict] | None = None) -> None:
        if entries is not None:
            self._cache = entries
            self._dirty = True
        if not self._dirty or self._cache is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._cache, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._dirty = False

    def is_processed(self, doc_id: str) -> bool:
        entry = self.load().get(doc_id, {})
        return entry.get("status") == "done"

    def is_unchanged(self, doc_id: str, content_hash: str) -> bool:
        entry = self.load().get(doc_id, {})
        return entry.get("hash") == content_hash

    def is_mtime_unchanged(self, doc_id: str, mtime: int) -> bool:
        entry = self.load().get(doc_id, {})
        return entry.get("mtime") == mtime

    def mark_pending(self, items: list[tuple[str, str, str, dict]]) -> None:
        entries = self.load()
        for doc_id, path, title, fetch_extra in items:
            entries[doc_id] = {
                "status": "pending",
                "path": path,
                "title": title,
                "fetch_extra": fetch_extra,
            }
        self._dirty = True
        self.save()

    def mark_done(self, doc_id: str, content_hash: str, path: str = "", mtime: int | None = None,
                  source_hash: str | None = None) -> None:
        entries = self.load()
        entry = {"status": "done", "hash": content_hash, "path": path}
        if mtime is not None:
            entry["mtime"] = mtime
        if source_hash is not None:
            entry["source_hash"] = source_hash
        entries[doc_id] = entry
        self._dirty = True
        self.save()

    def is_source_unchanged(self, doc_id: str, current_source_hash: str) -> bool:
        entry = self.load().get(doc_id, {})
        stored = entry.get("source_hash")
        if stored is None:
            stored = entry.get("hash")
        return stored == current_source_hash

    def get_path(self, doc_id: str) -> str:
        return self.load().get(doc_id, {}).get("path", "")

    def get_mtime(self, doc_id: str) -> int | None:
        return self.load().get(doc_id, {}).get("mtime")

    def find_pending(self) -> list[tuple[str, str, str, dict]]:
        result = []
        for doc_id, entry in self.load().items():
            if entry.get("status") == "pending":
                result.append((doc_id, entry.get("title", ""), entry.get("path", ""), entry.get("fetch_extra", {})))
        return result

    def find_removed(self, current_ids: list[str]) -> list[str]:
        stored = self.load()
        current_set = set(current_ids)
        return [doc_id for doc_id in stored if doc_id not in current_set]

    def mark_removed(self, doc_id: str) -> None:
        entries = self.load()
        entries.pop(doc_id, None)
        self._dirty = True
        self.save()
