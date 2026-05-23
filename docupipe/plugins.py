from __future__ import annotations

import importlib.metadata
import importlib.util
import logging
import sys
from pathlib import Path

logger = logging.getLogger("docupipe.plugins")

_PLUGIN_REGISTRY: dict[str, list[tuple[str, str]]] = {}
_loaded_paths: set[Path] = set()

CONVENTION_DIRS = [
    Path.home() / ".docupipe" / "plugins",
]


def load_plugins():
    """阶段 1（import 时）：仅加载 entry_points 插件。"""
    loaded = _load_from_entry_points()
    for name, count in loaded:
        logger.info("Loaded plugin: %s (%d components)", name, count)


def load_config_plugins(plugin_dirs: list[str]):
    """阶段 2（运行时）：加载约定目录和配置指定的插件目录。"""
    if not isinstance(plugin_dirs, list):
        raise TypeError(
            f"plugin_dirs 必须是列表，收到 {type(plugin_dirs).__name__}"
        )
    for dir_path in plugin_dirs:
        plugin_dir = Path(dir_path).expanduser().resolve()
        if plugin_dir.is_dir():
            loaded = _load_from_directory(plugin_dir)
            for name, count in loaded:
                logger.info("Loaded plugin: %s (%d components)", name, count)

    for conv_dir in CONVENTION_DIRS:
        resolved = conv_dir.resolve()
        if resolved.is_dir() and resolved not in _loaded_paths:
            loaded = _load_from_directory(resolved)
            for name, count in loaded:
                logger.info("Loaded plugin: %s (%d components)", name, count)


def _load_from_directory(plugin_dir: Path) -> list[tuple[str, int]]:
    """从目录加载本地插件文件/包。"""
    if not plugin_dir.is_dir():
        return []
    if plugin_dir in _loaded_paths:
        return []
    _loaded_paths.add(plugin_dir)

    results: list[tuple[str, int]] = []
    for item in sorted(plugin_dir.iterdir()):
        if item.name.startswith("_") or item.name == "__pycache__":
            continue
        try:
            if item.is_file() and item.suffix == ".py" and item.name != "__init__.py":
                count = _import_file(item)
                results.append((str(item), count))
            elif item.is_dir() and (item / "__init__.py").exists():
                count = _import_package(item)
                results.append((str(item), count))
        except Exception:
            logger.exception("Failed to load plugin: %s", item)
    return results


def _import_file(path: Path) -> int:
    """从 .py 文件加载本地插件。"""
    before = _count_registered()
    stem = path.stem
    module_name = f"_docupipe_plugin_{stem}"
    if module_name in sys.modules:
        return _count_registered() - before

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        logger.warning("Could not load %s (spec is None)", path)
        return 0

    parent_dir = str(path.parent)
    sys.path.insert(0, parent_dir)
    try:
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)

    _set_plugin_source(f"file:{path}")
    count = _count_registered() - before
    if count > 0:
        _PLUGIN_REGISTRY.setdefault(str(path), []).extend(
            [(t, n) for t, reg in _registries().items() for n in reg
             if getattr(reg[n], "_plugin_source", None) == f"file:{path}"]
        )
    return count


def _import_package(path: Path) -> int:
    """从目录（含 __init__.py）加载本地插件包。"""
    before = _count_registered()
    init_path = path / "__init__.py"
    module_name = f"_docupipe_plugin_{path.name}"
    if module_name in sys.modules:
        return _count_registered() - before

    spec = importlib.util.spec_from_file_location(
        module_name, init_path,
        submodule_search_locations=[str(path)],
    )
    if spec is None or spec.loader is None:
        return 0

    parent_dir = str(path.parent)
    sys.path.insert(0, parent_dir)
    try:
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)

    _set_plugin_source(f"package:{path}")
    count = _count_registered() - before
    if count > 0:
        _PLUGIN_REGISTRY.setdefault(str(path), []).extend(
            [(t, n) for t, reg in _registries().items() for n in reg
             if getattr(reg[n], "_plugin_source", None) == f"package:{path}"]
        )
    return count


def _load_from_entry_points() -> list[tuple[str, int]]:
    """从 entry_points('docupipe.plugins') 加载 pip 插件。"""
    results: list[tuple[str, int]] = []
    eps = importlib.metadata.entry_points(group="docupipe.plugins")
    for ep in eps:
        try:
            load_fn = ep.load()
            before = _count_registered()
            load_fn()
            after = _count_registered()
            count = after - before
            if count > 0:
                dist_name = ep.dist.name if ep.dist else ep.name
                _set_plugin_source(f"pip:{dist_name}")
                _PLUGIN_REGISTRY.setdefault(dist_name, []).extend(
                    [(t, n) for t, reg in _registries().items() for n in reg
                     if getattr(reg[n], "_plugin_source", None) == f"pip:{dist_name}"]
                )
            results.append((ep.name, count))
        except Exception:
            logger.exception("Failed to load entry_point plugin '%s'", ep.name)
    return results


def _set_plugin_source(source: str):
    """注册后置注入：遍历所有注册表，为尚无 _plugin_source 的组件设置来源。"""
    for reg in _registries().values():
        for cls in reg.values():
            if not hasattr(cls, "_plugin_source"):
                cls._plugin_source = source


def _count_registered() -> int:
    """统计当前注册的组件总数。"""
    return sum(len(reg) for reg in _registries().values())


def _registries() -> dict[str, dict]:
    """延迟导入并返回所有组件注册表。"""
    from docupipe.sources import SOURCES
    from docupipe.destinations import DESTINATIONS
    from docupipe.steps import STEPS
    from docupipe.converters import CONVERTERS
    return {"source": SOURCES, "destination": DESTINATIONS,
            "step": STEPS, "converter": CONVERTERS}
