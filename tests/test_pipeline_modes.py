from __future__ import annotations

import pytest

from docupipe.pipeline import Pipeline
from docupipe.sources.base import SourceBase
from tests.conftest import (
    FakeSource, FakeDestination, FakeSourceWithMeta,
    _make_bundle, _make_meta,
)


class TestPipelineModes:
    def test_full_mode_processes_all(self, tmp_path):
        bundles = [_make_bundle("1", "A"), _make_bundle("2", "B")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.run(mode="full")
        assert len(dest.written) == 2
        state = pipeline.state.load()
        assert state["1"]["status"] == "done"
        assert state["2"]["status"] == "done"

    def test_full_mode_resume_skips_processed(self, tmp_path):
        bundles = [_make_bundle("1", "A"), _make_bundle("2", "B")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.run(mode="full")
        assert len(dest.written) == 2
        dest2 = FakeDestination()
        pipeline2 = Pipeline(FakeSource([]), dest2, tmp_path, pipeline_name="test")
        pipeline2.run(mode="full", resume=True)
        assert len(dest2.written) == 0

    def test_incremental_only_processes_new(self, tmp_path):
        metas = [_make_meta("1", "A", "hello"), _make_meta("2", "B", "world")]
        source = FakeSourceWithMeta(metas)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.run(mode="incremental")
        assert len(dest.written) == 2
        metas2 = [_make_meta("1", "A", "hello"), _make_meta("2", "B", "world"), _make_meta("3", "C", "new")]
        source2 = FakeSourceWithMeta(metas2)
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source2, dest2, tmp_path, pipeline_name="test")
        pipeline2.run(mode="incremental")
        assert len(dest2.written) == 1
        assert dest2.written[0].context["title"] == "C"

    def test_mirror_mtime_skips_unchanged(self, tmp_path):
        metas = [_make_meta("1", "A", "hello", mtime=1000)]
        source = FakeSourceWithMeta(metas)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test", change_detection="mtime")
        pipeline.run(mode="mirror")
        assert len(dest.written) == 1
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source, dest2, tmp_path, pipeline_name="test", change_detection="mtime")
        pipeline2.run(mode="mirror")
        assert len(dest2.written) == 0

    def test_mirror_mtime_reprocesses_changed(self, tmp_path):
        metas1 = [_make_meta("1", "A", "hello", mtime=1000)]
        source1 = FakeSourceWithMeta(metas1)
        dest = FakeDestination()
        pipeline = Pipeline(source1, dest, tmp_path, pipeline_name="test", change_detection="mtime")
        pipeline.run(mode="mirror")
        assert len(dest.written) == 1
        metas2 = [_make_meta("1", "A", "hello", mtime=2000)]
        source2 = FakeSourceWithMeta(metas2)
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source2, dest2, tmp_path, pipeline_name="test", change_detection="mtime")
        pipeline2.run(mode="mirror")
        assert len(dest2.written) == 1

    def test_mirror_hash_skips_unchanged(self, tmp_path):
        metas = [_make_meta("1", "A", "hello")]
        source = FakeSourceWithMeta(metas)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test", change_detection="hash")
        pipeline.run(mode="mirror")
        assert len(dest.written) == 1
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source, dest2, tmp_path, pipeline_name="test", change_detection="hash")
        pipeline2.run(mode="mirror")
        assert len(dest2.written) == 0

    def test_mirror_removes_deleted_from_dest(self, tmp_path):
        metas1 = [_make_meta("1", "A", "hello"), _make_meta("2", "B", "world")]
        source1 = FakeSourceWithMeta(metas1)
        dest = FakeDestination()
        pipeline = Pipeline(source1, dest, tmp_path, pipeline_name="test", change_detection="mtime")
        pipeline.run(mode="mirror")
        assert len(dest.written) == 2
        metas2 = [_make_meta("1", "A", "hello")]
        source2 = FakeSourceWithMeta(metas2)
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source2, dest2, tmp_path, pipeline_name="test", change_detection="mtime")
        pipeline2.run(mode="mirror")
        assert dest2.removed == ["2"]

    def test_mirror_delete_disabled(self, tmp_path):
        metas1 = [_make_meta("1", "A"), _make_meta("2", "B")]
        source1 = FakeSourceWithMeta(metas1)
        dest = FakeDestination()
        pipeline = Pipeline(source1, dest, tmp_path, pipeline_name="test", change_detection="mtime", mirror_delete=False)
        pipeline.run(mode="mirror")
        metas2 = [_make_meta("1", "A")]
        source2 = FakeSourceWithMeta(metas2)
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source2, dest2, tmp_path, pipeline_name="test", change_detection="mtime", mirror_delete=False)
        pipeline2.run(mode="mirror")
        assert dest2.removed == []

    def test_mirror_unsupported_change_detection_raises(self, tmp_path):
        source = FakeSource([])
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test", change_detection="mtime")
        with pytest.raises(ValueError, match="不支持"):
            pipeline.run(mode="mirror")

    def test_post_steps_executed_after_write(self, tmp_path):
        from docupipe.steps.base import Step
        executed = []
        class SpyPostStep(Step):
            name = "spy"
            def process(self, bundle):
                executed.append(bundle.context["id"])
                return bundle
        bundles = [_make_bundle("1", "A")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test", post_steps=[SpyPostStep()])
        pipeline.run(mode="full")
        assert executed == ["1"]

    def test_post_steps_not_executed_on_skip(self, tmp_path):
        from docupipe.steps.base import Step
        executed = []
        class SpyPostStep(Step):
            name = "spy"
            def process(self, bundle):
                executed.append(bundle.context["id"])
                return bundle
        metas = [_make_meta("1", "A", "hello", mtime=1000)]
        source = FakeSourceWithMeta(metas)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test", change_detection="mtime", post_steps=[SpyPostStep()])
        pipeline.run(mode="mirror")
        assert len(executed) == 1
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source, dest2, tmp_path, pipeline_name="test", change_detection="mtime", post_steps=[SpyPostStep()])
        pipeline2.run(mode="mirror")
        assert len(executed) == 1

    def test_finalize_steps_executed_after_all_processed(self, tmp_path):
        from docupipe.steps.base import Step
        order = []
        class SpyFinalizeStep(Step):
            name = "spy_finalize"
            def process(self, bundle):
                order.append(("finalize", bundle.context["id"]))
                return bundle
        bundles = [_make_bundle("1", "A"), _make_bundle("2", "B")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test",
                            finalize_steps=[SpyFinalizeStep()])
        pipeline.run(mode="full")
        assert order == [("finalize", "1"), ("finalize", "2")]

    def test_finalize_steps_not_run_on_dry_run(self, tmp_path):
        from docupipe.steps.base import Step
        order = []
        class SpyFinalizeStep(Step):
            name = "spy_finalize"
            def process(self, bundle):
                order.append(bundle.context["id"])
                return bundle
        bundles = [_make_bundle("1", "A")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test",
                            finalize_steps=[SpyFinalizeStep()])
        pipeline.run(mode="full", dry_run=True)
        assert order == []

    def test_finalize_steps_collects_only_successful(self, tmp_path):
        from docupipe.steps.base import Step
        from docupipe.models import SkipBundle
        finalized = []
        class SpyFinalizeStep(Step):
            name = "spy_finalize"
            def process(self, bundle):
                finalized.append(bundle.context["id"])
                return bundle
        source2 = FakeSourceWithMeta(
            metas=[_make_meta("1", "A"), _make_meta("2", "B")],
            bundles={"1": _make_bundle("1", "A")}
        )
        original_fetch = source2.fetch
        def patched_fetch(meta):
            if meta.id == "2":
                raise SkipBundle("跳过")
            return original_fetch(meta)
        source2.fetch = patched_fetch

        dest = FakeDestination()
        pipeline = Pipeline(source2, dest, tmp_path, pipeline_name="test",
                            finalize_steps=[SpyFinalizeStep()])
        pipeline.run(mode="full")
        assert finalized == ["1"]

    def test_state_file_named_by_pipeline(self, tmp_path):
        bundles = [_make_bundle("1", "A")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="my-pipeline")
        pipeline.run(mode="full")
        assert (tmp_path / "my-pipeline_state.json").exists()

    def test_state_file_custom_name(self, tmp_path):
        bundles = [_make_bundle("1", "A")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test", state_file="custom.json")
        pipeline.run(mode="full")
        assert (tmp_path / "custom.json").exists()

    def test_full_resume_from_interrupted_state(self, tmp_path):
        bundles = [_make_bundle("1", "A"), _make_bundle("2", "B"), _make_bundle("3", "C")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.state.mark_done("1", "hash1", "A")
        pipeline.state.mark_pending([("2", "B", "B", {})])
        pipeline.state.mark_done("3", "hash3", "C")
        source2 = FakeSource(bundles)
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source2, dest2, tmp_path, pipeline_name="test")
        pipeline2.run(mode="full", resume=True)
        assert len(dest2.written) == 1
        assert dest2.written[0].context["title"] == "B"


class TestPipeline:
    def test_run_writes_all(self, tmp_path):
        bundles = [_make_bundle("1", "A"), _make_bundle("2", "B")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.run()

        assert len(dest.written) == 2
        assert dest.written[0].context["title"] == "A"
        assert dest.written[1].context["title"] == "B"

    def test_run_resume_skips_processed(self, tmp_path):
        bundle = _make_bundle("1", "A")
        source = FakeSource([bundle])
        dest = FakeDestination()

        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.run()
        assert len(dest.written) == 1

        dest2 = FakeDestination()
        pipeline2 = Pipeline(source, dest2, tmp_path, pipeline_name="test")
        pipeline2.run(mode="full", resume=True)
        assert len(dest2.written) == 0

    def test_run_sync_skips_unchanged(self, tmp_path):
        metas = [_make_meta("1", "A", "hello")]
        source = FakeSourceWithMeta(metas)
        dest = FakeDestination()

        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.run()
        assert len(dest.written) == 1

        dest2 = FakeDestination()
        pipeline2 = Pipeline(source, dest2, tmp_path, pipeline_name="test", change_detection="hash")
        pipeline2.run(mode="mirror", change_detection="hash")
        assert len(dest2.written) == 0

    def test_run_sync_removes_missing(self, tmp_path):
        metas1 = [_make_meta("1", "A", "hello"), _make_meta("2", "B", "world")]
        source1 = FakeSourceWithMeta(metas1)
        dest = FakeDestination()
        pipeline1 = Pipeline(source1, dest, tmp_path, pipeline_name="test")
        pipeline1.run()

        metas2 = [_make_meta("1", "A", "hello")]
        source2 = FakeSourceWithMeta(metas2)
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source2, dest2, tmp_path, pipeline_name="test", change_detection="hash")
        pipeline2.run(mode="mirror", change_detection="hash")

        assert dest2.removed == ["2"]

    def test_run_dry_run(self, tmp_path):
        bundle = _make_bundle("1", "A")
        source = FakeSource([bundle])
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.run(dry_run=True)

        assert len(dest.written) == 0
        assert pipeline.state.load() == {}

    def test_dry_run_sync_no_state_mutation(self, tmp_path):
        metas = [_make_meta("1", "A", "hello")]
        source = FakeSourceWithMeta(metas)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test", change_detection="hash")

        pipeline.run(mode="mirror", change_detection="hash", dry_run=True)
        assert len(dest.written) == 0
        assert len(dest.removed) == 0
        assert pipeline.state.load() == {}

        pipeline.run(mode="mirror", change_detection="hash", dry_run=True)
        assert len(dest.written) == 0
        assert len(dest.removed) == 0
        assert pipeline.state.load() == {}

    def test_dry_run_resume_idempotent(self, tmp_path):
        bundles = [_make_bundle("1", "A"), _make_bundle("2", "B")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")

        pipeline.run(mode="full", resume=True, dry_run=True)
        assert len(dest.written) == 0
        assert pipeline.state.load() == {}

        pipeline.run(mode="full", resume=True, dry_run=True)
        assert len(dest.written) == 0
        assert pipeline.state.load() == {}

    def test_run_with_steps(self, tmp_path):
        bundles = [_make_bundle("1", "A", content="hello")]
        source = FakeSource(bundles)
        dest = FakeDestination()

        from docupipe.steps.base import Step

        class UpperStep(Step):
            name = "upper"
            def process(self, bundle):
                bundle.main.content = bundle.main.content.upper()
                return bundle

        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test", steps=[UpperStep()])
        pipeline.run()
        assert len(dest.written) == 1
        assert dest.written[0].main.content == "HELLO"

    def test_run_with_empty_steps_processes_all(self, tmp_path):
        bundles = [_make_bundle("1", "A")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test", steps=[])
        pipeline.run()
        assert len(dest.written) == 1
