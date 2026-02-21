from __future__ import annotations

from typing import Any
from cortex.security.path_guard import enforce_allowed_path


def fs_list(path: str, allowed_paths: list[str]) -> list[dict[str, Any]]:
    rp = enforce_allowed_path(path, allowed_paths)
    if not rp.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in rp.iterdir():
        out.append({"name": p.name, "path": str(p), "type": "dir" if p.is_dir() else "file"})
    return out