from __future__ import annotations

from typing import Any, Dict, List, Literal
from pydantic import BaseModel, Field

RiskLevel = Literal["SAFE", "MODIFY", "CRITICAL"]


class Step(BaseModel):
    id: str
    description: str
    tool: str
    params: Dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel = "SAFE"
    requires_approval: bool = False


class Plan(BaseModel):
    steps: List[Step]


class RunResult(BaseModel):
    session_id: str
    dry_run: bool
    plan: Plan