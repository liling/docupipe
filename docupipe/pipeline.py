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
        """标记文档为待处理。items: [(doc_id, path, title, fetch_extra), ...]"""
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
        stored = entry.get("source_hash") or entry.get("hash")
        return stored == current_source_hash

    def get_path(self, doc_id: str) -> str:
        return self.load().get(doc_id, {}).get("path", "")

    def get_mtime(self, doc_id: str) -> int | None:
        return self.load().get(doc_id, {}).get("mtime")

    def find_pending(self) -> list[tuple[str, str, str, dict]]:
        """返回 [(doc_id, title, path, fetch_extra), ...] 待处理的条目"""
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
        pipeline_name: str = "",
        display: Display | None = None,
        steps: list | None = None,
        post_steps: list | None = None,
        dest_config: dict | None = None,
        state_file: str | None = None,
        mode: str = "full",
        change_detection: str | None = None,
        mirror_delete: bool = True,
    ):
        self.source = source
        self.dest = dest
        self._pipeline_name = pipeline_name
        if state_file:
            self.state = StateManager(state_dir / state_file)
        else:
            name = pipeline_name or f"{source.name}_{dest.name}"
            self.state = StateManager(state_dir / f"{name}_state.json")
        self._display = display or Display()
        self._steps = steps
        self._post_steps = post_steps or []
        self._dest_config = dest_config
        self._mode = mode
        self._change_detection = change_detection
        self._mirror_delete = mirror_delete

    def run(self, *, mode: str | None = None, resume: bool = False,
            change_detection: str | None = None, dry_run: bool = False) -> None:
        effective_mode = mode or self._mode
        effective_cd = change_detection or self._change_detection

        logger.info("Pipeline 开始: %s → %s (mode=%s, cd=%s, dry_run=%s)",
                     self.source.name, self.dest.name, effective_mode, effective_cd, dry_run)

        if effective_mode == "full" and resume:
            self._run_full_resume(dry_run)
        elif effective_mode == "full":
            self._run_full(dry_run)
        elif effective_mode == "incremental":
            self._run_incremental(dry_run)
        elif effective_mode == "mirror":
            self._validate_change_detection(effective_cd)
            self._run_mirror(effective_cd, dry_run)
        else:
            raise ValueError(f"未知的运行模式: {effective_mode}")

        self._display.stop()
        self._display.print_summary()
        logger.info("Pipeline 完成: %s → %s", self.source.name, self.dest.name)

    def _validate_change_detection(self, cd: str | None) -> None:
        if cd is None:
            raise ValueError("mirror 模式必须指定 change_detection")
        supported = self.source.supported_change_detection()
        if cd not in supported:
            raise ValueError(
                f"source '{self.source.name}' 不支持变更检测策略 '{cd}'，"
                f"支持的策略: {', '.join(supported) or '(无)'}"
            )

    def _run_full(self, dry_run: bool) -> None:
        metas = self.source.list()
        logger.info("待处理文档: %d 个", len(metas))
        self._display.start(f"Pipeline: {self.source.name} → {self.dest.name}", len(metas))

        if not dry_run:
            pending_items = [(m.id, m.path, m.title, dict(m.extra)) for m in metas]
            self.state.mark_pending(pending_items)

        for meta in metas:
            self._process_document(meta, dry_run=dry_run)

    def _run_full_resume(self, dry_run: bool) -> None:
        pending = self.state.find_pending()
        if not pending:
            logger.info("无待处理文档，resume 完成")
            self._display.start(f"Pipeline: {self.source.name} → {self.dest.name}", 0)
            return

        logger.info("Resume: 待处理文档 %d 个", len(pending))
        self._display.start(f"Pipeline: {self.source.name} → {self.dest.name}", len(pending))

        for doc_id, title, path, fetch_extra in pending:
            meta = BundleMeta(id=doc_id, title=title, path=path, extra=fetch_extra)
            self._process_document(meta, dry_run=dry_run)

    def _run_incremental(self, dry_run: bool) -> None:
        metas = self.source.list()
        new_metas = [m for m in metas if not self.state.is_processed(m.id)]
        logger.info("新增文档: %d / %d 个", len(new_metas), len(metas))
        self._display.start(f"Pipeline: {self.source.name} → {self.dest.name}", len(new_metas))

        for meta in new_metas:
            self._process_document(meta, dry_run=dry_run)

    def _run_mirror(self, change_detection: str, dry_run: bool) -> None:
        metas = self.source.list()
        logger.info("待检查文档: %d 个", len(metas))
        self._display.start(f"Pipeline: {self.source.name} → {self.dest.name}", len(metas))

        for meta in metas:
            if not self.state.is_processed(meta.id):
                self._process_document(meta, change_detection=change_detection, dry_run=dry_run)
                continue

            changed = False
            if change_detection == "mtime":
                mtime = meta.extra.get("mtime")
                if mtime is None:
                    logger.warning("文档缺少 mtime，降级为重新处理: %s", meta.path)
                    changed = True
                elif not self.state.is_mtime_unchanged(meta.id, mtime):
                    changed = True
                else:
                    self._display.result("skip", f"{meta.path} (mtime 无变化)")
            elif change_detection == "hash":
                changed = True

            if changed:
                self._process_document(meta, change_detection=change_detection, dry_run=dry_run)

        if self._mirror_delete:
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

    def _process_document(self, meta: BundleMeta, *,
                         change_detection: str | None = None,
                         dry_run: bool = False) -> None:
        _display_path = meta.path
        self._display.set_current(_display_path)
        try:
            bundle = self.source.fetch(meta)

            bundle.context["id"] = meta.id
            bundle.context["title"] = meta.title
            bundle.context["path"] = meta.path
            bundle.context["filename"] = Path(meta.path).name if meta.path else ""
            bundle.context["_source"] = self.source.name

            source_hash = bundle_hash(bundle)

            if change_detection == "hash" and self.state.is_processed(meta.id):
                if self.state.is_source_unchanged(meta.id, source_hash):
                    self._display.result("skip", f"{_display_path} (hash 无变化)")
                    return

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

                mtime = meta.extra.get("mtime")
                self.state.mark_done(meta.id, bundle_hash_value, meta.path, mtime=mtime, source_hash=source_hash)

                for post_step in self._post_steps:
                    post_step.process(bundle)

        except SkipBundle as e:
            logger.info("跳过文档: %s - %s", meta.path, e)
            self._display.result("skip", f"{meta.path} ({e})")
        except Exception as e:
            logger.error("文档处理失败: %s - %s", meta.path, e)
            self._display.result("error", f"{meta.path}: {e}")
            self._display.add_failure()
        finally:
            self._display.clear_current(_display_path)
