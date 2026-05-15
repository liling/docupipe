from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from docpipe.destinations.base import DestinationBase
from docpipe.display import Display
from docpipe.models import SkipDocument
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
        type_resolver=None,
        content_type_strategy: ContentTypeStrategy | None = None,
    ):
        self.source = source
        self.dest = dest
        self.state = StateManager(state_dir / f"{source.name}_{dest.name}_state.json")
        self._display = display or Display()
        self._type_resolver = type_resolver
        self._content_type_strategy = content_type_strategy

    def _resolve_type(self, doc_meta):
        ext_raw = doc_meta.extra.get("extension", "")
        extension = f".{ext_raw}" if ext_raw else ""
        mime_type = doc_meta.extra.get("contentType", "")
        return self._type_resolver.resolve(extension, mime_type)

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

            # 类型策略过滤
            if self._content_type_strategy:
                # 第一级：ContentTypeStrategy
                content_type = doc_meta.extra.get("contentType", "")
                action = self._content_type_strategy.resolve(content_type)
                if action is None or action == "skip":
                    ct_label = content_type or "未知类型"
                    self._display.result("skip", f"{doc_meta.path} [contentType={ct_label}, action={action or 'skip'}]")
                    continue
                if action in ("source", "download"):
                    converter_name = None
                elif action == "convert":
                    # 第二级：TypeRuleResolver（仅 convert 动作）
                    if self._type_resolver:
                        converter_name = self._resolve_type(doc_meta)
                        if converter_name == "skip":
                            ext_info = doc_meta.extra.get("extension", "") or ""
                            ext_label = f".{ext_info}" if ext_info else "未知扩展名"
                            self._display.result("skip", f"{doc_meta.path} [contentType={content_type}, converter=skip: {ext_label}]")
                            continue
                        if converter_name == "source":
                            converter_name = None
                    else:
                        converter_name = None
            elif self._type_resolver:
                # 向后兼容：无 ContentTypeStrategy 时走原有逻辑
                converter_name = self._resolve_type(doc_meta)
                ext_info = doc_meta.extra.get("extension", "") or ""
                type_info = doc_meta.extra.get("contentType", "") or ""
                type_label = f".{ext_info}" if ext_info else type_info or "未知类型"
                if converter_name is None:
                    self._display.result("skip", f"{doc_meta.path} [action=convert, 无匹配 converter: {type_label}]")
                    continue
                if converter_name == "skip":
                    self._display.result("skip", f"{doc_meta.path} [action=convert, converter=skip: {type_label}]")
                    continue
                if converter_name == "source":
                    converter_name = None
            else:
                converter_name = None

            # 构建策略标签用于输出
            _strategy_parts = []
            if self._content_type_strategy:
                _strategy_parts.append(f"action={action}")
            if converter_name:
                _strategy_parts.append(f"converter={converter_name}")
            _strategy_label = f" [{', '.join(_strategy_parts)}]" if _strategy_parts else ""

            _display_path = f"{doc_meta.path}{_strategy_label}"
            self._display.set_current(_display_path)
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
                    self._display.result("info", f"[dry-run] {_display_path}")
                else:
                    self.dest.write(doc)
                    self._display.result("success", _display_path)
                    self.state.mark_done(doc_meta.id, doc.meta.hash, doc_meta.path)
            except SkipDocument as e:
                logger.info("跳过文档: %s - %s", doc_meta.path, e)
                self._display.result("skip", f"{doc_meta.path} ({e})")
            except Exception as e:
                ct = doc_meta.extra.get("contentType", "")
                ext = doc_meta.extra.get("extension", "")
                detail = f"contentType={ct}" + (f", extension={ext}" if ext else "")
                logger.error("文档处理失败: %s [%s] - %s", doc_meta.path, detail, e)
                self._display.result("error", f"{doc_meta.path} [{detail}]: {e}")
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
