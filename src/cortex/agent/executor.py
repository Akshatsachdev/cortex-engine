from __future__ import annotations

from typing import Any
from cortex.agent.models import Plan, StepResult
from cortex.runtime.logging import append_jsonl
from cortex.tools.registry import get as get_tool


class ExecutionDenied(Exception):
    pass


def execute_plan(
    *,
    session_id: str,
    plan: Plan,
    log_path,
) -> list[StepResult]:
    results: list[StepResult] = []

    for step in plan.steps:
        tool_spec = get_tool(step.tool)

        # Phase 1.2: SAFE-only execution
        if tool_spec.risk != "SAFE":
            raise ExecutionDenied(f"Non-SAFE tool blocked in Phase 1.2: {step.tool} ({tool_spec.risk})")

        append_jsonl(
            log_path,
            {"event": "tool_start", "session_id": session_id, "step_id": step.id, "tool": step.tool, "params": step.params},
        )

        try:
            # Convention: tools accept keyword args matching params
            output = tool_spec.fn(**step.params)

            append_jsonl(
                log_path,
                {"event": "tool_result", "session_id": session_id, "step_id": step.id, "tool": step.tool, "ok": True},
            )

            results.append(StepResult(step_id=step.id, tool=step.tool, ok=True, output=output))
        except Exception as e:
            append_jsonl(
                log_path,
                {"event": "tool_error", "session_id": session_id, "step_id": step.id, "tool": step.tool, "ok": False, "error": str(e)},
            )
            results.append(StepResult(step_id=step.id, tool=step.tool, ok=False, error=str(e)))

    return results