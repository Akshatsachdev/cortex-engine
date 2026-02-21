from __future__ import annotations

from cortex.agent.models import Plan

FORBIDDEN_KEYWORDS = {
    "delete all",
    "wipe",
    "format disk",
    "steal",
    "exfiltrate",
    "keylogger",
    "backdoor",
    "credential",
    "password dump",
    "ransomware",
}


class PolicyViolation(Exception):
    pass


def forbidden_intent_check(text: str) -> None:
    t = text.lower()
    for kw in FORBIDDEN_KEYWORDS:
        if kw in t:
            raise PolicyViolation(f"Forbidden intent detected: {kw}")


def validate_plan_or_raise(plan: Plan) -> None:
    ids = [s.id for s in plan.steps]
    if len(ids) != len(set(ids)):
        raise PolicyViolation("Duplicate step ids in plan.")

    for s in plan.steps:
        forbidden_intent_check(s.description)
        forbidden_intent_check(str(s.params))