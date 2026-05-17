# Bundle Context 字段标准化

## 目标

统一 `Bundle.context` 和 `FileItem.content_type` 的命名与值格式，消除当前扩展名/类型/MIME 混用的问题。

## 三条规则

1. **`FileItem.content_type` 必须是 MIME type** — 如 `text/markdown`、`application/pdf`、`image/png`，不是扩展名也不是自定义字符串
2. **context key 全部 snake_case** — source 特有字段加 `source_` 前缀（如 `dingtalk_content_type`），通用字段不加前缀
3. **`context["extension"]` 是纯扩展名** — 不含点号，所有 source 统一写入

## 字段变更

### 重命名

| 现有 key | 标准化后 key | 来源 |
|---|---|---|
| `contentType` | `dingtalk_content_type` | 钉钉 |
| `doc_type` | `tencent_doc_type` | 腾讯 |
| `updateTime` | `<source>_update_time` | 按来源区分 |

### 不变

- `extension` — 通用字段，纯扩展名不含点号
- `space_name` — 通用字段
- `absolute_path` — 通用字段
- Pipeline 注入字段：`id`、`title`、`path`、`filename`、`_source`、`hash`

## FileItem.content_type 修复

各 source fetch 中 content_type 赋值统一改为 MIME type：

- localdrive：`"markdown"` → `"text/markdown"`，`"pdf"` → `"application/pdf"`
- dingtalk：`content_type=extension` → 用 MIME 映射
- tencent：`content_type=ext` → 用 MIME 映射

新增工具函数 `guess_mime_type(extension: str, default: str = "") -> str`，集中处理扩展名→MIME 映射。放在 `utils.py` 中。

## Context 字段注册表

在 `models.py` 中以模块级注释维护字段说明，每个字段注明：类型、含义、写入者、读取者。新增 source/step 时必须先查阅此表，复用已有 key 或按规则添加新 key。

## 涉及文件

- `models.py` — 加 context 字段注册表注释
- `utils.py`（新建）— `guess_mime_type()` 工具函数
- `sources/localdrive.py` — 修复 content_type，extra key 改 snake_case
- `sources/dingtalk.py` — 修复 content_type，key 改 `dingtalk_` 前缀 + snake_case
- `sources/tencent.py` — 修复 content_type，key 改 `tencent_` 前缀 + snake_case
- `destinations/localdrive.py` — sidecar JSON key 对应更新
- `destinations/hindsight.py` — context key 读取对应更新
- 所有相关测试
