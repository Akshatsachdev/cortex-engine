import json
import subprocess
import sys
from pathlib import Path

from platformdirs import user_data_dir


def run_cli(*args: str) -> subprocess.CompletedProcess:
    """
    Run Cortex CLI via python -m cortex.cli so CI doesn't rely on PATH console script.
    """
    return subprocess.run(
        [sys.executable, "-m", "cortex.cli", *args],
        capture_output=True,
        text=True,
        check=False,  # explicitly handled via assertions
    )


def test_cli_help():
    r = run_cli("--help")
    assert r.returncode == 0, r.stderr


def test_commands_and_logs():
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

    # execute should work (SAFE tool only)
    r = run_cli("run", "--execute", "list current folder")
    assert r.returncode == 0, r.stderr
    assert "Results" in (r.stdout + r.stderr)

    # Cross-platform logs directory (must match runtime/config.py)
    data_dir = Path(user_data_dir("cortex"))
    logs_dir = data_dir / "logs"
    assert logs_dir.exists(), f"Logs dir not found: {logs_dir}"

    logs = sorted(logs_dir.glob("session_*.jsonl"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    assert logs, f"No session logs found in: {logs_dir}"

    latest = logs[0]
    lines = latest.read_text(encoding="utf-8").splitlines()
    assert len(
        lines) >= 2, f"Expected >=2 JSONL lines in {latest}, got {len(lines)}"

    events = [json.loads(line) for line in lines]

    def ev_name(e: dict):
        return e.get("event") or e.get("type")

    ev_names = {ev_name(e) for e in events}
    assert "session_start" in ev_names
    assert "plan_validated" in ev_names

    # Find the plan_validated event that contains the full plan (loop writes {"plan": ...})
    plan_event = next(
        (e for e in events if ev_name(e) ==
         "plan_validated" and isinstance(e.get("plan"), dict)),
        None,
    )

    assert plan_event is not None, "plan_validated event with full 'plan' not found in logs"

    steps = plan_event["plan"]["steps"]
    assert steps and isinstance(steps, list)

    params = steps[0].get("params", {})
    assert "allowed_paths" in params, f"'allowed_paths' missing in plan params. got: {params}"
