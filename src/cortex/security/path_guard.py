from __future__ import annotations

from pathlib import Path
import os

from typing import Iterable, Optional


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


def _is_drive_root(p: Path) -> bool:
    # e.g. C:\ or D:\
    try:
        return p.parent == p and str(p).endswith(("\\", "/"))
    except Exception:
        return False


def _windows_protected_prefixes() -> list[Path]:
    # Use environment variables so it works across machines/CI.
    prefixes: list[Path] = []
    windir = os.environ.get("WINDIR")  # usually C:\Windows
    if windir:
        prefixes.append(Path(windir))
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        prefixes.append(Path(program_files))
    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    if program_files_x86:
        prefixes.append(Path(program_files_x86))
    program_data = os.environ.get("ProgramData")
    if program_data:
        prefixes.append(Path(program_data))
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        prefixes.append(Path(local_app_data))
    app_data = os.environ.get("APPDATA")
    if app_data:
        prefixes.append(Path(app_data))
    return [p.expanduser().resolve() for p in prefixes if str(p).strip()]


def _deny_if_system_path(resolved: Path) -> None:
    # Only enforce these on Windows
    if os.name != "nt":
        return
    rp = resolved.resolve()
    # Deny drive root like C:\
    if _is_drive_root(rp):
        raise PathViolation("Drive root access is denied")
    for prefix in _windows_protected_prefixes():
        try:
            if rp == prefix or rp.is_relative_to(prefix):
                raise PathViolation(f"System path access is denied: {prefix}")
        except AttributeError:
            # Python < 3.9 fallback (not needed usually)
            if str(rp).lower().startswith(str(prefix).lower().rstrip("\\") + "\\"):
                raise PathViolation(f"System path access is denied: {prefix}")


def enforce_allowed_path(target: str | Path, allowed_paths: list[str]) -> Path:
    tp = Path(target).expanduser()
    rp = tp.resolve(strict=False)

    if _is_sensitive(rp):
        raise PathViolation(f"Sensitive path denied: {rp}")

    _deny_if_system_path(rp)

    roots = [Path.home().resolve(strict=False)] if not allowed_paths else [
        Path(p).expanduser().resolve(strict=False) for p in allowed_paths
    ]

    ok = any(rp == root or str(rp).startswith(str(root) + os.sep)
             for root in roots)
    if not ok:
        raise PathViolation(f"Path outside allowed sandbox: {rp}")

    return rp
