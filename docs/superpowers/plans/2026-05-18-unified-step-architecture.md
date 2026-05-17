# 统一 Step 架构 + 腾讯文档删除 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一 PipelineStep/PostStep 为一个 Step 基类，新增 finalize_steps 执行位置，实现腾讯文档删除 step。

**Architecture:** 所有 step 共享同一基类和注册表，Pipeline 通过三个配置位置（steps/post_steps/finalize_steps）决定调用时机。TencentDeleteStep 放在 finalize_steps 中使用，确保所有文档处理完毕后才执行删除。

**Tech Stack:** Python 3.11+ / pytest / unittest.mock / FastMCP Client

---

### Task 1: PipelineStep 重命名为 Step

**Files:**
- Modify: `docupipe/steps/base.py`
- Modify: `docupipe/steps/__init__.py`
- Modify: `docupipe/steps/convert.py`
- Modify: `docupipe/steps/image_description.py`
- Modify: `docupipe/steps/s3_upload.py`
- Modify: `docupipe/steps/resolve_attachments.py`
- Modify: `tests/test_docpipe.py`（PipelineStep 引用）

- [ ] **Step 1: 重命名 steps/base.py 中的 PipelineStep → Step**

`docupipe/steps/base.py` 第 8 行，将类名 `PipelineStep` 改为 `Step`：

```python
from __future__ import annotations

from abc import ABC, abstractmethod

from docupipe.models import Bundle


class Step(ABC):
    name: str = ""

    @abstractmethod
    def process(self, bundle: Bundle) -> Bundle:
        """处理文档包，返回处理后的文档包"""

    def update_config(self, config: dict) -> None:
        """用已解析的配置更新组件属性。"""
        for key, value in config.items():
            attr = f"_{key}"
            if hasattr(self, attr):
                setattr(self, attr, value)
```

- [ ] **Step 2: 更新 steps/__init__.py**

`docupipe/steps/__init__.py`，将所有 `PipelineStep` 改为 `Step`：

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docupipe.steps.base import Step

STEPS: dict[str, type[Step]] = {}


def register_step(name: str):
    def decorator(cls: type[Step]):
        STEPS[name] = cls
        cls.name = name
        return cls
    return decorator


def get_step(name: str) -> type[Step]:
    if name not in STEPS:
        raise ValueError(f"未知的 step: {name}，可选: {', '.join(STEPS.keys())}")
    return STEPS[name]


# 自动注册内置 step
import docupipe.steps.convert  # noqa: F401, E402
import docupipe.steps.image_description  # noqa: F401, E402
import docupipe.steps.s3_upload  # noqa: F401, E402
import docupipe.steps.resolve_attachments  # noqa: F401, E402
```

- [ ] **Step 3: 更新 4 个 step 文件的 import**

每个文件中将 `from docupipe.steps.base import PipelineStep` 改为 `from docupipe.steps.base import Step`，将 `class XxxStep(PipelineStep)` 改为 `class XxxStep(Step)`：

- `docupipe/steps/convert.py`：第 12 行 import、第 28 行类定义
- `docupipe/steps/image_description.py`：第 8 行 import、第 14 行类定义
- `docupipe/steps/s3_upload.py`：第 13 行 import、第 19 行类定义
- `docupipe/steps/resolve_attachments.py`：第 9 行 import、第 34 行类定义

- [ ] **Step 4: 更新测试文件**

`tests/test_docpipe.py` 第 539-541 行：

```python
from docupipe.steps.base import Step

class UpperStep(Step):
```

- [ ] **Step 5: 运行测试验证**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add docupipe/steps/base.py docupipe/steps/__init__.py docupipe/steps/convert.py docupipe/steps/image_description.py docupipe/steps/s3_upload.py docupipe/steps/resolve_attachments.py tests/test_docpipe.py
git commit -m "refactor: PipelineStep 重命名为 Step"
```

---

### Task 2: 移除 post_steps/ 模块，统一注册

**Files:**
- Delete: `docupipe/post_steps/base.py`
- Delete: `docupipe/post_steps/__init__.py`
- Delete: `docupipe/post_steps/__pycache__/`（如存在）
- Modify: `docupipe/cli.py`
- Modify: `docupipe/pipeline.py`（post_steps 类型标注）
- Modify: `tests/test_docpipe.py`

- [ ] **Step 1: 删除 post_steps 目录**

```bash
rm -rf docupipe/post_steps/
```

- [ ] **Step 2: 更新 cli.py**

将第 57 行的 `from docupipe.post_steps import get_post_step` 移除。

将第 103-106 行的 post_steps 加载改为使用统一注册表，同时支持配置传参（与 steps 同格式）：

```python
        post_steps = _load_steps(pipe_config.get("post_steps", []), global_config, extension_rules)
```

在 `_run_from_config` 函数顶部添加辅助函数（放在 `for pipe_config in pipelines:` 循环之前）：

```python
    def _load_steps(specs, global_config, extension_rules):
        """从配置加载 step 列表"""
        steps = []
        for spec in specs:
            if isinstance(spec, str):
                name = spec
                kwargs = {}
            else:
                items = list(spec.items())
                name, kwargs = items[0] if items else ("", {})

            global_step_config = global_config.get(name, {})
            if global_step_config:
                kwargs = deep_merge(global_step_config, kwargs)

            if name == "convert":
                kwargs["extension_rules"] = extension_rules

            step_cls = get_step(name)
            steps.append(step_cls(**kwargs))
        return steps
```

然后将第 84-101 行的 steps 加载也改为调用此函数：

```python
        steps = _load_steps(pipe_config.get("steps", []), global_config, extension_rules)
        post_steps = _load_steps(pipe_config.get("post_steps", []), global_config, extension_rules)
```

- [ ] **Step 3: 更新 pipeline.py 的类型标注**

`docupipe/pipeline.py` 第 147 行，将 post_steps 的注释从 `post_steps` 改为更通用的描述（不需要改代码逻辑，只是类型现在是 `Step`）。实际不需要改动代码，因为 `list` 类型是通用的。

- [ ] **Step 4: 更新测试文件**

`tests/test_docpipe.py` 中所有 `from docupipe.post_steps.base import PostStep` 改为 `from docupipe.steps.base import Step`，`PostStep` 改为 `Step`。

涉及位置：
- 第 208 行、第 210 行：`test_post_steps_executed_after_write`
- 第 223 行、第 225 行：`test_post_steps_not_executed_on_skip`
- 第 1339-1357 行：`TestPostStepRegistry` 整个类重写为使用 `Step`：

```python
class TestStepRegistry:
    def test_get_unknown_raises(self):
        from docupipe.steps import get_step
        with pytest.raises(ValueError, match="未知的 step"):
            get_step("nonexistent")

    def test_register_and_get(self):
        from docupipe.steps import STEPS, register_step, get_step
        from docupipe.steps.base import Step

        @register_step("test_step_reg")
        class _TestStep(Step):
            def process(self, bundle):
                return bundle

        assert "test_step_reg" in STEPS
        assert get_step("test_step_reg") is _TestStep
        # 清理
        STEPS.pop("test_step_reg", None)
```

- [ ] **Step 5: 运行测试验证**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add -A docupipe/post_steps/ docupipe/cli.py docupipe/pipeline.py tests/test_docpipe.py
git commit -m "refactor: 移除 post_steps 模块，统一使用 Step 注册表"
```

---

### Task 3: Pipeline 添加 finalize_steps 支持

**Files:**
- Modify: `docupipe/pipeline.py`
- Modify: `tests/test_docpipe.py`

- [ ] **Step 1: 写 finalize_steps 的失败测试**

在 `tests/test_docpipe.py` 中添加测试（在 `test_post_steps_executed_after_write` 之后）：

```python
    def test_finalize_steps_executed_after_all_processed(self, tmp_path):
        """finalize_steps 在所有文档处理完毕后执行"""
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
        # finalize_steps 在所有文档处理完毕后执行，顺序与处理顺序一致
        assert order == [("finalize", "1"), ("finalize", "2")]

    def test_finalize_steps_not_run_on_dry_run(self, tmp_path):
        """dry_run 模式下 finalize_steps 不执行"""
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
        """只有成功写入的文档才会触发 finalize_steps"""
        from docupipe.steps.base import Step
        finalized = []
        class SpyFinalizeStep(Step):
            name = "spy_finalize"
            def process(self, bundle):
                finalized.append(bundle.context["id"])
                return bundle
        bundles = [_make_bundle("1", "A")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        # 让 dest.write 对第二个调用抛异常 — 但这里只有一个 bundle，用 SkipBundle 测试
        # 改用包含两个 bundle，第二个 fetch 抛 SkipBundle 的方式
        source2 = _FakeSourceWithMeta(
            metas=[_make_meta("1", "A"), _make_meta("2", "B")],
            bundles={"1": _make_bundle("1", "A")}
        )
        # 让 source2.fetch 对 "2" 抛 SkipBundle
        original_fetch = source2.fetch
        def patched_fetch(meta):
            if meta.id == "2":
                raise SkipBundle("跳过")
            return original_fetch(meta)
        source2.fetch = patched_fetch

        pipeline = Pipeline(source2, dest, tmp_path, pipeline_name="test",
                            finalize_steps=[SpyFinalizeStep()])
        pipeline.run(mode="full")
        assert finalized == ["1"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestPipelineModes::test_finalize_steps_executed_after_all_processed -v`
Expected: FAIL — `Pipeline.__init__()` 没有 `finalize_steps` 参数

- [ ] **Step 3: 实现 Pipeline 的 finalize_steps 支持**

`docupipe/pipeline.py`：

**3a.** 构造函数添加 `finalize_steps` 参数（第 147 行后加参数，第 164 行后存储）：

```python
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
```

在 `self._post_steps = post_steps or []` 之后添加：

```python
        self._finalize_steps = finalize_steps or []
```

**3b.** 在 `run()` 方法中，`_run_*` 调用之前初始化 bundle 收集列表，调用之后执行 finalize：

```python
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
```

**3c.** 添加 `_run_finalize_steps` 方法（在 `_validate_change_detection` 方法之后）：

```python
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
```

**3d.** 在 `_process_document()` 中收集 bundle（第 327 行，post_steps 之后）：

在 `for post_step in self._post_steps:` 循环之后添加：

```python
                if self._finalize_steps:
                    self._finalized_bundles.append(bundle)
```

- [ ] **Step 4: 运行测试验证**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add docupipe/pipeline.py tests/test_docpipe.py
git commit -m "feat: Pipeline 添加 finalize_steps 支持"
```

---

### Task 4: CLI 支持 finalize_steps 配置

**Files:**
- Modify: `docupipe/cli.py`

- [ ] **Step 1: 在 cli.py 中添加 finalize_steps 加载**

在 `_run_from_config` 函数中，`post_steps = _load_steps(...)` 之后添加：

```python
        finalize_steps = _load_steps(pipe_config.get("finalize_steps", []), global_config, extension_rules)
```

在 `Pipeline(...)` 构造调用中添加 `finalize_steps` 参数：

```python
            pipeline = Pipeline(
                source, dest, ctx.obj["state_dir"],
                pipeline_name=pipe_name,
                display=Display(),
                steps=steps,
                post_steps=post_steps,
                finalize_steps=finalize_steps,
                dest_config=dest_kwargs,
                state_file=pipe_config.get("state_file"),
                mode=effective_mode,
                change_detection=effective_cd,
                mirror_delete=options.get("mirror_delete", True),
            )
```

- [ ] **Step 2: 运行测试验证**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 3: 提交**

```bash
git add docupipe/cli.py
git commit -m "feat: CLI 支持 finalize_steps 配置"
```

---

### Task 5: TencentSource 注入 space_id + _TencentDocClient 添加 delete_node

**Files:**
- Modify: `docupipe/sources/tencent.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_docpipe.py` 末尾添加测试类（或创建新测试文件 `tests/test_tencent_delete.py`）：

```python
class TestTencentDocClient:
    def test_delete_node_calls_mcp(self):
        from unittest.mock import patch, MagicMock
        from docupipe.sources.tencent import _TencentDocClient

        with patch("docupipe.sources.tencent._TencentDocClient._call_tool") as mock_call:
            mock_call.return_value = MagicMock()
            client = _TencentDocClient("fake-token")
            client.delete_node("space_123", "node_456")
            mock_call.assert_called_once_with("delete_space_node", {
                "space_id": "space_123",
                "node_id": "node_456",
                "remove_type": "current",
            })

    def test_delete_node_with_remove_type_all(self):
        from unittest.mock import patch, MagicMock
        from docupipe.sources.tencent import _TencentDocClient

        with patch("docupipe.sources.tencent._TencentDocClient._call_tool") as mock_call:
            mock_call.return_value = MagicMock()
            client = _TencentDocClient("fake-token")
            client.delete_node("space_123", "node_456", remove_type="all")
            mock_call.assert_called_once_with("delete_space_node", {
                "space_id": "space_123",
                "node_id": "node_456",
                "remove_type": "all",
            })


class TestTencentSourceSpaceId:
    def test_fetch_injects_space_id(self):
        from unittest.mock import patch, MagicMock
        from docupipe.sources.tencent import TencentSource
        from docupipe.models import BundleMeta

        with patch("docupipe.sources.tencent._TencentDocClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.get_content.return_value = "# Test"
            MockClient.return_value = mock_instance
            MockClient.resolve_space_name.return_value = "space_123"

            source = TencentSource(space_id="space_123")
            meta = BundleMeta(id="node_1", title="Test", extra={"tencent_doc_type": "doc"})
            bundle = source.fetch(meta)
            assert bundle.context["space_id"] == "space_123"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_tencent_delete.py -v`
Expected: FAIL — `_TencentDocClient` 没有 `delete_node` 方法

- [ ] **Step 3: 实现 delete_node 方法**

在 `docupipe/sources/tencent.py` 的 `_TencentDocClient` 类中（`export_file` 方法之后），添加：

```python
    def delete_node(self, space_id: str, node_id: str, remove_type: str = "current") -> None:
        """删除空间节点"""
        self._call_tool("delete_space_node", {
            "space_id": space_id,
            "node_id": node_id,
            "remove_type": remove_type,
        })
```

- [ ] **Step 4: 实现 space_id 注入**

在 `docupipe/sources/tencent.py` 的 `TencentSource.fetch()` 方法中，`context = dict(meta.extra)` 之后添加：

```python
        context["space_id"] = self._space_id
```

- [ ] **Step 5: 运行测试验证**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add docupipe/sources/tencent.py tests/test_tencent_delete.py
git commit -m "feat: _TencentDocClient 添加 delete_node，TencentSource 注入 space_id"
```

---

### Task 6: 创建 TencentDeleteStep

**Files:**
- Create: `docupipe/steps/tencent_delete.py`
- Modify: `docupipe/steps/__init__.py`
- Modify: `tests/test_tencent_delete.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_tencent_delete.py` 中添加：

```python
from unittest.mock import patch, MagicMock

import pytest

from docupipe.models import Bundle, FileItem


class TestTencentDeleteStep:
    def _make_bundle(self, node_id="node_1", space_id="space_123"):
        return Bundle(
            files=[FileItem(name="test.md", content="hello", content_type="text/markdown", role="main")],
            context={"id": node_id, "space_id": space_id, "path": "test.md"},
        )

    def test_process_deletes_node(self):
        with patch("docupipe.steps.tencent_delete._TencentDocClient") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance

            from docupipe.steps.tencent_delete import TencentDeleteStep
            step = TencentDeleteStep()
            bundle = self._make_bundle()
            result = step.process(bundle)

            mock_instance.delete_node.assert_called_once_with("space_123", "node_1", "current")
            assert result is bundle

    def test_process_with_remove_type_all(self):
        with patch("docupipe.steps.tencent_delete._TencentDocClient") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance

            from docupipe.steps.tencent_delete import TencentDeleteStep
            step = TencentDeleteStep(remove_type="all")
            bundle = self._make_bundle()
            step.process(bundle)

            mock_instance.delete_node.assert_called_once_with("space_123", "node_1", "all")

    def test_process_logs_warning_on_missing_context(self):
        with patch("docupipe.steps.tencent_delete._TencentDocClient") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance

            from docupipe.steps.tencent_delete import TencentDeleteStep
            step = TencentDeleteStep()
            bundle = Bundle(
                files=[FileItem(name="test.md", content="hello", content_type="text/markdown", role="main")],
                context={"id": "node_1"},  # 缺少 space_id
            )
            step.process(bundle)
            mock_instance.delete_node.assert_not_called()

    def test_process_continues_on_delete_failure(self):
        with patch("docupipe.steps.tencent_delete._TencentDocClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.delete_node.side_effect = RuntimeError("API 错误")
            MockClient.return_value = mock_instance

            from docupipe.steps.tencent_delete import TencentDeleteStep
            step = TencentDeleteStep()
            bundle = self._make_bundle()
            # 不应抛异常
            result = step.process(bundle)
            assert result is bundle

    def test_raises_without_token(self):
        with patch.dict("os.environ", {}, clear=True):
            # 移除可能存在的 TENCENT_DOCS_TOKEN
            import os
            os.environ.pop("TENCENT_DOCS_TOKEN", None)
            from docupipe.steps.tencent_delete import TencentDeleteStep
            with pytest.raises(ValueError, match="TENCENT_DOCS_TOKEN"):
                TencentDeleteStep()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_tencent_delete.py -v`
Expected: FAIL — `docupipe.steps.tencent_delete` 模块不存在

- [ ] **Step 3: 创建 TencentDeleteStep**

创建 `docupipe/steps/tencent_delete.py`：

```python
"""腾讯文档删除 step

放在 finalize_steps 中使用，确保所有文档处理完毕后再执行删除。
"""
from __future__ import annotations

import logging
import os

from docupipe.models import Bundle
from docupipe.sources.tencent import _TencentDocClient
from docupipe.steps import register_step
from docupipe.steps.base import Step

logger = logging.getLogger(__name__)


@register_step("tencent_delete")
class TencentDeleteStep(Step):
    def __init__(self, remove_type: str = "current", **kwargs):
        self._remove_type = remove_type
        token = os.environ.get("TENCENT_DOCS_TOKEN", "")
        if not token:
            raise ValueError("环境变量 TENCENT_DOCS_TOKEN 未设置")
        self._client = _TencentDocClient(token)

    def process(self, bundle: Bundle) -> Bundle:
        space_id = bundle.context.get("space_id", "")
        node_id = bundle.context.get("id", "")
        if not space_id or not node_id:
            logger.warning("缺少 space_id 或 id，跳过删除: id=%s, space_id=%s", node_id, space_id)
            return bundle
        try:
            self._client.delete_node(space_id, node_id, self._remove_type)
            logger.info("已删除腾讯文档: %s (%s)", bundle.context.get("path", node_id), node_id)
        except Exception as e:
            logger.warning("删除腾讯文档失败: %s - %s", node_id, e)
        return bundle
```

- [ ] **Step 4: 注册 tencent_delete**

在 `docupipe/steps/__init__.py` 末尾添加 import：

```python
import docupipe.steps.tencent_delete  # noqa: F401, E402
```

- [ ] **Step 5: 运行测试验证**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add docupipe/steps/tencent_delete.py docupipe/steps/__init__.py tests/test_tencent_delete.py
git commit -m "feat: 新增 TencentDeleteStep，从腾讯文档删除已处理文档"
```

---

### Task 7: 端到端验证

**Files:**
- 无新增，运行完整测试

- [ ] **Step 1: 运行完整测试套件**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 2: 验证 YAML 配置格式**

确认以下配置格式可被正确解析（手动检查 cli.py 逻辑）：

```yaml
pipelines:
  - name: tencent-to-hs
    source:
      tencent:
        space_name: "测试空间"
    destination:
      hindsight:
        bank_id: "${HINDSIGHT_BANK_ID}"
    steps:
      - convert
    finalize_steps:
      - tencent_delete:
          remove_type: current
```

- [ ] **Step 3: 最终提交**

如果有任何修正，提交。
