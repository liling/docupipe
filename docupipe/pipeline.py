from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from docupipe.config import resolve_context_vars
from docupipe.destinations.base import DestinationBase
from docupipe.display import Display
from docupipe.models import Bundle, BundleMeta, SkipBundle
from docupipe.sources.base import SourceBase

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


def content_hash(content: str | bytes) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def bundle_hash(bundle: Bundle) -> str:
    """从 Bundle 的主文件内容计算 hash"""
    if bundle.main is None:
        return ""
    return content_hash(bundle.main.content)


class Pipeline:
    def __init__(
        self,
        source: SourceBase,
        dest: DestinationBase,
        state_dir: Path,
        display: Display | None = None,
        steps: list | None = None,
        dest_config: dict | None = None,
    ):
        self.source = source
        self.dest = dest
        self.state = StateManager(state_dir / f"{source.name}_{dest.name}_state.json")
        self._display = display or Display()
        self._steps = steps
        self._dest_config = dest_config

    def run(self, *, resume: bool = False, sync: bool = False, dry_run: bool = False) -> None:
        logger.info("Pipeline 开始: %s → %s (resume=%s, sync=%s, dry_run=%s)",
                     self.source.name, self.dest.name, resume, sync, dry_run)
        metas = self.source.list()

        if resume:
            metas = [m for m in metas if not self.state.is_processed(m.id)]

        logger.info("待处理文档: %d 个", len(metas))

        self._display.start(f"Pipeline: {self.source.name} → {self.dest.name}", len(metas))

        for meta in metas:
            if sync and self.state.is_unchanged(meta.id, meta.hash):
                self._display.result("skip", f"{meta.path} (无变化)")
                continue

            _display_path = meta.path
            self._display.set_current(_display_path)
            try:
                bundle = self.source.fetch(meta)

                # 设置 Bundle 的通用上下文字段
                bundle.context["id"] = meta.id
                bundle.context["title"] = meta.title
                bundle.context["path"] = meta.path
                bundle.context["filename"] = Path(meta.path).name if meta.path else ""
                bundle.context["_source"] = self.source.name

                # 运行处理步骤
                if self._steps is not None:
                    for step in self._steps:
                        step_name = step.name or step.__class__.__name__
                        self._display.set_step(step_name)
                        bundle.context["_step_progress"] = self._display.set_step
                        try:
                            bundle = step.process(bundle)
                        finally:
                            bundle.context.pop("_step_progress", None)
                            self._display.clear_step()

                # 计算最终 hash
                bundle_hash_value = bundle_hash(bundle)
                bundle.context["hash"] = bundle_hash_value

                if dry_run:
                    self._display.result("info", f"[dry-run] {_display_path}")
                else:
                    if self._dest_config:
                        resolved = resolve_context_vars(self._dest_config, bundle.context)
                        self.dest.update_config(resolved)
                    self.dest.write(bundle)
                    self._display.result("success", _display_path)
                    self.state.mark_done(meta.id, bundle_hash_value, meta.path)
            except SkipBundle as e:
                logger.info("跳过文档: %s - %s", meta.path, e)
                self._display.result("skip", f"{meta.path} ({e})")
            except Exception as e:
                logger.error("文档处理失败: %s - %s", meta.path, e)
                self._display.result("error", f"{meta.path}: {e}")
                self._display.add_failure()
            finally:
                self._display.clear_current(_display_path)

        if sync:
            removed = self.state.find_removed([m.id for m in metas])
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
