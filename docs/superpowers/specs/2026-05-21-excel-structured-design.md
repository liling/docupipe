# Excel 结构化提取 Step 设计文档

## 目标

新建 `excel_structured` Step，用 openpyxl 直接读取 Excel 文件，做预处理后按 Sheet 输出为独立的 Markdown 表格文件，配合 Hindsight destination 实现精细化知识管理。

## 组件定位

- **类型**：Step（处理步骤）
- **注册名**：`excel_structured`
- **位置**：`docupipe/steps/excel_structured.py`
- **位置**：在 pipeline 中放在 `convert` step 之前

## Pipeline 流程

```
source → excel_structured → convert → ... → dest
           ↓ (xlsx)           ↓ (其他)
        转为 Markdown 表格   原样传递，由 convert 处理
           ↓
        convert 检测已是 md，跳过
```

- xlsx 文件：excel_structured 处理后输出 Markdown，convert step 跳过（已是 md）
- 其他格式：excel_structured 原样返回（pass-through），convert step 正常处理

## 输入输出

### 输入

Bundle 的 `main` FileItem：
- `content`：bytes（.xlsx 文件原始内容）
- `content_type`：包含 `spreadsheet` 或 `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- `bundle.context["extension"]` 为 `xlsx`

### 输出

替换 Bundle 的 files 列表：
- 第一个 Sheet → `role="main"` 的 FileItem（Markdown 表格）
- 其余 Sheet → `role="attachment"` 的 FileItem（Markdown 表格）
- 如果只有一个 Sheet，则只输出一个 main FileItem
- 每个 FileItem：
  - `name`：`{原文件名stem}_{sheet名}.md`
  - `content`：Markdown 表格字符串
  - `content_type`：`text/markdown`
  - `role`：`"main"`（第一个 Sheet）或 `"attachment"`（其余）

Bundle context 更新：
- `extension` → `"md"`

### 输出格式示例

每个 Sheet 的 Markdown 表格：

```markdown
## Sheet1

| 姓名 | 部门 | 职位 | 入职日期 |
|------|------|------|----------|
| 张三 | 销售部 | 经理 | 2023-01-01 |
| 李四 | 技术部 | 工程师 | 2022-06-15 |
```

## 预处理逻辑

通过 step 配置项控制，所有选项均有默认值：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `fill_merged` | `true` | 扫描合并区域，将左上角值填充到区域内所有单元格 |
| `skip_hidden` | `true` | 跳过隐藏的行和列 |
| `skip_empty` | `true` | 跳过全空的行和列 |

配置示例：

```yaml
steps:
  - excel_structured:
      fill_merged: true
      skip_hidden: true
      skip_empty: true
```

### Pass-through 行为

当输入文件不是 xlsx 时（通过 `bundle.context["extension"]` 判断），step 原样返回 Bundle，不做任何处理。

## Hindsight Destination 改动

### 新增 `process_roles` 配置项

- 类型：`list[str]`
- 默认值：`["main"]`
- 作用：控制 `write()` 方法处理哪些 role 的 FileItem

当配置为 `["main", "attachment"]` 时，`write()` 遍历所有匹配 role 的 FileItem，为每个调用 `retain_batch()`。

### 每个 Sheet 的 document_id 区分

需要确保每个 Sheet 有不同的 `document_id`。`_build_retain_item` 在遍历多文件时，从 FileItem 的 name 中解析 Sheet 名（格式为 `{stem}_{sheet}.md`），将其作为 `_sheet_name` 注入 context 副本，用于 `document_id_template` 插值。

```yaml
destination:
  hindsight:
    process_roles: [main, attachment]
    document_id_template: "${context._source}:${context.id}:${context._sheet_name}"
```

### _build_retain_item 改动

新增可选参数 `file_item: FileItem | None` 和 `sheet_name: str | None`：
- 当 `file_item` 不为 None 时，用该 FileItem 的内容替代 `bundle.main`
- 当 `sheet_name` 不为 None 时，将其注入 context 副本的 `_sheet_name` 字段
- 不传参时行为不变，保持向后兼容

### write() 方法改动

当 `process_roles` 包含多个 role 时，遍历所有匹配的 FileItem：
```python
for role in self._process_roles:
    for file_item in bundle.files_by_role(role):
        item = self._build_retain_item(bundle, file_item=file_item, sheet_name=_parse_sheet_name(file_item.name))
        client.retain_batch(self.bank_id, items=[item], retain_async=True)
```

返回第一个文件的 `document_id`（保持接口兼容）。

## 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `docupipe/steps/excel_structured.py` | 新建 | Step 实现 |
| `docupipe/steps/__init__.py` | 修改 | import 注册 |
| `docupipe/destinations/hindsight.py` | 修改 | 支持 process_roles |
| `docupipe/models.py` | 修改 | Bundle context 字段注册表中添加 `_sheet_name` |
| `tests/test_excel_structured.py` | 新建 | 测试 |

## 依赖

- `openpyxl`：新增运行时依赖

## 配置示例

```yaml
pipelines:
  - name: excel-to-hindsight
    source:
      localdrive:
        path: ./data/excel
        include: ["*.xlsx"]
    steps:
      - excel_structured
    destination:
      hindsight:
        process_roles: [main, attachment]
        document_id_template: "${context._source}:${context.id}:${context._sheet_name}"

  - name: mixed-docs-to-hindsight
    source:
      localdrive:
        path: ./data/docs
    steps:
      - excel_structured    # xlsx 走结构化，其他格式 pass-through
      - convert             # 处理其他格式，xlsx 已是 md 跳过
    destination:
      hindsight:
        process_roles: [main, attachment]
```
