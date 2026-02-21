from __future__ import annotations

from cortex.agent.models import Step


def requires_confirm(step: Step) -> bool:
    return step.risk_level == "MODIFY"


def requires_explicit_yes(step: Step) -> bool:
    return step.risk_level == "CRITICAL"