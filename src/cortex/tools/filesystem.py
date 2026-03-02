from __future__ import annotations
import fnmatch
from typing import List
from pathlib import Path
from typing import Optional

from typing import Any
from cortex.security.path_guard import enforce_allowed_path

__all__ = [
    "fs_list",
    "fs_search",
    "fs_read_text",
    "fs_write_text",
    "fs_move_rename",
    "fs_delete",
]


def fs_list(path: str, allowed_paths: list[str]) -> list[dict[str, Any]]:
    rp = enforce_allowed_path(path, allowed_paths)
    if not rp.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in rp.iterdir():
        out.append({"name": p.name, "path": str(
            p), "type": "dir" if p.is_dir() else "file"})
    return out


def fs_search(path: str, pattern: str, allowed_paths: List[str]) -> list[dict]:
    base = enforce_allowed_path(path, allowed_paths)

    results = []
    for p in Path(base).rglob("*"):
        if fnmatch.fnmatch(p.name, pattern):
            results.append({
                "name": p.name,
                "path": str(p.resolve()),
                "type": "dir" if p.is_dir() else "file",
            })
    return results


MAX_READ_BYTES = 1_000_000  # 1MB


def fs_read_text(path: str, allowed_paths: List[str]) -> str:
    p = enforce_allowed_path(path, allowed_paths)

    p = Path(p)
    if not p.is_file():
        raise ValueError("Not a file")

    size = p.stat().st_size
    if size > MAX_READ_BYTES:
        raise ValueError("File too large (limit 1MB)")

    return p.read_text(encoding="utf-8")


def fs_write_text(
    path: Optional[str] = None,
    content: str = "",
    allowed_paths: list[str] = None,
    file_path: Optional[str] = None,
) -> dict:
    allowed_paths = allowed_paths or []
    target = path or file_path
    if not target:
        raise ValueError("Missing path/file_path")

    rp = enforce_allowed_path(target, allowed_paths)
    p = Path(rp)

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")

    return {"written": str(p)}


def fs_move_rename(src: str, dest: str, allowed_paths: List[str]) -> dict:
    src_p = Path(enforce_allowed_path(src, allowed_paths))
    dest_p = Path(enforce_allowed_path(dest, allowed_paths))

    src_p.rename(dest_p)
    return {"moved": str(dest_p)}


def fs_delete(path: str = None, allowed_paths: list[str] = None, file_path: str = None) -> dict:
    """
    CRITICAL: Delete a file (or empty directory).
    Accepts either `path` or `file_path` for planner robustness.
    """
    allowed_paths = allowed_paths or []
    target = path or file_path
    if not target:
        raise ValueError("Missing path/file_path")

    rp = enforce_allowed_path(target, allowed_paths)
    p = Path(rp)

    if not p.exists():
        raise FileNotFoundError(f"Path not found: {p}")

    # Safety: only delete files or EMPTY dirs in Phase 1.8
    if p.is_file():
        p.unlink()
        return {"deleted": str(p), "type": "file"}

    if p.is_dir():
        # only allow empty directory delete for now
        p.rmdir()
        return {"deleted": str(p), "type": "dir"}

    raise ValueError("Unsupported path type")
