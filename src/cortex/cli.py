from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from getpass import getpass
from pathlib import Path

from cortex.security.path_guard import enforce_allowed_path, PathViolation
from cortex.runtime.config import load_config, write_config, config_path
from cortex.tools.base import ToolSpec
from cortex.tools.filesystem import *
from cortex.tools.registry import register, list_tools
from cortex.agent.loop import run_task
from cortex.cli_llm import app as llm_app
from cortex.security.passwords import hash_password, verify_password
from cortex.runtime.logging import audit_event

from cortex.runtime.config import effective_allowed_paths

from cortex.tools.filesystem import fs_delete

app = typer.Typer(add_completion=False,
                  help="Cortex Engine — secure local-first runtime.")
console = Console()

config_app = typer.Typer(help="Config management")
permissions_app = typer.Typer(help="Permissions / sandbox info")
tools_app = typer.Typer(help="Tool registry")
sandbox_app = typer.Typer(help="Sandbox guard utilities")
secure_app = typer.Typer(help="Secure mode controls (SAFE-only hard lock).")

app.add_typer(config_app, name="config")
app.add_typer(permissions_app, name="permissions")
app.add_typer(tools_app, name="tools")
app.add_typer(sandbox_app, name="sandbox")
app.add_typer(llm_app, name="llm")
app.add_typer(secure_app, name="secure")


def _bootstrap_tools() -> None:
    register(ToolSpec(name="filesystem.list", risk="SAFE", fn=fs_list))
    register(ToolSpec(name="filesystem.search", risk="SAFE", fn=fs_search))
    register(ToolSpec(name="filesystem.read_text", risk="SAFE", fn=fs_read_text))
    register(ToolSpec(name="filesystem.write_text",
             risk="MODIFY", fn=fs_write_text))
    register(ToolSpec(name="filesystem.delete", risk="CRITICAL", fn=fs_delete))


@app.callback()
def _main() -> None:
    _bootstrap_tools()


# ---------------- CONFIG ----------------

@config_app.command("init")
def config_init() -> None:
    cfg = load_config()
    p = write_config(cfg)
    console.print(Panel.fit(f"Config written: {p}", title="cortex"))


# ---------------- PERMISSIONS ----------------

@permissions_app.command("show")
def permissions_show() -> None:
    cfg = load_config()
    allowed = effective_allowed_paths(cfg) or ["(default) HOME directory"]

    t = Table(title="Cortex Permissions")
    t.add_column("Allowed Paths")
    for p in allowed:
        t.add_row(str(p))
    console.print(t)
    console.print(f"[dim]Config: {config_path()}[/dim]")


# ---------------- TOOLS ----------------

@tools_app.command("list")
def tools_list() -> None:
    t = Table(title="Registered Tools")
    t.add_column("Name")
    t.add_column("Risk")
    for tool in list_tools():
        t.add_row(tool.name, tool.risk)
    console.print(t)


# ---------------- SANDBOX ----------------

@sandbox_app.command("check")
def sandbox_check(
    path: str = typer.Argument(...,
                               help="Path to test against sandbox allowlist")
) -> None:
    cfg = load_config()
    allowed = effective_allowed_paths(cfg) or ["(default) HOME directory"]

    try:
        rp = enforce_allowed_path(path, allowed)
        console.print(f"[green]ALLOWED[/green] {rp}")
    except PathViolation as e:
        console.print(f"[red]DENIED[/red] {e}")
        raise typer.Exit(code=3)


# ---------------- SECURE MODE ----------------

@secure_app.command("status")
def secure_status():
    cfg = load_config()
    secure = cfg.get("secure") or {}
    typer.echo(f"secure.enabled = {bool(secure.get('enabled'))}")
    typer.echo(f"secure.allowed_paths = {secure.get('allowed_paths') or []}")


@secure_app.command("enable")
def secure_enable():
    cfg = load_config()

    confirm = input(
        "Type YES to enable secure mode (SAFE tools only): ").strip()
    if confirm.lower() != "yes":
        typer.echo("Secure mode enable cancelled.")
        raise typer.Exit(code=1)

    pw1 = getpass("Set secure mode password: ")
    pw2 = getpass("Confirm password: ")
    if pw1 != pw2:
        raise typer.BadParameter("Passwords do not match")

    cfg.setdefault("secure", {})
    cfg["secure"]["password_hash"] = hash_password(pw1)
    cfg["secure"]["enabled"] = True
    cfg["secure"].setdefault("allowed_paths", [])
    write_config(cfg)
    audit_event("secure_mode_enabled", {"secure_enabled": True})
    typer.echo("Secure mode ENABLED (SAFE tools only).")


@secure_app.command("disable")
def secure_disable():
    cfg = load_config()

    secure = cfg.get("secure") or {}
    stored = secure.get("password_hash")
    if not stored:
        audit_event("secure_password_failed", {"reason": "no_password_hash"})
        raise typer.BadParameter(
            "Secure mode password is not set. Cannot disable securely.")

    pw = getpass("Enter secure mode password to disable: ")
    if not verify_password(pw, stored):
        audit_event("secure_password_failed", {"reason": "invalid_password"})
        raise typer.BadParameter("Invalid password")

    cfg.setdefault("secure", {})
    cfg["secure"]["enabled"] = False
    write_config(cfg)
    audit_event("secure_mode_disabled", {"secure_enabled": False})
    typer.echo("Secure mode DISABLED.")


@secure_app.command("allow-path")
def secure_allow_path(path: str):
    cfg = load_config()

    p = str(Path(path).expanduser().resolve())
    cfg.setdefault("secure", {})
    cfg["secure"].setdefault("allowed_paths", [])
    if p not in cfg["secure"]["allowed_paths"]:
        cfg["secure"]["allowed_paths"].append(p)
        write_config(cfg)

    audit_event("secure_allowed_path_added", {"path": p})
    typer.echo(f"Allowed path added: {p}")


@secure_app.command("clear-paths")
def secure_clear_paths():
    cfg = load_config()
    cfg.setdefault("secure", {})
    cfg["secure"]["allowed_paths"] = []
    write_config(cfg)
    audit_event("secure_allowed_paths_cleared", {})
    typer.echo("Allowed paths cleared.")


# ---------------- RUN ----------------

@app.command("run")
def run(
    task: str = typer.Argument(..., help="Natural language task"),
    dry_run: bool = typer.Option(
        True, "--dry-run/--execute", help="Dry run prints plan only"),
    non_interactive: bool = typer.Option(
        False, "--non-interactive", help="Fail if approval is required"),
) -> None:
    result = run_task(task, dry_run=dry_run, non_interactive=non_interactive)

    console.print(Panel.fit(("Plan Generated (dry-run)" if dry_run else "Plan Executed"),
                  title=f"session {result.session_id}"))

    for s in result.plan.steps:
        console.print(f"[bold]{s.id}[/bold] {s.description}")
        console.print(f"  tool: {s.tool}")
        console.print(f"  risk: {s.risk_level}")
        console.print(f"  params: {s.params}")

    if not dry_run:
        console.print("\n[bold]Results[/bold]")
        for r in result.results:
            if r.ok:
                console.print(f"[green]OK[/green] {r.step_id} {r.tool}")
                console.print(f"  output: {r.output}")
            else:
                console.print(f"[red]FAIL[/red] {r.step_id} {r.tool}")
                console.print(f"  error: {r.error}")
        if not result.results:
            console.print(
                "[yellow]No steps executed (approval denied or dry-run).[/yellow]")


# ---------------- INTERACTIVE ----------------

@app.command("interactive")
def interactive() -> None:
    console.print(
        Panel.fit("Cortex Interactive (Phase 1.1: dry-run only)", title="cortex"))
    console.print("[dim]Type 'exit' to quit.[/dim]")

    while True:
        task = console.input("\n[bold]task>[/bold] ").strip()
        if task.lower() in {"exit", "quit"}:
            break
        result = run_task(task, dry_run=True)
        console.print(
            f"[green]session[/green] {result.session_id} plan steps: {len(result.plan.steps)}")


# ---------------- SHORTCUT ----------------

@app.command("install-shortcut")
def install_shortcut() -> None:
    bat = "Cortex Engine.bat"
    content = "@echo off\r\ncortex interactive\r\n"
    with open(bat, "w", encoding="utf-8") as f:
        f.write(content)
    console.print(Panel.fit(f"Created: {bat}", title="cortex"))


if __name__ == "__main__":
    app()
