from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

RiskLevel = Literal["SAFE", "MODIFY", "CRITICAL"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    risk: RiskLevel
    fn: Callable[..., Any]