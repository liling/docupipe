# Plugin System Design

## 目标

让 source、destination、step、converter 等组件可以在 docupipe 核心包外部实现，通过插件机制自动发现和加载。支持个人复用和第三方扩展两种场景。

## 设计决策

| 决策 | 选择 |
|------|------|
| 插件形式 | pip 包 + 本地文件/目录 |
| 发现方式 | entry_points + 约定目录 + 配置目录 |
| 注册模式 | 单一 entry_points group + 自注册 |
| 冲突处理 | 抛出 ValueError |
| API 风格 | 复用现有 @register_xxx 装饰器 |

## 插件发现

### 发现路径（按加载顺序）

1. **内置组件**（最高优先级）：现有 `__init__.py` 中的硬编码 import
2. **约定目录**：`~/.docupipe/plugins/`（全局用户级）
3. **配置目录**：YAML 中 `plugin_dirs` 字段指定的路径
4. **entry_points**：`docupipe.plugins` group 中的入口函数

### 约定目录扫描规则

- 扫描目录下所有 `.py` 文件（不含 `_` 前缀）
- 扫描含 `__init__.py` 的子目录（Python 包）
- 不递归扫描子目录的子目录

### YAML 配置

`plugin_dirs` 是可选的顶层字段：

```yaml
plugin_dirs:
  - ./my_plugins/
  - /shared/docupipe/plugins/
```

## 插件 API

### pip 插件

插件是独立的 Python 包，通过 `pyproject.toml` 声明入口：

```toml
[project.entry-points."docupipe.plugins"]
notion = "docupipe_notion:load_plugin"
```

入口函数负责触发组件注册：

```python
# docupipe_notion/__init__.py
def load_plugin():
    from .source import NotionSource        # @register_source 触发注册
    from .destination import NotionDest     # @register_destination 触发注册
```

### 本地插件

`plugins/` 目录下的 `.py` 文件或 Python 包，直接使用装饰器：

```python
# plugins/notion_source.py
from docupipe.sources import register_source
from docupipe.sources.base import SourceBase

@register_source("notion")
class NotionSource(SourceBase):
    ...
```

## 实现方案

### 新增文件

- `docupipe/plugins.py`：插件加载器，包含 `_load_plugins()` 函数

### 修改文件

- `docupipe/__init__.py`：在导入子模块前调用 `_load_plugins()`
- `docupipe/sources/__init__.py`、`destinations/__init__.py`、`steps/__init__.py`、`converters/__init__.py`：`register_xxx` 装饰器增加冲突检测
- `docupipe/cli.py`：扩展 `sources`/`destinations` 命令显示来源，新增 `plugins` 命令
- `docupipe/config.py`：解析 `plugin_dirs` 配置字段

### 注册冲突检测

修改 `register_xxx` 装饰器，在注册时检查名称是否已存在：

```python
def register_source(name: str):
    def decorator(cls):
        if name in SOURCES:
            raise ValueError(f"source '{name}' 已注册")
        SOURCES[name] = cls
        cls.name = name
        return cls
    return decorator
```

### 组件来源追踪

注册时在类上记录 `_plugin_source` 属性：

- 内置组件：`"built-in"`
- pip 插件组件：包名（如 `"docupipe_notion"`）
- 本地插件组件：文件路径（如 `"./plugins/custom.py"`）

### 加载时机

在 `docupipe/__init__.py` 中，先调用 `_load_plugins()`，再 import 各子模块：

```python
# docupipe/__init__.py
from docupipe.plugins import _load_plugins
_load_plugins()

from docupipe import sources, destinations, steps, converters  # noqa: E402, F401
```

### 插件加载器核心逻辑

```python
# docupipe/plugins.py
import importlib
import importlib.metadata
import importlib.util
import logging
from pathlib import Path

logger = logging.getLogger("docupipe.plugins")

PLUGIN_DIRS = [
    Path.home() / ".docupipe" / "plugins",
]

def _load_plugins():
    """发现并加载所有插件。"""
    loaded = []

    # 1. 约定目录
    for plugin_dir in PLUGIN_DIRS:
        if plugin_dir.is_dir():
            loaded.extend(_load_from_directory(plugin_dir))

    # 2. entry_points
    loaded.extend(_load_from_entry_points())

    # 打印加载结果
    if loaded:
        for name, count in loaded:
            logger.info(f"Loaded plugin: {name} ({count} components)")


def _load_from_directory(plugin_dir: Path) -> list[tuple[str, int]]:
    """从目录加载本地插件。"""
    results = []
    for item in sorted(plugin_dir.iterdir()):
        if item.name.startswith("_"):
            continue
        if item.is_file() and item.suffix == ".py":
            count = _import_file(item)
            results.append((str(item), count))
        elif item.is_dir() and (item / "__init__.py").exists():
            count = _import_package(item)
            results.append((str(item), count))
    return results


def _load_from_entry_points() -> list[tuple[str, int]]:
    """从 entry_points 加载 pip 插件。"""
    results = []
    eps = importlib.metadata.entry_points(group="docupipe.plugins")
    for ep in eps:
        load_fn = ep.load()
        before = _count_registered()
        load_fn()
        after = _count_registered()
        count = after - before
        results.append((ep.name, count))
    return results


def _count_registered() -> int:
    """统计当前已注册的组件总数。"""
    from docupipe.sources import SOURCES
    from docupipe.destinations import DESTINATIONS
    from docupipe.steps import STEPS
    from docupipe.converters import CONVERTERS
    return len(SOURCES) + len(DESTINATIONS) + len(STEPS) + len(CONVERTERS)
```

## CLI 扩展

### 组件列表显示来源

```bash
$ docupipe sources
  dingtalk (built-in)
  notion (plugin: docupipe_notion)
```

### 新增 plugins 命令

```bash
$ docupipe plugins
  docupipe_notion: NotionSource, NotionDestination
  ./plugins/custom.py: CustomStep
```

## 错误处理

| 场景 | 行为 |
|------|------|
| 插件目录不存在 | 静默跳过 |
| 本地插件导入失败 | 记录错误日志，跳过该插件，继续加载其他 |
| entry_points 加载失败 | 记录错误日志，跳过该插件 |
| 组件名冲突 | 抛出 ValueError，终止启动 |
| 插件函数抛异常 | 记录错误日志，跳过该插件 |

## 测试计划

- 单元测试：`_load_from_directory()`、`_load_from_entry_points()`、冲突检测
- 集成测试：临时目录中放置 .py 插件文件，验证加载和注册
- Mock 测试：mock `importlib.metadata.entry_points()` 验证 entry_points 加载
