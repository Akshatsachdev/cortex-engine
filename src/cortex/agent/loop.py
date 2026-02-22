from __future__ import annotations
from cortex.llm.planner import build_plan
from cortex.tools.registry import list_tools
from cortex.agent.models import Plan, Step, RunResult
from cortex.runtime.session import new_session
from cortex.runtime.logging import append_jsonl, session_log_path
from cortex.security.policy_engine import validate_plan_or_raise
from cortex.runtime.config import load_config
from cortex.agent.executor import execute_plan


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
    allowed_tools = [t.name for t in list_tools()]
    session = new_session()
    logp = session_log_path(session.session_id)

    append_jsonl(
        logp,
        {"type": "session_start", "session_id": session.session_id,
            "task": task, "dry_run": dry_run},
    )

    plan = build_plan(task=task, allowed_tools=allowed_tools,
                      session_id=session.session_id)
    validate_plan_or_raise(plan)

    append_jsonl(
        logp,
        {"type": "plan_validated", "session_id": session.session_id,
            "plan": plan.model_dump()},
    )

    results = []
    if not dry_run:
        results = execute_plan(
            session_id=session.session_id, plan=plan, log_path=logp)

    result = RunResult(session_id=session.session_id,
                       dry_run=dry_run, plan=plan, results=results)

    append_jsonl(
        logp,
        {"type": "run_result", "session_id": session.session_id,
            "result": result.model_dump()},
    )

    return result
