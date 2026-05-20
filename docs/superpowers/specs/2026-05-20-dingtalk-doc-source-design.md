# Dingtalk Source doc 模式设计

## 背景

现有 dingtalk source 只支持从钉钉知识库（wiki）获取文档。用户需要从钉盘/文档的任意文件夹（包括别人共享的文件夹）获取文档内容。

## 方案

在现有 DingtalkSource 中新增 `mode` 参数，`wiki`（默认）走现有知识库逻辑，`doc` 走文件夹逻辑。fetch() 完全复用，只修改 list()。

## 配置

```yaml
# wiki 模式（默认，向后兼容）
source:
  dingtalk:
    space: "平台产品知识库"

# doc 模式
source:
  dingtalk:
    mode: doc
    folder_id: "g1YGl6Pm2Db8DZExP5MClVxLq0Ee4p79"
    include_types: [DOCUMENT]  # 可选
```

## 参数校验

- `mode: wiki`（默认）：必须提供 `space` 或 `space_id`
- `mode: doc`：必须提供 `folder_id`，不使用 `space`/`space_id`/`folders`
- `mode` 未知值：报错

## __init__ 变更

- 新增 `mode` 参数，默认 `"wiki"`
- wiki 模式：现有逻辑不变
- doc 模式：只存 `folder_id`，不解析 `space_id`/`space_name`

## list() 的 doc 模式

在 `list()` 方法开头分支：
```python
def list(self) -> list[BundleMeta]:
    if self._mode == "doc":
        return self._list_doc_mode()
    # 现有 wiki 模式逻辑不变
```

`_list_doc_mode()` 流程：
1. 调用 `_WikiClient.list_nodes_by_folder(folder_id)` 递归获取所有节点
2. 过滤文件夹节点（只保留文件和在线文档）
3. 可选 `include_types` 过滤
4. 构建路径：以文件夹名为根，递归拼接子路径
5. 构建 BundleMeta（id、title、path、extra 与 wiki 模式一致）

### _WikiClient 新增方法

```python
def list_nodes_by_folder(self, folder_id: str) -> list[dict]:
    """dws doc list --folder <folderId>"""
```

返回的节点结构与 wiki 模式相同（包含 nodeId、name、nodeType、extension、contentType、updateTime 等）。

### 递归遍历

复用现有的递归逻辑模式。doc 模式的入口是 folder_id 而非 workspace_id + folder_id，递归时通过 hasChildren 判断是否继续深入。

## fetch() 复用

fetch() 不做任何修改。两种模式的文档获取方式相同：
- ALIDOC 类型 → `dws doc read` 读取 Markdown
- 文件类型 → `dws doc download` 下载二进制

## context 字段

doc 模式与 wiki 模式的 context 字段一致，唯一区别：
- `space_name`：wiki 模式设置为知识库名称，doc 模式为空
- 其余字段（mtime、dingtalk_content_type、extension 等）行为相同

## 影响范围

- `docupipe/sources/dingtalk.py`：修改 `__init__` 和 `list()`，新增 `_list_doc_mode()`
- `_WikiClient`：新增 `list_nodes_by_folder()` 方法
- 无架构变更，无新增依赖
