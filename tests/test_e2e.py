from __future__ import annotations

"""端到端集成测试：真实组件组合的完整流程测试。

测试场景：
1. LocalDrive → ConvertStep → LocalDrive (完整文件转换流程)
2. FakeSource → Steps 链式执行 → FakeDestination
3. mirror 模式完整流程：新增、修改、删除
4. dry_run 模式验证不写入任何内容
5. 配置系统端到端：YAML → runner → Pipeline 执行
6. 错误路径：处理失败文档时继续处理其他文档
"""

import json
import yaml
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from docupipe.models import Bundle, BundleMeta, FileItem, SkipBundle
from docupipe.pipeline import Pipeline
from docupipe.state import StateManager, bundle_hash
from docupipe.steps.base import Step
from docupipe.sources.base import SourceBase
from docupipe.destinations.base import DestinationBase
from tests.conftest import FakeSource, FakeDestination, FakeSourceWithMeta, _make_bundle, _make_meta


class TestLocalDriveToEndToEnd:
    """LocalDrive Source → ConvertStep → LocalDrive Destination 完整流程"""

    def test_text_file_passes_through_without_conversion(self, tmp_path):
        """纯文本文件无转换规则时直接传递"""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "readme.md").write_text("# Hello\n\nWorld", encoding="utf-8")

        from docupipe.sources.localdrive import LocalDriveSource
        from docupipe.destinations.localdrive import LocalDriveDestination

        source = LocalDriveSource(input_dir=str(src_dir))
        dest_dir = tmp_path / "dest"
        dest = LocalDriveDestination(output_dir=str(dest_dir))

        pipeline = Pipeline(source, dest, tmp_path / "state", pipeline_name="e2e-text")
        pipeline.run(mode="full")

        output_file = dest_dir / "readme.md"
        assert output_file.exists()
        assert output_file.read_text(encoding="utf-8") == "# Hello\n\nWorld"

        sidecar = output_file.with_suffix(".md.json")
        assert sidecar.exists()
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        assert meta["title"] == "readme"

    def test_multiple_files_processed(self, tmp_path):
        """多个文件全部处理"""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "a.md").write_text("A", encoding="utf-8")
        (src_dir / "b.md").write_text("B", encoding="utf-8")
        (src_dir / "c.md").write_text("C", encoding="utf-8")

        from docupipe.sources.localdrive import LocalDriveSource
        from docupipe.destinations.localdrive import LocalDriveDestination

        source = LocalDriveSource(input_dir=str(src_dir))
        dest_dir = tmp_path / "dest"
        dest = LocalDriveDestination(output_dir=str(dest_dir))

        pipeline = Pipeline(source, dest, tmp_path / "state", pipeline_name="e2e-multi")
        pipeline.run(mode="full")

        assert (dest_dir / "a.md").exists()
        assert (dest_dir / "b.md").exists()
        assert (dest_dir / "c.md").exists()


class TestStepChaining:
    """Steps 链式执行测试"""

    def test_multiple_steps_chain_execution(self, tmp_path):
        """多个 Step 按顺序链式执行"""
        class AppendStep(Step):
            name = "append"
            def __init__(self, suffix: str):
                self._suffix = suffix
            def process(self, bundle):
                bundle.main.content += self._suffix
                return bundle

        bundles = [_make_bundle("1", "doc", content="hello")]
        source = FakeSource(bundles)
        dest = FakeDestination()

        pipeline = Pipeline(
            source, dest, tmp_path, pipeline_name="chain",
            steps=[AppendStep("→1"), AppendStep("→2"), AppendStep("→3")],
        )
        pipeline.run(mode="full")

        assert len(dest.written) == 1
        assert dest.written[0].main.content == "hello→1→2→3"

    def test_step_can_modify_context(self, tmp_path):
        """Step 可以修改 Bundle context"""
        class ContextStep(Step):
            name = "context_mod"
            def process(self, bundle):
                bundle.context["processed"] = "yes"
                bundle.context["custom_field"] = "custom_value"
                return bundle

        bundles = [_make_bundle("1", "doc")]
        source = FakeSource(bundles)
        dest = FakeDestination()

        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="ctx", steps=[ContextStep()])
        pipeline.run(mode="full")

        assert dest.written[0].context["processed"] == "yes"
        assert dest.written[0].context["custom_field"] == "custom_value"

    def test_step_can_add_attachments(self, tmp_path):
        """Step 可以向 Bundle 添加附件"""
        class AttachmentStep(Step):
            name = "add_attachment"
            def process(self, bundle):
                bundle.add(FileItem(
                    name="generated.txt",
                    content="generated content",
                    content_type="text/plain",
                    role="attachment",
                ))
                return bundle

        bundles = [_make_bundle("1", "doc", content="main")]
        source = FakeSource(bundles)
        dest = FakeDestination()

        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="attach", steps=[AttachmentStep()])
        pipeline.run(mode="full")

        assert len(dest.written[0].files) == 2
        attachment = [f for f in dest.written[0].files if f.role == "attachment"][0]
        assert attachment.name == "generated.txt"


class TestMirrorModeFull:
    """mirror 模式完整流程：新增、修改、删除"""

    def test_full_mirror_lifecycle(self, tmp_path):
        """完整的 mirror 生命周期：首次同步 → 新增 → 修改 → 删除"""
        # 使用 FakeSource + FakeDestination 测试 mirror 逻辑
        # (LocalDriveDestination.remove 未实现，无法测试删除)
        source = FakeSourceWithMeta(
            metas=[_make_meta("a", "A", "A v1"), _make_meta("b", "B", "B v1")],
            bundles={
                "a": _make_bundle("a", "A", content="A v1"),
                "b": _make_bundle("b", "B", content="B v1"),
            }
        )
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="mirror", change_detection="hash")
        pipeline.run(mode="mirror")

        assert len(dest.written) == 2
        written_ids = {b.context["id"] for b in dest.written}
        assert written_ids == {"a", "b"}

        # 修改 a，删除 b，新增 c
        source2 = FakeSourceWithMeta(
            metas=[_make_meta("a", "A", "A v2"), _make_meta("c", "C", "C v1")],
            bundles={
                "a": _make_bundle("a", "A", content="A v2"),
                "c": _make_bundle("c", "C", content="C v1"),
            }
        )
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source2, dest2, tmp_path, pipeline_name="mirror", change_detection="hash")
        pipeline2.run(mode="mirror")

        # a 被重新处理（内容变化）
        assert len(dest2.written) == 2
        written_ids2 = {b.context["id"] for b in dest2.written}
        assert written_ids2 == {"a", "c"}
        # b 被从目标中删除
        assert dest2.removed == ["b"]
        # a 的内容已更新
        a_bundle = [b for b in dest2.written if b.context["id"] == "a"][0]
        assert a_bundle.main.content == "A v2"


class TestDryRunMode:
    """dry_run 模式验证不写入任何内容"""

    def test_dry_run_no_writes(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "doc.md").write_text("content", encoding="utf-8")

        from docupipe.sources.localdrive import LocalDriveSource
        from docupipe.destinations.localdrive import LocalDriveDestination

        source = LocalDriveSource(input_dir=str(src_dir))
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        dest = LocalDriveDestination(output_dir=str(dest_dir))

        pipeline = Pipeline(source, dest, tmp_path / "state", pipeline_name="dryrun")
        pipeline.run(mode="full", dry_run=True)

        # 目标目录应该为空
        assert len(list(dest_dir.iterdir())) == 0
        # 状态文件不应该存在
        assert not (tmp_path / "state" / "dryrun_state.json").exists()

    def test_dry_run_with_steps_no_side_effects(self, tmp_path):
        """dry_run 模式下 steps 仍然执行（用于预览），但不写入"""
        executed = []
        class SpyStep(Step):
            name = "spy"
            def process(self, bundle):
                executed.append(bundle.context["id"])
                bundle.main.content = "MODIFIED"
                return bundle

        bundles = [_make_bundle("1", "doc", content="original")]
        source = FakeSource(bundles)
        dest = FakeDestination()

        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="dryrun-step", steps=[SpyStep()])
        pipeline.run(mode="full", dry_run=True)

        # Step 被执行
        assert executed == ["1"]
        # 但没有写入
        assert len(dest.written) == 0


class TestRunnerEndToEnd:
    """配置系统端到端：YAML → runner → Pipeline 执行"""

    def test_runner_executes_pipeline_from_yaml(self, tmp_path):
        from docupipe.runner import run_pipeline_from_config

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "doc.md").write_text("hello", encoding="utf-8")

        dest_dir = tmp_path / "dest"

        config = {
            "localdrive": {"output_dir": str(dest_dir)},
            "pipelines": [{
                "name": "e2e-runner",
                "mode": "full",
                "source": {"localdrive": {"input_dir": str(src_dir)}},
                "destination": {"localdrive": {}},
                "steps": [],
            }]
        }

        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump(config), encoding="utf-8")

        run_pipeline_from_config(
            config_path=str(config_path),
            state_dir=tmp_path / "state",
        )

        assert (dest_dir / "doc.md").exists()
        assert (dest_dir / "doc.md").read_text(encoding="utf-8") == "hello"

    def test_runner_with_env_interpolation(self, tmp_path, monkeypatch):
        """YAML 配置中的环境变量插值"""
        from docupipe.runner import run_pipeline_from_config

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "doc.md").write_text("hello", encoding="utf-8")

        dest_dir = tmp_path / "dest"
        monkeypatch.setenv("TEST_OUTPUT_DIR", str(dest_dir))

        config_text = f"""
localdrive:
  output_dir: ${{TEST_OUTPUT_DIR}}
pipelines:
  - name: env-test
    mode: full
    source:
      localdrive:
        input_dir: {src_dir}
    destination:
      localdrive: {{}}
    steps: []
"""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(config_text, encoding="utf-8")

        run_pipeline_from_config(
            config_path=str(config_path),
            state_dir=tmp_path / "state",
        )

        assert (dest_dir / "doc.md").exists()


class TestErrorHandling:
    """错误路径测试"""

    def test_fetch_failure_continues_processing(self, tmp_path):
        """一个文档 fetch 失败时，继续处理其他文档"""
        source = FakeSourceWithMeta(
            metas=[_make_meta("1", "A"), _make_meta("2", "B"), _make_meta("3", "C")],
            bundles={"1": _make_bundle("1", "A"), "3": _make_bundle("3", "C")}
        )
        original_fetch = source.fetch
        def patched_fetch(meta):
            if meta.id == "2":
                raise RuntimeError("fetch failed for doc 2")
            return original_fetch(meta)
        source.fetch = patched_fetch

        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="error-fetch")
        pipeline.run(mode="full")

        # 文档 1 和 3 被处理，文档 2 失败
        assert len(dest.written) == 2
        written_ids = {b.context["id"] for b in dest.written}
        assert written_ids == {"1", "3"}

    def test_step_failure_continues_processing(self, tmp_path):
        """一个 Step 抛出异常时，Pipeline 继续处理其他文档"""
        class FailingStep(Step):
            name = "fail"
            def process(self, bundle):
                if bundle.context["id"] == "2":
                    raise RuntimeError("step failed for doc 2")
                bundle.main.content += " [processed]"
                return bundle

        bundles = [
            _make_bundle("1", "A", content="a"),
            _make_bundle("2", "B", content="b"),
            _make_bundle("3", "C", content="c"),
        ]
        source = FakeSource(bundles)
        dest = FakeDestination()

        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="error-step", steps=[FailingStep()])
        pipeline.run(mode="full")

        # 文档 1 和 3 被处理，文档 2 失败
        assert len(dest.written) == 2
        written_ids = {b.context["id"] for b in dest.written}
        assert written_ids == {"1", "3"}

        # 被处理的文档内容被 step 修改
        for b in dest.written:
            assert "[processed]" in b.main.content

    def test_skip_bundle_does_not_count_as_written(self, tmp_path):
        """SkipBundle 异常不应计入写入"""
        source = FakeSourceWithMeta(
            metas=[_make_meta("1", "A"), _make_meta("2", "B")],
            bundles={"1": _make_bundle("1", "A")}
        )
        original_fetch = source.fetch
        def patched_fetch(meta):
            if meta.id == "2":
                raise SkipBundle("unsupported type")
            return original_fetch(meta)
        source.fetch = patched_fetch

        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="skip")
        pipeline.run(mode="full")

        assert len(dest.written) == 1
        assert dest.written[0].context["id"] == "1"

    def test_state_corruption_recovery(self, tmp_path):
        """状态文件损坏时，Pipeline 能恢复（重新处理）"""
        state_file = tmp_path / "corrupt_state.json"
        state_file.write_text("not valid json{{{", encoding="utf-8")

        sm = StateManager(state_file)
        # 损坏的状态应该被重置为空
        assert sm.load() == {}

        # 继续正常运行
        sm.mark_done("1", "hash1", "doc1")
        assert sm.is_processed("1")


class TestPostStepsAndFinalizeSteps:
    """post_steps 和 finalize_steps 集成测试"""

    def test_post_steps_run_after_each_successful_write(self, tmp_path):
        """post_steps 在每次成功写入后执行"""
        executed = []
        class PostStep(Step):
            name = "post"
            def process(self, bundle):
                executed.append(("post", bundle.context["id"]))
                return bundle

        bundles = [_make_bundle("1", "A"), _make_bundle("2", "B")]
        source = FakeSource(bundles)
        dest = FakeDestination()

        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="post", post_steps=[PostStep()])
        pipeline.run(mode="full")

        assert executed == [("post", "1"), ("post", "2")]

    def test_finalize_steps_run_once_after_all_processed(self, tmp_path):
        """finalize_steps 在所有文档处理完后执行一次"""
        all_bundles = []
        class FinalizeStep(Step):
            name = "finalize"
            def process(self, bundle):
                all_bundles.append(bundle.context["id"])
                return bundle

        bundles = [_make_bundle("1", "A"), _make_bundle("2", "B"), _make_bundle("3", "C")]
        source = FakeSource(bundles)
        dest = FakeDestination()

        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="finalize", finalize_steps=[FinalizeStep()])
        pipeline.run(mode="full")

        assert all_bundles == ["1", "2", "3"]

    def test_post_steps_not_run_on_skip(self, tmp_path):
        """跳过的文档不执行 post_steps"""
        executed = []
        class PostStep(Step):
            name = "post"
            def process(self, bundle):
                executed.append(bundle.context["id"])
                return bundle

        source = FakeSourceWithMeta(
            metas=[_make_meta("1", "A", mtime=1000), _make_meta("2", "B", mtime=2000)],
            bundles={"1": _make_bundle("1", "A"), "2": _make_bundle("2", "B")}
        )
        # 首次运行，处理两个文档
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="post-skip", change_detection="mtime", post_steps=[PostStep()])
        pipeline.run(mode="mirror")
        assert executed == ["1", "2"]

        # 再次运行，mtime 无变化，都应跳过
        executed.clear()
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source, dest2, tmp_path, pipeline_name="post-skip", change_detection="mtime", post_steps=[PostStep()])
        pipeline2.run(mode="mirror")
        assert executed == []
