# 如何添加新组件

所有组件的注册模式相同，三步即可添加。

## Prerequisites

- 已安装 `pip install -e ".[dev]"`
- 了解组件类型含义：Source（数据源）、Destination（目标）、Step（处理步骤）、Converter（格式转换）

## 步骤

### 1. 创建组件文件

在对应目录下创建文件：

| 组件类型 | 目录 | 继承 |
|----------|------|------|
| Source | `docupipe/sources/` | `SourceBase` |
| Destination | `docupipe/destinations/` | `DestinationBase` |
| Step | `docupipe/steps/` | `Step` |
| Converter | `docupipe/converters/` | `ConverterBase` |

### 2. 实现抽象方法 + 添加装饰器

以 Source 为例（`sources/custom.py`）：

```python
from docupipe.models import Bundle, BundleMeta
from docupipe.sources import register_source
from docupipe.sources.base import SourceBase


@register_source("custom")
class CustomSource(SourceBase):
    def __init__(self, **kwargs):
        # 接收来自 YAML 配置的参数
        pass

    def list(self) -> list[BundleMeta]:
        # 返回文档列表
        return [
            BundleMeta(
                id="unique_id",
                title="文档标题",
                path="relative/path",
                extra={"key": "value"},
            )
        ]

    def fetch(self, meta: BundleMeta) -> Bundle:
        # 根据 meta 获取文档内容
        return Bundle(
            files=[FileItem(name="doc.md", content="# 内容", content_type="text/markdown", role="main")],
            context=dict(meta.extra),
        )
```

其他组件类型：

```python
# Destination
from docupipe.destinations import register_destination
from docupipe.destinations.base import DestinationBase

@register_destination("custom")
class CustomDestination(DestinationBase):
    def write(self, bundle: Bundle) -> str:
        # 写入文档，返回目标 ID
        pass


# Step
from docupipe.steps import register_step
from docupipe.steps.base import Step

@register_step("custom")
class CustomStep(Step):
    def process(self, bundle: Bundle) -> Bundle:
        # 处理文档，返回处理后的 Bundle
        return bundle


# Converter
from docupipe.converters import register_converter
from docupipe.converters.base import ConverterBase

@register_converter("custom")
class CustomConverter(ConverterBase):
    def convert(self, file_path: Path) -> str:
        # 返回 Markdown 文本
        return "# converted content"
```

### 3. 在 `__init__.py` 中注册

在对应的 `__init__.py` 文件中添加 import：

```python
# sources/__init__.py
import docupipe.sources.custom  # 添加这行

# destinations/__init__.py
import docupipe.destinations.custom

# steps/__init__.py
import docupipe.steps.custom

# converters/__init__.py
from docupipe.converters import custom  # 或 import docupipe.converters.custom
```

## Verification

运行以下命令确认组件已注册：

```bash
python -m docupipe sources       # 列出所有 Source
python -m docupipe destinations  # 列出所有 Destination
```

在配置文件中使用新组件：

```yaml
pipelines:
  - name: test-custom
    source:
      custom:
        param1: value
    destination:
      localdrive:
        output_dir: ./output
    steps:
      - custom_step_name
    post_steps:
      - custom_step_name
    finalize_steps:
      - custom_step_name
```

## Troubleshooting

**组件未出现在列表中**：确认 `__init__.py` 中有 import 语句，且 import 没有报错。

**配置解析失败**：确认组件类的 `__init__` 参数名与 YAML 配置中的 key 匹配。多余的参数会被 kwargs 接收。

**Bundle Context 字段冲突**：在 `models.py` 顶部的字段注册表中查找，避免使用已占用的字段名。通用字段用 snake_case，Source 特有字段用 `{source}_` 前缀。
