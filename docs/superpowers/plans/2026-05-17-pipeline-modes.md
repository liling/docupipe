# Pipeline 运行模式与增量同步 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 pipeline 运行模式，支持 full/incremental/mirror 三种模式、mtime/hash 变更检测、post step 机制。

**Architecture:** 删除现有 `--resume` / `--sync` 参数，统一用 `--mode` 控制。Pipeline 按模式分派不同处理逻辑。Source 声明变更检测能力，启动时校验。Post step 与 step 共享注册机制，在 dest.write + state.mark_done 成功后执行。状态文件按 pipeline name 命名，增加 mtime 字段。

**Tech Stack:** Python 3.11+ / Click / pytest

---

### Task 1: SourceBase 接口变更

**Files:**
- Modify: `docupipe/sources/base.py`
- Modify: `tests/test_docpipe.py` (FakeSource 类)

- [ ] **Step 1: 写失败测试**

在 `tests/test_docpipe.py` 的 `FakeSource` 类后面添加测试：

```python
class TestSourceBaseInterface:
    def test_supported_change_detection_default_empty(self):
        from docupipe.sources.base import SourceBase
        # SourceBase 默认不支持任何变更检测
        assert SourceBase.supported_change_detection is not None

    def test_delete_default_raises(self, tmp_path):
        from docupipe.sources.base import SourceBase
        source = FakeSource([])
        with pytest.raises(NotImplementedError):
            source.delete("some_id")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestSourceBaseInterface -v`
Expected: FAIL

- [ ] **Step 3: 实现 SourceBase 变更**

修改 `docupipe/sources/base.py`：

```python
from __future__ import annotations

from abc import ABC, abstractmethod

from docupipe.models import Bundle, BundleMeta


class SourceBase(ABC):
    name: str = ""

    @abstractmethod
    def list(self) -> list[BundleMeta]:
        """列出所有可获取的文档包"""

    @abstractmethod
    def fetch(self, meta: BundleMeta) -> Bundle:
        """获取单个文档包的完整内容"""

    def supported_change_detection(self) -> list[str]:
        """返回支持的变更检测策略，如 ['mtime', 'hash']"""
        return []

    def delete(self, doc_id: str) -> None:
        """删除指定文档（可选实现）"""
        raise NotImplementedError
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestSourceBaseInterface -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add docupipe/sources/base.py tests/test_docpipe.py
git commit -m "feat: SourceBase 增加 supported_change_detection 和 delete 方法"
```

---

### Task 2: StateManager 支持 mtime 和新命名

**Files:**
- Modify: `docupipe/pipeline.py` (StateManager 类)
- Modify: `tests/test_docpipe.py` (TestStateManager)

- [ ] **Step 1: 写失败测试**

在 `tests/test_docpipe.py` 的 `TestStateManager` 类中添加：

```python
def test_mark_done_with_mtime(self, tmp_path):
    sm = StateManager(tmp_path / "state.json")
    sm.mark_done("a", "h1", "path/a", mtime=1713571200000)
    entry = sm.load()["a"]
    assert entry["status"] == "done"
    assert entry["hash"] == "h1"
    assert entry["path"] == "path/a"
    assert entry["mtime"] == 1713571200000

def test_get_mtime(self, tmp_path):
    sm = StateManager(tmp_path / "state.json")
    sm.mark_done("a", "h1", "path/a", mtime=1713571200000)
    assert sm.get_mtime("a") == 1713571200000

def test_get_mtime_missing(self, tmp_path):
    sm = StateManager(tmp_path / "state.json")
    assert sm.get_mtime("nonexistent") is None

def test_is_mtime_unchanged(self, tmp_path):
    sm = StateManager(tmp_path / "state.json")
    sm.mark_done("a", "h1", "path/a", mtime=100)
    assert sm.is_mtime_unchanged("a", 100)
    assert not sm.is_mtime_unchanged("a", 200)
    assert not sm.is_mtime_unchanged("b", 100)

def test_mark_pending(self, tmp_path):
    sm = StateManager(tmp_path / "state.json")
    sm.mark_pending([("id1", "path/a", "A", {"ext": "md"}), ("id2", "path/b", "B", {})])
    entries = sm.load()
    assert entries["id1"]["status"] == "pending"
    assert entries["id1"]["path"] == "path/a"
    assert entries["id1"]["title"] == "A"
    assert entries["id1"]["fetch_extra"] == {"ext": "md"}
    assert entries["id2"]["status"] == "pending"

def test_find_pending(self, tmp_path):
    sm = StateManager(tmp_path / "state.json")
    sm.mark_pending([("id1", "path/a", "A", {})])
    sm.mark_done("id1", "h1", "path/a")
    sm.mark_pending([("id2", "path/b", "B", {})])
    pending = sm.find_pending()
    assert len(pending) == 1
    assert pending[0][0] == "id2"

def test_find_pending_returns_meta_info(self, tmp_path):
    sm = StateManager(tmp_path / "state.json")
    sm.mark_pending([("id1", "path/a", "标题A", {"ext": "md"})])
    pending = sm.find_pending()
    assert len(pending) == 1
    doc_id, title, path, fetch_extra = pending[0]
    assert doc_id == "id1"
    assert title == "标题A"
    assert path == "path/a"
    assert fetch_extra == {"ext": "md"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestStateManager -v`
Expected: FAIL（`mark_done` 不接受 mtime 参数，`get_mtime`/`is_mtime_unchanged` 不存在）

- [ ] **Step 3: 实现 StateManager 变更**

修改 `docupipe/pipeline.py` 中 StateManager 类：

```python
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
        result = {}
        for k, v in raw.items():
            if isinstance(v, str):
                result[k] = {"hash": v, "path": "", "status": "done"}
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
        self.save(entries)

    def mark_done(self, doc_id: str, content_hash: str, path: str = "", mtime: int | None = None) -> None:
        entries = self.load()
        entry = {"status": "done", "hash": content_hash, "path": path}
        if mtime is not None:
            entry["mtime"] = mtime
        entries[doc_id] = entry
        self.save(entries)

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
        self.save(entries)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestStateManager -v`
Expected: PASS

- [ ] **Step 5: 运行全部测试确认无回归**

Run: `python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 6: 提交**

```bash
git add docupipe/pipeline.py tests/test_docpipe.py
git commit -m "feat: StateManager 支持 mtime 字段和新方法"
```

---

### Task 3: Post step 基础设施

**Files:**
- Create: `docupipe/post_steps/__init__.py`
- Create: `docupipe/post_steps/base.py`

- [ ] **Step 1: 创建 post step 基类**

创建 `docupipe/post_steps/base.py`：

```python
from __future__ import annotations

from abc import ABC, abstractmethod

from docupipe.models import Bundle


class PostStep(ABC):
    name: str = ""

    @abstractmethod
    def process(self, bundle: Bundle) -> Bundle:
        """处理成功后的后置动作，返回 bundle"""
```

- [ ] **Step 2: 创建 post step 注册表**

创建 `docupipe/post_steps/__init__.py`：

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docupipe.post_steps.base import PostStep

POST_STEPS: dict[str, type[PostStep]] = {}


def register_post_step(name: str):
    def decorator(cls: type[PostStep]):
        POST_STEPS[name] = cls
        cls.name = name
        return cls
    return decorator


def get_post_step(name: str) -> type[PostStep]:
    if name not in POST_STEPS:
        raise ValueError(f"未知的 post_step: {name}，可选: {', '.join(POST_STEPS.keys())}")
    return POST_STEPS[name]
```

- [ ] **Step 3: 写测试**

在 `tests/test_docpipe.py` 中添加：

```python
class TestPostStepRegistry:
    def test_get_unknown_raises(self):
        from docupipe.post_steps import get_post_step
        with pytest.raises(ValueError, match="未知的 post_step"):
            get_post_step("nonexistent")

    def test_register_and_get(self):
        from docupipe.post_steps import POST_STEPS, register_post_step, get_post_step
        from docupipe.post_steps.base import PostStep

        @register_post_step("test_post")
        class _TestPost(PostStep):
            def process(self, bundle):
                return bundle

        assert "test_post" in POST_STEPS
        assert get_post_step("test_post") is _TestPost
        # 清理
        POST_STEPS.pop("test_post", None)
```

- [ ] **Step 4: 运行测试**

Run: `python -m pytest tests/test_docpipe.py::TestPostStepRegistry -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add docupipe/post_steps/ tests/test_docpipe.py
git commit -m "feat: 创建 post step 基类和注册表"
```

---

### Task 4: Pipeline 核心重构 — 构造函数和模式分派

**Files:**
- Modify: `docupipe/pipeline.py` (Pipeline 类)

这是最核心的改动。Pipeline 类需要接受新参数，run 方法按模式分派。

- [ ] **Step 1: 写失败测试**

在 `tests/test_docpipe.py` 中添加新测试类：

```python
def _make_meta(id: str, title: str, content: str = "hello", path: str = "",
                mtime: int | None = None, **extra) -> BundleMeta:
    return BundleMeta(
        id=id, title=title, path=path or f"{title}.md",
        hash=content_hash(content),
        extra={"mtime": mtime, **extra} if mtime else extra,
    )


class _FakeSourceWithMeta(SourceBase):
    """支持自定义 list 结果和 mtime 的 FakeSource"""
    name = "fake"

    def __init__(self, metas: list[BundleMeta] | None = None, bundles: dict[str, Bundle] | None = None, **kwargs):
        self._metas = metas or []
        self._bundles = bundles or {}

    def list(self) -> list[BundleMeta]:
        return self._metas

    def fetch(self, meta: BundleMeta) -> Bundle:
        if meta.id in self._bundles:
            return self._bundles[meta.id]
        return _make_bundle(meta.id, meta.title, path=meta.path)

    def supported_change_detection(self) -> list[str]:
        return ["mtime", "hash"]

    def delete(self, doc_id: str) -> None:
        self._metas = [m for m in self._metas if m.id != doc_id]


class TestPipelineModes:
    def test_full_mode_processes_all(self, tmp_path):
        bundles = [_make_bundle("1", "A"), _make_bundle("2", "B")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.run(mode="full")

        assert len(dest.written) == 2
        state = pipeline.state.load()
        assert "1" in state
        assert "2" in state

    def test_full_mode_resume_skips_processed(self, tmp_path):
        bundles = [_make_bundle("1", "A"), _make_bundle("2", "B")]
        source = FakeSource(bundles)
        dest = FakeDestination()

        # 先跑一次 full
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.run(mode="full")
        assert len(dest.written) == 2

        # resume：全部已完成，无需处理
        dest2 = FakeDestination()
        pipeline2 = Pipeline(FakeSource([]), dest2, tmp_path, pipeline_name="test")
        pipeline2.run(mode="full", resume=True)
        assert len(dest2.written) == 0

    def test_incremental_only_processes_new(self, tmp_path):
        metas = [_make_meta("1", "A", "hello"), _make_meta("2", "B", "world")]
        source = _FakeSourceWithMeta(metas)
        dest = FakeDestination()

        # 第一次 incremental：处理全部（状态为空，都是新增）
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.run(mode="incremental")
        assert len(dest.written) == 2

        # 第二次 incremental：新增一个文档
        metas2 = [_make_meta("1", "A", "hello"), _make_meta("2", "B", "world"), _make_meta("3", "C", "new")]
        source2 = _FakeSourceWithMeta(metas2)
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source2, dest2, tmp_path, pipeline_name="test")
        pipeline2.run(mode="incremental")
        assert len(dest2.written) == 1
        assert dest2.written[0].context["title"] == "C"

    def test_mirror_mtime_skips_unchanged(self, tmp_path):
        metas = [_make_meta("1", "A", "hello", mtime=1000)]
        source = _FakeSourceWithMeta(metas)
        dest = FakeDestination()

        # 第一次 mirror：处理全部
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test",
                           change_detection="mtime")
        pipeline.run(mode="mirror")
        assert len(dest.written) == 1

        # 第二次 mirror：mtime 没变，跳过
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source, dest2, tmp_path, pipeline_name="test",
                            change_detection="mtime")
        pipeline2.run(mode="mirror")
        assert len(dest2.written) == 0

    def test_mirror_mtime_reprocesses_changed(self, tmp_path):
        metas1 = [_make_meta("1", "A", "hello", mtime=1000)]
        source1 = _FakeSourceWithMeta(metas1)
        dest = FakeDestination()

        pipeline = Pipeline(source1, dest, tmp_path, pipeline_name="test",
                           change_detection="mtime")
        pipeline.run(mode="mirror")
        assert len(dest.written) == 1

        # mtime 变了
        metas2 = [_make_meta("1", "A", "hello", mtime=2000)]
        source2 = _FakeSourceWithMeta(metas2)
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source2, dest2, tmp_path, pipeline_name="test",
                            change_detection="mtime")
        pipeline2.run(mode="mirror")
        assert len(dest2.written) == 1

    def test_mirror_hash_skips_unchanged(self, tmp_path):
        metas = [_make_meta("1", "A", "hello")]
        source = _FakeSourceWithMeta(metas)
        dest = FakeDestination()

        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test",
                           change_detection="hash")
        pipeline.run(mode="mirror")
        assert len(dest.written) == 1

        # hash 没变（内容相同）
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source, dest2, tmp_path, pipeline_name="test",
                            change_detection="hash")
        pipeline2.run(mode="mirror")
        assert len(dest2.written) == 0

    def test_mirror_removes_deleted_from_dest(self, tmp_path):
        metas1 = [_make_meta("1", "A", "hello"), _make_meta("2", "B", "world")]
        source1 = _FakeSourceWithMeta(metas1)
        dest = FakeDestination()

        pipeline = Pipeline(source1, dest, tmp_path, pipeline_name="test",
                           change_detection="mtime")
        pipeline.run(mode="mirror")
        assert len(dest.written) == 2

        # 源头只剩一个
        metas2 = [_make_meta("1", "A", "hello")]
        source2 = _FakeSourceWithMeta(metas2)
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source2, dest2, tmp_path, pipeline_name="test",
                            change_detection="mtime")
        pipeline2.run(mode="mirror")
        assert dest2.removed == ["2"]

    def test_mirror_delete_disabled(self, tmp_path):
        metas1 = [_make_meta("1", "A"), _make_meta("2", "B")]
        source1 = _FakeSourceWithMeta(metas1)
        dest = FakeDestination()

        pipeline = Pipeline(source1, dest, tmp_path, pipeline_name="test",
                           change_detection="mtime", mirror_delete=False)
        pipeline.run(mode="mirror")

        metas2 = [_make_meta("1", "A")]
        source2 = _FakeSourceWithMeta(metas2)
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source2, dest2, tmp_path, pipeline_name="test",
                            change_detection="mtime", mirror_delete=False)
        pipeline2.run(mode="mirror")
        assert dest2.removed == []

    def test_mirror_unsupported_change_detection_raises(self, tmp_path):
        """source 不支持指定的变更检测策略时报错"""
        source = FakeSource([])  # FakeSource 不声明支持任何策略
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test",
                           change_detection="mtime")
        with pytest.raises(ValueError, match="不支持"):
            pipeline.run(mode="mirror")

    def test_post_steps_executed_after_write(self, tmp_path):
        from docupipe.post_steps.base import PostStep

        executed = []

        class SpyPostStep(PostStep):
            name = "spy"
            def process(self, bundle):
                executed.append(bundle.context["id"])
                return bundle

        bundles = [_make_bundle("1", "A")]
        source = FakeSource(bundles)
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test",
                           post_steps=[SpyPostStep()])
        pipeline.run(mode="full")
        assert executed == ["1"]

    def test_post_steps_not_executed_on_skip(self, tmp_path):
        """mirror 模式跳过的文档不执行 post step"""
        from docupipe.post_steps.base import PostStep

        executed = []

        class SpyPostStep(PostStep):
            name = "spy"
            def process(self, bundle):
                executed.append(bundle.context["id"])
                return bundle

        metas = [_make_meta("1", "A", "hello", mtime=1000)]
        source = _FakeSourceWithMeta(metas)
        dest = FakeDestination()

        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test",
                           change_detection="mtime", post_steps=[SpyPostStep()])
        pipeline.run(mode="mirror")
        assert len(executed) == 1

        # 第二次运行，mtime 没变，跳过
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source, dest2, tmp_path, pipeline_name="test",
                            change_detection="mtime", post_steps=[SpyPostStep()])
        pipeline2.run(mode="mirror")
        assert len(executed) == 1  # 没有新增

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
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test",
                           state_file="custom.json")
        pipeline.run(mode="full")

        assert (tmp_path / "custom.json").exists()

    def test_full_resume_from_interrupted_state(self, tmp_path):
        """模拟中断：状态文件有 pending 条目"""
        bundles = [_make_bundle("1", "A"), _make_bundle("2", "B"), _make_bundle("3", "C")]
        source = FakeSource(bundles)
        dest = FakeDestination()

        # 手动写一个不完整的状态：1 和 3 已完成，2 还是 pending
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.state.mark_done("1", "hash1", "A")
        pipeline.state.mark_pending([("2", "B", "B", {})])
        pipeline.state.mark_done("3", "hash3", "C")

        # resume：只需处理 pending 的 2
        source2 = FakeSource(bundles)
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source2, dest2, tmp_path, pipeline_name="test")
        pipeline2.run(mode="full", resume=True)
        assert len(dest2.written) == 1
        assert dest2.written[0].context["title"] == "B"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestPipelineModes -v`
Expected: FAIL（Pipeline 构造函数和 run 方法签名不匹配）

- [ ] **Step 3: 重写 Pipeline 类**

将 `docupipe/pipeline.py` 中的 Pipeline 类替换为：

```python
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

        # 全部标记为 pending
        if not dry_run:
            pending_items = [(m.id, m.path, m.title, dict(m.extra)) for m in metas]
            self.state.mark_pending(pending_items)

        for meta in metas:
            self._process_document(meta, dry_run=dry_run)

    def _run_full_resume(self, dry_run: bool) -> None:
        """不调 list()，从状态文件找 pending 的文档继续处理"""
        pending = self.state.find_pending()
        if not pending:
            logger.info("无待处理文档，resume 完成")
            self._display.start(f"Pipeline: {self.source.name} → {self.dest.name}", 0)
            return

        logger.info("Resume: 待处理文档 %d 个", len(pending))
        self._display.start(f"Pipeline: {self.source.name} → {self.dest.name}", len(pending))

        for doc_id, title, path, fetch_extra in pending:
            # 从状态文件中的信息重建 BundleMeta
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
                # 新增
                self._process_document(meta, change_detection=change_detection, dry_run=dry_run)
                continue

            # 已存在的文档：检查是否变更
            changed = False
            if change_detection == "mtime":
                mtime = meta.extra.get("mtime")
                if mtime is not None and not self.state.is_mtime_unchanged(meta.id, mtime):
                    changed = True
                elif mtime is not None:
                    self._display.result("skip", f"{meta.path} (mtime 无变化)")
            elif change_detection == "hash":
                changed = True  # hash 策略必须 fetch 才能判断，交给 _process_document 处理

            if changed:
                self._process_document(meta, change_detection=change_detection, dry_run=dry_run)

        # 删除检测
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

            # 设置 Bundle 的通用上下文字段
            bundle.context["id"] = meta.id
            bundle.context["title"] = meta.title
            bundle.context["path"] = meta.path
            bundle.context["filename"] = Path(meta.path).name if meta.path else ""
            bundle.context["_source"] = self.source.name

            # hash 策略：fetch 后比对 hash
            if change_detection == "hash" and self.state.is_processed(meta.id):
                bundle_hash_value = bundle_hash(bundle)
                if self.state.is_unchanged(meta.id, bundle_hash_value):
                    self._display.result("skip", f"{_display_path} (hash 无变化)")
                    return

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

                mtime = meta.extra.get("mtime")
                self.state.mark_done(meta.id, bundle_hash_value, meta.path, mtime=mtime)

                # 执行 post steps
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
```

- [ ] **Step 4: 运行新测试**

Run: `python -m pytest tests/test_docpipe.py::TestPipelineModes -v`
Expected: PASS

- [ ] **Step 5: 更新旧测试以适配新 Pipeline 签名**

旧测试中的 `Pipeline(source, dest, tmp_path)` 需要改为 `Pipeline(source, dest, tmp_path, pipeline_name="test")`。

旧测试中 `pipeline.run(resume=True)` 改为 `pipeline.run(mode="full", resume=True)`。
旧测试中 `pipeline.run(sync=True)` 改为 `pipeline.run(mode="mirror", change_detection="hash")`。

修改 `TestPipeline` 类中的所有测试方法：

```python
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

    def test_run_full_resume_skips_processed(self, tmp_path):
        bundle = _make_bundle("1", "A")
        source = FakeSource([bundle])
        dest = FakeDestination()

        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.run()
        assert len(dest.written) == 1

        # resume：全部已完成，无需处理
        dest2 = FakeDestination()
        pipeline2 = Pipeline(FakeSource([]), dest2, tmp_path, pipeline_name="test")
        pipeline2.run(mode="full", resume=True)
        assert len(dest2.written) == 0

    def test_run_mirror_hash_skips_unchanged(self, tmp_path):
        bundle = _make_bundle("1", "A", content="hello")
        source = FakeSource([bundle])
        dest = FakeDestination()

        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test",
                           change_detection="hash")
        pipeline.run(mode="mirror")
        assert len(dest.written) == 1

        dest2 = FakeDestination()
        pipeline2 = Pipeline(source, dest2, tmp_path, pipeline_name="test",
                            change_detection="hash")
        pipeline2.run(mode="mirror")
        assert len(dest2.written) == 0

    def test_run_mirror_removes_missing(self, tmp_path):
        bundles1 = [_make_bundle("1", "A"), _make_bundle("2", "B")]
        source1 = FakeSource(bundles1)
        dest = FakeDestination()
        pipeline1 = Pipeline(source1, dest, tmp_path, pipeline_name="test",
                            change_detection="hash")
        pipeline1.run(mode="mirror")

        bundles2 = [_make_bundle("1", "A")]
        source2 = FakeSource(bundles2)
        dest2 = FakeDestination()
        pipeline2 = Pipeline(source2, dest2, tmp_path, pipeline_name="test",
                            change_detection="hash")
        pipeline2.run(mode="mirror")

        assert dest2.removed == ["2"]

    def test_run_dry_run(self, tmp_path):
        bundle = _make_bundle("1", "A")
        source = FakeSource([bundle])
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test")
        pipeline.run(dry_run=True)

        assert len(dest.written) == 0
        assert pipeline.state.load() == {}

    def test_dry_run_mirror_no_state_mutation(self, tmp_path):
        bundle = _make_bundle("1", "A")
        source = FakeSource([bundle])
        dest = FakeDestination()
        pipeline = Pipeline(source, dest, tmp_path, pipeline_name="test",
                           change_detection="hash")

        pipeline.run(mode="mirror", dry_run=True)
        assert len(dest.written) == 0
        assert len(dest.removed) == 0
        assert pipeline.state.load() == {}

        pipeline.run(mode="mirror", dry_run=True)
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

        from docupipe.steps.base import PipelineStep

        class UpperStep(PipelineStep):
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
```

注意：旧的 `test_run_resume_skips_processed` 重命名为 `test_run_full_resume_skips_processed`，`test_run_sync_skips_unchanged` 重命名为 `test_run_mirror_hash_skips_unchanged`，`test_run_sync_removes_missing` 重命名为 `test_run_mirror_removes_missing`。

- [ ] **Step 6: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 7: 提交**

```bash
git add docupipe/pipeline.py tests/test_docpipe.py
git commit -m "feat: Pipeline 按模式分派运行逻辑，支持 full/incremental/mirror"
```

---

### Task 5: Source 实现 — 声明变更检测能力和提供 mtime

**Files:**
- Modify: `docupipe/sources/localdrive.py`
- Modify: `docupipe/sources/dingtalk.py`
- Modify: `docupipe/sources/tencent.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_docpipe.py` 中添加：

```python
class TestSourceChangeDetection:
    def test_localdrive_supports_mtime_and_hash(self, tmp_path):
        from docupipe.sources.localdrive import LocalDriveSource
        (tmp_path / "test.md").write_text("hello")
        source = LocalDriveSource(input_dir=str(tmp_path))
        assert sorted(source.supported_change_detection()) == ["hash", "mtime"]

    def test_localdrive_list_provides_mtime(self, tmp_path):
        from docupipe.sources.localdrive import LocalDriveSource
        (tmp_path / "test.md").write_text("hello")
        source = LocalDriveSource(input_dir=str(tmp_path))
        metas = source.list()
        assert len(metas) == 1
        assert metas[0].extra.get("mtime") is not None
        assert isinstance(metas[0].extra["mtime"], int)

    def test_dingtalk_supports_mtime_and_hash(self):
        from docupipe.sources.dingtalk import DingtalkSource
        # 不连接 API，只检查类方法
        assert "mtime" in DingtalkSource.supported_change_detection(DingtalkSource)
        assert "hash" in DingtalkSource.supported_change_detection(DingtalkSource)

    def test_tencent_supports_hash_only(self):
        from docupipe.sources.tencent import TencentSource
        assert sorted(TencentSource.supported_change_detection(TencentSource)) == ["hash"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestSourceChangeDetection -v`
Expected: FAIL

- [ ] **Step 3: 修改 localdrive source**

在 `docupipe/sources/localdrive.py` 中：

1. 在 `LocalDriveSource` 类中添加方法：

```python
def supported_change_detection(self) -> list[str]:
    return ["mtime", "hash"]

def delete(self, doc_id: str) -> None:
    """按 doc_id（content hash）查找并删除文件"""
    metas = self.list()
    for meta in metas:
        if meta.id == doc_id:
            abs_path = meta.extra.get("absolute_path", "")
            if abs_path and Path(abs_path).exists():
                Path(abs_path).unlink()
            return
```

2. 在 `list()` 方法中，构建 `extra` 字典时加入 mtime。找到 `extra={` 的位置，改为：

```python
extra={
    "extension": ext,
    "absolute_path": str(f),
    "size": f.stat().st_size,
    "mtime": int(f.stat().st_mtime * 1000),
},
```

- [ ] **Step 4: 修改 dingtalk source**

在 `docupipe/sources/dingtalk.py` 的 `DingtalkSource` 类中添加方法：

```python
def supported_change_detection(self) -> list[str]:
    return ["mtime", "hash"]
```

`updateTime` 已经在 `list()` 中存入 `extra["dingtalk_update_time"]`，但 spec 要求在 `extra["mtime"]` 中提供统一的毫秒时间戳。修改 `list()` 方法中 `extra={` 部分，增加 `"mtime"` 字段：

```python
extra={
    "dingtalk_content_type": content_type,
    "extension": extension,
    "dingtalk_update_time": node.get("updateTime"),
    "dingtalk_node_type": node_type,
    "space_name": self._space_name,
    "mtime": node.get("updateTime"),
},
```

钉钉的 `updateTime` 本身就是毫秒时间戳，无需转换。

- [ ] **Step 5: 修改 tencent source**

在 `docupipe/sources/tencent.py` 的 `TencentSource` 类中添加方法：

```python
def supported_change_detection(self) -> list[str]:
    return ["hash"]
```

- [ ] **Step 6: 运行测试**

Run: `python -m pytest tests/test_docpipe.py::TestSourceChangeDetection -v`
Expected: PASS

- [ ] **Step 7: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 8: 提交**

```bash
git add docupipe/sources/localdrive.py docupipe/sources/dingtalk.py docupipe/sources/tencent.py tests/test_docpipe.py
git commit -m "feat: 各 source 声明变更检测能力，localdrive/dingtalk 提供 mtime"
```

---

### Task 6: CLI 和配置解析

**Files:**
- Modify: `docupipe/cli.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_docpipe.py` 中添加 CLI 集成测试：

```python
class TestCLIConfig:
    def test_parse_mode_from_config(self, tmp_path):
        import yaml
        config = {
            "pipelines": [{
                "name": "test",
                "mode": "incremental",
                "source": {"fake": {}},
                "destination": {"fake": {}},
            }]
        }
        path = tmp_path / "test.yaml"
        path.write_text(yaml.dump(config), encoding="utf-8")
        # 验证配置能被解析
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert raw["pipelines"][0]["mode"] == "incremental"

    def test_parse_post_steps_from_config(self, tmp_path):
        import yaml
        config = {
            "pipelines": [{
                "name": "test",
                "post_steps": ["some_post_step"],
                "source": {"fake": {}},
                "destination": {"fake": {}},
            }]
        }
        path = tmp_path / "test.yaml"
        path.write_text(yaml.dump(config), encoding="utf-8")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert raw["pipelines"][0]["post_steps"] == ["some_post_step"]

    def test_parse_state_file_from_config(self, tmp_path):
        import yaml
        config = {
            "pipelines": [{
                "name": "test",
                "state_file": "custom_state.json",
                "source": {"fake": {}},
                "destination": {"fake": {}},
            }]
        }
        path = tmp_path / "test.yaml"
        path.write_text(yaml.dump(config), encoding="utf-8")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert raw["pipelines"][0]["state_file"] == "custom_state.json"
```

- [ ] **Step 2: 运行测试**

Run: `python -m pytest tests/test_docpipe.py::TestCLIConfig -v`
Expected: PASS（这些是纯配置解析测试）

- [ ] **Step 3: 重写 CLI run 命令**

修改 `docupipe/cli.py`：

```python
@main.command()
@click.option("--config", "config_path", default="docupipe.yaml", help="配置文件路径")
@click.option("--pipeline", "pipeline_name", default=None, help="配置文件中的 pipeline 名称")
@click.option("--mode", type=click.Choice(["full", "incremental", "mirror"]), default=None,
              help="运行模式（覆盖配置）")
@click.option("--resume", is_flag=True, default=False, help="full 模式下断点续传")
@click.option("--change-detection", type=click.Choice(["mtime", "hash"]), default=None,
              help="mirror 模式的变更检测策略（覆盖配置）")
@click.option("--dry-run", is_flag=True, default=False, help="只打印不执行")
@click.pass_context
def run(ctx, config_path, pipeline_name, mode, resume, change_detection, dry_run):
    """运行文档传输 pipeline"""
    _run_from_config(ctx, config_path, pipeline_name, mode, resume, change_detection, dry_run)
```

- [ ] **Step 4: 重写 _run_from_config 函数**

```python
def _run_from_config(ctx, config_path, pipeline_name, cli_mode, cli_resume, cli_change_detection, dry_run):
    import yaml

    from docupipe.config import deep_merge, execute_variables_script, parse_component_config, resolve_env_vars
    from docupipe.destinations import get_destination
    from docupipe.display import Display
    from docupipe.pipeline import Pipeline
    from docupipe.post_steps import get_post_step
    from docupipe.sources import get_source
    from docupipe.steps import get_step

    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    variables = execute_variables_script(raw)
    config = resolve_env_vars(raw, variables)

    global_config = {k: v for k, v in config.items() if k not in ("pipelines", "variables")}
    converters_config = global_config.pop("converters", global_config.pop("type_rules", {}))
    extension_rules = converters_config.get("extensions", {})

    pipelines = config.get("pipelines", [])

    if pipeline_name:
        pipelines = [p for p in pipelines if p.get("name") == pipeline_name]
        if not pipelines:
            click.echo(f"未找到 pipeline: {pipeline_name}")
            raise SystemExit(1)

    for pipe_config in pipelines:
        source_name, source_kwargs = parse_component_config(pipe_config, global_config, "source")
        source = get_source(source_name)(**source_kwargs)

        dest_name, dest_kwargs = parse_component_config(pipe_config, global_config, "destination")
        dest = get_destination(dest_name)(**dest_kwargs)

        steps = []
        for step_spec in pipe_config.get("steps", []):
            if isinstance(step_spec, str):
                step_name = step_spec
                step_kwargs = {}
            else:
                items = list(step_spec.items())
                step_name, step_kwargs = items[0] if items else ("", {})

            global_step_config = global_config.get(step_name, {})
            if global_step_config:
                step_kwargs = deep_merge(global_step_config, step_kwargs)

            if step_name == "convert":
                step_kwargs["extension_rules"] = extension_rules

            step_cls = get_step(step_name)
            steps.append(step_cls(**step_kwargs))

        post_steps = []
        for ps_name in pipe_config.get("post_steps", []):
            ps_cls = get_post_step(ps_name)
            post_steps.append(ps_cls())

        pipe_name = pipe_config.get("name", "")
        effective_mode = cli_mode or pipe_config.get("mode", "full")
        effective_cd = cli_change_detection or pipe_config.get("change_detection")
        options = pipe_config.get("options", {})

        try:
            pipeline = Pipeline(
                source, dest, ctx.obj["state_dir"],
                pipeline_name=pipe_name,
                display=Display(),
                steps=steps,
                post_steps=post_steps,
                dest_config=dest_kwargs,
                state_file=pipe_config.get("state_file"),
                mode=effective_mode,
                change_detection=effective_cd,
                mirror_delete=options.get("mirror_delete", True),
            )
            pipeline.run(
                resume=cli_resume,
                dry_run=dry_run,
            )
        finally:
            if hasattr(dest, "close"):
                dest.close()
```

- [ ] **Step 5: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 6: 提交**

```bash
git add docupipe/cli.py tests/test_docpipe.py
git commit -m "feat: CLI 重构为 --mode/--resume/--change-detection，解析新配置项"
```

---

### Task 7: 更新配置文件和示例

**Files:**
- Modify: `docupipe.yaml`
- Modify: `examples/dingtalk-wiki-to-hindsight.yaml`
- Modify: `examples/tencent-docs-to-obsidian.yaml`
- Modify: `examples/quick-start.yaml`（如存在）

- [ ] **Step 1: 更新 docupipe.yaml**

移除所有 `options: {resume: true}` 或 `options: {sync: true}`。各 pipeline 不需要指定 mode（默认 full）。如果某个 pipeline 应该用新模式，添加 `mode:` 字段。当前所有 pipeline 保持 `mode: full`（默认值，无需显式写）。

- [ ] **Step 2: 更新示例文件中的注释**

将 `--resume` 相关的注释替换为新模式说明。例如 `examples/dingtalk-wiki-to-hindsight.yaml` 中的：

```
#   docupipe run --config ... --resume   # 断点续传
```

改为：

```
#   docupipe run --config ... --resume           # full 模式断点续传
#   docupipe run --config ... --mode incremental  # 只处理新增
#   docupipe run --config ... --mode mirror --change-detection mtime  # 增量同步
```

- [ ] **Step 3: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 4: 提交**

```bash
git add docupipe.yaml examples/
git commit -m "docs: 更新配置文件和示例，适配新模式"
```

---

### Task 8: 更新 CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: 更新架构文档**

在 `CLAUDE.md` 中更新数据流和命令说明：

将数据流部分更新为新模式描述，将 CLI 命令更新为新参数。将 `--resume` / `--sync` 替换为 `--mode` / `--change-detection`。增加 post_steps 的描述。

- [ ] **Step 2: 提交**

```bash
git add CLAUDE.md
git commit -m "docs: 更新 CLAUDE.md 架构说明"
```
