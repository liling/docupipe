# 可配置文件类型处理器设计

## 目标

将文件类型判断和内容转换从 Source 中解耦，建立可配置的类型→处理器映射机制。通过 YAML 配置文件定义哪些文件类型用哪个转换器处理，支持扩展名和 MIME 类型两种匹配规则。

## 架构

```
配置文件 (type_rules)
       ↓
TypeRuleResolver (查表：扩展名/MIME → converter 名)
       ↓
Pipeline (过滤 + 调度)
   ├── 无匹配 → 跳过，不下载
   ├── skip → 跳过
   └── converter 名 → Source.fetch() 下载 → Converter.convert() 转换
```

## Converter 接口

### 抽象基类

```python
# docpipe/converters/base.py
class ConverterBase(ABC):
    name: str = ""

    @abstractmethod
    def convert(self, file_path: Path) -> str:
        """将文件转换为 Markdown，返回 Markdown 文本"""
```

### 注册机制

```python
# docpipe/converters/__init__.py
CONVERTERS: dict[str, type[ConverterBase]] = {}

def register_converter(name: str):
    def decorator(cls):
        CONVERTERS[name] = cls
        return cls
    return decorator

def get_converter(name: str) -> type[ConverterBase]:
    if name not in CONVERTERS:
        raise ValueError(f"未知的 converter: {name}")
    return CONVERTERS[name]
```

### 内置实现

**MarkitdownConverter** — 封装现有 markitdown 逻辑：

```python
@register_converter("markitdown")
class MarkitdownConverter(ConverterBase):
    name = "markitdown"

    def convert(self, file_path: Path) -> str:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(str(file_path))
        return result.markdown
```

**SkipConverter** — 特殊处理器，配置中值为 `skip` 时使用。Pipeline 直接跳过，不调用 converter。

## TypeRuleResolver

根据扩展名/MIME 类型查找处理器名。扩展名优先，MIME 其次。

```python
# docpipe/converters/resolver.py
class TypeRuleResolver:
    def __init__(self, extension_rules: dict[str, str], mime_rules: dict[str, str] | None = None):
        self._extension_rules = extension_rules   # {".pdf": "mineru", ".docx": "markitdown"}
        self._mime_rules = mime_rules or {}

    def resolve(self, extension: str, mime_type: str = "") -> str | None:
        if extension in self._extension_rules:
            return self._extension_rules[extension]
        if mime_type and mime_type in self._mime_rules:
            return self._mime_rules[mime_type]
        return None
```

同时充当白名单：凡是在 `extension_rules` 中出现的扩展名才会处理，没出现的一律跳过（不下载）。

## 配置文件

在 pipeline 同级加 `type_rules` 段：

```yaml
type_rules:
  extensions:
    ".pdf": mineru
    ".docx": markitdown
    ".xlsx": markitdown
    ".pptx": markitdown
    ".doc": markitdown
    ".xls": markitdown
    ".ppt": markitdown
    ".html": markitdown
    ".htm": markitdown
    ".csv": markitdown
    ".json": markitdown
    ".xml": markitdown
    ".txt": markitdown
    ".md": markitdown
    ".rtf": markitdown
    ".odt": markitdown
    ".ods": markitdown
  mime_types: {}

pipelines:
  - name: shujuxian-to-hindsight
    source: dingtalk
    destination: hindsight
    source_config:
      space_id: "nb9XJB7qpnkxQXyA"
      image_description: true
      ...
    dest_config:
      ...
    options:
      resume: true
      sync: true
```

## Pipeline 改造

### 构造函数

`type_resolver` 为必传参数：

```python
class Pipeline:
    def __init__(self, source, dest, state_dir, display=None, type_resolver=None):
        self._type_resolver = type_resolver
        ...
```

### 执行流程

1. Source `list_documents()` 返回所有文件元数据（不过滤类型）
2. Pipeline 用 TypeRuleResolver 查表——无匹配的 skip，不进 fetch
3. 钉钉原生文档 (ALIDOC/adoc) 由 Source 直接读为 Markdown，不走 converter
4. 其他文件由 Source 下载到临时路径，Pipeline 调用 converter 转换
5. 转换结果（Markdown）传给 Destination

### 伪代码

```python
for doc_meta in docs:
    ext_raw = doc_meta.extra.get('extension', '')
    extension = f".{ext_raw}" if ext_raw else ""
    mime_type = doc_meta.extra.get('contentType', '')
    converter_name = self._type_resolver.resolve(extension, mime_type)

    if converter_name is None:
        self._display.result("skip", f"{doc_meta.title} (无处理规则)")
        continue

    if converter_name == "skip":
        self._display.result("skip", f"{doc_meta.title} (跳过)")
        continue

    self._display.set_current(doc_meta.title)
    try:
        doc = self.source.fetch(doc_meta)
        # 钉钉原生文档已经转为 Markdown
        if not doc.meta.extra.get("_needs_conversion"):
            # 已是 Markdown，直接用
            pass
        else:
            converter = get_converter(converter_name)()
            file_path = Path(doc.meta.extra["_temp_file"])
            doc.content = converter.convert(file_path)
            file_path.unlink(missing_ok=True)

        # 后续：清理 HTML、图片描述、写 Destination（原有逻辑）
        ...
    except Exception as e:
        ...
    finally:
        self._display.clear_current(doc_meta.title)
```

## DingtalkSource 改造

### list_documents()

移除 `_CONVERTIBLE_EXTENSIONS`、`_SKIP_CONTENT_TYPES` 过滤逻辑，返回所有文件元数据。仅跳过文件夹。

### fetch()

- 钉钉原生文档 (ALIDOC/adoc)：直接 `read_document()` 读为 Markdown，设置 `_needs_conversion = False`
- 其他文件：下载到临时路径，在 `doc.meta.extra["_temp_file"]` 中记录路径，设置 `_needs_conversion = True`
- 移除 `_download_and_convert()` 方法（转换逻辑移到 Pipeline）

## CLI 改造

`_run_from_config()` 解析 `type_rules`，构建 `TypeRuleResolver` 传给 Pipeline：

```python
type_rules = config.get("type_rules", {})
resolver = TypeRuleResolver(
    extension_rules=type_rules.get("extensions", {}),
    mime_rules=type_rules.get("mime_types", {}),
)
pipeline = Pipeline(source, dest, ctx.obj["state_dir"],
                    display=Display(), type_resolver=resolver)
```

## 文件变更清单

| 文件 | 变更 |
|------|------|
| `docpipe/converters/__init__.py` | 新建，注册机制 |
| `docpipe/converters/base.py` | 新建，ConverterBase 抽象基类 |
| `docpipe/converters/markitdown.py` | 新建，MarkitdownConverter |
| `docpipe/converters/resolver.py` | 新建，TypeRuleResolver |
| `docpipe/pipeline.py` | 改造，集成 type_resolver + converter 调用 |
| `docpipe/sources/dingtalk.py` | 改造，移除类型过滤和转换逻辑 |
| `docpipe/cli.py` | 改造，解析 type_rules 配置 |
| `docpipe.yaml` | 改造，添加 type_rules 段 |
| `tests/test_converters.py` | 新建，converter 和 resolver 测试 |
