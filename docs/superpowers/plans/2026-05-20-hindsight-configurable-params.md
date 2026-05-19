# Hindsight Destination 可配置参数 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Hindsight destination 的 document_id、context、tags、metadata 支持通过 YAML 配置文件自定义。

**Architecture:** 复用现有的 `dest_config` → `resolve_context_vars` → `update_config` 机制。在 HindsightDestination 中增加 4 个可选属性（`document_id_template`、`context_template`、`extra_tags`、`extra_metadata`），在 `_build_retain_item` 中优先使用配置值，未配置则保持现有行为。

**Tech Stack:** Python 3.11+ / pytest

---

### Task 1: 添加 _config_keys 和新属性到 HindsightDestination.__init__

**Files:**
- Modify: `docupipe/destinations/hindsight.py:13-26`

- [ ] **Step 1: 写失败测试 — _config_keys 存在且包含新字段**

在 `tests/test_docpipe.py` 的 `TestUpdateConfig` 类中添加测试：

```python
def test_hindsight_config_keys(self):
    from docupipe.destinations.hindsight import HindsightDestination
    dest = HindsightDestination()
    assert "document_id_template" in dest._config_keys
    assert "context_template" in dest._config_keys
    assert "extra_tags" in dest._config_keys
    assert "extra_metadata" in dest._config_keys
    assert "context_prefix" in dest._config_keys
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestUpdateConfig::test_hindsight_config_keys -v`
Expected: FAIL — `HindsightDestination` 没有 `_config_keys`

- [ ] **Step 3: 实现 — 在 HindsightDestination 中添加 `_config_keys` 和新属性**

修改 `docupipe/destinations/hindsight.py`，在类声明中添加 `_config_keys`，在 `__init__` 中添加新参数：

```python
@register_destination("hindsight")
class HindsightDestination(DestinationBase):
    _config_keys = {"context_prefix", "document_id_template", "context_template", "extra_tags", "extra_metadata"}

    def __init__(
        self,
        bank_id: str | None = None,
        api_url: str | None = None,
        api_key: str | None = None,
        context_prefix: str | None = None,
        document_id_template: str | None = None,
        context_template: str | None = None,
        extra_tags: list | None = None,
        extra_metadata: dict | None = None,
        **kwargs,
    ):
        self.bank_id = bank_id or os.environ.get("HINDSIGHT_BANK_ID", "")
        self.api_url = api_url or os.environ.get("HINDSIGHT_API_URL", "")
        self.api_key = api_key or os.environ.get("HINDSIGHT_API_KEY", "")
        self._context_prefix = context_prefix or os.environ.get("HINDSIGHT_CONTEXT", "")
        self._document_id_template = document_id_template
        self._context_template = context_template
        self._extra_tags = extra_tags
        self._extra_metadata = extra_metadata
        self._client = None
```

注意 `context_prefix` 原来存在 `self.context_prefix`（公开属性），现在改为 `self._context_prefix`（私有属性），与 `update_config` 的 `self._{key}` 命名一致。

- [ ] **Step 4: 更新引用 `self.context_prefix` 的地方为 `self._context_prefix`**

在 `_build_retain_item` 方法中（第 64 行），将 `self.context_prefix` 改为 `self._context_prefix`：

```python
        if self._context_prefix:
            context_str = self._context_prefix
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestUpdateConfig::test_hindsight_config_keys -v`
Expected: PASS

- [ ] **Step 6: 运行全量测试确认无回归**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add docupipe/destinations/hindsight.py tests/test_docpipe.py
git commit -m "feat: 为 HindsightDestination 添加 _config_keys 和可配置参数属性"
```

---

### Task 2: 实现 document_id_template 支持

**Files:**
- Modify: `docupipe/destinations/hindsight.py:84-86`
- Modify: `tests/test_docpipe.py`

- [ ] **Step 1: 写失败测试 — document_id_template 替换默认格式**

在 `tests/test_docpipe.py` 中新增测试类：

```python
class TestHindsightDocumentIdTemplate:
    def _make_dest(self, template=None):
        from docupipe.destinations.hindsight import HindsightDestination
        kwargs = {"bank_id": "test", "api_url": "http://localhost", "api_key": "k"}
        if template:
            kwargs["document_id_template"] = template
        return HindsightDestination(**kwargs)

    def _make_bundle(self, **extra):
        from docupipe.models import Bundle, FileItem
        ctx = {"id": "doc1", "title": "测试", "path": "space1/folder/doc", "hash": "abc123", "_source": "dingtalk"}
        ctx.update(extra)
        return Bundle(
            files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
            context=ctx,
        )

    def test_default_document_id(self):
        dest = self._make_dest()
        item = dest._build_retain_item(self._make_bundle())
        assert item["document_id"] == "dingtalk:doc1"

    def test_template_document_id(self):
        dest = self._make_dest(template="${context.space_name}/${context.id}")
        # update_config 模拟 pipeline 的 resolve_context_vars → update_config 流程
        from docupipe.config import resolve_context_vars
        config = {"document_id_template": "${context.space_name}/${context.id}"}
        resolved = resolve_context_vars(config, {"space_name": "myspace", "id": "doc1"})
        dest.update_config(resolved)
        item = dest._build_retain_item(self._make_bundle())
        assert item["document_id"] == "myspace/doc1"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestHindsightDocumentIdTemplate -v`
Expected: `test_template_document_id` FAIL — 模板值被 resolve 成具体字符串后通过 `update_config` 设置到 `_document_id_template`，但 `_build_retain_item` 还没使用它

- [ ] **Step 3: 实现 — 在 `_build_retain_item` 中使用 `_document_id_template`**

修改 `docupipe/destinations/hindsight.py` 的 `_build_retain_item` 方法，将 document_id 生成逻辑改为：

```python
        # document_id
        if self._document_id_template:
            document_id = self._document_id_template
        else:
            source_name = bundle_context.get("_source", "local")
            document_id = f"{source_name}:{bundle_context['id']}"
```

注意：`_document_id_template` 在此时已经被 `update_config` 解析为具体值，无需再次调用 `resolve_context_vars`。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestHindsightDocumentIdTemplate -v`
Expected: PASS

- [ ] **Step 5: 运行全量测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add docupipe/destinations/hindsight.py tests/test_docpipe.py
git commit -m "feat: 支持 document_id_template 配置"
```

---

### Task 3: 实现 context_template 支持

**Files:**
- Modify: `docupipe/destinations/hindsight.py:63-73`
- Modify: `tests/test_docpipe.py`

- [ ] **Step 1: 写失败测试 — context_template 替换默认逻辑**

在 `tests/test_docpipe.py` 中新增测试类：

```python
class TestHindsightContextTemplate:
    def _make_dest(self, context_template=None, context_prefix=None):
        from docupipe.destinations.hindsight import HindsightDestination
        kwargs = {"bank_id": "test", "api_url": "http://localhost", "api_key": "k"}
        if context_template:
            kwargs["context_template"] = context_template
        if context_prefix:
            kwargs["context_prefix"] = context_prefix
        return HindsightDestination(**kwargs)

    def _make_bundle(self, **extra):
        from docupipe.models import Bundle, FileItem
        ctx = {"id": "doc1", "title": "测试", "path": "space1/folder/doc", "hash": "abc123", "_source": "dingtalk"}
        ctx.update(extra)
        return Bundle(
            files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
            context=ctx,
        )

    def test_default_context(self):
        dest = self._make_dest()
        item = dest._build_retain_item(self._make_bundle())
        assert "来自" in item["context"]

    def test_context_prefix(self):
        dest = self._make_dest(context_prefix="产品知识库")
        item = dest._build_retain_item(self._make_bundle())
        assert item["context"] == "产品知识库"

    def test_context_template_overrides_prefix(self):
        dest = self._make_dest(context_template="来自${context.space_name}", context_prefix="产品知识库")
        from docupipe.config import resolve_context_vars
        config = {"context_template": "来自${context.space_name}"}
        resolved = resolve_context_vars(config, {"space_name": "myspace"})
        dest.update_config(resolved)
        item = dest._build_retain_item(self._make_bundle())
        assert item["context"] == "来自myspace"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestHindsightContextTemplate -v`
Expected: `test_context_template_overrides_prefix` FAIL

- [ ] **Step 3: 实现 — 在 `_build_retain_item` 中使用 `_context_template`**

修改 `docupipe/destinations/hindsight.py` 的 context 生成逻辑：

```python
        # context
        if self._context_template:
            context_str = self._context_template
        elif self._context_prefix:
            context_str = self._context_prefix
        else:
            folder_display = "/".join(path_parts[1:]) if len(path_parts) > 1 else ""
            if folder_display:
                context_str = f"文档：{bundle_context['title']}，来自 {space_name}/{folder_display}"
            elif space_name:
                context_str = f"文档：{bundle_context['title']}，来自 {space_name}"
            else:
                context_str = f"文档：{bundle_context['title']}"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestHindsightContextTemplate -v`
Expected: PASS

- [ ] **Step 5: 运行全量测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add docupipe/destinations/hindsight.py tests/test_docpipe.py
git commit -m "feat: 支持 context_template 配置"
```

---

### Task 4: 实现 extra_tags 支持

**Files:**
- Modify: `docupipe/destinations/hindsight.py:57-61`
- Modify: `tests/test_docpipe.py`

- [ ] **Step 1: 写失败测试 — extra_tags 追加到自动生成的 tags**

在 `tests/test_docpipe.py` 中新增测试类：

```python
class TestHindsightExtraTags:
    def _make_dest(self, extra_tags=None):
        from docupipe.destinations.hindsight import HindsightDestination
        kwargs = {"bank_id": "test", "api_url": "http://localhost", "api_key": "k"}
        if extra_tags:
            kwargs["extra_tags"] = extra_tags
        return HindsightDestination(**kwargs)

    def _make_bundle(self, **extra):
        from docupipe.models import Bundle, FileItem
        ctx = {"id": "doc1", "title": "测试", "path": "space1/folder/doc", "hash": "abc123", "_source": "dingtalk"}
        ctx.update(extra)
        return Bundle(
            files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
            context=ctx,
        )

    def test_default_tags(self):
        dest = self._make_dest()
        item = dest._build_retain_item(self._make_bundle())
        assert "space:space1" in item["tags"]
        assert "path:folder" in item["tags"]

    def test_extra_tags_appended(self):
        dest = self._make_dest()
        from docupipe.config import resolve_context_vars
        config = {"extra_tags": ["custom:${context.space_name}", "env:prod"]}
        resolved = resolve_context_vars(config, {"space_name": "myspace"})
        dest.update_config(resolved)
        item = dest._build_retain_item(self._make_bundle())
        assert "space:space1" in item["tags"]
        assert "custom:myspace" in item["tags"]
        assert "env:prod" in item["tags"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestHindsightExtraTags -v`
Expected: `test_extra_tags_appended` FAIL

- [ ] **Step 3: 实现 — 在 `_build_retain_item` 中追加 extra_tags**

修改 `docupipe/destinations/hindsight.py` 的 tags 生成逻辑，在现有 tags 生成后追加：

```python
        # 从 path 构建标签
        path_parts = Path(bundle_context["path"]).parts
        space_name = path_parts[0] if path_parts else ""
        path_tags = [f"path:{part}" for part in path_parts[1:]]
        tags = ([f"space:{space_name}"] if space_name else []) + path_tags

        # 追加额外标签
        if self._extra_tags:
            tags.extend(self._extra_tags)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestHindsightExtraTags -v`
Expected: PASS

- [ ] **Step 5: 运行全量测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add docupipe/destinations/hindsight.py tests/test_docpipe.py
git commit -m "feat: 支持 extra_tags 配置"
```

---

### Task 5: 实现 extra_metadata 支持

**Files:**
- Modify: `docupipe/destinations/hindsight.py:94-105`
- Modify: `tests/test_docpipe.py`

- [ ] **Step 1: 写失败测试 — extra_metadata 追加到自动生成的 metadata**

在 `tests/test_docpipe.py` 中新增测试类：

```python
class TestHindsightExtraMetadata:
    def _make_dest(self, extra_metadata=None):
        from docupipe.destinations.hindsight import HindsightDestination
        kwargs = {"bank_id": "test", "api_url": "http://localhost", "api_key": "k"}
        if extra_metadata:
            kwargs["extra_metadata"] = extra_metadata
        return HindsightDestination(**kwargs)

    def _make_bundle(self, **extra):
        from docupipe.models import Bundle, FileItem
        ctx = {"id": "doc1", "title": "测试", "path": "space1/folder/doc", "hash": "abc123", "_source": "dingtalk"}
        ctx.update(extra)
        return Bundle(
            files=[FileItem(name="t.md", content="hello", content_type="text/markdown", role="main")],
            context=ctx,
        )

    def test_default_metadata(self):
        dest = self._make_dest()
        item = dest._build_retain_item(self._make_bundle())
        assert item["metadata"]["title"] == "测试"
        assert "author" not in item["metadata"]

    def test_extra_metadata_merged(self):
        dest = self._make_dest()
        from docupipe.config import resolve_context_vars
        config = {"extra_metadata": {"author": "${context.author:-unknown}", "version": "1.0"}}
        resolved = resolve_context_vars(config, {"author": "张三"})
        dest.update_config(resolved)
        item = dest._build_retain_item(self._make_bundle())
        assert item["metadata"]["title"] == "测试"
        assert item["metadata"]["author"] == "张三"
        assert item["metadata"]["version"] == "1.0"

    def test_extra_metadata_overwrites_existing(self):
        """extra_metadata 的值可以覆盖自动生成的字段"""
        dest = self._make_dest()
        from docupipe.config import resolve_context_vars
        config = {"extra_metadata": {"title": "自定义标题"}}
        resolved = resolve_context_vars(config, {})
        dest.update_config(resolved)
        item = dest._build_retain_item(self._make_bundle())
        assert item["metadata"]["title"] == "自定义标题"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_docpipe.py::TestHindsightExtraMetadata -v`
Expected: `test_extra_metadata_merged` 和 `test_extra_metadata_overwrites_existing` FAIL

- [ ] **Step 3: 实现 — 在 `_build_retain_item` 中合并 extra_metadata**

修改 `docupipe/destinations/hindsight.py` 的 metadata 部分，在 return 语句之前合并 extra_metadata：

将现有的 return 语句改为先构建 item dict，然后合并 extra_metadata：

```python
        item = {
            "content": content,
            "document_id": document_id,
            "timestamp": timestamp,
            "context": context_str,
            "tags": tags,
            "metadata": {
                "id": bundle_context["id"],
                "title": bundle_context["title"],
                "content_type": bundle_context.get("dingtalk_content_type", ""),
                "extension": bundle_context.get("extension", ""),
                "dingtalk_extension": bundle_context.get("dingtalk_extension", ""),
                "space_name": bundle_context.get("space_name", ""),
                "relative_path": bundle_context["path"],
                "full_path": f"{bundle_context.get('space_name', '')}/{bundle_context['path']}" if bundle_context.get("space_name") else bundle_context["path"],
                "content_hash": bundle_context["hash"],
                "update_time": str(update_time) if update_time else "",
            },
        }

        if self._extra_metadata:
            item["metadata"].update(self._extra_metadata)

        return item
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_docpipe.py::TestHindsightExtraMetadata -v`
Expected: PASS

- [ ] **Step 5: 运行全量测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add docupipe/destinations/hindsight.py tests/test_docpipe.py
git commit -m "feat: 支持 extra_metadata 配置"
```

---

### Task 6: 更新配置示例文件

**Files:**
- Modify: `docupipe.example.yaml`

- [ ] **Step 1: 在 docupipe.example.yaml 中添加新配置字段的示例**

在 hindsight destination 配置中添加注释说明新增的可选字段。找到 hindsight destination 配置块，在 `context_prefix` 后添加注释示例：

```yaml
    # 可选高级配置（支持 ${context.xxx} 插值）
    # document_id_template: "${context.space_name}/${context.path}"
    # context_template: "来自${context.space_name}的${context.title}"
    # extra_tags:
    #   - "custom:${context.space_name}"
    # extra_metadata:
    #   author: "${context.author:-unknown}"
```

- [ ] **Step 2: 运行全量测试确认无回归**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 3: 提交**

```bash
git add docupipe.example.yaml
git commit -m "docs: 更新配置示例，添加 hindsight 可配置参数说明"
```
