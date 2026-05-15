from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docpipe.destinations.base import DestinationBase

DESTINATIONS: dict[str, type[DestinationBase]] = {}


def register_destination(name: str):
    def decorator(cls: type[DestinationBase]):
        DESTINATIONS[name] = cls
        cls.name = name
        return cls
    return decorator


def get_destination(name: str) -> type[DestinationBase]:
    if name not in DESTINATIONS:
        raise ValueError(f"未知的 destination: {name}，可选: {', '.join(DESTINATIONS.keys())}")
    return DESTINATIONS[name]


# 自动注册内置 destination
import docpipe.destinations.hindsight  # noqa: F401, E402
