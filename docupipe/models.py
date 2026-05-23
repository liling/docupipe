from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath


# Bundle context 字段注册表
#
# 新增 source/step 时必须先查阅此表，复用已有 key 或按规则添加。
# 规则：
#   - 通用字段：snake_case，无前缀
#   - Source 特有字段：{source}_前缀 + snake_case
#   - 值类型：extension 是纯扩展名不含点号，content_type 必须是 MIME type
#
# Pipeline 注入字段（pipeline.py）：
#   id              | str  | 文档唯一标识
#   title           | str  | 文档标题
#   path            | str  | 文档路径
#   filename        | str  | 文件名
#   _source         | str  | 来源名称
#   hash            | str  | 内容 SHA-256 哈希
#   _step_progress  | callable | 进度回调（临时，step 执行期间存在）
#
# 通用字段（多个 source 共用）：
#   extension       | str  | 文件扩展名，不含点号 | Source 写入 | ConvertStep 读取
#   space_name      | str  | 知识库/空间名称      | 钉钉/腾讯写入 | Destination 读取
#   absolute_path   | str  | 本地文件绝对路径      | LocalDrive 写入 | ResolveAttachmentsStep 读取
#   image_metadata  | dict | 图片描述 AI 处理结果  | ImageDescriptionStep 写入
#   mtime           | int  | 通用修改时间戳（毫秒）| Dingtalk/LocalDrive 写入 | Pipeline/Hindsight 读取
#
# Source 特有字段：
#   dingtalk_content_type | str | 钉钉文档类型枚举（ALIDOC/DOCUMENT 等）| DingtalkSource 写入
#   dingtalk_extension    | str | 钉钉原始扩展名（内容转换前）| DingtalkSource 写入
#   dingtalk_update_time  | int | 钉钉文档更新时间戳（毫秒）| DingtalkSource 写入 | HindsightDestination 读取
#   dingtalk_node_type    | str | 钉钉节点类型（folder/doc 等）| DingtalkSource 写入
#   tencent_doc_type      | str | 腾讯文档类型枚举（document/sheet 等）| TencentSource 写入
#   tencent_node_type     | str | 腾讯节点类型（wiki_folder/doc 等）| TencentSource 写入
#   tencent_has_child     | bool | 腾讯节点是否有子节点 | TencentSource 写入


class SkipBundle(Exception):
    """Source 发出此异常表示该文档包应跳过"""
    pass


@dataclass
class FileItem:
    name: str
    content: str | bytes
    content_type: str = ""
    role: str = "main"
    context: dict = field(default_factory=dict)


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