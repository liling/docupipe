from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from docpipe.destinations.base import DestinationBase
from docpipe.display import Display
from docpipe.models import Document, DocumentMeta, SkipDocument
from docpipe.sources.base import SourceBase

logger = logging.getLogger(__name__)


class StateManager:
    def __init__(self, path: Path):
        self._path = path

    def load(self) -> dict[str, dict]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        # 兼容旧格式：{id: hash} → {id: {"hash": hash, "path": ""}}
        result = {}
        for k, v in raw.items():
            if isinstance(v, str):
                result[k] = {"hash": v, "path": ""}
            else:
                result[k] = v
        return result

    def save(self, entries: dict[str, dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def is_processed(self, doc_id: str) -> bool:
        return doc_id in self.load()

    def is_unchanged(self, doc_id: str, content_hash: str) -> bool:
        entry = self.load().get(doc_id, {})
        return entry.get("hash") == content_hash

    def mark_done(self, doc_id: str, content_hash: str, path: str = "") -> None:
        entries = self.load()
        entries[doc_id] = {"hash": content_hash, "path": path}
        self.save(entries)

    def get_path(self, doc_id: str) -> str:
        return self.load().get(doc_id, {}).get("path", "")

    def find_removed(self, current_ids: list[str]) -> list[str]:
        stored = self.load()
        current_set = set(current_ids)
        return [doc_id for doc_id in stored if doc_id not in current_set]

    def mark_removed(self, doc_id: str) -> None:
        entries = self.load()
        entries.pop(doc_id, None)
        self.save(entries)


class ContentTypeStrategy:
    """钉钉 contentType 到处理动作的映射"""

    def __init__(self, rules: dict[str, str] | None = None):
        self._rules = rules or {}

    def resolve(self, content_type: str) -> str | None:
        return self._rules.get(content_type)


def content_hash(content: str | bytes) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


class Pipeline:
    def __init__(
        self,
        source: SourceBase,
        dest: DestinationBase,
        state_dir: Path,
        display: Display | None = None,
        steps: list | None = None,
        type_resolver=None,
        content_type_strategy: ContentTypeStrategy | None = None,
    ):
        self.source = source
        self.dest = dest
        self.state = StateManager(state_dir / f"{source.name}_{dest.name}_state.json")
        self._display = display or Display()
        self._steps = steps or []
        self._type_resolver = type_resolver
        self._content_type_strategy = content_type_strategy

    def _resolve_type(self, doc_meta):
        ext_raw = doc_meta.extra.get("extension", "")
        extension = f".{ext_raw}" if ext_raw else ""
        mime_type = doc_meta.extra.get("contentType", "")
        return self._type_resolver.resolve(extension, mime_type)

    def _process_with_legacy_rules(self, doc: Document, doc_meta: DocumentMeta) -> Document | None:
        """CLI 参数模式的旧逻辑，返回 None 表示跳过"""
        converter_name = None
        if self._content_type_strategy:
            ct = doc_meta.extra.get("contentType", "")
            action = self._content_type_strategy.resolve(ct)
            if action is None or action == "skip":
                self._display.result("skip", f"{doc_meta.path} [contentType={ct or '未知'}]")
                return None
            if action == "convert" and self._type_resolver:
                converter_name = self._resolve_type(doc_meta)
                if converter_name == "skip":
                    self._display.result("skip", f"{doc_meta.path} [无匹配 converter]")
                    return None
                if converter_name == "source":
                    converter_name = None
            # action == "source", "download", or convert with no resolver: no conversion
        elif self._type_resolver:
            converter_name = self._resolve_type(doc_meta)
            if converter_name is None:
                self._display.result("skip", f"{doc_meta.path} [无匹配 converter]")
                return None
            if converter_name == "skip":
                self._display.result("skip", f"{doc_meta.path} [无匹配 converter]")
                return None
            if converter_name == "source":
                converter_name = None

        # 仅在 Source 标记需要转换时执行 converter
        if doc.meta.extra.get("_needs_conversion") and converter_name:
            return self._run_converter(doc, converter_name)
        return doc

    def _run_converter(self, doc: Document, converter_name: str) -> Document:
        """执行 converter 转换"""
        from docpipe.converters import get_converter
        converter_cls = get_converter(converter_name)
        converter = converter_cls()
        file_path = Path(doc.meta.extra.get("_temp_file", doc.meta.extra.get("absolute_path", "")))
        try:
            doc.content = converter.convert(file_path)
            doc.content_type = "markdown"
        finally:
            if doc.meta.extra.get("_temp_file"):
                file_path.unlink(missing_ok=True)
        return doc

    def run(self, *, resume: bool = False, sync: bool = False, dry_run: bool = False) -> None:
        logger.info("Pipeline 开始: %s → %s (resume=%s, sync=%s, dry_run=%s)",
                     self.source.name, self.dest.name, resume, sync, dry_run)
        docs = self.source.list_documents()

        if resume:
            docs = [d for d in docs if not self.state.is_processed(d.id)]

        logger.info("待处理文档: %d 个", len(docs))

        self._display.start(f"Pipeline: {self.source.name} → {self.dest.name}", len(docs))

        for doc_meta in docs:
            if sync and self.state.is_unchanged(doc_meta.id, doc_meta.hash):
                self._display.result("skip", f"{doc_meta.path} (无变化)")
                continue

            _display_path = doc_meta.path
            self._display.set_current(_display_path)
            try:
                doc = self.source.fetch(doc_meta)

                if self._steps:
                    for step in self._steps:
                        doc = step.process(doc)
                elif self._type_resolver or self._content_type_strategy:
                    doc = self._process_with_legacy_rules(doc, doc_meta)
                    if doc is None:
                        continue

                if not doc.meta.hash:
                    doc.meta.hash = content_hash(doc.content)
                doc.meta.extra["_source"] = self.source.name

                if dry_run:
                    self._display.result("info", f"[dry-run] {_display_path}")
                else:
                    self.dest.write(doc)
                    self._display.result("success", _display_path)
                    self.state.mark_done(doc_meta.id, doc.meta.hash, doc_meta.path)
            except SkipDocument as e:
                logger.info("跳过文档: %s - %s", doc_meta.path, e)
                self._display.result("skip", f"{doc_meta.path} ({e})")
            except Exception as e:
                logger.error("文档处理失败: %s - %s", doc_meta.path, e)
                self._display.result("error", f"{doc_meta.path}: {e}")
                self._display.add_failure()
            finally:
                self._display.clear_current(_display_path)

        if sync:
            removed = self.state.find_removed([d.id for d in docs])
            for doc_id in removed:
                doc_path = self.state.get_path(doc_id) or doc_id
                try:
                    if not dry_run:
                        self.dest.remove(doc_id)
                        self.state.mark_removed(doc_id)
                    self._display.result("info", f"从 {self.dest.name} 移除: {doc_path}")
                except NotImplementedError:
                    pass
                except Exception as e:
                    self._display.result("error", f"移除失败 {doc_path}: {e}")

        self._display.stop()
        self._display.print_summary()
        logger.info("Pipeline 完成: %s → %s", self.source.name, self.dest.name)
