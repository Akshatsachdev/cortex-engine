from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SecureDecision:
    allowed: bool
    reason: Optional[str] = None


def secure_allows_tool(secure_enabled: bool, tool_risk: str) -> SecureDecision:
    if not secure_enabled:
        return SecureDecision(True)

    tool_risk = (tool_risk or "SAFE").upper()

    if tool_risk == "SAFE":
        return SecureDecision(True)

    return SecureDecision(
        False,
        "Secure mode enabled: only SAFE tools are allowed",
    )
