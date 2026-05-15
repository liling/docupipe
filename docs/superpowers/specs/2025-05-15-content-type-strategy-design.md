# ContentTypeStrategy 设计：钉钉文档类型策略分层

## 背景

当前 docpipe 对钉钉文档类型的处理存在以下问题：

1. 钉钉 API 返回 `contentType`（DOCUMENT / ALIDOC / ARCHIVE / IMAGE / OTHER），这是 Source 领域概念，不是标准 MIME type
2. `TypeRuleResolver` 将 contentType 当作 MIME type 处理，且只配置了 ALIDOC 和少数几种，导致大量 DOCUMENT / ARCHIVE / IMAGE / OTHER 类型文档因"无处理规则"被跳过
3. 过滤逻辑分散在两处：`dingtalk.py` 的 `_UNSUPPORTED_EXTENSIONS` 硬编码列表 + YAML 的 `type_rules` 配置
4. ALIDOC 内部有多种子类型（adoc / axls / able / aform / abitable / amindmap），需要独立的处理器体系

## 设计

### 核心思路

将类型处理拆成两个独立的层级：

1. **ContentTypeStrategy**（策略层）：钉钉 contentType → 处理动作
2. **TypeRuleResolver**（转换层）：文件扩展名 → Converter

两层解耦，ContentTypeStrategy 的映射绑定在 pipeline 配置上，不同的 Source+Destination 组合可以有不同策略。

### 动作（Action）集合

| Action    | 含义                                 |
| --------- | ------------------------------------ |
| `convert` | 下载文件，通过 Converter 转为 Markdown |
| `skip`    | 跳过，不处理                          |
| `source`  | Source 原生处理（如 ALIDOC 的 Markdown 导出） |
| `download` | 下载原始文件，不转换（如迁移到网盘场景） |
| `None`    | 无规则，跳过并记录日志                 |

### ContentTypeStrategy 类

```python
class ContentTypeStrategy:
    """钉钉 contentType 到处理动作的映射"""

    def __init__(self, rules: dict[str, str]):
        self._rules = rules

    def resolve(self, content_type: str) -> str | None:
        return self._rules.get(content_type)
```

- 规则来自 pipeline 配置的 `content_type_rules` 字段
- 如果 pipeline 没有配置 `content_type_rules`，不启用此层，保持向后兼容

### Pipeline 处理流程

```
文档进入 Pipeline
    ↓
1. ContentTypeStrategy.resolve(contentType) → action
    ├─ None 或 "skip"  → 跳过，记录日志
    ├─ "source"        → Source 原生处理
    ├─ "download"      → Source 下载原始文件，不做转换
    └─ "convert"       → 进入第二级
            ↓
       2. TypeRuleResolver.resolve(extension) → converter_name
           ├─ None      → 跳过，记录日志
           ├─ "skip"    → 跳过
           └─ 具体名称   → 调用对应 Converter
```

### YAML 配置结构

```yaml
pipelines:
  dingtalk-to-hindsight:
    source: dingtalk
    dest: hindsight
    content_type_rules:          # 第一级：contentType → action
      DOCUMENT: convert
      ALIDOC: source
      ARCHIVE: skip
      IMAGE: skip
      OTHER: skip
    converters:                   # 第二级：extension → converter（仅 convert 动作）
      extensions:
        ".pdf": markitdown
        ".docx": markitdown
        ".xlsx": markitdown
        ".pptx": markitdown
        ".doc": markitdown
        ".html": markitdown
        ".txt": markitdown
        ".md": markitdown
        ".csv": markitdown

  dingtalk-to-baidu:
    source: dingtalk
    dest: baidu_cloud
    content_type_rules:
      DOCUMENT: download
      ALIDOC: skip
      ARCHIVE: download
      IMAGE: download
      OTHER: download
```

命名变更：原来的 `type_rules` 改为 `converters`，因为 ContentTypeStrategy 接管了类型层面的决策，剩下的纯粹是 converter 映射。

### ALIDOC 处理器体系

ALIDOC 的 contentType 映射到 `source` 动作后，由 Source 内部的 ALIDOC handler 处理：

- `adoc`（或无扩展名）→ 导出 Markdown（当前行为，保持不变）
- `axls / able / aform / abitable / amindmap` → 跳过，记录清晰的日志

改造要点：
- 移除 `dingtalk.py` 中 `_UNSUPPORTED_EXTENSIONS` 硬编码列表
- 子类型跳过逻辑整合到 ALIDOC handler 内部
- 未来可为每种 ALIDOC 子类型注册专门的处理器

### 日志改进

当前日志：`产品规划物料/解决方案/金智教育统一身份认证解决方案0528 [无处理规则: DOCUMENT]`

改造后日志应更清晰：
- `[contentType=DOCUMENT, action=convert, converter=未匹配扩展名]` — 转换时无对应 converter
- `[contentType=ALIDOC, action=source, 子类型=axls, 跳过]` — ALIDOC 子类型不支持

### 向后兼容

- 如果 pipeline 配置中没有 `content_type_rules` 字段，跳过 ContentTypeStrategy 层，直接走现有 TypeRuleResolver 逻辑
- 命令行模式（不带 YAML）行为不变

## 涉及文件

| 文件 | 改动 |
| ---- | ---- |
| `docpipe/pipeline.py` | 新增 `ContentTypeStrategy` 类，修改 Pipeline.run() 流程 |
| `docpipe/sources/dingtalk.py` | 移除 `_UNSUPPORTED_EXTENSIONS`，整合 ALIDOC handler 逻辑 |
| `docpipe/cli.py` | 支持从 YAML 读取 `content_type_rules` 和 `converters` 配置 |
| 配置文件 `docpipe.yaml` | 更新配置结构 |
