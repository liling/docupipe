from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docupipe.sources.base import SourceBase

SOURCES: dict[str, type[SourceBase]] = {}


def register_source(name: str):
    def decorator(cls: type[SourceBase]):
        SOURCES[name] = cls
        cls.name = name
        return cls
    return decorator


def get_source(name: str) -> type[SourceBase]:
    if name not in SOURCES:
        raise ValueError(f"未知的 source: {name}，可选: {', '.join(SOURCES.keys())}")
    return SOURCES[name]


# 自动注册内置 source
import docupipe.sources.dingtalk  # noqa: F401, E402
import docupipe.sources.localdrive  # noqa: F401, E402
import docupipe.sources.tencent  # noqa: F401, E402
