from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docupipe.post_steps.base import PostStep

POST_STEPS: dict[str, type[PostStep]] = {}


def register_post_step(name: str):
    def decorator(cls: type[PostStep]):
        POST_STEPS[name] = cls
        cls.name = name
        return cls
    return decorator


def get_post_step(name: str) -> type[PostStep]:
    if name not in POST_STEPS:
        raise ValueError(f"未知的 post_step: {name}，可选: {', '.join(POST_STEPS.keys())}")
    return POST_STEPS[name]
