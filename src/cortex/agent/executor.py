from __future__ import annotations

from typing import Any
from cortex.agent.models import Plan, StepResult
from cortex.runtime.logging import append_jsonl
from cortex.tools.registry import get as get_tool
from cortex.runtime.config import load_config
from cortex.security.secure_mode import secure_allows_tool


class ExecutionDenied(Exception):
    pass


def execute_plan(
    *,
    session_id: str,
    plan: Plan,
    log_path,
) -> list[StepResult]:
    results: list[StepResult] = []

    # Load config once (secure mode state)
    cfg = load_config()

    for step in plan.steps:
        tool_spec = get_tool(step.tool)
        tool_risk = (tool_spec.risk or "SAFE").upper()  # source of truth

        # 🔐 HARD SECURE MODE ENFORCEMENT (NON-BYPASSABLE)

        secure_enabled = bool((cfg.get("secure") or {}).get("enabled"))
        decision = secure_allows_tool(secure_enabled, tool_risk)
        if not decision.allowed:
            append_jsonl(
                log_path,
                {
                    "event": "secure_mode_blocked",
                    "session_id": session_id,
                    "step_id": step.id,
                    "tool": tool_spec.name,
                    "risk": str(tool_risk),
                    "reason": decision.reason,
                },
            )

            results.append(
                StepResult(
                    step_id=step.id,
                    tool=step.tool,
                    ok=False,
                    error=f"Blocked by secure mode: {decision.reason}",
                )
            )
            continue  # DO NOT EXECUTE TOOL

        # Phase 1.6: approval enforcement (still applies)
        if tool_risk in ("MODIFY", "CRITICAL") and not getattr(step, "approved", False):
            raise ExecutionDenied(
                f"Approval required but not granted: {step.tool} ({tool_risk})"
            )

        append_jsonl(
            log_path,
            {
                "event": "tool_start",
                "session_id": session_id,
                "step_id": step.id,
                "tool": step.tool,
                "params": step.params,
            },
        )

        try:
            # Convention: tools accept keyword args matching params
            output = tool_spec.fn(**step.params)

            append_jsonl(
                log_path,
                {
                    "event": "tool_result",
                    "session_id": session_id,
                    "step_id": step.id,
                    "tool": step.tool,
                    "ok": True,
                },
            )

            results.append(
                StepResult(
                    step_id=step.id,
                    tool=step.tool,
                    ok=True,
                    output=output,
                )
            )
        except Exception as e:
            append_jsonl(
                log_path,
                {
                    "event": "tool_error",
                    "session_id": session_id,
                    "step_id": step.id,
                    "tool": step.tool,
                    "ok": False,
                    "error": str(e),
                },
            )
            results.append(
                StepResult(
                    step_id=step.id,
                    tool=step.tool,
                    ok=False,
                    error=str(e),
                )
            )

    return results
