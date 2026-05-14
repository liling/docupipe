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
