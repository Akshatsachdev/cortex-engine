from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid


@dataclass(frozen=True)
class Session:
    session_id: str
    started_utc: str


def new_session() -> Session:
    sid = uuid.uuid4().hex[:12]
    ts = datetime.now(timezone.utc).isoformat()
    return Session(session_id=sid, started_utc=ts)