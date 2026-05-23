from __future__ import annotations

from datetime import date, datetime
from pathlib import PurePosixPath
from typing import Any

from jinja2 import BaseLoader, StrictUndefined
from jinja2.sandbox import SandboxedEnvironment
from jinja2.exceptions import UndefinedError as Jinja2UndefinedError


def _date_format(value: Any, fmt: str = "%Y-%m-%d") -> str:
    if isinstance(value, (int, float)):
        value = datetime.fromtimestamp(value / 1000)
    elif isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, (datetime, date)):
        return value.strftime(fmt)
    return str(value)


def _basename(value: Any) -> str:
    return PurePosixPath(str(value)).name


def _extension(value: Any) -> str:
    name = PurePosixPath(str(value)).name
    if "." in name:
        return name.rsplit(".", 1)[1]
    return ""


_env = SandboxedEnvironment(
    loader=BaseLoader(),
    undefined=StrictUndefined,
    autoescape=False,
)
_env.filters["date_format"] = _date_format
_env.filters["basename"] = _basename
_env.filters["extension"] = _extension


def render_template(value: Any, context: dict) -> Any:
    """使用 Jinja2 渲染模板字符串。对 dict/list 递归处理。"""
    if isinstance(value, str):
        tpl = _env.from_string(value)
        try:
            return tpl.render(**context)
        except Jinja2UndefinedError as e:
            raise ValueError(
                f"模板渲染错误，配置中引用了不存在的字段: {e}"
            ) from e
    if isinstance(value, dict):
        return {k: render_template(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [render_template(v, context) for v in value]
    return value
