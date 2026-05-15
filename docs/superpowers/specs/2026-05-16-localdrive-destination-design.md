# LocalDrive Destination 设计

## 概述

将 Pipeline 处理后的文档保存到本地磁盘，按原始路径重建目录结构。

## 配置

```yaml
pipelines:
  - name: wiki-to-local
    source: dingtalk
    destination: localdrive
    destination_config:
      output_dir: ./output
```

## 目录结构

以 `output_dir` 为根，用 `space_name` + `meta.path` 重建完整路径。每个文档旁生成同名 `.json` 伴生文件存储元信息：

```
output/
  知识库A/
    产品规划/
      方案.md
      方案.md.json        ← {id, title, hash, contentType, ...}
      需求文档.docx
      需求文档.docx.json
  知识库B/
    会议纪要.md
    会议纪要.md.json
```

扩展名根据 `doc.content_type` 推断：`markdown` → `.md`，`text` → `.txt`，其余用原始 extension。

## 接口实现

### `write(doc: Document) -> str`

1. 路径拼接：`output_dir / space_name / meta.path`
2. 如果 meta.path 已含扩展名且与 content_type 一致，直接使用；否则追加推断的扩展名
3. 目录不存在则 `mkdir -p` 创建
4. 文件已存在且内容相同（hash 比较）→ 跳过，返回路径
5. 文件已存在但内容不同 → 覆盖
6. 写入 `doc.content`（str 直接写，bytes 二进制写）
7. 写入伴生 `.json` 文件，内容为 `{id, title, contentType, extension, space_name, relative_path, full_path, content_hash}`
8. 返回写入的绝对路径

### `remove(doc_id: str) -> None`

根据状态文件中记录的 path 删除对应文件及其 `.json` 伴生文件。文件不存在时静默跳过。

## 文件

- `docpipe/destinations/localdrive.py` — 实现 `LocalDriveDestination`
- `docpipe/destinations/__init__.py` — 添加自动导入
- `tests/test_docpipe.py` — 添加单元测试

## 不包含

- 格式转换（由 pipeline 的 converter 决定）
- 文件权限设置
- 压缩打包
