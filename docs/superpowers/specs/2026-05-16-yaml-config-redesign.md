# YAML 配置重设计

## 概述

重构 `docpipe.yaml` 配置结构：

1. **source/destination 合并**：类型声明与配置合并为对象（`source: {dingtalk: {space_id: xxx}}`）
2. **全局配置顶层化**：去掉 `defaults` 层，组件配置（`hindsight`、`image_description`、`converters`）直接放顶层，pipeline 中可覆盖
3. **凭据环境变量插值**：支持 `${ENV_VAR}` 和 `${VAR:-default}` 语法，YAML 不再明文存储密码
4. **steps 管线**：`convert` 和 `image_description` 从 source/pipeline 逻辑中抽离为可组合的 step
5. **过滤下沉到 source**：移除 `content_type_rules`，由各 source 自行实现过滤（dingtalk 用 `include_types`，localdrive 用 `include`/`exclude`）

## 新 YAML 结构

顶层除 `pipelines` 外均为全局配置，pipeline 中可覆盖：

```yaml
# 全局配置（pipeline 中可覆盖）
hindsight:
  api_url: ${HINDSIGHT_API_URL}
  api_key: ${HINDSIGHT_API_KEY}
  bank_id: ${HINDSIGHT_BANK_ID}

image_description:
  api_key: ${IMAGE_API_KEY}
  base_url: ${IMAGE_BASE_URL}
  model: qwen3.5-flash

converters:
  extensions:
    ".pdf": mineru
    ".docx": mineru

pipelines:
  - name: shujuxian-to-hindsight
    source:
      dingtalk:
        space_id: nb9XJB7qpnkxQXyA
        folders: ["产品规划物料/解决方案"]
        include_types: [DOCUMENT, ALIDOC]
    destination:
      hindsight:
        context_prefix: "数据线知识库文档"
    steps:
      - convert
      - image_description
    options:
      resume: true
      sync: true

  - name: shujuxian-to-local
    source:
      dingtalk:
        space_id: nb9XJB7qpnkxQXyA
        folders: ["产品规划物料/解决方案"]
        include_types: [DOCUMENT, ALIDOC]
    destination:
      localdrive:
        output_dir: ./output
    steps:
      - convert
      - image_description

  - name: local-to-hindsight
    source:
      localdrive:
        input_dir: ./output
        include: ["*.md"]
    destination:
      hindsight:
        context_prefix: "本地文档"
    steps:
      - convert
```

## 配置解析规则

### 顶层结构

YAML 顶层只有两类 key：
- **`pipelines`** — pipeline 列表（必需）
- **其他 key** — 全局配置，按 key 名称匹配 pipeline 中的同名组件，做深度合并

### source / destination 合并

旧结构：
```yaml
source: dingtalk
source_config: {space_id: xxx}
```

新结构：
```yaml
source:
  dingtalk:
    space_id: xxx
```

解析时，`source`/`destination` 对象的 key 是 type 名称，value 是配置字典。同一个对象只允许一个 key。

### 全局配置合并

顶层配置按 type 名称与 pipeline 中的配置深度合并（pipeline 值覆盖全局）：

```yaml
# 顶层全局
hindsight:
  api_url: http://localhost:8888
  api_key: secret
  bank_id: docpipe

# pipeline 中
destination:
  hindsight:
    context_prefix: "文档"

# 解析后等价于
destination:
  hindsight:
    api_url: http://localhost:8888  # from 顶层
    api_key: secret                  # from 顶层
    bank_id: docpipe                 # from 顶层
    context_prefix: "文档"           # from pipeline
```

### steps

`steps` 是 pipeline 级别的处理步骤列表。每个 step 是一个字符串或对象：

- `- convert` — 字符串，使用全局 `converters` 配置做路由
- `- image_description` — 字符串，使用顶层 `image_description` 配置
- `- image_description: {model: gpt-4o}` — 对象，key 是 step 名称，value 是覆盖配置

**Step 接口：**

```python
class PipelineStep(ABC):
    @abstractmethod
    def process(self, doc: Document) -> Document:
        """处理文档，返回处理后的文档"""
```

**已注册的 step：**

| step 名称 | 说明 | 配置来源 |
|-----------|------|---------|
| `convert` | 检查 extension 是否有对应 converter，有则转换 | 全局 `converters` |
| `image_description` | 处理 markdown 中的图片，生成描述 | 顶层 `image_description` + pipeline 覆盖 |

**convert step 行为：**

对 fetch 到的文档，检查 `extra["extension"]` 是否在全局 `converters.extensions` 中有映射：
- 有映射 → 调用对应 converter，替换 `doc.content` 为转换结果
- 映射为 `"source"` → 跳过转换，原样传递
- 无映射 → 跳过转换，原样传递

这替代了原 `content_type_rules` 的转换路由功能。

**image_description step 行为：**

对 `doc.content`（markdown 文本）中的图片链接，下载图片并调用 Vision API 生成描述。行为和现有 `ImagePostProcessor` 一致。非文本内容跳过。

### ${ENV_VAR} 插值

YAML 解析后，递归遍历所有字符串值，替换环境变量引用：

- `${VAR}` → 替换为 `os.environ["VAR"]`，不存在则保持原样
- `${VAR:-default}` → 不存在时使用 `default`

```python
_ENV_PATTERN = re.compile(r'\$\{([^}]+)\}')

def resolve_env_vars(value):
    if isinstance(value, str):
        return _ENV_PATTERN.sub(_replace_env, value)
    if isinstance(value, dict):
        return {k: resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_env_vars(v) for v in value]
    return value
```

### source 过滤

过滤职责从 pipeline 的 `content_type_rules` 移到 source：

- **localdrive**：已有 `include`/`exclude` glob 规则
- **dingtalk**：新增 `include_types` 参数，值为 contentType 列表（如 `[DOCUMENT, ALIDOC]`）。不在列表中的类型在 `list_documents()` 阶段就跳过

`content_type_rules` 配置项完全移除。

## pipeline 执行流程

```
source.list_documents()  →  带过滤的文档列表
       ↓
source.fetch(doc_meta)   →  Document
       ↓
step: convert            →  检查 extension → converter 转换
       ↓
step: image_description  →  处理图片
       ↓
destination.write(doc)   →  写入目标
```

## 文件变更

| 文件 | 变更 |
|------|------|
| `docpipe/cli.py` | `_run_from_config` 重写：解析新结构、全局配置合并、env 插值、steps 构建 |
| `docpipe/pipeline.py` | 移除 `ContentTypeStrategy`，新增 `PipelineStep` 接口和 steps 执行逻辑 |
| `docpipe/steps/__init__.py` | 新建 step 注册表 |
| `docpipe/steps/base.py` | `PipelineStep` 抽象基类 |
| `docpipe/steps/convert.py` | `ConvertStep` — 从 pipeline.py 的转换逻辑抽取 |
| `docpipe/steps/image_description.py` | `ImageDescriptionStep` — 从 dingtalk.py 的图片处理抽取 |
| `docpipe/sources/dingtalk.py` | 移除 image_processor 相关代码，新增 `include_types` 过滤 |
| `docpipe/converters/resolver.py` | 保持不变 |
| `docpipe.yaml` | 改写为新结构 |

## 向后兼容

旧格式配置不再支持。升级时需手动转换 YAML 格式。

CLI 参数模式（`--source dingtalk --dest hindsight`）继续工作，不走 YAML 解析。

## 不包含

- steps 的插件化注册机制（硬编码 convert + image_description）
- step 的条件执行（如只在某个 source type 时执行）
- CLI 参数模式的改动
