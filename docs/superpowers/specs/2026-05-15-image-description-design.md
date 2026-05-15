# 图片描述性信息处理设计

## 背景

从钉钉知识库下载的文档放入 Hindsight 后，图片引用（如 `![imag.png](https://alidocs.oss-cn-zhangjiakou/...)`）只显示一个无意义的文件名，缺乏信息量。

## 目标

1. 在放入 Hindsight 前，使用视觉模型生成图片内容的中文描述
2. 在 markdown 中用描述性内容替换原始图片引用
3. 在 Document meta 中保存映射关系：描述性文件名 → 原始 OSS URL

## 数据结构

### Document.extra 新增字段

```python
doc.meta.extra = {
    "image_metadata": {
        "architecture-diagram.png": {
            "original_url": "https://alidocs.oss-cn-zhangjiakou/a/6GO49kNeMs3gqyLZ/c8246c14466c45e2a95421e3252f6b692622.png",
            "description": "展示微服务三层架构，包含网关层、服务层和数据层"
        }
    }
}
```

### Markdown 输出格式

原始：
```markdown
![imag.png](https://alidocs.oss-cn-zhangjiakou/a/6GO49kNeMs3gqyLZ/c8246c14466c45e2a95421e3252f6b692622.png "")
```

处理后：
```markdown
**系统架构图**：展示微服务三层架构，包含网关层、服务层和数据层

![系统架构图](image://architecture-diagram.png)
```

## 架构

```
fetch() 流程：
  1. 调用 dws doc read 获取原始 markdown
  2. ImagePostProcessor 处理图片引用
     - 解析 markdown 中的图片引用
     - 下载图片
     - 调用 OpenAI 兼容 Vision API 生成描述
     - 替换 markdown 中的引用
  3. 将图片元数据存入 doc.meta.extra["image_metadata"]
  4. 返回处理后的 Document
```

## 组件设计

### ImagePostProcessor

```python
class ImagePostProcessor:
    """处理 markdown 中的图片引用，生成描述性名称和内容说明"""

    def __init__(self, vision_client: OpenAIVisionClient):
        self.vision_client = vision_client

    def process(self, markdown: str, source_context: str) -> tuple[str, dict]:
        """
        参数:
            markdown: 原始 markdown 文本
            source_context: 文档标题/路径，用于辅助描述

        返回:
            (处理后的 markdown, 图片元数据映射)
        """
```

### OpenAIVisionClient

```python
class OpenAIVisionClient:
    """使用 OpenAI 兼容接口的图片描述客户端"""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def describe(self, image_bytes: bytes, context: str) -> tuple[str, str]:
        """
        调用 vision API 生成图片描述
        返回: (filename, description)
            filename: 如 "architecture-diagram"
            description: 中文描述，如 "展示微服务三层架构"
        """
```

### 放置位置

在 `docpipe/sources/dingtalk.py` 中新增 `ImagePostProcessor`，保持 Source 职责单一。

## 配置

### 环境变量

```bash
IMAGE_DESCRIPTION_API_KEY=sk-xxx          # API 密钥
IMAGE_DESCRIPTION_BASE_URL=https://...    # API Base URL（兼容第三方）
IMAGE_DESCRIPTION_MODEL=gpt-4o            # 模型名称
IMAGE_DESCRIPTION_TIMEOUT=30              # 超时秒数（默认30）
IMAGE_DESCRIPTION_MAX_SIZE=10485760       # 最大图片尺寸 10MB
```

### YAML 配置文件

```yaml
sources:
  dingtalk:
    space_id: "xxx"
    image_description:
      enabled: true
      api_key: "${IMAGE_DESCRIPTION_API_KEY}"
      base_url: "${IMAGE_DESCRIPTION_BASE_URL}"
      model: "gpt-4o"
```

## 错误处理

| 场景 | 处理方式 |
|------|---------|
| 图片下载失败 | 保留原始引用，记录警告日志 |
| Vision API 调用失败 | 保留原始引用，记录错误日志 |
| 超时 | 重试 1 次，失败则保留原始引用 |
| 无效图片格式 | 跳过，保留原始引用 |

**原则：** 图片处理失败不应导致整个文档传输失败，降级为保留原始引用。

## Vision API 提示词

```
这是一篇文档《{context}》中的图片。

请完成两个任务：
1. 生成一个简短的英文文件名（3-5个单词，用连字符连接，如 "system-architecture-diagram"）
2. 用一句话描述图片内容（中文，适合在文档中作为图片说明）

请以 JSON 格式返回：
{"filename": "...", "description": "..."}
```

## 依赖

新增 `openai>=1.0.0` 到项目依赖。

## 测试

- 单元测试：mock VisionClient，验证 markdown 替换和元数据生成
- 集成测试：实际调用 API，验证描述质量
- 手动验证：运行完整 pipeline，检查输出 markdown 和 meta
