from __future__ import annotations
import re

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
    tools_csv = ", ".join(allowed_tools)

    return (
        "You are Cortex Planner.\n"
        "Return ONLY ONE JSON object. No prose.\n"
        "First line MUST be <json> and then JSON immediately.\n"
        f"Task: {task}\n"
        f"AllowedTools: {tools_csv}\n"
        "\n"
        "GOAL: produce a minimal, correct, safe plan.\n"
        "Prefer 1 step when possible.\n"
        "\n"
        "HARD SAFETY RULES (never violate):\n"
        "- Only use http:// or https:// URLs.\n"
        "- NEVER output URLs with schemes: chrome://, edge://, about:, file://.\n"
        "- NEVER invent identity/profile URLs for people (e.g., linkedin.com/in/<slug>). Use search pages.\n"
        "- Do NOT use browser.fetch for YouTube search/play flows (pages are large).\n"
        "\n"
        "BROWSER PARAM EXTRACTION (must follow):\n"
        "- If the task contains 'in/from/using/with <browser>' where <browser> is one of\n"
        "  {chrome, brave, edge, firefox}, set params.browser to that value.\n"
        "- Do NOT create an extra step to 'open chrome'. Use params.browser instead.\n"
        "\n"
        "TOOL-SPECIFIC RULES:\n"
        "1) browser.open (SAFE)\n"
        "   - params: {\"url\": \"https://...\", \"browser\": \"default|chrome|brave|edge|firefox\" (optional)}\n"
        "   - Use for opening a website or a search results page.\n"
        "\n"
        "2) browser.fetch (SAFE)\n"
        "   - Use ONLY when the user explicitly asks to fetch/read/download page content as text/json.\n"
        "   - Avoid for dynamic/large sites (YouTube, LinkedIn, Gmail).\n"
        "\n"
        "3) email.compose (SAFE)\n"
        "   - params: {\"to\": \"...\", \"subject\": \"...\", \"body\": \"...\", \"browser\": \"...\" (optional)}\n"
        "   - If the user mentions a browser (chrome/brave/edge/firefox), set params.browser accordingly.\n"
        "   - Do NOT add browser.open chrome:// steps.\n"
        "\n"
        "DETERMINISTIC WEBSITE INTENTS:\n"
        "- If user says 'play <query> on youtube' or 'play <query> in youtube.com':\n"
        "  Open the YouTube search URL with browser.open:\n"
        "  https://www.youtube.com/results?search_query=<urlencoded query>\n"
        "  (ONE step only)\n"
        "\n"
        "- If user says 'open <name> in linkedin' or 'find <name> on linkedin':\n"
        "  Open LinkedIn people search URL with browser.open:\n"
        "  https://www.linkedin.com/search/results/people/?keywords=<urlencoded name>\n"
        "  (Do NOT invent linkedin /in/ profile)\n"
        "\n"
        "- If user says 'search <query> on google':\n"
        "  Open: https://www.google.com/search?q=<urlencoded query>\n"
        "\n"
        "URL ENCODING:\n"
        "- Replace spaces with + and percent-encode special characters.\n"
        "\n"
        "JSON schema (exact keys):\n"
        "{\"steps\":[{\"tool\":\"...\",\"description\":\"...\",\"params\":{},\"risk_level\":\"SAFE\",\"requires_approval\":false}]}\n"
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


_BROWSER_RE = re.compile(
    r"\b(?:in|from|using|with)\s+(chrome|brave|edge|firefox)\b|\b(chrome|brave|edge|firefox)\s+browser\b",
    re.IGNORECASE,
)


def _extract_browser_hint(task: str) -> str | None:
    t = (task or "").strip()
    if not t:
        return None
    m = _BROWSER_RE.search(t)
    if not m:
        return None
    b = (m.group(1) or m.group(2) or "").lower()
    return b or None


def _inject_browser_hint(task: str, plan_dict: Dict[str, Any]) -> None:
    """
    Production-grade: do not rely on LLM to pass browser choice.
    If user mentions a browser, inject params.browser for tools that support it.
    """
    browser = _extract_browser_hint(task)
    if not browser:
        return

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

        if tool in {"browser.open", "browser.search", "email.compose"}:
            params.setdefault("browser", browser)


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
                task=task,
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
            task=task,
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
    task: str,
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

            _inject_browser_hint(task, data)

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
