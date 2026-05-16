from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath


class SkipBundle(Exception):
    """Source 发出此异常表示该文档包应跳过"""
    pass




@dataclass
class FileItem:
    name: str
    content: str | bytes
    content_type: str = ""
    role: str = "main"
    metadata: dict = field(default_factory=dict)


@dataclass
class Bundle:
    files: list[FileItem] = field(default_factory=list)
    context: dict = field(default_factory=dict)

    @property
    def main(self) -> FileItem | None:
        """获取 role=main 的主文件"""
        return next((f for f in self.files if f.role == "main"), None)

    def get_by_role(self, role: str) -> list[FileItem]:
        return [f for f in self.files if f.role == role]

    def add(self, file: FileItem) -> None:
        if any(f.name == file.name for f in self.files):
            stem = PurePosixPath(file.name).stem
            suffix = PurePosixPath(file.name).suffix
            seq = 1
            while any(f.name == f"{stem}_{seq}{suffix}" for f in self.files):
                seq += 1
            file.name = f"{stem}_{seq}{suffix}"
        self.files.append(file)

    def remove(self, name: str) -> None:
        self.files = [f for f in self.files if f.name != name]


@dataclass
class BundleMeta:
    id: str
    title: str
    path: str = ""
    hash: str = ""
    extra: dict = field(default_factory=dict)