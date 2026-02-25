from __future__ import annotations


class PlannerAbortError(RuntimeError):
    """
    Raised when LLM planning must abort safely (e.g., both primary and fallback fail).
    The agent loop should catch this and stop before executing any tools.
    """
    pass
