from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docupipe.destinations.base import DestinationBase

DESTINATIONS: dict[str, type[DestinationBase]] = {}


def register_destination(name: str):
    def decorator(cls: type[DestinationBase]):
        if name in DESTINATIONS:
            existing = DESTINATIONS[name]
            existing_source = getattr(existing, "_plugin_source", "built-in")
            raise ValueError(
                f"destination '{name}' 已注册 (来源: {existing_source})"
            )
        DESTINATIONS[name] = cls
        cls.name = name
        return cls
    return decorator


def get_destination(name: str) -> type[DestinationBase]:
    if name not in DESTINATIONS:
        raise ValueError(f"未知的 destination: {name}，可选: {', '.join(DESTINATIONS.keys())}")
    return DESTINATIONS[name]


# 自动注册内置 destination
import docupipe.destinations.hindsight  # noqa: F401, E402
import docupipe.destinations.localdrive  # noqa: F401, E402

for cls in DESTINATIONS.values():
    if not hasattr(cls, "_plugin_source"):
        cls._plugin_source = "built-in"
