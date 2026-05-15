from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from docpipe.destinations.base import DestinationBase
from docpipe.display import Display
from docpipe.sources.base import SourceBase

logger = logging.getLogger(__name__)


class StateManager:
    def __init__(self, path: Path):
        self._path = path

    def load(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self, hashes: dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(hashes, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def is_processed(self, doc_id: str) -> bool:
        return doc_id in self.load()

    def is_unchanged(self, doc_id: str, content_hash: str) -> bool:
        return self.load().get(doc_id) == content_hash

    def mark_done(self, doc_id: str, content_hash: str) -> None:
        hashes = self.load()
        hashes[doc_id] = content_hash
        self.save(hashes)

    def find_removed(self, current_ids: list[str]) -> list[str]:
        stored = self.load()
        current_set = set(current_ids)
        return [doc_id for doc_id in stored if doc_id not in current_set]

    def mark_removed(self, doc_id: str) -> None:
        hashes = self.load()
        hashes.pop(doc_id, None)
        self.save(hashes)


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
        type_resolver=None,
    ):
        self.source = source
        self.dest = dest
        self.state = StateManager(state_dir / f"{source.name}_{dest.name}_state.json")
        self._display = display or Display()
        self._type_resolver = type_resolver

    def _resolve_type(self, doc_meta):
        ext_raw = doc_meta.extra.get("extension", "")
        extension = f".{ext_raw}" if ext_raw else ""
        mime_type = doc_meta.extra.get("contentType", "")
        return self._type_resolver.resolve(extension, mime_type)

    def run(self, *, resume: bool = False, sync: bool = False, dry_run: bool = False) -> None:
        logger.info("Pipeline 开始: %s → %s (resume=%s, sync=%s, dry_run=%s)",
                     self.source.name, self.dest.name, resume, sync, dry_run)
        docs = self.source.list_documents()
        logger.info("待处理文档: %d 个", len(docs))

        if resume:
            docs = [d for d in docs if not self.state.is_processed(d.id)]

        self._display.start(f"Pipeline: {self.source.name} → {self.dest.name}", len(docs))

        for doc_meta in docs:
            if sync and self.state.is_unchanged(doc_meta.id, doc_meta.hash):
                self._display.result("skip", f"{doc_meta.path} (无变化)")
                continue

            # 类型规则过滤
            if self._type_resolver:
                converter_name = self._resolve_type(doc_meta)
                if converter_name is None:
                    self._display.result("skip", f"{doc_meta.path} (无处理规则)")
                    continue
                if converter_name == "skip":
                    self._display.result("skip", f"{doc_meta.path} (跳过)")
                    continue
                if converter_name == "source":
                    converter_name = None
            else:
                converter_name = None

            self._display.set_current(doc_meta.path)
            try:
                doc = self.source.fetch(doc_meta)

                # 转换：如果 Source 标记需要转换，调用 converter
                if doc.meta.extra.get("_needs_conversion") and converter_name:
                    from docpipe.converters import get_converter
                    converter_cls = get_converter(converter_name)
                    converter = converter_cls()
                    file_path = Path(doc.meta.extra["_temp_file"])
                    try:
                        doc.content = converter.convert(file_path)
                    finally:
                        file_path.unlink(missing_ok=True)

                if not doc.meta.hash:
                    doc.meta.hash = content_hash(doc.content)
                doc.meta.extra["_source"] = self.source.name

                if dry_run:
                    self._display.result("info", f"[dry-run] {doc_meta.path}")
                else:
                    self.dest.write(doc)
                    self._display.result("success", doc_meta.path)

                self.state.mark_done(doc_meta.id, doc.meta.hash)
            except Exception as e:
                logger.error("文档处理失败: %s - %s", doc_meta.path, e)
                self._display.result("error", f"{doc_meta.path}: {e}")
                self._display.add_failure()
            finally:
                self._display.clear_current(doc_meta.path)

        if sync:
            doc_paths = {d.id: d.path for d in docs}
            removed = self.state.find_removed([d.id for d in docs])
            for doc_id in removed:
                doc_path = doc_paths.get(doc_id, doc_id)
                try:
                    if not dry_run:
                        self.dest.remove(doc_id)
                    self.state.mark_removed(doc_id)
                    self._display.result("info", f"已移除: {doc_path}")
                except NotImplementedError:
                    pass
                except Exception as e:
                    self._display.result("error", f"移除失败 {doc_path}: {e}")

        self._display.stop()
        self._display.print_summary()
        logger.info("Pipeline 完成: %s → %s", self.source.name, self.dest.name)
