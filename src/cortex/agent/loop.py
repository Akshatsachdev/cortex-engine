from __future__ import annotations

from cortex.llm.planner import build_plan
from cortex.tools.registry import list_tools
from cortex.agent.models import Plan, Step, RunResult
from cortex.runtime.session import new_session
from cortex.runtime.logging import append_jsonl, session_log_path
from cortex.security.policy_engine import validate_plan_or_raise
from cortex.runtime.config import load_config
from cortex.agent.executor import execute_plan
from cortex.llm.errors import PlannerAbortError
from cortex.tools.registry import get as get_tool
from cortex.runtime.config import effective_allowed_paths
from cortex.security.secure_mode import secure_allows_tool


def _request_approval(step: Step, *, non_interactive: bool, logp, session_id: str) -> bool:
    append_jsonl(
        logp,
        {
            "event": "approval_requested",
            "session_id": session_id,
            "step_id": step.id,
            "tool": step.tool,
            "risk_level": step.risk_level,
        },
    )

    if non_interactive:
        append_jsonl(
            logp,
            {
                "event": "approval_denied",
                "session_id": session_id,
                "step_id": step.id,
                "tool": step.tool,
                "reason": "non_interactive",
            },
        )
        return False

    rl = (step.risk_level or "SAFE").upper()

    if rl == "MODIFY":
        ans = input(
            f"\nApprove MODIFY step {step.id} ({step.tool})? [y/N]: ").strip().lower()
        ok = ans in ("y", "yes")
    elif rl == "CRITICAL":
        ans = input(
            f"\nType YES to approve CRITICAL step {step.id} ({step.tool}): ").strip()
        ok = ans.lower() == "yes"
    else:
        ok = True  # SAFE

    append_jsonl(
        logp,
        {
            "event": "approval_granted" if ok else "approval_denied",
            "session_id": session_id,
            "step_id": step.id,
            "tool": step.tool,
        },
    )
    return ok


def build_stub_plan(task: str) -> Plan:
    cfg = load_config()
    allowed_paths = effective_allowed_paths(cfg)

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


def run_task(task: str, dry_run: bool = True, non_interactive: bool = False) -> RunResult:
    allowed_tools = [t.name for t in list_tools()]
    session = new_session()
    logp = session_log_path(session.session_id)

    append_jsonl(
        logp,
        {
            "event": "session_start",
            "session_id": session.session_id,
            "task": task,
            "dry_run": dry_run,
            "non_interactive": non_interactive,
        },
    )

    # ---------------------------
    # Build + validate plan
    # ---------------------------
    try:
        plan = build_plan(
            task=task,
            allowed_tools=allowed_tools,
            session_id=session.session_id,
        )
        validate_plan_or_raise(plan)

        append_jsonl(
            logp,
            {
                "event": "plan_validated",
                "session_id": session.session_id,
                "plan": plan.model_dump(),
            },
        )

    except PlannerAbortError as e:
        abort_plan = build_stub_plan(f"ABORTED: {task}")

        append_jsonl(
            logp,
            {
                "event": "plan_validated",
                "session_id": session.session_id,
                "plan": abort_plan.model_dump(),
                "fallback": True,
                "reason": "llm_abort",
            },
        )

        append_jsonl(
            logp,
            {
                "event": "llm_abort",
                "session_id": session.session_id,
                "reason": str(e),
            },
        )

        fallback_results = []
        if not dry_run:
            append_jsonl(
                logp,
                {
                    "event": "execution_authorized",
                    "session_id": session.session_id,
                    "approved_map": {s.id: True for s in abort_plan.steps},
                    "fallback": True,
                    "reason": "llm_abort",
                },
            )

            fallback_results = execute_plan(
                session_id=session.session_id,
                plan=abort_plan,
                log_path=logp,
            )

        result = RunResult(
            session_id=session.session_id,
            dry_run=dry_run,
            plan=abort_plan,
            results=fallback_results,
        )

        append_jsonl(
            logp,
            {
                "event": "run_result",
                "session_id": session.session_id,
                "result": result.model_dump(),
            },
        )
        return result

    except Exception as e:
        fail_plan = build_stub_plan(f"FAILED: {task}")

        append_jsonl(
            logp,
            {
                "event": "plan_validated",
                "session_id": session.session_id,
                "plan": fail_plan.model_dump(),
                "fallback": True,
                "reason": "run_failed",
            },
        )

        append_jsonl(
            logp,
            {
                "event": "run_failed",
                "session_id": session.session_id,
                "error": str(e),
            },
        )

        fallback_results = []
        if not dry_run:
            append_jsonl(
                logp,
                {
                    "event": "execution_authorized",
                    "session_id": session.session_id,
                    "approved_map": {s.id: True for s in fail_plan.steps},
                    "fallback": True,
                    "reason": "run_failed",
                },
            )

            fallback_results = execute_plan(
                session_id=session.session_id,
                plan=fail_plan,
                log_path=logp,
            )

        result = RunResult(
            session_id=session.session_id,
            dry_run=dry_run,
            plan=fail_plan,
            results=fallback_results,
        )

        append_jsonl(
            logp,
            {
                "event": "run_result",
                "session_id": session.session_id,
                "result": result.model_dump(),
            },
        )
        return result

    # ---------------------------
    # Execution
    # ---------------------------
    results = []

    if not dry_run:
        approved_steps = []

    for step in plan.steps:
        # ✅ Production: registry risk is source of truth
        tool_spec = get_tool(step.tool)
        tool_risk = (tool_spec.risk or "SAFE").upper()

        # 🔐 SECURE MODE CHECK
        cfg = load_config()
        secure_enabled = bool((cfg.get("secure") or {}).get("enabled"))

        decision = secure_allows_tool(secure_enabled, tool_risk)
        if not decision.allowed:
            append_jsonl(
                logp,
                {
                    "event": "secure_mode_blocked",
                    "session_id": session.session_id,
                    "step_id": step.id,
                    "tool": step.tool,
                    "risk_level": tool_risk,
                    "reason": decision.reason,
                },
            )

            # Abort execution cleanly
            result = RunResult(
                session_id=session.session_id,
                dry_run=dry_run,
                plan=plan,
                results=[],
            )

            append_jsonl(
                logp,
                {
                    "event": "run_result",
                    "session_id": session.session_id,
                    "result": result.model_dump(),
                },
            )
            return result

        # Keep plan consistent with registry risk (UI + audit correctness)
        step = step.model_copy(
            update={
                "risk_level": tool_risk,
                "requires_approval": tool_risk in ("MODIFY", "CRITICAL"),
            }
        )

        needs = tool_risk in ("MODIFY", "CRITICAL")

        if needs:
            ok = _request_approval(
                step,
                non_interactive=non_interactive,
                logp=logp,
                session_id=session.session_id,
            )
            if not ok:
                # Abort: no execution
                result = RunResult(
                    session_id=session.session_id, dry_run=dry_run, plan=plan, results=[])
                append_jsonl(logp, {
                             "event": "run_result", "session_id": session.session_id, "result": result.model_dump()})
                return result

            step = step.model_copy(update={"approved": True})

        approved_steps.append(step)

    # Replace plan with approved plan
    plan = plan.model_copy(update={"steps": approved_steps})

    append_jsonl(
        logp,
        {
            "event": "execution_authorized",
            "session_id": session.session_id,
            "approved_map": {s.id: getattr(s, "approved", False) for s in plan.steps},
        },
    )

    # Execute
    results = execute_plan(
        session_id=session.session_id, plan=plan, log_path=logp)

    # ---------------------------
    # Final result (ALWAYS)
    # ---------------------------
    result = RunResult(session_id=session.session_id,
                       dry_run=dry_run, plan=plan, results=results)

    append_jsonl(
        logp,
        {"event": "run_result", "session_id": session.session_id,
            "result": result.model_dump()},
    )

    return result
