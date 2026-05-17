# Python 变量系统设计

## 概述

在 YAML 配置中增加 `variables` 块，支持通过 Python 脚本动态定义变量。变量在配置中用 `${var_name}` 引用，与现有环境变量使用统一语法，Python 变量优先级高于环境变量。

## YAML 配置结构

在配置文件顶层新增可选的 `variables` 块，支持两种形式：

**内嵌脚本：**

```yaml
variables:
  script: |
    import datetime
    today = datetime.date.today().isoformat()
    return {"today": today, "batch_id": "batch-" + today}

pipelines:
  - name: my-pipeline
    source:
      hindsight:
        bank_id: ${HINDSIGHT_BANK_ID}
        query: "date:${today}"
```

**外部文件：**

```yaml
variables:
  script_file: ./scripts/vars.py
```

外部脚本同样需要 `return {"key": "value", ...}`。

规则：
- `variables` 块是可选的。没有它时行为和现在完全一致。
- `script` 和 `script_file` 互斥，同时指定时 `script_file` 优先。

## 执行流程

当前流程：`加载 YAML → resolve_env_vars() → 解析组件配置`

新增步骤后：

```
加载 YAML
  → 执行 variables 脚本，得到 dict
  → resolve_vars()：统一处理 ${var}，优先级：Python 变量 > 环境变量 > 默认值
    → 解析组件配置（和现在一样）
```

对现有 `resolve_env_vars()` 的改造：
- 先查 Python 变量 dict
- 没找到再查 `os.environ`
- 都没有则用 `${VAR:-default}` 的默认值
- 都没有且无默认值，保留原始 `${VAR}` 字符串（和现在行为一致）

## 脚本执行模型

- 脚本通过 `exec()` 执行，包装成函数以支持 `return` 和 `import`
- 必须返回 dict，否则启动时报错
- value 都会被转为字符串（配置插值是字符串操作）
- 不做安全限制——能编辑配置文件的人本身就能执行任意代码

## 错误处理

| 场景 | 行为 |
|------|------|
| `variables` 块缺失 | 行为和现在一致 |
| `script` 和 `script_file` 都没指定 | 静默忽略 |
| 脚本返回非 dict | 启动时报错 |
| 脚本返回空 dict | 正常 |
| value 是非字符串类型 | `str()` 转换 |
| key 是非字符串类型 | 报错 |
| `script_file` 指向不存在的文件 | 启动时报错 |
| Python 变量与环境变量同名 | Python 变量覆盖 |
| `script` 和 `script_file` 同时指定 | `script_file` 优先，warn 日志 |

## 影响范围

- `docupipe/config.py`：改造 `resolve_env_vars()` 接受可选的 Python 变量 dict；新增脚本执行逻辑
- `docupipe/cli.py`：启动时读取 `variables` 配置并执行脚本
- 测试：覆盖脚本执行、插值优先级、错误处理

## 不做的事

- 不做 Python 沙箱或安全限制
- 不支持每个变量单独定义脚本
- 不支持变量间引用（脚本内部的 Python 逻辑自行处理依赖）
