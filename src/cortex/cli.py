from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cortex.security.path_guard import enforce_allowed_path, PathViolation
from cortex.runtime.config import load_config, write_config, config_path
from cortex.tools.base import ToolSpec
from cortex.tools.filesystem import fs_list
from cortex.tools.registry import register, list_tools
from cortex.agent.loop import run_task

app = typer.Typer(add_completion=False, help="Cortex Engine — secure local-first runtime.")
console = Console()

config_app = typer.Typer(help="Config management")
permissions_app = typer.Typer(help="Permissions / sandbox info")
tools_app = typer.Typer(help="Tool registry")
sandbox_app = typer.Typer(help="Sandbox guard utilities")

app.add_typer(config_app, name="config")
app.add_typer(permissions_app, name="permissions")
app.add_typer(tools_app, name="tools")
app.add_typer(sandbox_app, name="sandbox")


def _bootstrap_tools() -> None:
    # Phase 1.1: register SAFE tools only
    register(ToolSpec(name="filesystem.list", risk="SAFE", fn=fs_list))


@app.callback()
def _main() -> None:
    _bootstrap_tools()


@config_app.command("init")
def config_init() -> None:
    cfg = load_config()
    p = write_config(cfg)
    console.print(Panel.fit(f"Config written: {p}", title="cortex"))


@permissions_app.command("show")
def permissions_show() -> None:
    cfg = load_config()
    allowed = cfg.get("allowed_paths") or ["(default) HOME directory"]
    t = Table(title="Cortex Permissions")
    t.add_column("Allowed Paths")
    for p in allowed:
        t.add_row(str(p))
    console.print(t)
    console.print(f"[dim]Config: {config_path()}[/dim]")


@tools_app.command("list")
def tools_list() -> None:
    t = Table(title="Registered Tools")
    t.add_column("Name")
    t.add_column("Risk")
    for tool in list_tools():
        t.add_row(tool.name, tool.risk)
    console.print(t)


@sandbox_app.command("check")
def sandbox_check(
    path: str = typer.Argument(..., help="Path to test against sandbox allowlist")
) -> None:
    cfg = load_config()
    allowed = cfg.get("allowed_paths") or []
    try:
        rp = enforce_allowed_path(path, allowed)
        console.print(f"[green]ALLOWED[/green] {rp}")
    except PathViolation as e:
        console.print(f"[red]DENIED[/red] {e}")
        raise typer.Exit(code=3)


@app.command("run")
def run(
    task: str = typer.Argument(..., help="Natural language task"),
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Dry run prints plan only (execute not in Phase 1.1)"),
) -> None:
    if not dry_run:
        console.print("[red]Execute is not enabled in Phase 1.1. Use --dry-run.[/red]")
        raise typer.Exit(code=2)

    result = run_task(task, dry_run=True)

    console.print(Panel.fit("Plan Generated (dry-run)", title=f"session {result.session_id}"))
    for s in result.plan.steps:
        console.print(f"[bold]{s.id}[/bold] {s.description}")
        console.print(f"  tool: {s.tool}")
        console.print(f"  risk: {s.risk_level}")
        console.print(f"  params: {s.params}")


@app.command("interactive")
def interactive() -> None:
    console.print(Panel.fit("Cortex Interactive (Phase 1.1: dry-run only)", title="cortex"))
    console.print("[dim]Type 'exit' to quit.[/dim]")

    while True:
        task = console.input("\n[bold]task>[/bold] ").strip()
        if task.lower() in {"exit", "quit"}:
            break
        result = run_task(task, dry_run=True)
        console.print(f"[green]session[/green] {result.session_id} plan steps: {len(result.plan.steps)}")


@app.command("install-shortcut")
def install_shortcut() -> None:
    # Minimal Phase 1.1: create a .bat in current directory
    bat = "Cortex Engine.bat"
    content = "@echo off\r\ncortex interactive\r\n"
    with open(bat, "w", encoding="utf-8") as f:
        f.write(content)
    console.print(Panel.fit(f"Created: {bat}", title="cortex"))


if __name__ == "__main__":
    app()