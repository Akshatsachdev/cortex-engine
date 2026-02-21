from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from cortex.runtime.config import logs_dir


def session_log_path(session_id: str) -> Path:
    return logs_dir() / f"session_{session_id}.jsonl"


def append_jsonl(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")