from __future__ import annotations

import copy
import logging
import os
import re
from pathlib import Path
from typing import Any

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


logger = logging.getLogger(__name__)


def resolve_env_vars(value: Any, variables: dict[str, str] | None = None) -> Any:
    """递归替换 ${VAR}，优先级：variables dict > 环境变量 > 默认值"""
    vars_dict = variables or {}

    def _replace(match: re.Match) -> str:
        expr = match.group(1)
        if ":-" in expr:
            var, default = expr.split(":-", 1)
            var = var.strip()
            if var in vars_dict:
                return vars_dict[var]
            return os.environ.get(var, default)
        var = expr.strip()
        if var in vars_dict:
            return vars_dict[var]
        val = os.environ.get(var)
        if val is None:
            logger.warning("环境变量未设置: '%s'，将保留原始值", var)
            return match.group(0)
        return val

    if isinstance(value, str):
        return _ENV_PATTERN.sub(_replace, value)
    if isinstance(value, dict):
        return {k: resolve_env_vars(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_env_vars(v, variables) for v in value]
    return value



def execute_variables_script(raw_config: dict) -> dict[str, str]:
    """执行配置中的 variables 脚本，返回变量字典。"""
    vars_block = raw_config.get("variables")
    if not vars_block:
        return {}

    script_file = vars_block.get("script_file")
    script_inline = vars_block.get("script")

    if script_file and script_inline:
        logging.getLogger(__name__).warning("variables 同时指定了 script 和 script_file，使用 script_file")

    if script_file:
        path = Path(script_file)
        if not path.is_file():
            raise FileNotFoundError(f"variables script_file 不存在: {script_file}")
        source = path.read_text(encoding="utf-8")
    elif script_inline:
        source = script_inline
    else:
        return {}

    func_lines = ["def _vars_func():"]
    for line in source.splitlines():
        func_lines.append("    " + line if line.strip() else "")
    func_source = "\n".join(func_lines)

    namespace: dict = {}
    exec(func_source, namespace)
    result = namespace["_vars_func"]()

    if not isinstance(result, dict):
        raise TypeError(f"variables 脚本必须返回 dict，实际返回了 {type(result).__name__}")

    variables: dict[str, str] = {}
    for k, v in result.items():
        if not isinstance(k, str):
            raise TypeError(f"variables 脚本返回的 key 必须是字符串，实际为 {type(k).__name__}: {k}")
        variables[k] = str(v)

    return variables


def deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典，override 覆盖 base，不修改 base"""
    result = copy.deepcopy(base)
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
