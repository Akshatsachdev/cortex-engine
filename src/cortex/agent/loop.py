from __future__ import annotations

from cortex.agent.models import Plan, Step, RunResult
from cortex.runtime.session import new_session
from cortex.runtime.logging import append_jsonl, session_log_path
from cortex.security.policy_engine import validate_plan_or_raise
from cortex.runtime.config import load_config


def build_stub_plan(task: str) -> Plan:
    cfg = load_config()
    allowed_paths = cfg.get("allowed_paths") or []

    return Plan(
        steps=[
            Step(
                id="step_1",
                description=f"List files in the current folder relevant to: {task}",
                tool="filesystem.list",
                params={"path": ".", "allowed_paths": allowed_paths},
                risk_level="SAFE",
                requires_approval=False,
            )
        ]
    )


def run_task(task: str, dry_run: bool = True) -> RunResult:
    session = new_session()
    logp = session_log_path(session.session_id)

    append_jsonl(
        logp,
        {"event": "session_start", "session_id": session.session_id, "task": task, "dry_run": dry_run},
    )

    plan = build_stub_plan(task)
    validate_plan_or_raise(plan)

    append_jsonl(
        logp,
        {"event": "plan_validated", "session_id": session.session_id, "plan": plan.model_dump()},
    )

    result = RunResult(session_id=session.session_id, dry_run=dry_run, plan=plan)
    append_jsonl(
        logp,
        {"event": "run_result", "session_id": session.session_id, "result": result.model_dump()},
    )
    return result