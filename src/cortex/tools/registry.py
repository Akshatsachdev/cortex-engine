from __future__ import annotations

from typing import Dict, List
from cortex.tools.base import ToolSpec

_REGISTRY: Dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> None:
    _REGISTRY[spec.name] = spec


def get(name: str) -> ToolSpec:
    if name not in _REGISTRY:
        raise KeyError(f"Tool not registered: {name}")
    return _REGISTRY[name]


def list_tools() -> List[ToolSpec]:
    return sorted(_REGISTRY.values(), key=lambda t: t.name)