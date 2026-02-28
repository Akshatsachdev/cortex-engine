from __future__ import annotations
from typing import Optional
from datetime import datetime, timezone

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


def audit_log_path() -> Path:
    # global audit stream (events outside a session, e.g. secure enable/disable)
    return logs_dir() / "audit.jsonl"


def audit_event(event: str, data: Optional[dict[str, Any]] = None, *, session_id: Optional[str] = None) -> None:
    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "data": data or {},
    }
    if session_id:
        payload["session_id"] = session_id
        append_jsonl(session_log_path(session_id), payload)
    else:
        append_jsonl(audit_log_path(), payload)
