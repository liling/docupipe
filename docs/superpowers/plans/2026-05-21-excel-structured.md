# Excel 结构化提取 Step 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新建 `excel_structured` Step，将 Excel 文件按 Sheet 结构化提取为 Markdown 表格，并改造 Hindsight destination 支持多文件写入。

**Architecture:** 新建 `excel_structured` Step（用 openpyxl），放在 pipeline 的 convert step 之前。对 xlsx 文件做预处理（合并单元格、隐藏行列、空行列）后按 Sheet 输出独立 Markdown 表格 FileItem。同时改造 Hindsight destination 支持 `process_roles` 配置，遍历多个 FileItem 逐一 retain。

**Tech Stack:** Python 3.11+ / openpyxl / pytest

---

## Task 1: 添加 openpyxl 依赖

**Files:**
- Modify: `pyproject.toml:22-34`

- [ ] **Step 1: 在 dependencies 中添加 openpyxl**

在 `pyproject.toml` 的 `dependencies` 列表中添加 `"openpyxl>=3.1.0"`：

```toml
dependencies = [
    "click>=8.1.0",
    "markitdown[all]>=0.1.0",
    "hindsight-client>=0.1.0",
    "rich>=13.0.0",
    "python-dotenv>=1.0.0",
    "pyyaml>=6.0",
    "requests>=2.31.0",
    "openai>=1.0.0",
    "boto3>=1.28.0",
    "fastmcp>=2.0.0",
    "cryptography>=42.0.0",
    "openpyxl>=3.1.0",
]
```

- [ ] **Step 2: 安装依赖**

Run: `pip install -e ".[dev]"`

- [ ] **Step 3: 验证安装**

Run: `python -c "import openpyxl; print(openpyxl.__version__)"`
Expected: 输出 openpyxl 版本号

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: 添加 openpyxl 依赖"
```

---

## Task 2: 创建 excel_structured Step — 测试

**Files:**
- Create: `tests/test_excel_structured.py`

- [ ] **Step 1: 编写测试文件**

```python
from __future__ import annotations

import io

import openpyxl
import pytest

from docupipe.models import Bundle, FileItem
from docupipe.steps.excel_structured import ExcelStructuredStep


def _make_xlsx_bytes(sheets: dict[str, list[list]]) -> bytes:
    """辅助函数：根据 sheets 定义生成 xlsx bytes。

    sheets: {"SheetName": [[row1_col1, row1_col2], [row2_col1, ...]], ...}
    """
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_xlsx_bundle(sheets: dict[str, list[list]]], **extra_ctx) -> Bundle:
    """创建包含 xlsx 文件的 Bundle。"""
    return Bundle(
        files=[FileItem(name="test.xlsx", content=_make_xlsx_bytes(sheets), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", role="main")],
        context={"extension": "xlsx", "id": "doc1", "title": "test.xlsx", "path": "test.xlsx", **extra_ctx},
    )


class TestExcelStructuredPassthrough:
    def test_non_xlsx_extension_returns_unchanged(self):
        bundle = Bundle(
            files=[FileItem(name="doc.pdf", content=b"pdf-data", content_type="application/pdf", role="main")],
            context={"extension": "pdf"},
        )
        step = ExcelStructuredStep()
        result = step.process(bundle)
        assert result is bundle
        assert result.main.content == b"pdf-data"

    def test_no_extension_returns_unchanged(self):
        bundle = Bundle(
            files=[FileItem(name="doc", content=b"data", content_type="", role="main")],
            context={},
        )
        step = ExcelStructuredStep()
        result = step.process(bundle)
        assert result is bundle

    def test_no_main_file_returns_unchanged(self):
        bundle = Bundle(files=[], context={"extension": "xlsx"})
        step = ExcelStructuredStep()
        result = step.process(bundle)
        assert result is bundle


class TestExcelStructuredSingleSheet:
    def test_single_sheet_produces_one_main_file(self):
        bundle = _make_xlsx_bundle({"员工表": [["姓名", "部门"], ["张三", "销售部"]]})
        step = ExcelStructuredStep()
        result = step.process(bundle)

        assert len(result.files) == 1
        main = result.main
        assert main is not None
        assert main.role == "main"
        assert main.content_type == "text/markdown"
        assert main.name == "test_员工表.md"
        assert "张三" in main.content
        assert "销售部" in main.content
        assert "姓名" in main.content
        assert "部门" in main.content

    def test_extension_updated_to_md(self):
        bundle = _make_xlsx_bundle({"Sheet1": [["A", "B"], ["1", "2"]]})
        step = ExcelStructuredStep()
        result = step.process(bundle)
        assert result.context["extension"] == "md"

    def test_markdown_table_format(self):
        bundle = _make_xlsx_bundle({"S": [["姓名", "年龄"], ["张三", "30"]]})
        step = ExcelStructuredStep()
        result = step.process(bundle)
        lines = result.main.content.strip().split("\n")
        assert lines[0] == "## S"
        assert lines[1] == ""
        assert lines[2] == "| 姓名 | 年龄 |"
        assert "|---" in lines[3]
        assert lines[4] == "| 张三 | 30 |"


class TestExcelStructuredMultipleSheets:
    def test_two_sheets_produces_main_and_attachment(self):
        bundle = _make_xlsx_bundle({
            "Sheet1": [["A"], ["1"]],
            "Sheet2": [["B"], ["2"]],
        })
        step = ExcelStructuredStep()
        result = step.process(bundle)

        assert len(result.files) == 2
        assert result.files[0].role == "main"
        assert result.files[1].role == "attachment"
        assert "Sheet1" in result.files[0].name
        assert "Sheet2" in result.files[1].name

    def test_three_sheets_produces_one_main_two_attachments(self):
        bundle = _make_xlsx_bundle({
            "A": [["x"], ["1"]],
            "B": [["y"], ["2"]],
            "C": [["z"], ["3"]],
        })
        step = ExcelStructuredStep()
        result = step.process(bundle)

        assert len(result.files) == 3
        roles = [f.role for f in result.files]
        assert roles == ["main", "attachment", "attachment"]


class TestExcelStructuredMergedCells:
    def test_merged_cells_filled(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Merged"
        ws["A1"] = "合并值"
        ws.merge_cells("A1:B1")
        ws["A2"] = "其他"
        ws["B2"] = "数据"

        buf = io.BytesIO()
        wb.save(buf)
        bundle = Bundle(
            files=[FileItem(name="merged.xlsx", content=buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", role="main")],
            context={"extension": "xlsx", "id": "d1", "title": "merged.xlsx", "path": "merged.xlsx"},
        )

        step = ExcelStructuredStep(fill_merged=True)
        result = step.process(bundle)
        content = result.main.content
        assert "合并值" in content

    def test_merged_cells_not_filled_when_disabled(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Merged"
        ws["A1"] = "合并值"
        ws.merge_cells("A1:B1")

        buf = io.BytesIO()
        wb.save(buf)
        bundle = Bundle(
            files=[FileItem(name="merged.xlsx", content=buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", role="main")],
            context={"extension": "xlsx"},
        )

        step = ExcelStructuredStep(fill_merged=False)
        result = step.process(bundle)
        assert result is bundle  # 不填充合并单元格时，B1 为空会导致表格格式异常，但 step 仍应正常工作


class TestExcelStructuredHiddenRows:
    def test_hidden_rows_skipped(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Hidden"
        ws.append(["姓名", "部门"])
        ws.append(["张三", "销售部"])
        ws.append(["李四", "技术部"])
        ws.row_dimensions[3].hidden = True  # 第 3 行（李四）隐藏
        ws.append(["王五", "市场部"])

        buf = io.BytesIO()
        wb.save(buf)
        bundle = Bundle(
            files=[FileItem(name="hidden.xlsx", content=buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", role="main")],
            context={"extension": "xlsx"},
        )

        step = ExcelStructuredStep(skip_hidden=True)
        result = step.process(bundle)
        content = result.main.content
        assert "张三" in content
        assert "王五" in content
        assert "李四" not in content


class TestExcelStructuredHiddenCols:
    def test_hidden_columns_skipped(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "HiddenCol"
        ws.append(["姓名", "秘密", "部门"])
        ws.column_dimensions["B"].hidden = True
        ws.append(["张三", "机密", "销售部"])

        buf = io.BytesIO()
        wb.save(buf)
        bundle = Bundle(
            files=[FileItem(name="hidden_col.xlsx", content=buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", role="main")],
            context={"extension": "xlsx"},
        )

        step = ExcelStructuredStep(skip_hidden=True)
        result = step.process(bundle)
        content = result.main.content
        assert "姓名" in content
        assert "部门" in content
        assert "秘密" not in content
        assert "机密" not in content


class TestExcelStructuredEmptyRowsCols:
    def test_empty_rows_skipped(self):
        bundle = _make_xlsx_bundle({"S": [["A"], ["1"], [], ["2"]]})
        step = ExcelStructuredStep(skip_empty=True)
        result = step.process(bundle)
        content = result.main.content
        assert "1" in content
        assert "2" in content
        # 空行应被跳过
        lines = [l for l in content.split("\n") if l.strip() and not l.startswith("#") and not l.startswith("|-")]
        # 标题行 + 2个数据行 = 3 行（不含空行）
        data_lines = [l for l in lines if l.startswith("|")]
        assert len(data_lines) == 3  # header + 2 data rows

    def test_empty_rows_kept_when_disabled(self):
        bundle = _make_xlsx_bundle({"S": [["A"], ["1"], [], ["2"]]})
        step = ExcelStructuredStep(skip_empty=False)
        result = step.process(bundle)
        content = result.main.content
        data_lines = [l for l in content.split("\n") if l.strip().startswith("|") and not l.startswith("|-")]
        # header + empty row + 2 data rows
        assert len(data_lines) >= 3
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_excel_structured.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'docupipe.steps.excel_structured'`

---

## Task 3: 创建 excel_structured Step — 实现

**Files:**
- Create: `docupipe/steps/excel_structured.py`
- Modify: `docupipe/steps/__init__.py:26-31`

- [ ] **Step 1: 实现 ExcelStructuredStep**

创建 `docupipe/steps/excel_structured.py`：

```python
from __future__ import annotations

import io
import logging
from pathlib import PurePosixPath

import openpyxl

from docupipe.models import Bundle, FileItem
from docupipe.steps import register_step
from docupipe.steps.base import Step

logger = logging.getLogger(__name__)


@register_step("excel_structured")
class ExcelStructuredStep(Step):
    _config_keys = {"fill_merged", "skip_hidden", "skip_empty"}

    def __init__(
        self,
        fill_merged: bool = True,
        skip_hidden: bool = True,
        skip_empty: bool = True,
        **kwargs,
    ):
        self._fill_merged = fill_merged
        self._skip_hidden = skip_hidden
        self._skip_empty = skip_empty

    def process(self, bundle: Bundle) -> Bundle:
        ext = bundle.context.get("extension", "")
        if ext != "xlsx":
            return bundle

        main = bundle.main
        if not main or not isinstance(main.content, bytes):
            return bundle

        wb = openpyxl.load_workbook(io.BytesIO(main.content), read_only=False, data_only=True)

        if self._fill_merged:
            self._fill_merged_cells(wb)

        stem = PurePosixPath(main.name).stem
        new_files: list[FileItem] = []

        for ws in wb.worksheets:
            md = self._sheet_to_markdown(ws)
            if not md.strip():
                continue

            role = "main" if not new_files else "attachment"
            sheet_name = ws.title
            new_files.append(FileItem(
                name=f"{stem}_{sheet_name}.md",
                content=md,
                content_type="text/markdown",
                role=role,
            ))

        wb.close()

        if not new_files:
            return bundle

        bundle.files = new_files
        bundle.context["extension"] = "md"
        return bundle

    @staticmethod
    def _fill_merged_cells(wb: openpyxl.Workbook) -> None:
        for ws in wb.worksheets:
            for merged_range in list(ws.merged_cells.ranges):
                top_left = ws.cell(row=merged_range.min_row, column=merged_range.min_col).value
                ws.unmerge_cells(str(merged_range))
                for row in range(merged_range.min_row, merged_range.max_row + 1):
                    for col in range(merged_range.min_col, merged_range.max_col + 1):
                        ws.cell(row=row, column=col).value = top_left

    def _sheet_to_markdown(self, ws: openpyxl.worksheet.worksheet.Worksheet) -> str:
        hidden_rows: set[int] = set()
        hidden_cols: set[int] = set()
        if self._skip_hidden:
            hidden_rows = {r for r, dim in ws.row_dimensions.items() if dim.hidden}
            hidden_cols = {c for c, dim in ws.column_dimensions.items() if dim.hidden}

        rows: list[list[str]] = []
        for row_cells in ws.iter_rows():
            row_num = row_cells[0].row
            if self._skip_hidden and row_num in hidden_rows:
                continue

            values = []
            for cell in row_cells:
                if self._skip_hidden and cell.column in hidden_cols:
                    continue
                values.append(str(cell.value) if cell.value is not None else "")

            if self._skip_empty and all(v == "" for v in values):
                continue

            rows.append(values)

        if not rows:
            return ""

        # 统一列数（取最大值）
        max_cols = max(len(r) for r in rows)
        for r in rows:
            while len(r) < max_cols:
                r.append("")

        # 构建 Markdown 表格
        lines = [f"## {ws.title}", ""]
        header = rows[0]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "|".join("---" for _ in header) + "|")
        for row in rows[1:]:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines) + "\n"
```

- [ ] **Step 2: 在 __init__.py 注册 step**

在 `docupipe/steps/__init__.py` 末尾添加 import：

```python
import docupipe.steps.excel_structured  # noqa: F401, E402
```

- [ ] **Step 3: 运行测试验证通过**

Run: `python -m pytest tests/test_excel_structured.py -v`
Expected: 全部 PASS

- [ ] **Step 4: 运行全量测试确认无回归**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add docupipe/steps/excel_structured.py docupipe/steps/__init__.py tests/test_excel_structured.py
git commit -m "feat: 添加 excel_structured step，支持按 Sheet 结构化提取 Excel"
```

---

## Task 4: 改造 Hindsight Destination — 测试

**Files:**
- Modify: `tests/test_hindsight.py`

- [ ] **Step 1: 添加 process_roles 相关测试**

在 `tests/test_hindsight.py` 末尾添加：

```python
class TestHindsightProcessRoles:
    def test_default_process_roles_only_main(self):
        from unittest.mock import MagicMock, call

        dest = _make_dest()
        dest._client = MagicMock()
        bundle = _make_bundle()
        bundle.files.append(FileItem(name="extra.md", content="extra content", content_type="text/markdown", role="attachment"))

        dest._client = MagicMock()
        # 模拟 _get_client
        dest._HindsightDestination__client = dest._client
        orig_get = dest._get_client
        dest._get_client = lambda: dest._client

        dest.write(bundle)
        # 默认只处理 main，调用一次 retain_batch
        assert dest._client.retain_batch.call_count == 1

    def test_process_roles_includes_attachment(self):
        from unittest.mock import MagicMock

        dest = _make_dest()
        dest._process_roles = ["main", "attachment"]

        bundle = _make_bundle()
        bundle.files.append(FileItem(name="test_Sheet2.md", content="sheet2 data", content_type="text/markdown", role="attachment"))

        mock_client = MagicMock()
        dest._client = mock_client

        # 覆盖 _get_client
        dest._get_client = lambda: mock_client

        doc_id = dest.write(bundle)
        assert mock_client.retain_batch.call_count == 2
        assert doc_id is not None

    def test_process_roles_with_sheet_name_in_document_id(self):
        dest = _make_dest(template="${context._source}:${context.id}:${context._sheet_name}")

        bundle = _make_bundle()
        bundle.files.append(FileItem(name="test_Sheet2.md", content="sheet2 data", content_type="text/markdown", role="attachment"))

        # 测试 _build_retain_item 带 sheet_name 参数
        item = dest._build_retain_item(bundle, file_item=bundle.files[1], sheet_name="Sheet2")
        assert item["document_id"] == "dingtalk:doc1:Sheet2"
        assert item["content"] == "sheet2 data"

    def test_build_retain_item_with_file_item_uses_its_content(self):
        dest = _make_dest()
        bundle = _make_bundle()
        extra_file = FileItem(name="test_Sheet2.md", content="sheet2 content", content_type="text/markdown", role="attachment")
        bundle.files.append(extra_file)

        item = dest._build_retain_item(bundle, file_item=extra_file, sheet_name="Sheet2")
        assert item["content"] == "sheet2 content"

    def test_build_retain_item_without_file_item_backward_compatible(self):
        dest = _make_dest()
        bundle = _make_bundle()
        item = dest._build_retain_item(bundle)
        assert item["content"] == "hello"
        assert "_sheet_name" not in item["metadata"]
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_hindsight.py::TestHindsightProcessRoles -v`
Expected: FAIL — `_build_retain_item` 不接受 `file_item` 和 `sheet_name` 参数

---

## Task 5: 改造 Hindsight Destination — 实现

**Files:**
- Modify: `docupipe/destinations/hindsight.py`
- Modify: `docupipe/models.py:7-38`

- [ ] **Step 1: 在 models.py context 字段注册表添加 _sheet_name**

在 `docupipe/models.py` 的注释注册表中，Source 特有字段部分之后添加：

```python
#   _sheet_name           | str  | Excel Sheet 名称         | ExcelStructuredStep 写入 | HindsightDestination 读取
```

- [ ] **Step 2: 修改 HindsightDestination.__init__ 添加 process_roles**

在 `docupipe/destinations/hindsight.py` 中：

修改 `_config_keys`：
```python
_config_keys = {"context_prefix", "document_id_template", "context_template", "extra_tags", "extra_metadata", "process_roles"}
```

修改 `__init__` 签名，添加 `process_roles` 参数：
```python
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
    process_roles: list | None = None,
    **kwargs,
):
    # ... 原有赋值 ...
    self._process_roles = process_roles or ["main"]
```

- [ ] **Step 3: 修改 write() 方法支持多文件**

```python
def write(self, bundle: Bundle) -> str:
    client = self._get_client()

    if len(self._process_roles) == 1 and self._process_roles[0] == "main":
        item = self._build_retain_item(bundle)
        client.retain_batch(self.bank_id, items=[item], retain_async=True)
        return item["document_id"]

    first_id = None
    for role in self._process_roles:
        for file_item in bundle.get_by_role(role):
            sheet_name = PurePosixPath(file_item.name).stem
            item = self._build_retain_item(bundle, file_item=file_item, sheet_name=sheet_name)
            client.retain_batch(self.bank_id, items=[item], retain_async=True)
            if first_id is None:
                first_id = item["document_id"]

    return first_id or ""
```

注意：需要在文件顶部的 import 中添加 `from pathlib import PurePosixPath`。

`sheet_name` 直接使用 FileItem name 的 stem（如 `test_Sheet2.md` → `test_Sheet2`）。对于多 Sheet 场景，每个 Sheet 的 `document_id` 通过 `document_id_template` 中的 `${context._sheet_name}` 区分。`_sheet_name` 的值即为此 stem。

- [ ] **Step 4: 修改 _build_retain_item 支持可选参数**

```python
def _build_retain_item(self, bundle: Bundle, *, file_item: FileItem | None = None, sheet_name: str | None = None) -> dict:
    bundle_context = bundle.context
    # 使用传入的 file_item 或默认的 main
    target_file = file_item or bundle.main
    if not target_file:
        raise ValueError("Bundle must have a main file")

    content = target_file.content if isinstance(target_file.content, str) else target_file.content.decode("utf-8")

    # 如果有 sheet_name，创建 context 副本并注入
    if sheet_name is not None:
        bundle_context = {**bundle_context, "_sheet_name": sheet_name}

    # ... 后续逻辑使用 bundle_context 而非 bundle.context ...
    # （其余代码不变，只需把所有 bundle.context 引用改为 bundle_context）
```

注意：需要将 `_build_retain_item` 内部所有 `bundle.context` 引用替换为局部的 `bundle_context`。当没有 `sheet_name` 时，`bundle_context` 就是 `bundle.context`（同一个引用），行为不变。

完整的修改后 `_build_retain_item`：

```python
def _build_retain_item(self, bundle: Bundle, *, file_item: FileItem | None = None, sheet_name: str | None = None) -> dict:
    bundle_context = dict(bundle.context)
    if sheet_name is not None:
        bundle_context["_sheet_name"] = sheet_name

    target_file = file_item or bundle.main
    if not target_file:
        raise ValueError("Bundle must have a main file")

    content = target_file.content if isinstance(target_file.content, str) else target_file.content.decode("utf-8")

    space_name = bundle_context.get("space_name", "")
    path_parts = Path(bundle_context["path"]).parts
    path_tags = [f"path:{part}" for part in path_parts[1:]] if len(path_parts) > 1 else []
    tags = ([f"space:{space_name}"] if space_name else []) + path_tags

    if self._extra_tags:
        tags.extend(self._extra_tags)

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

    update_time = bundle_context.get("mtime")
    if update_time:
        tz = timezone(timedelta(hours=8))
        dt = datetime.fromtimestamp(update_time / 1000, tz=tz)
        timestamp = dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    else:
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")

    if self._document_id_template:
        document_id = self._document_id_template
    else:
        source_name = bundle_context.get("_source", "local")
        document_id = f"{source_name}:{bundle_context['id']}"
        if sheet_name:
            document_id = f"{document_id}:{sheet_name}"

    item = {
        "content": content,
        "document_id": document_id,
        "timestamp": timestamp,
        "context": context_str,
        "tags": tags,
        "metadata": {
            **{k: str(v) if not isinstance(v, str) else v for k, v in bundle_context.items()},
            "content_type": bundle_context.get("dingtalk_content_type", ""),
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

- [ ] **Step 5: 运行 Hindsight 测试验证通过**

Run: `python -m pytest tests/test_hindsight.py -v`
Expected: 全部 PASS（包括新测试和原有测试）

- [ ] **Step 6: 运行全量测试确认无回归**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
git add docupipe/destinations/hindsight.py docupipe/models.py tests/test_hindsight.py
git commit -m "feat: Hindsight destination 支持 process_roles 多文件写入"
```

---

## Task 6: 端到端集成测试

**Files:**
- Create: `tests/test_excel_structured.py`（追加）

- [ ] **Step 1: 在测试文件中追加集成测试类**

在 `tests/test_excel_structured.py` 末尾追加：

```python
class TestExcelStructuredIntegration:
    def test_full_pipeline_excel_to_hindsight_items(self):
        """模拟完整 pipeline: excel_structured → HindsightDestination._build_retain_item"""
        from docupipe.destinations.hindsight import HindsightDestination

        # 准备 Excel Bundle
        bundle = _make_xlsx_bundle(
            {"员工": [["姓名", "部门"], ["张三", "销售部"]], "项目": [["名称", "状态"], ["Alpha", "进行中"]]},
            _source="local",
        )

        # Step 1: excel_structured 处理
        step = ExcelStructuredStep()
        result = step.process(bundle)

        assert len(result.files) == 2
        assert result.files[0].role == "main"
        assert result.files[1].role == "attachment"

        # Step 2: Hindsight destination 处理多文件
        dest = HindsightDestination(
            bank_id="test",
            api_url="http://localhost",
            api_key="k",
            document_id_template="${context._source}:${context.id}:${context._sheet_name}",
        )
        dest._process_roles = ["main", "attachment"]

        for file_item in result.files:
            sheet_name = PurePosixPath(file_item.name).stem
            item = dest._build_retain_item(result, file_item=file_item, sheet_name=sheet_name)
            assert item["content"]
            assert "local:doc1:" in item["document_id"]
```

需要在文件顶部已有 `from pathlib import PurePosixPath`，如果没有则添加。

- [ ] **Step 2: 运行全量测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_excel_structured.py
git commit -m "test: 添加 excel_structured 端到端集成测试"
```
