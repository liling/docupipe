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
