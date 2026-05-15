# LocalDrive Source 设计

## 概述

用 `LocalDriveSource` 替换现有 `LocalSource`，支持从本地文件夹读取所有类型文件。现有 `local.py` 仅扫描 markdown 文件，新实现扫描所有文件并通过 pipeline 已有的 converter 系统处理格式转换。

注册名为 `localdrive`，与 `LocalDriveDestination` 保持一致。额外注册 `local` 别名向后兼容。

## 配置

```yaml
pipelines:
  - name: docs-to-hindsight
    source: localdrive
    destination: hindsight
    source_config:
      input_dir: ./docs
      include: ["*.pdf", "*.docx", "*.md"]
      exclude: [".git/**", "*.tmp"]
```

CLI 用法：

```bash
docpipe run --source localdrive --dest hindsight --input-dir ./docs
```

## 过滤规则

`include` 和 `exclude` 均为可选的 glob 列表，匹配相对于 `input_dir` 的路径。

- `include` 为空或未设置 → 包含所有文件
- `exclude` 优先于 `include`：先检查是否被排除，再检查是否被包含
- 使用 `pathlib.PurePath.match()` 做 glob 匹配

## 目录遍历

递归扫描 `input_dir` 下所有文件，跳过：
- 隐藏目录（`.` 开头）
- 隐藏文件（`.` 开头）

## 接口实现

### `__init__(self, input_dir: str, include: list[str] | None = None, exclude: list[str] | None = None, **kwargs)`

验证 `input_dir` 存在且为目录，存储 `include`/`exclude` 规则。

### `list_documents() -> list[DocumentMeta]`

1. 递归遍历目录，跳过隐藏目录和隐藏文件
2. 对每个文件，检查 exclude/include 规则
3. 无扩展名文件抛出 `SkipDocument`
4. 计算 SHA256 内容哈希
5. 返回 `DocumentMeta`，按路径排序

```python
DocumentMeta(
    id=sha256(relative_path),
    title=file_stem,
    path=str(relative_path),
    hash=sha256(file_content),
    extra={
        "extension": ".pdf",
        "absolute_path": str(absolute_path),
        "size": file_size,
    },
)
```

### `fetch(doc_meta: DocumentMeta) -> Document`

1. 从 `extra["absolute_path"]` 读取文件
2. 文本扩展名（`.md`, `.txt`, `.csv`, `.json`, `.yaml`, `.yml`, `.xml`, `.html`, `.css`, `.js`, `.ts`, `.py`, `.toml`, `.ini`, `.cfg`, `.log`, `.rst`）读取为 `str`
3. 其余扩展名读取为 `bytes`
4. `content_type` = 扩展名去掉 `.`（如 `"pdf"`, `"md"`）

## 与 Pipeline 集成

localdrive 不做格式转换，交给 pipeline 已有的处理链路：

```
localdrive 扫描 .pdf → content_type="pdf"
→ content_type_rules 判断为 "convert"
→ TypeRuleResolver 找到 markitdown converter
→ converter 转 markdown
→ 写入 destination
```

converter 需要文件路径，通过 `extra["absolute_path"]` 传递。

## 文件变更

| 文件 | 变更 |
|------|------|
| `docpipe/sources/localdrive.py` | 新建 `LocalDriveSource`，注册为 `localdrive` + `local` 别名 |
| `docpipe/sources/local.py` | 删除（功能已迁移到 localdrive.py） |
| `docpipe/cli.py` | `_extract_source_config` 增加 `localdrive` 分支，透传 `include`/`exclude` |
| `tests/test_docpipe.py` | 更新 `LocalSource` 相关测试，增加过滤规则测试 |

## 测试

用 `tmp_path` 创建临时目录和文件，测试：

- 递归扫描子目录
- 跳过隐藏目录和隐藏文件
- include 规则过滤
- exclude 规则过滤
- exclude 优先于 include
- 无扩展名文件跳过
- 文本文件读取为 `str`
- 二进制文件读取为 `bytes`
- content_type 为扩展名（无 `.`）
- hash 计算正确

## 不包含

- 格式转换（由 pipeline converter 处理）
- 文件监听/增量扫描
- 符号链接特殊处理
- 文件权限检查
