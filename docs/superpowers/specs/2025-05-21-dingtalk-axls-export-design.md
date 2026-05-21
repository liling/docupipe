# 钉钉电子表格（axls）导出支持

## 背景

DingtalkSource 当前不支持 `axls`（钉钉在线电子表格）类型的文档，它在 `_ALIDOC_UNSUPPORTED` 中被跳过。

钉钉电子表格与普通文档（adoc）不同，不能通过 `dws doc read` 或 `dws doc download` 获取内容。需要使用钉钉表格 MCP 的 `submit_export_job` / `query_export_job` 工具导出为 xlsx，再通过现有 markitdown converter 转为 markdown。

## 方案

### 数据流

```
DingtalkSource.fetch(axls)
  → 解密 dws token → FastMCP Client 连接钉钉 sheet MCP
  → submit_export_job(nodeId, "xlsx") → jobId
  → 轮询 query_export_job(jobId) → xlsx 下载链接
  → 下载 xlsx → 返回 Bundle（extension=xlsx）
  → 后续由 convert step + markitdown 转为 markdown
```

### 实现要点

#### 1. dws token 解密（`_decrypt_dws_token()`）

dws 将 OAuth token 加密存储在 `~/.dws/.data` 中：

- 加密方案：PBKDF2-SHA256（600000 次迭代）+ AES-256-GCM
- 密码：本机 MAC 地址
- 文件格式：salt(32 bytes) + nonce(12 bytes) + ciphertext+tag

Python 实现使用 `cryptography` 库，约 15 行代码。

#### 2. MCP 客户端（`_SheetExportClient`）

参照 `tencent.py` 的 `_TencentDocClient` 模式：

- 使用 FastMCP Client 连接钉钉 sheet MCP 端点
- Bearer token 认证（从 dws token 解密获取）
- 实现 `submit_export()` 和 `poll_export()` 方法
- 复用 `asyncio.Runner` 处理同步/异步转换

#### 3. DingtalkSource.fetch() 扩展

在 `fetch()` 方法中，对 axls 类型：

1. 从 `_ALIDOC_UNSUPPORTED` 中移除 `axls`
2. 使用 `_SheetExportClient` 提交导出任务
3. 轮询直到导出完成（最长等待 5 分钟，每次间隔 3 秒）
4. 下载 xlsx 文件，返回 Bundle（content_type 为 xlsx 二进制）

#### 4. 复用现有转换链

xlsx 文件走现有 pipeline：

- convert step 中 markitdown converter 已配置 `.xlsx: markitdown`
- 无需新增 converter 或 step

### 关键文件

| 文件 | 改动 |
|------|------|
| `sources/dingtalk.py` | 从 `_ALIDOC_UNSUPPORTED` 移除 `axls`；新增 `_SheetExportClient` 和 axls 导出逻辑 |

### 配置

无需新增配置。MCP 端点和 token 路径硬编码（钉钉 MCP 端点固定，dws token 路径固定 `~/.dws/.data`）。

### 依赖

- `cryptography`：用于 AES-256-GCM 解密（需检查是否已在依赖中）
- `fastmcp`：已引入（tencent.py 使用）

### 错误处理

- dws 未登录（`.data` 不存在）：SkipBundle + 明确提示
- 导出超时：SkipBundle + 日志记录
- token 过期：提示运行 `dws auth login` 刷新
