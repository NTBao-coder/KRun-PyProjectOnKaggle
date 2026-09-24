from typing import Optional

import typer

from krun import __version__

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


if __name__ == "__main__":
    app()

