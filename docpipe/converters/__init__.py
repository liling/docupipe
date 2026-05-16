from __future__ import annotations

CONVERTERS: dict[str, type] = {}


def register_converter(name: str):
    def decorator(cls):
        CONVERTERS[name] = cls
        return cls
    return decorator


def get_converter(name: str):
    if name not in CONVERTERS:
        raise ValueError(f"未知的 converter: {name}")
    return CONVERTERS[name]


from docpipe.converters import markitdown  # noqa: E402,F401
from docpipe.converters import mineru  # noqa: E402,F401
