# Resolve Attachments Step 设计文档

## 概述

新增 `resolve_attachments` 步骤，解析 markdown 主文件中的本地文件引用，从磁盘读取这些文件加入 bundle。通常放在 `s3_upload` 之前使用。

## 步骤注册

- 注册名：`resolve_attachments`
- 文件：`docpipe/steps/resolve_attachments.py`
- 在 `docpipe/steps/__init__.py` 中 import 触发注册

## 处理流程

1. 获取 `bundle.main`，检查内容是否为 `str`（markdown），不是则跳过返回
2. 从 `bundle.context` 取 `absolute_path`，推导主文件所在目录作为基准目录
3. 正则扫描 markdown 中所有 `![alt](path)` 和 `[text](path)` 引用
4. 过滤掉外部引用（`http://`、`https://`、`#`、`data:` 开头），只保留相对路径
5. 对每个本地引用：
   - 拼接基准目录得到绝对路径
   - 文件不存在则跳过（warning 日志）
   - 读取文件内容（文本读 str，二进制读 bytes）
   - 根据 role 规则分配 role：图片扩展名 → `"image"`，其他 → `"attachment"`
   - 创建 FileItem 并加入 bundle（name 用引用路径，如 `images/photo.png`）
6. 返回 bundle

## 配置

无配置项。`__init__` 只接收 `**kwargs`。步骤依赖 bundle 中已有的 `absolute_path` 和 markdown 内容。

## 边界情况

| 情况 | 处理方式 |
|------|----------|
| 主文件不是 markdown（content 不是 str） | 直接返回原始 bundle |
| `absolute_path` 不在 context 中 | 跳过，打 warning 日志 |
| 引用的文件不存在 | 跳过该文件，打 warning 日志 |
| 文件已在 bundle 中（同名） | bundle.add() 自动重命名 |

## 依赖

无新依赖，使用标准库。
