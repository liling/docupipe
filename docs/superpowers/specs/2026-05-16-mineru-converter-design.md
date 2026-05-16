# MinerU Converter 设计

## 概述

新增 `mineru` converter，使用 MinerU 3.x 将 PDF、DOCX、PPTX、XLSX、图片转换为 Markdown，保留图片引用和表格。

## 配置

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

## 接口实现

### `MineruConverter.convert(file_path: Path) -> str`

MinerU 3.x 的 `do_parse()` 将结果写入磁盘（不返回字符串），因此需要写入临时目录再读回：

1. 读取文件为 bytes（使用 `mineru.cli.common.read_fn()`）
2. 创建临时目录作为 output_dir
3. 调用 `do_parse(output_dir, pdf_file_names, pdf_bytes_list, p_lang_list, backend="pipeline", parse_method="auto", f_dump_md=True, ...)` 写入 .md 文件
4. 关闭不必要的输出（`f_dump_middle_json=False`, `f_dump_model_output=False`, `f_dump_orig_pdf=False`, `f_dump_content_list=False`, `f_draw_layout_bbox=False`, `f_draw_span_bbox=False`）
5. 在 output_dir 中查找生成的 .md 文件，读取并返回
6. 临时目录自动清理

固定参数：`backend="pipeline"`，`parse_method="auto"`，`f_make_md_mode=MakeMode.MM_MD`。

## 文件

- 创建：`docpipe/converters/mineru.py`
- 修改：`docpipe/converters/__init__.py` — 添加自动导入
- 修改：`tests/test_docpipe.py` — 添加单元测试

## 不包含

- 可配置的 parse_method（固定 auto）
- 自定义模型路径配置
- 图片单独上传或 base64 编码
- CLI/FastAPI 方式调用（直接用 `do_parse()` 函数）
- markitdown 保留（作为备选 converter 仍可用，YAML 按需配置）
