import typer
from rich.console import Console

app = typer.Typer(add_completion=False,
                  help="Cortex Engine — Phase 1.0 skeleton.")
console = Console()


@app.command()
def hello() -> None:
    console.print("Cortex Engine is initialized ✅")


if __name__ == "__main__":
    app()
