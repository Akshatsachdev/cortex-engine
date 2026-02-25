from __future__ import annotations

from typing import List, Any, Dict

from cortex.agent.models import Plan
from cortex.config import get_config
from cortex.runtime.config import load_config
from cortex.runtime.logging import append_jsonl, session_log_path
from cortex.security.policy_engine import validate_plan_or_raise

from cortex.llm.json_extract import extract_first_json_object
from cortex.llm.provider_llamacpp import LlamaCppProvider


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
    allowed_paths = cfg.get("allowed_paths") or []

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

    # LLM disabled → fallback to stub
    if not cfg.llm.enabled:
        from cortex.agent.loop import build_stub_plan  # local import to avoid circular
        return build_stub_plan(task)

    # LLM enabled but llama-cpp not installed → fallback
    try:
        from llama_cpp import Llama  # noqa
    except Exception:
        from cortex.agent.loop import build_stub_plan
        return build_stub_plan(task)

    log_path = session_log_path(session_id)

    # Model missing / provider fails → fallback
    try:
        provider = LlamaCppProvider(
            model_path=cfg.llm.primary_model_path,
            n_ctx=cfg.llm.n_ctx,
            n_gpu_layers=cfg.gpu.n_gpu_layers if cfg.gpu.enable else 0,
            timeout=cfg.llm.timeout,
        )
    except Exception:
        from cortex.agent.loop import build_stub_plan
        return build_stub_plan(task)

    prompt = _build_prompt(task, allowed_tools)

    last_err: Exception | None = None

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

            # Inject allowed_paths before validation (locked requirement)
            _inject_allowed_paths(data)

            # Validate via Pydantic model
            plan = Plan.model_validate(data)

            # Validate via policy engine
            validate_plan_or_raise(plan)

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
                },
            )

    raise RuntimeError(f"LLM produced invalid plan after retry: {last_err}")
