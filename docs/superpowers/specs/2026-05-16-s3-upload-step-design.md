# S3 Upload Step 设计文档

## 概述

新增 `s3_upload` 步骤，将 markdown 文档的附件上传到 S3 兼容存储（如 rustfs），替换 markdown 中的引用 URL，并从 bundle 中移除已上传的附件。

## 步骤注册

- 注册名：`s3_upload`
- 文件：`docpipe/steps/s3_upload.py`
- 在 `docpipe/steps/__init__.py` 中 import 触发注册

## 配置结构

支持全局默认 + pipeline 级 deep merge：

```yaml
# 全局默认
s3_upload:
  endpoint_url: "http://localhost:9000"
  region: "us-east-1"
  bucket: "my-bucket"
  access_key: ""
  secret_key: ""
  prefix: "attachments"
  url_prefix: "https://cdn.example.com"
  roles: ["image"]
  id_key: "id"

# pipeline 中可覆盖任意字段
pipelines:
  - source: ...
    steps:
      - s3_upload:
          bucket: "other-bucket"
```

`__init__` 接收所有配置参数，构建 boto3 client。

### 配置项说明

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `endpoint_url` | S3 兼容服务地址 | `"http://localhost:9000"` |
| `region` | 区域 | `"us-east-1"` |
| `bucket` | 存储桶名称 | `"my-bucket"` |
| `access_key` | 访问密钥 | `""` |
| `secret_key` | 密钥 | `""` |
| `prefix` | S3 key 前缀 | `"attachments"` |
| `url_prefix` | 自定义 URL 前缀 | `"https://cdn.example.com"` |
| `roles` | 要处理的附件角色列表 | `["image"]` |
| `id_key` | context 中取文档 ID 的 key | `"id"` |

## 处理流程

`process(bundle)` 逻辑：

1. 获取主文件 `bundle.main`，检查 `content` 是否为 `str`，不是则跳过返回
2. 按 `roles` 过滤 `bundle.files`，筛选要处理的附件
3. 逐个上传附件：
   - 获取 `document_id`：`bundle.context.get(id_key)`
   - 构建 S3 key：`{prefix}/{document_id}/{filename}`
   - 调用 `put_object` 上传 `FileItem.content`（bytes）
   - 拼接公共 URL：`{url_prefix}/{key}`
   - 正则替换 markdown 中指向该文件名的引用为新 URL
4. 从 `bundle.files` 中移除已上传且已替换的附件
5. 返回 bundle

### URL 替换规则

匹配 markdown 中指向该文件名的路径，包括带 `images/` 前缀和不带前缀两种情况：

- `![alt](images/foo.png)` → `![alt]({url_prefix}/{prefix}/{doc_id}/foo.png)`
- `![alt](foo.png)` → `![alt]({url_prefix}/{prefix}/{doc_id}/foo.png)`
- `[text](images/foo.png)` → `[text]({url_prefix}/{prefix}/{doc_id}/foo.png)`
- `[text](foo.png)` → `[text]({url_prefix}/{prefix}/{doc_id}/foo.png)`

## 边界情况与错误处理

| 情况 | 处理方式 |
|------|----------|
| 主文件不是 markdown（content 不是 str） | 直接返回原始 bundle |
| 没有符合 roles 的附件 | 直接返回，跳过上传 |
| `id_key` 在 context 中不存在 | 用 `"unknown"` 作为 fallback，打 warning 日志 |
| 单个文件上传失败 | 记录 warning 日志，跳过该文件（不替换 URL、不移除），继续处理其余文件 |
| markdown 中找不到该文件名的引用 | 文件仍然上传，但不移除（下游可能还需要） |

## 依赖

- `boto3` — S3 兼容 SDK，需添加到项目依赖
