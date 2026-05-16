from __future__ import annotations

import os
import tempfile
from pathlib import Path

from docupipe.converters import register_converter
from docupipe.converters.base import ConverterBase


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
