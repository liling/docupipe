from __future__ import annotations

import os
import re
from typing import Any

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def resolve_env_vars(value: Any) -> Any:
    """递归替换 ${ENV_VAR} 和 ${ENV_VAR:-default}"""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(_replace_env, value)
    if isinstance(value, dict):
        return {k: resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_env_vars(v) for v in value]
    return value


def _replace_env(match: re.Match) -> str:
    expr = match.group(1)
    if ":-" in expr:
        var, default = expr.split(":-", 1)
        return os.environ.get(var.strip(), default)
    val = os.environ.get(expr.strip())
    return val if val is not None else match.group(0)


def deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典，override 覆盖 base"""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def parse_component_config(pipeline_config: dict, global_config: dict, component_key: str) -> tuple[str, dict]:
    """解析 source 或 destination 配置，返回 (type_name, merged_config)"""
    comp = pipeline_config.get(component_key, {})
    if not comp:
        raise ValueError(f"缺少 {component_key} 配置")

    items = list(comp.items())
    if len(items) != 1:
        raise ValueError(f"{component_key} 必须只有一个 type，当前有: {list(comp.keys())}")

    type_name, config = items[0]
    config = dict(config) if config else {}

    global_comp = global_config.get(type_name, {})
    if global_comp:
        config = deep_merge(global_comp, config)

    return type_name, config
