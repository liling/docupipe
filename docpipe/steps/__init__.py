from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docpipe.steps.base import PipelineStep

STEPS: dict[str, type[PipelineStep]] = {}


def register_step(name: str):
    def decorator(cls: type[PipelineStep]):
        STEPS[name] = cls
        cls.name = name
        return cls
    return decorator


def get_step(name: str) -> type[PipelineStep]:
    if name not in STEPS:
        raise ValueError(f"未知的 step: {name}，可选: {', '.join(STEPS.keys())}")
    return STEPS[name]


# 自动注册内置 step
import docpipe.steps.convert  # noqa: F401, E402
import docpipe.steps.image_description  # noqa: F401, E402
import docpipe.steps.s3_upload  # noqa: F401, E402
