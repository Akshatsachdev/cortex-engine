from __future__ import annotations

from typing import List, Any, Dict

from cortex.agent.models import Plan
from cortex.config import get_config
from cortex.runtime.config import load_config
from cortex.runtime.logging import append_jsonl, session_log_path
from cortex.security.policy_engine import validate_plan_or_raise

from cortex.llm.json_extract import extract_first_json_object
from cortex.llm.provider_llamacpp import LlamaCppProvider

from cortex.llm.errors import PlannerAbortError
from cortex.runtime.config import effective_allowed_paths, load_config


def _build_prompt(task: str, allowed_tools: List[str]) -> str:
    # Keep it short. Template-first. No long “rules list”.
    tools_csv = ", ".join(allowed_tools)

    # We OPEN the <json> tag at the end so the model begins inside JSON mode.
    return (
        "You are Cortex Planner.\n"
        "Output ONLY ONE JSON object describing the tool plan.\n"
        "Start with <json> on the first line and output JSON immediately. No prose.\n"
        f"Task: {task}\n"
        f"AllowedTools: {tools_csv}\n"
        "JSON schema (exact keys):\n"
        '{"steps":[{"tool":"...","description":"...","params":{},"risk_level":"SAFE","requires_approval":false}]}\n'
        "<json>\n"
    )


def _inject_allowed_paths(plan_dict: Dict[str, Any]) -> None:
    """
    Locked requirement: always inject allowed_paths into each step params.
    Source of truth: runtime config used by stub planner.
    """
    cfg = load_config()
    allowed_paths = effective_allowed_paths(cfg)

    steps = plan_dict.get("steps") or []
    if not isinstance(steps, list):
        return

    for s in steps:
        if not isinstance(s, dict):
            continue

        tool = str(s.get("tool", ""))
        params = s.get("params")
        if not isinstance(params, dict):
            params = {}
            s["params"] = params

            # Default required params for filesystem.list
        if tool == "filesystem.list" and "path" not in params:
            params["path"] = "."

        # Inject allowed_paths for filesystem tools (and generally safe to include)
        if tool.startswith("filesystem.") and "allowed_paths" not in params:
            params["allowed_paths"] = allowed_paths

        # If model omitted requires_approval but gave risk_level, set sensible default
        # (keeps things robust; policy engine still validates)
        if "risk_level" in s and "requires_approval" not in s:
            rl = str(s.get("risk_level", "SAFE")).upper()
            s["requires_approval"] = rl in ("MODIFY", "CRITICAL")


def _inject_step_ids(plan_dict: dict) -> None:
    steps = plan_dict.get("steps") or []
    for idx, step in enumerate(steps, start=1):
        if isinstance(step, dict) and "id" not in step:
            step["id"] = f"step_{idx}"


def build_plan(task: str, allowed_tools: List[str], session_id: str) -> Plan:
    cfg = get_config()

    # LLM disabled → fallback to stub (unchanged)
    if not cfg.llm.enabled:
        from cortex.agent.loop import build_stub_plan  # local import to avoid circular
        return build_stub_plan(task)

    # llama-cpp not installed → fallback to stub (keeps CI safe)
    try:
        from llama_cpp import Llama  # noqa: F401
    except Exception:
        from cortex.agent.loop import build_stub_plan
        return build_stub_plan(task)

    log_path = session_log_path(session_id)
    prompt = _build_prompt(task, allowed_tools)

    # ---------- PRIMARY ----------
    try:
        provider_primary = LlamaCppProvider(
            model_path=cfg.llm.primary_model_path,
            n_ctx=cfg.llm.n_ctx,
            n_gpu_layers=cfg.gpu.n_gpu_layers if cfg.gpu.enable else 0,
            timeout=cfg.llm.timeout,
        )
    except Exception as e:
        append_jsonl(
            log_path, {"type": "llm_primary_failed", "error": f"load_error: {e}"})
        provider_primary = None

    if provider_primary is not None:
        try:
            return _try_build_plan_with_provider(
                provider=provider_primary,
                prompt=prompt,
                session_id=session_id,
            )
        except Exception as e:
            append_jsonl(
                log_path, {"type": "llm_primary_failed", "error": str(e)})

    # ---------- FAILOVER ----------
    try:
        provider_fallback = LlamaCppProvider(
            model_path=cfg.llm.fallback_model_path,
            n_ctx=cfg.llm.n_ctx,
            n_gpu_layers=cfg.gpu.n_gpu_layers if cfg.gpu.enable else 0,
            timeout=cfg.llm.timeout,
        )
    except Exception as e:
        append_jsonl(log_path, {"type": "llm_abort",
                     "reason": f"fallback_load_error: {e}"})
        raise PlannerAbortError(
            f"Primary failed and fallback failed to load: {e}"
        ) from e

    append_jsonl(
        log_path,
        {
            "type": "llm_failover_used",
            "fallback_model_path": cfg.llm.fallback_model_path,
        },
    )

    try:
        return _try_build_plan_with_provider(
            provider=provider_fallback,
            prompt=prompt,
            session_id=session_id,
        )
    except Exception as e:
        append_jsonl(log_path, {"type": "llm_abort", "reason": str(e)})
        raise PlannerAbortError(
            f"Both primary and fallback planning failed: {e}"
        ) from e


def _try_build_plan_with_provider(
    *,
    provider: LlamaCppProvider,
    prompt: str,
    session_id: str,
) -> Plan:
    cfg = get_config()
    log_path = session_log_path(session_id)

    last_err: Exception | None = None

    # Phase 1.4: invalid JSON retry stays per-model, then failover triggers
    for attempt in range(2):
        raw = provider.generate(
            prompt=prompt,
            max_tokens=cfg.llm.max_tokens,
            temperature=cfg.llm.temperature,
            log_path=log_path,
            stop=["</json>"],
        ).text

        try:
            data = extract_first_json_object(raw)

            _inject_step_ids(data)

            # Locked requirement
            _inject_allowed_paths(data)

            plan = Plan.model_validate(data)

            validate_plan_or_raise(plan)

            append_jsonl(
                log_path, {"type": "plan_validated", "steps": len(plan.steps)})
            return plan

        except Exception as e:
            last_err = e
            append_jsonl(
                log_path,
                {
                    "type": "llm_invalid_json",
                    "attempt": attempt + 1,
                    "error": str(e),
                    "raw_preview": raw[:800],
                    "model": provider.model_path,
                },
            )

    raise RuntimeError(f"LLM produced invalid plan after retry: {last_err}")
