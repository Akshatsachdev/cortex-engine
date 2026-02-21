import json
import subprocess
import sys
from pathlib import Path


def run_cli(*args: str) -> subprocess.CompletedProcess:
    """
    Run Cortex CLI via python -m cortex.cli to avoid relying on console-script PATH in CI.
    """
    return subprocess.run(
        [sys.executable, "-m", "cortex.cli", *args],
        capture_output=True,
        text=True,
    )


def test_cli_help():
    r = run_cli("--help")
    assert r.returncode == 0, r.stderr


def test_phase_11_commands_and_logs():
    # config init
    r = run_cli("config", "init")
    assert r.returncode == 0, r.stderr

    # permissions show
    r = run_cli("permissions", "show")
    assert r.returncode == 0, r.stderr

    # tools list includes filesystem.list
    r = run_cli("tools", "list")
    assert r.returncode == 0, r.stderr
    assert "filesystem.list" in (r.stdout + r.stderr)

    # dry-run should work
    r = run_cli("run", "--dry-run", "organize my downloads")
    assert r.returncode == 0, r.stderr
    assert "Plan Generated" in (r.stdout + r.stderr)

    # Verify newest JSONL log exists + contains allowed_paths in plan params
    localappdata = Path.home() / "AppData" / "Local"
    logs_dir = localappdata / "cortex" / "cortex" / "logs"
    assert logs_dir.exists(), f"Logs dir not found: {logs_dir}"

    logs = sorted(logs_dir.glob("session_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    assert logs, f"No session logs found in: {logs_dir}"

    latest = logs[0]
    lines = latest.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 2, f"Expected >=2 JSONL lines in {latest}, got {len(lines)}"

    events = [json.loads(line) for line in lines]
    ev_names = {e.get("event") for e in events}

    assert "session_start" in ev_names
    assert "plan_validated" in ev_names

    # Find plan_validated and ensure allowed_paths is present in params
    plan_event = next(e for e in events if e.get("event") == "plan_validated")
    steps = plan_event["plan"]["steps"]
    assert steps and isinstance(steps, list)

    params = steps[0].get("params", {})
    assert "allowed_paths" in params, f"'allowed_paths' missing in plan params. got: {params}"