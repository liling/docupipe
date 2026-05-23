from __future__ import annotations

CONVERTERS: dict[str, type] = {}


def register_converter(name: str):
    def decorator(cls):
        if name in CONVERTERS:
            existing = CONVERTERS[name]
            existing_source = getattr(existing, "_plugin_source", "built-in")
            raise ValueError(
                f"converter '{name}' 已注册 (来源: {existing_source})"
            )
        CONVERTERS[name] = cls
        return cls
    return decorator


def get_converter(name: str):
    if name not in CONVERTERS:
        raise ValueError(f"未知的 converter: {name}")
    return CONVERTERS[name]


from docupipe.converters import markitdown  # noqa: E402,F401
from docupipe.converters import mineru  # noqa: E402,F401

for cls in CONVERTERS.values():
    if not hasattr(cls, "_plugin_source"):
        cls._plugin_source = "built-in"
