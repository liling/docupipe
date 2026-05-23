from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docupipe.steps.base import Step

STEPS: dict[str, type[Step]] = {}


def register_step(name: str):
    def decorator(cls: type[Step]):
        if name in STEPS:
            existing = STEPS[name]
            existing_source = getattr(existing, "_plugin_source", "built-in")
            raise ValueError(
                f"step '{name}' 已注册 (来源: {existing_source})"
            )
        STEPS[name] = cls
        cls.name = name
        return cls
    return decorator


def get_step(name: str) -> type[Step]:
    if name not in STEPS:
        raise ValueError(f"未知的 step: {name}，可选: {', '.join(STEPS.keys())}")
    return STEPS[name]


# 自动注册内置 step
import docupipe.steps.convert  # noqa: F401, E402
import docupipe.steps.image_description  # noqa: F401, E402
import docupipe.steps.s3_upload  # noqa: F401, E402
import docupipe.steps.resolve_attachments  # noqa: F401, E402
import docupipe.steps.tencent_delete  # noqa: F401, E402
import docupipe.steps.excel_structured  # noqa: F401, E402

for cls in STEPS.values():
    if not hasattr(cls, "_plugin_source"):
        cls._plugin_source = "built-in"
