from __future__ import annotations

import logging
from pathlib import Path

from docupipe.config import resolve_context_vars
from docupipe.destinations.base import DestinationBase
from docupipe.display import Display
from docupipe.models import Bundle, BundleMeta, SkipBundle
from docupipe.sources.base import SourceBase
from docupipe.state import StateManager, bundle_hash

logger = logging.getLogger(__name__)


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
        finalize_steps: list | None = None,
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
        self._finalize_steps = finalize_steps or []
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

        self._finalized_bundles: list[Bundle] = []

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

        self._run_finalize_steps(dry_run)

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

    def _run_finalize_steps(self, dry_run: bool) -> None:
        if dry_run or not self._finalized_bundles or not self._finalize_steps:
            return
        logger.info("执行 finalize_steps: %d 个文档", len(self._finalized_bundles))
        for bundle in self._finalized_bundles:
            for step in self._finalize_steps:
                try:
                    step.process(bundle)
                except Exception as e:
                    logger.error("finalize_step 失败: %s - %s", bundle.context.get("path", ""), e)

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

            if change_detection == "mtime":
                mtime = meta.extra.get("mtime")
                if mtime is None:
                    logger.warning("文档缺少 mtime，降级为重新处理: %s", meta.path)
                    self._process_document(meta, change_detection=change_detection, dry_run=dry_run)
                elif not self.state.is_mtime_unchanged(meta.id, mtime):
                    self._process_document(meta, change_detection=change_detection, dry_run=dry_run)
                else:
                    self._display.result("skip", f"{meta.path} (mtime 无变化)")
            elif change_detection == "hash":
                if meta.hash and not self.state.is_unchanged(meta.id, meta.hash):
                    self._process_document(meta, change_detection=change_detection, dry_run=dry_run)
                else:
                    self._display.result("skip", f"{meta.path} (hash 无变化)")

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

                if self._finalize_steps:
                    self._finalized_bundles.append(bundle)

        except SkipBundle as e:
            logger.info("跳过文档: %s - %s", meta.path, e)
            self._display.result("skip", f"{meta.path} ({e})")
        except Exception as e:
            logger.error("文档处理失败: %s - %s", meta.path, e)
            self._display.result("error", f"{meta.path}: {e}")
            self._display.add_failure()
        finally:
            self._display.clear_current(_display_path)
