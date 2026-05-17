from __future__ import annotations

import json
from pathlib import Path

from docupipe.destinations import register_destination
from docupipe.destinations.base import DestinationBase
from docupipe.models import Bundle


@register_destination("localdrive")
class LocalDriveDestination(DestinationBase):
    def __init__(self, output_dir: str, replace_extension: bool = False, save_sidecar: bool = True, **kwargs):
        self._output_dir = Path(output_dir)
        self._replace_extension = replace_extension
        self._save_sidecar = save_sidecar

    def write(self, bundle: Bundle) -> str:
        """写入Bundle到本地磁盘，包括主文件和所有附件"""
        main_file = bundle.main
        if not main_file:
            raise ValueError("Bundle must have a main file")

        # 解析主文件路径
        main_path = self._resolve_path(bundle)

        # 文件已存在且 hash 相同 → 跳过主文件
        if main_path.exists():
            sidecar = Path(str(main_path) + ".json")
            if sidecar.exists():
                stored = json.loads(sidecar.read_text(encoding="utf-8"))
                if stored.get("content_hash") == bundle.context.get("hash"):
                    pass  # 跳过主文件写入，但可能需要检查附件
                else:
                    self._write_main_file(main_path, main_file)
                    if self._save_sidecar:
                        self._write_sidecar(main_path, bundle)
        else:
            main_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_main_file(main_path, main_file)
            if self._save_sidecar:
                self._write_sidecar(main_path, bundle)

        # 写入所有非主文件（图片、附件等）
        main_dir = main_path.parent
        for file_item in bundle.files:
            if file_item.role != "main":
                # 文件名可能包含路径前缀，如 "images/image_1.png"
                file_path = main_dir / file_item.name
                file_path.parent.mkdir(parents=True, exist_ok=True)
                self._write_file(file_path, file_item)

        return str(main_path)

    def _write_main_file(self, file_path: Path, main_file) -> None:
        """写入主文件内容"""
        content = main_file.content
        self._write_file(file_path, main_file)

    def _write_file(self, file_path: Path, file_item) -> None:
        """写入任意文件内容"""
        content = file_item.content
        if isinstance(content, bytes):
            file_path.write_bytes(content)
        else:
            file_path.write_text(content, encoding="utf-8")

    def remove(self, bundle_id: str) -> None:
        raise NotImplementedError("localdrive remove 需要路径信息")

    def remove_by_path(self, file_path: str) -> None:
        """按路径删除文件及对应的 sidecar"""
        p = Path(file_path)
        if p.exists():
            p.unlink()
        sidecar = Path(file_path + ".json")
        if sidecar.exists():
            sidecar.unlink()

    def _resolve_path(self, bundle: Bundle) -> Path:
        """从 Bundle context 解析输出路径"""
        context = bundle.context
        space_name = context.get("space_name", "")
        rel_path = context["path"]

        # 追加或替换扩展名
        main_file = bundle.main
        if main_file:
            ext = self._content_type_to_ext(main_file.content_type)
        else:
            ext = ""
        if ext and not rel_path.endswith(ext):
            if self._replace_extension:
                stem = Path(rel_path).stem
                parent = str(Path(rel_path).parent)
                rel_path = f"{parent}/{stem}{ext}" if parent != "." else f"{stem}{ext}"
            else:
                rel_path = rel_path + ext

        if space_name:
            return self._output_dir / space_name / rel_path
        return self._output_dir / rel_path

    def _write_sidecar(self, file_path: Path, bundle: Bundle) -> None:
        """写入元数据 sidecar 文件"""
        context = bundle.context
        space_name = context.get("space_name", "")
        data = {
            "id": context["id"],
            "title": context["title"],
            "contentType": context.get("contentType", ""),
            "extension": context.get("extension", ""),
            "space_name": space_name,
            "relative_path": context["path"],
            "full_path": f"{space_name}/{context['path']}" if space_name else context["path"],
            "content_hash": context.get("hash", ""),
        }
        sidecar = Path(str(file_path) + ".json")
        sidecar.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _content_type_to_ext(content_type: str) -> str:
        """将 content_type 转换为文件扩展名"""
        mapping = {
            "markdown": ".md",
            "text/markdown": ".md",
            "text": ".txt",
            "text/plain": ".txt",
            "html": ".html",
            "text/html": ".html",
        }
        mapped = mapping.get(content_type)
        if mapped:
            return mapped
        if content_type:
            # 如果是 "/" 分隔的内容类型，取最后一部分
            if "/" in content_type:
                ext = content_type.split("/")[-1]
                # 移除版本号等后缀
                ext = ext.split("+")[0]
                return f".{ext}"
            return f".{content_type}"
        return ""
