# 钉钉知识库同步到 Hindsight 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建独立的 docpipe CLI 工具，从钉钉知识库下载内容转 Markdown 保存到本地，再增量同步到 Hindsight。

**Architecture:** 两步流水线——download 命令通过 subprocess 调用 dws CLI 遍历知识库并下载内容（在线文档读 Markdown，文件用 markitdown 转 Markdown），本地镜像知识库目录结构；retain 命令扫描本地 Markdown 计算 hash，增量调用 Hindsight API 上传。各自维护 JSON 状态文件支持断点续传和增量同步。

**Tech Stack:** Python 3.11+ / Click / markitdown / hindsight-client / dws CLI (subprocess)

---

## File Structure

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | 项目元数据、依赖、CLI 入口点 |
| `dwsdocs_downloader/__init__.py` | 包标记 |
| `dwsdocs_downloader/__main__.py` | `python -m` 入口 |
| `dwsdocs_downloader/config.py` | dataclass 配置 + 环境变量读取 |
| `dwsdocs_downloader/display.py` | 进度条 + 日志输出（简化版，基于 print + tqdm） |
| `dwsdocs_downloader/state.py` | JSON 状态文件读写（nodeId → hash 映射） |
| `dwsdocs_downloader/wiki_client.py` | 封装 dws CLI 调用（subprocess → JSON） |
| `dwsdocs_downloader/converter.py` | markitdown 文件转 Markdown |
| `dwsdocs_downloader/downloader.py` | 知识库下载编排（递归遍历 + 类型分发） |
| `dwsdocs_downloader/retain.py` | 扫描本地 Markdown → Hindsight retain |
| `dwsdocs_downloader/cli.py` | Click CLI：download / retain 两个子命令 |
| `tests/__init__.py` | 测试包标记 |
| `tests/test_state.py` | StateManager 单元测试 |
| `tests/test_wiki_client.py` | WikiClient 单元测试（mock subprocess） |
| `tests/test_converter.py` | FileConverter 单元测试 |
| `tests/test_downloader.py` | Downloader 集成测试 |
| `tests/test_retain.py` | RetainRunner 单元测试 |
| `tests/conftest.py` | 共享 fixtures（tmp_output_dir） |

---

### Task 1: 项目初始化

**Files:**
- Create: `pyproject.toml`
- Create: `dwsdocs_downloader/__init__.py`
- Create: `dwsdocs_downloader/__main__.py`

- [ ] **Step 1: 创建 pyproject.toml**

```toml
[project]
name = "dwsdocs-downloader"
version = "0.1.0"
description = "钉钉知识库内容下载并同步到 Hindsight"
requires-python = ">=3.11"
dependencies = [
    "click>=8.1.0",
    "markitdown[all]>=0.1.0",
    "hindsight-client>=0.1.0",
    "tqdm>=4.66.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "responses>=0.24.0",
]

[project.scripts]
dwsdocs-downloader = "dwsdocs_downloader.cli:main"

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["dwsdocs_downloader*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 2: 创建包文件**

`dwsdocs_downloader/__init__.py`:
```python
```

`dwsdocs_downloader/__main__.py`:
```python
from dwsdocs_downloader.cli import main

main()
```

- [ ] **Step 3: 安装开发依赖并验证**

Run: `cd ~/src/ai/docpipe && pip install -e ".[dev]"`
Expected: 安装成功

Run: `python -m dwsdocs_downloader --help`
Expected: 报错（cli.py 不存在），确认入口可运行

- [ ] **Step 4: 初始化 git 仓库并提交**

```bash
cd ~/src/ai/docpipe
echo "__pycache__/\n*.egg-info/\n.env\noutput/" > .gitignore
git init
git add .
git commit -m "feat: 初始化 dwsdocs-downloader 项目"
```

---

### Task 2: config 模块

**Files:**
- Create: `dwsdocs_downloader/config.py`
- Test: `tests/test_config.py`（不单独建文件，本 task 小）

- [ ] **Step 1: 实现 config.py**

```python
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    output_dir: Path = field(default_factory=lambda: Path("./output"))
    hindsight_api_url: str = ""
    hindsight_api_key: str = ""
    hindsight_bank_id: str = ""

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            hindsight_api_url=os.environ.get("HINDSIGHT_API_URL", ""),
            hindsight_api_key=os.environ.get("HINDSIGHT_API_KEY", ""),
            hindsight_bank_id=os.environ.get("HINDSIGHT_BANK_ID", ""),
        )
```

- [ ] **Step 2: 验证**

Run: `cd ~/src/ai/docpipe && python -c "from dwsdocs_downloader.config import Config; c = Config.from_env(); print(c)"`
Expected: 打印 Config 实例，hindsight 字段为空字符串（无环境变量时）

- [ ] **Step 3: 提交**

```bash
git add dwsdocs_downloader/config.py
git commit -m "feat: 添加 Config dataclass"
```

---

### Task 3: display 模块

**Files:**
- Create: `dwsdocs_downloader/display.py`

- [ ] **Step 1: 实现 display.py**

简化版进度输出，用 tqdm + print，不引入 Rich 依赖。

```python
from __future__ import annotations

import sys
import time


class Display:
    def __init__(self):
        self.total: int = 0
        self.completed: int = 0
        self.failed: int = 0
        self._start_time: float = 0
        self._title: str = ""

    def start(self, title: str, total: int) -> None:
        self._title = title
        self.total = total
        self.completed = 0
        self.failed = 0
        self._start_time = time.time()

    def stop(self) -> None:
        pass

    def log(self, level: str, message: str) -> None:
        print(f"[{level}] {message}")

    def result(self, status: str, message: str) -> None:
        icons = {"success": "✅", "skip": "⏭️ ", "error": "❌", "info": "ℹ️ "}
        icon = icons.get(status, "·")
        print(f"{icon} {message}")

    def update_progress(self) -> None:
        self.completed += 1
        done = self.completed + self.failed
        self.log("INFO", f"{self._title} {done}/{self.total}")

    def add_failure(self) -> None:
        self.failed += 1

    def print_summary(self) -> None:
        elapsed = time.time() - self._start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        print(f"\n{self._title}完成!")
        print(f"  总数: {self.total}  成功: {self.completed}  失败: {self.failed}  耗时: {minutes}分{seconds}秒")
```

- [ ] **Step 2: 提交**

```bash
git add dwsdocs_downloader/display.py
git commit -m "feat: 添加 Display 日志/进度输出"
```

---

### Task 4: state 模块

**Files:**
- Create: `dwsdocs_downloader/state.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_state.py`

- [ ] **Step 1: 写失败测试 tests/test_state.py**

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dwsdocs_downloader.state import StateManager


@pytest.fixture
def state_dir(tmp_path):
    return tmp_path / "state"


def test_save_and_load(state_dir):
    mgr = StateManager(state_dir, "download")
    mgr.save({"node1": "hash1", "node2": "hash2"})

    loaded = mgr.load()
    assert loaded == {"node1": "hash1", "node2": "hash2"}


def test_load_empty(state_dir):
    mgr = StateManager(state_dir, "download")
    assert mgr.load() == {}


def test_save_creates_directory(state_dir):
    mgr = StateManager(state_dir, "download")
    assert not state_dir.exists()
    mgr.save({"a": "b"})
    assert (state_dir / "download_state.json").exists()


def test_content_hash(tmp_path):
    from dwsdocs_downloader.state import content_hash

    f = tmp_path / "test.md"
    f.write_text("hello", encoding="utf-8")
    h1 = content_hash(f)
    assert len(h1) == 64  # sha256 hex

    f.write_text("world", encoding="utf-8")
    h2 = content_hash(f)
    assert h1 != h2
```

- [ ] **Step 2: 创建 tests/conftest.py**

```python
```

`tests/__init__.py`:
```python
```

- [ ] **Step 3: 运行测试验证失败**

Run: `cd ~/src/ai/docpipe && python -m pytest tests/test_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dwsdocs_downloader.state'`

- [ ] **Step 4: 实现 state.py**

```python
from __future__ import annotations

import hashlib
import json
from pathlib import Path


class StateManager:
    def __init__(self, state_dir: Path, task_type: str):
        self._path = state_dir / f"{task_type}_state.json"

    def load(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self, hashes: dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(hashes, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def content_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
```

- [ ] **Step 5: 运行测试验证通过**

Run: `cd ~/src/ai/docpipe && python -m pytest tests/test_state.py -v`
Expected: 4 passed

- [ ] **Step 6: 提交**

```bash
git add dwsdocs_downloader/state.py tests/
git commit -m "feat: 添加 StateManager 状态管理和 content_hash"
```

---

### Task 5: wiki_client 模块

**Files:**
- Create: `dwsdocs_downloader/wiki_client.py`
- Create: `tests/test_wiki_client.py`

- [ ] **Step 1: 写失败测试 tests/test_wiki_client.py**

```python
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from dwsdocs_downloader.wiki_client import WikiClient


def _mock_run(stdout: str, returncode: int = 0):
    result = MagicMock()
    result.stdout = stdout
    result.returncode = returncode
    result.stderr = ""
    return result


@pytest.fixture
def client():
    return WikiClient()


def test_list_nodes(client):
    nodes = [
        {"nodeId": "abc123", "title": "文档1", "nodeType": "doc"},
        {"nodeId": "def456", "title": "文件夹", "nodeType": "folder"},
    ]
    with patch("dwsdocs_downloader.wiki_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_run(json.dumps({"items": nodes}))
        result = client.list_nodes(workspace_id="space1")
        assert len(result) == 2
        assert result[0]["nodeId"] == "abc123"
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "list" in cmd
        assert "--workspace" in cmd
        assert "space1" in cmd


def test_list_nodes_with_folder(client):
    with patch("dwsdocs_downloader.wiki_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_run(json.dumps({"items": []}))
        client.list_nodes(workspace_id="space1", folder_id="folder1")
        cmd = mock_run.call_args[0][0]
        assert "--folder" in cmd
        assert "folder1" in cmd


def test_list_nodes_pagination(client):
    page1 = {"items": [{"nodeId": "a"}], "nextPageToken": "tok1"}
    page2 = {"items": [{"nodeId": "b"}]}
    with patch("dwsdocs_downloader.wiki_client.subprocess.run") as mock_run:
        mock_run.side_effect = [
            _mock_run(json.dumps(page1)),
            _mock_run(json.dumps(page2)),
        ]
        result = client.list_nodes(workspace_id="space1")
        assert len(result) == 2
        assert mock_run.call_count == 2


def test_get_node_info(client):
    info = {"nodeId": "abc", "title": "测试文档", "contentType": "ALIDOC", "extension": "adoc"}
    with patch("dwsdocs_downloader.wiki_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_run(json.dumps(info))
        result = client.get_node_info("abc")
        assert result["contentType"] == "ALIDOC"


def test_read_document(client):
    with patch("dwsdocs_downloader.wiki_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_run(json.dumps({"result": [{"type": "markdown", "content": "# Hello"}]}))
        result = client.read_document("abc")
        assert "Hello" in result


def test_download_file(client):
    with patch("dwsdocs_downloader.wiki_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_run(json.dumps({"downloadUrl": "https://example.com/file.pdf"}))
        result = client.download_file("abc")
        assert result == "https://example.com/file.pdf"


def test_get_space_info(client):
    info = {"id": "space1", "name": "技术文档库"}
    with patch("dwsdocs_downloader.wiki_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_run(json.dumps(info))
        result = client.get_space_info("space1")
        assert result["name"] == "技术文档库"


def test_dws_error_raises(client):
    with patch("dwsdocs_downloader.wiki_client.subprocess.run") as mock_run:
        mock_run.return_value = _mock_run("", returncode=1)
        with pytest.raises(RuntimeError, match="dws 命令失败"):
            client.get_space_info("space1")
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd ~/src/ai/docpipe && python -m pytest tests/test_wiki_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现 wiki_client.py**

```python
from __future__ import annotations

import json
import subprocess


class WikiClient:
    def _run_dws(self, args: list[str]) -> dict | list:
        cmd = ["dws"] + args + ["--format", "json", "--yes"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(f"dws 命令失败: {' '.join(args)}\n{result.stderr}")
        if not result.stdout.strip():
            return {}
        return json.loads(result.stdout)

    def list_nodes(self, workspace_id: str, folder_id: str | None = None) -> list[dict]:
        all_items: list[dict] = []
        page_token: str | None = None
        while True:
            args = ["doc", "list", "--workspace", workspace_id, "--page-size", "50"]
            if folder_id:
                args += ["--folder", folder_id]
            if page_token:
                args += ["--page-token", page_token]
            data = self._run_dws(args)
            items = data.get("items", []) if isinstance(data, dict) else []
            all_items.extend(items)
            page_token = data.get("nextPageToken") if isinstance(data, dict) else None
            if not page_token:
                break
        return all_items

    def get_node_info(self, node_id: str) -> dict:
        return self._run_dws(["doc", "info", "--node", node_id])

    def read_document(self, node_id: str) -> str:
        data = self._run_dws(["doc", "read", "--node", node_id])
        if isinstance(data, dict):
            results = data.get("result", [])
            parts = []
            for block in results:
                if isinstance(block, dict) and block.get("type") == "markdown":
                    parts.append(block.get("content", ""))
            return "\n".join(parts)
        return str(data)

    def download_file(self, node_id: str) -> str:
        data = self._run_dws(["doc", "download", "--node", node_id])
        if isinstance(data, dict):
            return data.get("downloadUrl", "")
        raise RuntimeError(f"下载失败，无法获取 URL: {node_id}")

    def get_space_info(self, space_id: str) -> dict:
        return self._run_dws(["wiki", "space", "get", "--id", space_id])
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd ~/src/ai/docpipe && python -m pytest tests/test_wiki_client.py -v`
Expected: 8 passed

- [ ] **Step 5: 提交**

```bash
git add dwsdocs_downloader/wiki_client.py tests/test_wiki_client.py
git commit -m "feat: 添加 WikiClient 封装 dws CLI 调用"
```

---

### Task 6: converter 模块

**Files:**
- Create: `dwsdocs_downloader/converter.py`
- Create: `tests/test_converter.py`

- [ ] **Step 1: 写失败测试 tests/test_converter.py**

```python
from __future__ import annotations

from pathlib import Path

import pytest

from dwsdocs_downloader.converter import FileConverter


@pytest.fixture
def converter():
    return FileConverter()


def test_convert_text_file(converter, tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("Hello World", encoding="utf-8")
    result = converter.convert(f)
    assert "Hello World" in result.markdown


def test_convert_md_file(converter, tmp_path):
    f = tmp_path / "test.md"
    f.write_text("# Title\n\nSome text", encoding="utf-8")
    result = converter.convert(f)
    assert "# Title" in result.markdown


def test_is_convertible(converter):
    assert converter.is_convertible("document.pdf")
    assert converter.is_convertible("sheet.xlsx")
    assert converter.is_convertible("report.docx")
    assert converter.is_convertible("data.pptx")
    assert not converter.is_convertible("image.png")
    assert not converter.is_convertible("video.mp4")


def test_convert_nonexistent_raises(converter):
    with pytest.raises(FileNotFoundError):
        converter.convert(Path("/nonexistent/file.pdf"))
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd ~/src/ai/docpipe && python -m pytest tests/test_converter.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现 converter.py**

```python
from __future__ import annotations

from pathlib import Path

from markitdown import MarkItDown

_CONVERTIBLE_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt",
    ".html", ".htm", ".csv", ".json", ".xml", ".txt", ".md",
    ".rtf", ".odt", ".ods",
}


class FileConverter:
    def __init__(self):
        self._md = MarkItDown()

    def is_convertible(self, filename: str) -> bool:
        ext = Path(filename).suffix.lower()
        return ext in _CONVERTIBLE_EXTENSIONS

    def convert(self, file_path: Path) -> MarkItDown.__class__.__bases__[0]:
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        result = self._md.convert(str(file_path))
        return result
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd ~/src/ai/docpipe && python -m pytest tests/test_converter.py -v`
Expected: 4 项通过

- [ ] **Step 5: 提交**

```bash
git add dwsdocs_downloader/converter.py tests/test_converter.py
git commit -m "feat: 添加 FileConverter 基于 markitdown 转文件为 Markdown"
```

---

### Task 7: downloader 模块

**Files:**
- Create: `dwsdocs_downloader/downloader.py`
- Create: `tests/test_downloader.py`

- [ ] **Step 1: 写失败测试 tests/test_downloader.py**

```python
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dwsdocs_downloader.downloader import Downloader
from dwsdocs_downloader.wiki_client import WikiClient
from dwsdocs_downloader.display import Display


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "output"


@pytest.fixture
def mock_client():
    return MagicMock(spec=WikiClient)


@pytest.fixture
def display():
    return Display()


def test_download_single_doc(mock_client, output_dir, display):
    mock_client.get_space_info.return_value = {"id": "sp1", "name": "测试知识库"}
    mock_client.list_nodes.return_value = [
        {"nodeId": "n1", "title": "文档1", "nodeType": "doc", "contentType": "ALIDOC", "extension": "adoc"},
    ]
    mock_client.get_node_info.return_value = {
        "nodeId": "n1", "title": "文档1", "contentType": "ALIDOC", "extension": "adoc",
    }
    mock_client.read_document.return_value = "# 文档1\n\n这是内容"

    dl = Downloader(mock_client, output_dir, display=display)
    dl.download(space_id="sp1")

    md_file = output_dir / "测试知识库" / "文档1.md"
    assert md_file.exists()
    assert "# 文档1" in md_file.read_text(encoding="utf-8")

    meta_file = output_dir / "测试知识库" / "文档1.meta.json"
    assert meta_file.exists()
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    assert meta["nodeId"] == "n1"
    assert meta["contentType"] == "ALIDOC"


def test_download_nested_folders(mock_client, output_dir, display):
    mock_client.get_space_info.return_value = {"id": "sp1", "name": "测试知识库"}
    mock_client.list_nodes.side_effect = [
        # 根目录
        [{"nodeId": "f1", "title": "子文件夹", "nodeType": "folder", "hasChildren": True}],
        # 子文件夹内容
        [{"nodeId": "n1", "title": "嵌套文档", "nodeType": "doc", "contentType": "ALIDOC", "extension": "adoc"}],
    ]
    mock_client.get_node_info.return_value = {
        "nodeId": "n1", "title": "嵌套文档", "contentType": "ALIDOC", "extension": "adoc",
    }
    mock_client.read_document.return_value = "# 嵌套文档"

    dl = Downloader(mock_client, output_dir, display=display)
    dl.download(space_id="sp1")

    md_file = output_dir / "测试知识库" / "子文件夹" / "嵌套文档.md"
    assert md_file.exists()


def test_download_file_type(mock_client, output_dir, display):
    mock_client.get_space_info.return_value = {"id": "sp1", "name": "测试知识库"}
    mock_client.list_nodes.return_value = [
        {"nodeId": "n2", "title": "报告", "nodeType": "file", "contentType": "FILE", "extension": "pdf"},
    ]
    mock_client.get_node_info.return_value = {
        "nodeId": "n2", "title": "报告", "contentType": "FILE", "extension": "pdf",
    }
    mock_client.download_file.return_value = "https://example.com/report.pdf"

    dl = Downloader(mock_client, output_dir, display=display)
    with patch("dwsdocs_downloader.downloader.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.content = b"%PDF-1.4 fake content"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        with patch("dwsdocs_downloader.downloader.FileConverter") as mock_conv_cls:
            mock_conv = MagicMock()
            mock_conv.is_convertible.return_value = True
            mock_conv.convert.return_value = MagicMock(markdown="# PDF 内容")
            mock_conv_cls.return_value = mock_conv
            dl.download(space_id="sp1")

    md_file = output_dir / "测试知识库" / "报告.md"
    assert md_file.exists()
    assert "PDF 内容" in md_file.read_text(encoding="utf-8")


def test_download_resume_skips_existing(mock_client, output_dir, display):
    mock_client.get_space_info.return_value = {"id": "sp1", "name": "测试知识库"}
    mock_client.list_nodes.return_value = [
        {"nodeId": "n1", "title": "已有文档", "nodeType": "doc"},
    ]

    # 预创建已存在的文件
    space_dir = output_dir / "测试知识库"
    space_dir.mkdir(parents=True, exist_ok=True)
    (space_dir / "已有文档.md").write_text("old content")
    (space_dir / "已有文档.meta.json").write_text(json.dumps({"nodeId": "n1"}))

    dl = Downloader(mock_client, output_dir, display=display)
    dl.download(space_id="sp1", resume=True)

    # 不应调用 read_document（跳过已有文档）
    mock_client.read_document.assert_not_called()


def test_sanitize_filename():
    from dwsdocs_downloader.downloader import sanitize_filename
    assert sanitize_filename("a/b:c*d?e") == "a_b_c_d_e"
    assert sanitize_filename("  ") == "未命名"
    assert sanitize_filename("正常名称") == "正常名称"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd ~/src/ai/docpipe && python -m pytest tests/test_downloader.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现 downloader.py**

```python
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import requests

from dwsdocs_downloader.converter import FileConverter
from dwsdocs_downloader.display import Display
from dwsdocs_downloader.state import StateManager, content_hash
from dwsdocs_downloader.wiki_client import WikiClient

_UNSAFE_CHARS = ('/', '\\', ':', '*', '?', '"', '<', '>', '|')


def sanitize_filename(name: str) -> str:
    for ch in _UNSAFE_CHARS:
        name = name.replace(ch, '_')
    name = name.strip()
    if not name or name == '.':
        return "未命名"
    # Windows 保留名
    if name.upper() in ('CON', 'PRN', 'AUX', 'NUL', 'COM1', 'LPT1'):
        return f"_{name}"
    return name


class Downloader:
    def __init__(self, client: WikiClient, output_dir: Path, display: Display | None = None):
        self._client = client
        self._output_dir = Path(output_dir)
        self._display = display or Display()
        self._converter = FileConverter()
        self._state = StateManager(self._output_dir / ".state", "download")

    def download(self, space_id: str, folder_id: str | None = None, resume: bool = False) -> None:
        space_info = self._client.get_space_info(space_id)
        space_name = sanitize_filename(space_info.get("name", space_id))
        space_dir = self._output_dir / space_name

        existing_hashes = self._state.load() if resume else {}

        self._display.start("下载知识库", 0)
        self._walk(space_dir, space_id, folder_id, existing_hashes, resume)
        self._display.stop()
        self._display.print_summary()

    def _walk(
        self,
        parent_dir: Path,
        workspace_id: str,
        folder_id: str | None,
        existing_hashes: dict[str, str],
        resume: bool,
    ) -> None:
        nodes = self._client.list_nodes(workspace_id, folder_id)
        for node in nodes:
            node_id = node.get("nodeId", "")
            title = node.get("title", "未命名")
            node_type = node.get("nodeType", "")

            if node_type == "folder":
                child_dir = parent_dir / sanitize_filename(title)
                child_dir.mkdir(parents=True, exist_ok=True)
                if node.get("hasChildren"):
                    self._walk(child_dir, workspace_id, node_id, existing_hashes, resume)
                continue

            # 文档/文件节点
            if resume and node_id in existing_hashes:
                md_path = parent_dir / f"{sanitize_filename(title)}.md"
                meta_path = parent_dir / f"{sanitize_filename(title)}.meta.json"
                if md_path.exists() and meta_path.exists():
                    self._display.log("DEBUG", f"跳过已有: {title}")
                    continue

            self._download_node(parent_dir, node, node_id, title)

    def _download_node(self, parent_dir: Path, node: dict, node_id: str, title: str) -> None:
        safe_name = sanitize_filename(title)

        # 如果 node 中已有类型信息，直接用；否则调 info
        content_type = node.get("contentType", "")
        extension = node.get("extension", "")
        if not content_type:
            info = self._client.get_node_info(node_id)
            content_type = info.get("contentType", "")
            extension = info.get("extension", "")

        try:
            if content_type == "ALIDOC" and extension == "adoc":
                markdown = self._client.read_document(node_id)
            else:
                # 文件类型：下载 → 转换
                markdown = self._download_and_convert(node_id, extension)

            self._save_document(parent_dir, safe_name, node_id, markdown, content_type, extension)
            self._display.result("success", f"{safe_name}")
        except Exception as e:
            self._display.result("error", f"{safe_name}: {e}")

    def _download_and_convert(self, node_id: str, extension: str) -> str:
        download_url = self._client.download_file(node_id)
        resp = requests.get(download_url, timeout=120)
        resp.raise_for_status()

        suffix = f".{extension}" if extension else ".bin"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = Path(tmp.name)

        try:
            result = self._converter.convert(tmp_path)
            return result.markdown
        finally:
            tmp_path.unlink(missing_ok=True)

    def _save_document(
        self,
        parent_dir: Path,
        safe_name: str,
        node_id: str,
        markdown: str,
        content_type: str,
        extension: str,
    ) -> None:
        parent_dir.mkdir(parents=True, exist_ok=True)
        md_path = parent_dir / f"{safe_name}.md"
        md_path.write_text(markdown, encoding="utf-8")

        meta = {
            "nodeId": node_id,
            "title": safe_name,
            "contentType": content_type,
            "extension": extension,
        }
        meta_path = parent_dir / f"{safe_name}.meta.json"
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd ~/src/ai/docpipe && python -m pytest tests/test_downloader.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add dwsdocs_downloader/downloader.py tests/test_downloader.py
git commit -m "feat: 添加 Downloader 递归遍历知识库并下载保存"
```

---

### Task 8: retain 模块

**Files:**
- Create: `dwsdocs_downloader/retain.py`
- Create: `tests/test_retain.py`

- [ ] **Step 1: 写失败测试 tests/test_retain.py**

```python
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dwsdocs_downloader.retain import RetainRunner
from dwsdocs_downloader.display import Display


def _create_doc(output_dir: Path, space_name: str, folder: str, name: str, node_id: str, content: str = "test content"):
    doc_dir = output_dir / space_name / folder if folder else output_dir / space_name
    doc_dir.mkdir(parents=True, exist_ok=True)
    md_path = doc_dir / f"{name}.md"
    md_path.write_text(content, encoding="utf-8")
    meta_path = doc_dir / f"{name}.meta.json"
    meta_path.write_text(json.dumps({
        "nodeId": node_id,
        "title": name,
        "contentType": "ALIDOC",
        "extension": "adoc",
    }), encoding="utf-8")
    return md_path


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "output"


@pytest.fixture
def display():
    return Display()


def test_scan_documents(output_dir, display):
    _create_doc(output_dir, "知识库", "子目录", "文档1", "n1")
    _create_doc(output_dir, "知识库", "", "文档2", "n2")

    runner = RetainRunner(output_dir, display=display)
    docs = runner.scan_documents()
    assert len(docs) == 2
    ids = {d["node_id"] for d in docs}
    assert ids == {"n1", "n2"}


def test_scan_documents_sync_no_changes(output_dir, display):
    _create_doc(output_dir, "知识库", "", "文档1", "n1")

    runner = RetainRunner(output_dir, display=display)
    # 先保存状态
    md_path = output_dir / "知识库" / "文档1.md"
    from dwsdocs_downloader.state import content_hash
    runner._state.save({"n1": content_hash(md_path)})

    changed, skipped = runner.scan_documents_sync()
    assert len(changed) == 0
    assert skipped == 1


def test_scan_documents_sync_with_changes(output_dir, display):
    _create_doc(output_dir, "知识库", "", "文档1", "n1", "原始内容")

    runner = RetainRunner(output_dir, display=display)
    # 保存旧 hash（不匹配当前内容）
    runner._state.save({"n1": "old_hash"})

    changed, skipped = runner.scan_documents_sync()
    assert len(changed) == 1
    assert skipped == 0


def test_build_retain_item(output_dir, display):
    _create_doc(output_dir, "知识库", "子目录", "文档1", "n1", "# 测试\n\n正文内容")

    runner = RetainRunner(output_dir, display=display)
    docs = runner.scan_documents()
    item = runner.build_retain_item(docs[0])

    assert item["document_id"] == "wiki:n1"
    assert "wiki" in item["tags"]
    assert item["metadata"]["nodeId"] == "n1"
    assert "# 测试" in item["content"]


def test_build_retain_item_context(output_dir, display):
    _create_doc(output_dir, "技术文档", "部署指南", "安装手册", "n2", "安装步骤")

    runner = RetainRunner(output_dir, display=display)
    docs = runner.scan_documents()
    item = runner.build_retain_item(docs[0])

    assert "技术文档" in item["context"]
    assert "部署指南" in item["context"]
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd ~/src/ai/docpipe && python -m pytest tests/test_retain.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现 retain.py**

```python
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from dwsdocs_downloader.display import Display
from dwsdocs_downloader.state import StateManager, content_hash


class RetainRunner:
    def __init__(self, output_dir: Path | str, display: Display | None = None):
        self._output_dir = Path(output_dir)
        self._display = display or Display()
        self._state = StateManager(self._output_dir / ".state", "retain")

    def scan_documents(self) -> list[dict]:
        docs: list[dict] = []
        for meta_path in sorted(self._output_dir.rglob("*.meta.json")):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                node_id = meta.get("nodeId", "")
                if not node_id:
                    continue
                md_path = meta_path.with_suffix(".md")
                if not md_path.exists():
                    continue
                relative = md_path.relative_to(self._output_dir)
                docs.append({
                    "node_id": node_id,
                    "title": meta.get("title", ""),
                    "content_type": meta.get("contentType", ""),
                    "extension": meta.get("extension", ""),
                    "md_path": md_path,
                    "relative_path": str(relative),
                    "folder_parts": relative.parts[:-1],
                })
            except (json.JSONDecodeError, OSError, ValueError):
                continue
        return docs

    def scan_documents_sync(self) -> tuple[list[dict], int]:
        stored_hashes = self._state.load()
        all_docs = self.scan_documents()
        changed: list[dict] = []
        skipped = 0
        for doc in all_docs:
            current_hash = content_hash(doc["md_path"])
            if stored_hashes.get(doc["node_id"]) == current_hash:
                skipped += 1
            else:
                changed.append(doc)
        return changed, skipped

    def build_retain_item(self, doc: dict) -> dict:
        md_content = doc["md_path"].read_text(encoding="utf-8")
        current_hash = content_hash(doc["md_path"])

        folder_parts = doc.get("folder_parts", ())
        space_name = folder_parts[0] if folder_parts else ""
        path_tags = [f"path:{part}" for part in folder_parts]
        tags = ["source:wiki"] + ([f"space:{space_name}"] if space_name else []) + path_tags

        folder_display = " / ".join(folder_parts[1:]) if len(folder_parts) > 1 else ""
        context_parts = [f"钉钉知识库文档"]
        if space_name:
            context_parts.append(f"知识库: {space_name}")
        if folder_display:
            context_parts.append(f"路径: {folder_display}")
        context_parts.append(doc["title"])
        context = "，".join(context_parts)

        return {
            "content": md_content,
            "document_id": f"wiki:{doc['node_id']}",
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "context": context,
            "tags": tags,
            "metadata": {
                "nodeId": doc["node_id"],
                "title": doc["title"],
                "contentType": doc["content_type"],
                "extension": doc["extension"],
                "relative_path": doc["relative_path"],
                "content_hash": current_hash,
            },
        }

    def run(
        self,
        client,
        bank_id: str,
        resume: bool = False,
        sync: bool = False,
        dry_run: bool = False,
    ) -> None:
        if sync:
            docs, skipped = self.scan_documents_sync()
            if skipped:
                self._display.log("INFO", f"{skipped} 个文档无变化，跳过")
        elif resume:
            stored = self._state.load()
            all_docs = self.scan_documents()
            docs = [d for d in all_docs if d["node_id"] not in stored]
        else:
            docs = self.scan_documents()

        if not docs:
            self._display.log("INFO", "没有需要同步的文档")
            return

        self._display.start("同步到 Hindsight", len(docs))

        uploaded = 0
        for doc in docs:
            title = doc["title"]
            try:
                item = self.build_retain_item(doc)
                if dry_run:
                    self._display.result("info", f"[dry-run] {title} tags={item['tags']}")
                else:
                    client.retain_batch(bank_id, items=[item], retain_async=True)
                    self._display.result("success", f"{title}")
                self._state.save({**self._state.load(), doc["node_id"]: item["metadata"]["content_hash"]})
                uploaded += 1
            except Exception as e:
                self._display.result("error", f"{title}: {e}")
                self._display.add_failure()

        self._display.stop()
        self._display.print_summary()
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd ~/src/ai/docpipe && python -m pytest tests/test_retain.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add dwsdocs_downloader/retain.py tests/test_retain.py
git commit -m "feat: 添加 RetainRunner 扫描本地 Markdown 同步到 Hindsight"
```

---

### Task 9: CLI 模块

**Files:**
- Create: `dwsdocs_downloader/cli.py`

- [ ] **Step 1: 实现 cli.py**

```python
from __future__ import annotations

import os
from pathlib import Path

import click


@click.group()
@click.option("--output", "output_dir", default="./output", help="输出目录")
@click.pass_context
def main(ctx, output_dir):
    """钉钉知识库下载并同步到 Hindsight"""
    ctx.ensure_object(dict)
    ctx.obj["output_dir"] = output_dir


@main.command()
@click.option("--space", required=True, help="知识库 ID")
@click.option("--folder", default=None, help="指定文件夹 ID，不传则从根目录开始")
@click.option("--resume", is_flag=True, default=False, help="跳过已下载的文档")
@click.pass_context
def download(ctx, space, folder, resume):
    """从钉钉知识库下载内容并保存为 Markdown"""
    output_dir = Path(ctx.obj["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    from dwsdocs_downloader.display import Display
    from dwsdocs_downloader.wiki_client import WikiClient
    from dwsdocs_downloader.downloader import Downloader

    display = Display()
    client = WikiClient()
    dl = Downloader(client, output_dir, display=display)
    dl.download(space_id=space, folder_id=folder, resume=resume)


@main.command()
@click.option("--bank-id", default=None, help="Hindsight Bank ID")
@click.option("--hindsight-url", default=None, help="Hindsight API URL")
@click.option("--hindsight-key", default=None, help="Hindsight API Key")
@click.option("--resume", is_flag=True, default=False, help="跳过已上传的文档")
@click.option("--sync", "sync_mode", is_flag=True, default=False, help="仅同步有变化的文档")
@click.option("--dry-run", is_flag=True, default=False, help="只打印不执行")
@click.pass_context
def retain(ctx, bank_id, hindsight_url, hindsight_key, resume, sync_mode, dry_run):
    """将本地 Markdown 文档同步到 Hindsight"""
    from hindsight_client import Hindsight

    output_dir = Path(ctx.obj["output_dir"])
    bank_id = bank_id or os.environ.get("HINDSIGHT_BANK_ID", "")
    hindsight_url = hindsight_url or os.environ.get("HINDSIGHT_API_URL", "")
    hindsight_key = hindsight_key or os.environ.get("HINDSIGHT_API_KEY", "")

    if not hindsight_url or not bank_id:
        click.echo("错误：缺少 HINDSIGHT_API_URL 或 HINDSIGHT_BANK_ID")
        raise SystemExit(1)

    from dwsdocs_downloader.display import Display
    from dwsdocs_downloader.retain import RetainRunner

    display = Display()
    runner = RetainRunner(output_dir, display=display)

    with Hindsight(base_url=hindsight_url, api_key=hindsight_key or None) as client:
        runner.run(client, bank_id, resume=resume, sync=sync_mode, dry_run=dry_run)
```

- [ ] **Step 2: 验证 CLI 可用**

Run: `cd ~/src/ai/docpipe && python -m dwsdocs_downloader --help`
Expected: 显示 help 信息，包含 download 和 retain 子命令

Run: `cd ~/src/ai/docpipe && python -m dwsdocs_downloader download --help`
Expected: 显示 download 帮助

- [ ] **Step 3: 提交**

```bash
git add dwsdocs_downloader/cli.py
git commit -m "feat: 添加 Click CLI — download 和 retain 命令"
```

---

### Task 10: CLAUDE.md 项目文档

**Files:**
- Create: `CLAUDE.md`（在项目根目录）

- [ ] **Step 1: 创建 CLAUDE.md**

```markdown
# CLAUDE.md

## 项目概述

`dwsdocs-downloader` 是一个 Python CLI 工具，用于从钉钉知识库读取内容（在线文档和上传文件），
转换为 Markdown 保存到本地，再增量同步到 Hindsight 记忆系统。

## 开发命令

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行全部测试
python -m pytest tests/ -v

# 运行单个测试文件
python -m pytest tests/test_state.py -v

# 运行 CLI
python -m dwsdocs_downloader --help
python -m dwsdocs_downloader download --space SPACE_ID --output-dir ./output
python -m dwsdocs_downloader retain --output-dir ./output
```

## 架构

两层流水线，数据流向：CLI → Downloader（下载到本地）/ RetainRunner（本地→Hindsight），各自独立。

| 模块 | 类 | 职责 |
|------|-----|------|
| `config.py` | `Config` | dataclass 配置，环境变量读取 |
| `display.py` | `Display` | 进度条和日志输出 |
| `state.py` | `StateManager` | JSON 状态文件读写（断点续传） |
| `wiki_client.py` | `WikiClient` | 封装 dws CLI 调用（subprocess → JSON） |
| `converter.py` | `FileConverter` | markitdown 文件转 Markdown |
| `downloader.py` | `Downloader` | 递归遍历知识库 + 类型分发 + 保存 |
| `retain.py` | `RetainRunner` | 扫描本地 Markdown → Hindsight retain |
| `cli.py` | - | Click CLI 入口 |

CLI 通过 Click 框架组织，支持两个子命令：
- `download`：从钉钉知识库下载内容到本地 Markdown
- `retain`：将本地 Markdown 增量同步到 Hindsight

## 技术栈

- Python 3.11+
- Click（CLI）、markitdown（文件转 Markdown）、hindsight-client（Hindsight API）
- 运行时依赖：dws CLI（钉钉知识库操作）
- 测试：pytest + unittest.mock

## 环境变量

- `HINDSIGHT_API_URL`、`HINDSIGHT_API_KEY`、`HINDSIGHT_BANK_ID`：Hindsight 服务连接

## 约定

- 提交信息使用中文描述 + `feat:`/`fix:` 前缀
- 输出目录默认 `./output/`
- 状态文件保存在 `output/.state/` 下
- document_id 前缀 `wiki:` 区分于 question-downloader 的 `question:`
```

- [ ] **Step 2: 提交**

```bash
git add CLAUDE.md
git commit -m "docs: 添加项目 CLAUDE.md"
```

---

### Task 11: 全量测试 + 端到端验证

**Files:**
- 无新增文件

- [ ] **Step 1: 运行全量测试**

Run: `cd ~/src/ai/docpipe && python -m pytest tests/ -v`
Expected: 所有测试通过

- [ ] **Step 2: 验证 CLI 帮助正常**

Run: `cd ~/src/ai/docpipe && dwsdocs-downloader --help`
Expected: 显示 `download` 和 `retain` 子命令

Run: `cd ~/src/ai/docpipe && dwsdocs-downloader download --help`
Expected: 显示 `--space`、`--folder`、`--resume` 参数

- [ ] **Step 3: 最终提交**

如果有任何修复，提交。
