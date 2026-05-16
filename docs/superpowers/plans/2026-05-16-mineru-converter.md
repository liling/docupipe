# MinerU Converter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `mineru` converter，使用 MinerU 3.x 将 PDF/DOCX/PPTX/XLSX/图片转换为 Markdown。

**Architecture:** 实现 `MineruConverter` 类，继承 `ConverterBase`，通过 `do_parse()` 写入临时目录再读回 Markdown 文件。注册到 converters 注册表后在 YAML 中按扩展名配置。

**Tech Stack:** mineru==3.1.14（`do_parse()` + `read_fn()`），tempfile，pathlib

---

### Task 1: 实现 MineruConverter + 测试

**Files:**
- Create: `docpipe/converters/mineru.py`
- Modify: `docpipe/converters/__init__.py` — 添加 mineru 自动导入
- Modify: `tests/test_docpipe.py` — 添加测试

- [ ] **Step 1: 编写测试 — mineru converter 注册和基本结构**

在 `tests/test_docpipe.py` 的 `TestRegistration` 类中添加：

```python
    def test_mineru_converter_registered(self):
        from docpipe.converters import CONVERTERS
        assert "mineru" in CONVERTERS
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_docpipe.py::TestRegistration::test_mineru_converter_registered -v`
Expected: FAIL — `mineru` not in CONVERTERS

- [ ] **Step 3: 创建 MineruConverter 实现**

创建 `docpipe/converters/mineru.py`：

```python
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from docpipe.converters import register_converter
from docpipe.converters.base import ConverterBase


@register_converter("mineru")
class MineruConverter(ConverterBase):
    name = "mineru"

    def convert(self, file_path: Path) -> str:
        from mineru.cli.common import do_parse, read_fn
        from mineru.utils.enum_class import MakeMode

        file_bytes = read_fn(file_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            do_parse(
                output_dir=tmpdir,
                pdf_file_names=[file_path.stem],
                pdf_bytes_list=[file_bytes],
                p_lang_list=["ch"],
                backend="pipeline",
                parse_method="auto",
                f_dump_md=True,
                f_dump_middle_json=False,
                f_dump_model_output=False,
                f_dump_orig_pdf=False,
                f_dump_content_list=False,
                f_draw_layout_bbox=False,
                f_draw_span_bbox=False,
                f_make_md_mode=MakeMode.MM_MD,
            )

            for root, dirs, files in os.walk(tmpdir):
                for f in files:
                    if f.endswith(".md"):
                        return (Path(root) / f).read_text(encoding="utf-8")

        raise RuntimeError(f"MinerU 未生成 .md 文件: {file_path.name}")
```

- [ ] **Step 4: 注册 mineru converter**

在 `docpipe/converters/__init__.py` 末尾添加（在 `markitdown` 导入之后）：

```python
from docpipe.converters import mineru  # noqa: E402,F401
```

- [ ] **Step 5: 运行测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_docpipe.py::TestRegistration::test_mineru_converter_registered -v`
Expected: PASS

- [ ] **Step 6: 运行全部测试确认无回归**

Run: `.venv/bin/python -m pytest tests/test_docpipe.py -v`
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add docpipe/converters/mineru.py docpipe/converters/__init__.py tests/test_docpipe.py
git commit -m "feat: 添加 MinerU Converter（PDF/DOCX/PPTX/XLSX/图片转 Markdown）"
```

---

### Task 2: 更新 docpipe.yaml 使用 mineru

**Files:**
- Modify: `docpipe.yaml`

- [ ] **Step 1: 更新 converters 配置**

将 `docpipe.yaml` 中的 converters 部分改为：

```yaml
converters:
  extensions:
    ".pdf": mineru
    ".docx": mineru
    ".pptx": mineru
    ".xlsx": mineru
    ".doc": mineru
    ".xls": mineru
    ".ppt": mineru
```

删除不再需要的 markitdown 扩展名映射（`.html`, `.htm`, `.csv`, `.json`, `.xml`, `.txt`, `.md`, `.rtf`, `.odt`, `.ods`）。

- [ ] **Step 2: 验证 YAML 可被正确解析**

Run: `.venv/bin/python -c "import yaml; c=yaml.safe_load(open('docpipe.yaml')); print(c['converters']['extensions'])"`
Expected: 输出包含 `".pdf": mineru` 等

- [ ] **Step 3: 提交**

```bash
git add docpipe.yaml
git commit -m "feat: 配置文件切换为 MinerU converter"
```
