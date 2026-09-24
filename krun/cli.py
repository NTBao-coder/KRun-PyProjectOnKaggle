from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from krun import __version__
from krun.config import CONFIG_FILE, write_default_config
from krun.errors import KrunError

console = Console()

app = typer.Typer(
    name="krun",
    help="Run local Python projects on Kaggle.",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"krun {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Run local Python projects on Kaggle."""


@app.command()
def init(
    project_name: Optional[str] = typer.Option(None, "--name", help="Project name."),
    entrypoint: str = typer.Option("train.py", help="Default Python entrypoint."),
    force: bool = typer.Option(False, "--force", help="Replace an existing krun.yaml."),
) -> None:
    """Create a krun.yaml in the current directory."""
    path = Path.cwd() / CONFIG_FILE
    if path.exists() and not force:
        console.print(f"[red]Configuration already exists:[/red] {path}")
        raise typer.Exit(1)

    name = project_name or Path.cwd().name
    write_default_config(path, name, entrypoint)
    console.print(f"[green]Created[/green] {path}")


def run_cli() -> None:
    try:
        app()
    except KrunError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc


if __name__ == "__main__":
    run_cli()
