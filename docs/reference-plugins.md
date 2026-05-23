# 插件系统参考

docupipe 支持通过插件扩展 Source、Destination、Step、Converter 四类组件，无需修改核心代码。插件通过两阶段加载机制引入。

## 加载机制

### 阶段 1：Entry Points（import 时）

`import docupipe` 时自动调用 `load_plugins()`，扫描所有已安装包中注册的 `docupipe.plugins` entry_points：

```toml
# 在插件的 pyproject.toml 中
[project.entry-points."docupipe.plugins"]
my_plugin = "my_plugin:register"
```

`register` 函数在内部调用 `register_source`/`register_destination`/`register_step`/`register_converter` 注册组件。

### 阶段 2：本地目录（运行时）

解析 YAML 配置时加载 `plugin_dirs` 指定的目录，随后扫描约定目录 `~/.docupipe/plugins/`。目录中每个 `.py` 文件或含 `__init__.py` 的包都会被执行。

以 `_` 开头的文件名、`__pycache__`、`__init__.py`、非 `.py` 文件被自动跳过。

### 幂等性

已加载的目录不会重复加载，由 `_loaded_paths` 集合保证。同一目录在配置中出现多次时，仅第一次生效。

## 配置

在 YAML 文件顶层添加 `plugin_dirs`：

```yaml
plugin_dirs:
  - ./my-plugins         # 相对于 CWD
  - ~/team-plugins       # 用户目录
  - /opt/docupipe/plugins # 绝对路径

pipelines:
  - name: with-plugins
    source:
      custom_source: {}
```

路径支持 `~` 展开，相对于 CWD 解析。

## 冲突检测

同名组件注册时抛出 `ValueError`：

```
ValueError: source 'custom_source' 已注册 (来源: built-in)
```

错误信息显示冲突双方的来源，便于定位。来源标签分为三种：

| 来源 | 标签示例 |
|------|---------|
| 内置组件 | `built-in` |
| 本地文件 | `file:/path/to/plugin.py` |
| 本地包 | `package:/path/to/pkg/` |
| pip 包 | `pip:package-name` |

## CLI 命令

```bash
# 查看所有已加载的插件及其注册的组件
python -m docupipe plugins

# 查看组件时显示来源
python -m docupipe sources
python -m docupipe destinations
```

`sources` 和 `destinations` 命令在每个组件后显示 `(built-in)` 或 `(plugin: file:...)`。

## 实现细节

### 模块命名

本地 `.py` 文件导入时使用 `_docupipe_plugin_{filename}` 前缀作为模块名，避免与标准库或已安装包冲突。

### 引用顺序

阶段 1 的 entry_points 优先于阶段 2 的本地目录。当阶段 2 目录中存在同名组件时，由于入口点已在 import 时注册，阶段 2 会触发冲突检测异常。

## 相关文档

- [如何添加新组件](howto-add-component.md) — 编写组件的详细步骤
- [配置系统参考](reference-configuration.md) — 完整配置格式说明
