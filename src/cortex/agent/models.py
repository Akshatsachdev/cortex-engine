from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
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


class StepResult(BaseModel):
    step_id: str
    tool: str
    ok: bool
    output: Optional[Any] = None
    error: Optional[str] = None


class RunResult(BaseModel):
    session_id: str
    dry_run: bool
    plan: Plan
    results: List[StepResult] = Field(default_factory=list)