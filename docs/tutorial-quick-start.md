# 教程：从钉钉知识库同步文档到 Hindsight Memory

你将搭建一条完整的文档 pipeline：从钉钉知识库读取文档，转换为 Markdown，为图片添加 AI 描述，然后写入 Hindsight Memory。整个过程无需写一行 Python 代码。

## 你需要准备

- Python 3.11+
- 钉钉知识库访问权限
- Hindsight Memory 服务地址和 API key
- OpenAI 兼容的图片描述 API key（或使用已有的 OpenAI key）

## Step 1: 安装和准备

```bash
# 安装 docupipe
pip install docupipe

# 安装 dws（钉钉 CLI，macOS/Linux）
curl -fsSL https://raw.githubusercontent.com/DingTalk-Real-AI/dingtalk-workspace-cli/main/scripts/install.sh | sh

# 登录钉钉（浏览器扫码）
dws auth login
```

运行 `dws auth login` 后，浏览器会弹出钉钉扫码页面。扫码完成后终端会显示"登录成功"。

## Step 2: 创建配置文件

创建 `docupipe.yaml`：

```yaml
hindsight:
  api_url: ${HINDSIGHT_API_URL}
  api_key: ${HINDSIGHT_API_KEY}
  bank_id: ${HINDSIGHT_BANK_ID}

image_description:
  api_key: ${IMAGE_DESCRIPTION_API_KEY}
  base_url: ${IMAGE_DESCRIPTION_BASE_URL}
  model: ${IMAGE_DESCRIPTION_MODEL:-gpt-4o}

converters:
  extensions:
    ".pdf": mineru
    ".docx": markitdown
    ".pptx": markitdown

pipelines:
  - name: wiki-to-hs
    source:
      dingtalk:
        space: "产品知识库"
    destination:
      hindsight:
        context_prefix: "知识库"
    steps:
      - convert
      - image_description
```

## Step 3: 设置环境变量

创建 `.env` 文件：

```bash
HINDSIGHT_API_URL=http://localhost:8888
HINDSIGHT_API_KEY=your_hs_api_key
HINDSIGHT_BANK_ID=your_bank_id
IMAGE_DESCRIPTION_API_KEY=sk-your_openai_key
IMAGE_DESCRIPTION_BASE_URL=https://api.openai.com/v1
IMAGE_DESCRIPTION_MODEL=gpt-4o
```

## Step 4: 运行 pipeline

```bash
python -m docupipe run --pipeline wiki-to-hs
```

你会看到类似这样的实时进度：

```
✅ 产品规划/解决方案/方案A.docx
✅ 技术文档/使用指南.md
⏭️  README.md (mtime 无变化)
❌ 开发文档/API.md: 网络超时
```

执行完毕后会显示汇总表格：

```
          Pipeline: wiki-to-hs 完成!
┌──────┬──────┬──────┬──────┬─────────┐
│ 总数 │ 成功 │ 跳过 │ 失败 │ 耗时    │
├──────┼──────┼──────┼──────┼─────────┤
│   10 │    8 │    1 │    1 │ 1分23秒 │
└──────┴──────┴──────┴──────┴─────────┘
```

## Step 5: 增量同步

再次运行时，已处理的文档会自动跳过：

```bash
python -m docupipe run --pipeline wiki-to-hs --mode incremental
```

只处理新增的文档。

## 你搭建了什么

- 一条自动化的文档 pipeline：钉钉知识库 → 格式转换 → AI 图片描述 → Hindsight Memory
- 配置完全声明式，修改参数不需要改代码
- 管道可中断、可恢复、可增量运行

## 下一步

- [配置系统参考](reference-configuration.html) — 完整的配置选项
- [如何添加新组件](howto-add-component.html) — 扩展 pipeline 能力
- [运行模式设计](explanation-modes.html) — 理解不同模式的适用场景
