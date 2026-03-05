from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.pretty import Pretty
from rich import box
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
from cortex.tools.browser import fsafe_browser_fetch
from cortex.runtime.config import effective_allowed_paths

from cortex.tools.browser import fsafe_browser_fetch, fsafe_browser_open

from cortex.tools.email import fsafe_email_compose

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
    register(ToolSpec(name="browser.fetch", risk="SAFE", fn=fsafe_browser_fetch))

    register(ToolSpec(name="browser.fetch", risk="SAFE", fn=fsafe_browser_fetch))
    register(ToolSpec(name="browser.open", risk="SAFE", fn=fsafe_browser_open))
    register(ToolSpec(name="email.compose", risk="SAFE", fn=fsafe_email_compose))


@app.callback()
def _main() -> None:
    _bootstrap_tools()


# ---------------- UX HELPERS ----------------

def _risk_style(risk: str) -> str:
    r = (risk or "").upper()
    if r == "SAFE":
        return "green"
    if r == "MODIFY":
        return "yellow"
    if r == "CRITICAL":
        return "red"
    return "white"


def _risk_badge(risk: str) -> Text:
    r = (risk or "UNKNOWN").upper()
    t = Text(r)
    t.stylize(f"bold {_risk_style(r)}")
    return t


def _render_secure_banner(cfg: dict) -> None:
    secure = (cfg.get("secure") or {})
    enabled = bool(secure.get("enabled"))
    if not enabled:
        return

    allowed = secure.get("allowed_paths") or []
    lines = [
        "[bold green]SECURE MODE ENABLED[/bold green]",
        "[dim]SAFE tools only. MODIFY/CRITICAL will be blocked.[/dim]",
    ]
    if allowed:
        lines.append("")
        lines.append("[bold]Allowed paths:[/bold]")
        for p in allowed:
            lines.append(f"  • {p}")
    else:
        lines.append("")
        lines.append(
            "[yellow]Allowed paths not set — default HOME-only policy applies.[/yellow]"
        )

    console.print(
        Panel("\n".join(lines), title="security", border_style="green"))


def _pretty_fs_list(output) -> bool:
    # output is typically: [{"name": "...", "path": "...", "type": "dir/file"}, ...]
    if isinstance(output, list) and output and isinstance(output[0], dict) and "name" in output[0]:
        for it in output:
            name = it.get("name", "")
            typ = it.get("type", "")
            badge = "[dim](dir)[/dim]" if typ == "dir" else ""
            console.print(f"{name} {badge}")
        return True
    return False


def _render_plan(result, dry_run: bool) -> None:
    title = "Plan Generated (dry-run)" if dry_run else "Plan Executed"
    console.print(Panel.fit(title, title=f"session {result.session_id}"))

    table = Table(
        title="Plan Steps",
        box=box.SIMPLE,
        show_lines=True,
        header_style="bold",
    )
    table.add_column("Step", style="bold", width=10)
    table.add_column("Description")
    table.add_column("Tool", style="cyan")
    table.add_column("Risk", justify="center", width=10)

    for s in result.plan.steps:
        table.add_row(
            str(s.id),
            s.description,
            s.tool,
            _risk_badge(s.risk_level),
        )

    console.print(table)

    # Optional: show params in a compact way
    if result.plan.steps:
        console.print("[bold]Step Params[/bold]")
        for s in result.plan.steps:
            console.print(f"[bold]{s.id}[/bold] {s.tool}")
            console.print(Pretty(s.params, indent_guides=True))
    else:
        console.print("[yellow]Planner returned no steps.[/yellow]")


def _render_results(result) -> None:
    console.print("\n[bold]Results[/bold]")

    if not result.results:
        console.print("[yellow]No steps executed.[/yellow]")
        console.print(
            "[dim]Possible reasons: approval denied, secure mode blocked, or no executable steps.[/dim]"
        )
        return

    ok = 0
    fail = 0

    for r in result.results:
        if r.ok:
            ok += 1
            console.print(
                f"[green]OK[/green] {r.step_id} [cyan]{r.tool}[/cyan]")

            if r.tool == "filesystem.list" and _pretty_fs_list(r.output):
                pass
            else:
                console.print(Pretty(r.output, indent_guides=True))

        else:
            fail += 1
            console.print(f"[red]FAIL[/red] {r.step_id} [cyan]{r.tool}[/cyan]")
            # Better “secure mode blocked” readability (best-effort until Phase 1.9.1)
            err = str(r.error or "")
            if "secure" in err.lower() and "block" in err.lower():
                console.print(
                    Panel(
                        err, title="[red]SECURITY BLOCKED[/red]", border_style="red")
                )
            else:
                console.print(
                    Panel(err or "Unknown error",
                          title="[red]Error[/red]", border_style="red")
                )

    # Summary
    total = ok + fail
    status = "[green]SUCCESS[/green]" if fail == 0 else "[red]FAILED[/red]"
    summary = Table(box=box.SIMPLE, show_header=False)
    summary.add_row("Steps executed", str(total))
    summary.add_row("Succeeded", f"[green]{ok}[/green]")
    summary.add_row("Failed", f"[red]{fail}[/red]")
    summary.add_row("Status", status)

    console.print(Panel(summary, title="Execution Summary"))

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
    cfg = load_config()
    _render_secure_banner(cfg)

    result = run_task(task, dry_run=dry_run, non_interactive=non_interactive)

    _render_plan(result, dry_run=dry_run)

    if not dry_run:
        _render_results(result)


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
