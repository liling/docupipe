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
