from __future__ import annotations

from pathlib import Path
import os



SENSITIVE_NAMES = {".env", ".ssh", ".git", "id_rsa", "id_ed25519"}


class PathViolation(Exception):
    pass


def _is_sensitive(p: Path) -> bool:
    parts = {x.lower() for x in p.parts}
    if any(name.lower() in parts for name in SENSITIVE_NAMES):
        return True
    if p.name.lower() in {x.lower() for x in SENSITIVE_NAMES}:
        return True
    return False


def enforce_allowed_path(target: str | Path, allowed_paths: list[str]) -> Path:
    tp = Path(target).expanduser()
    rp = tp.resolve(strict=False)

    if _is_sensitive(rp):
        raise PathViolation(f"Sensitive path denied: {rp}")

    roots = [Path.home().resolve(strict=False)] if not allowed_paths else [
        Path(p).expanduser().resolve(strict=False) for p in allowed_paths
    ]

    ok = any(rp == root or str(rp).startswith(str(root) + os.sep) for root in roots)
    if not ok:
        raise PathViolation(f"Path outside allowed sandbox: {rp}")

    return rp