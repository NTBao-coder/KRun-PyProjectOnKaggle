from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from krun import __version__
from krun.config import CONFIG_FILE, write_default_config
from krun.errors import KrunError
from krun.jobs import JobStore, new_kernel_slug
from krun.kaggle import KaggleClient, kaggle_username, normalize_accelerator, write_kernel_metadata
from krun.packaging import prepare_workspace
from krun.project import discover_project, resolve_project_path

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


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run(
    ctx: typer.Context,
    entrypoint: Optional[Path] = typer.Argument(None, help="Python file to run."),
    gpu: Optional[str] = typer.Option(None, "--gpu", help="GPU type: T4 or P100."),
    accelerator: Optional[str] = typer.Option(
        None,
        "--accelerator",
        help="Accelerator: CPU, T4, P100, or TPU.",
    ),
    owner: Optional[str] = typer.Option(None, "--owner", help="Kaggle username."),
    input_paths: Optional[list[Path]] = typer.Option(None, "--input", help="Local input inside the project."),
    verbose: bool = typer.Option(False, "--verbose", help="Show additional command output."),
) -> None:
    """Package and submit a Python project to Kaggle."""
    project = discover_project(Path.cwd(), entrypoint)
    for input_path in input_paths or []:
        resolved = resolve_project_path(project.root, input_path, "input")
        if not resolved.exists():
            raise KrunError(f"Input path not found: {resolved}")

    requested = gpu or accelerator or project.config.runtime.accelerator
    machine_shape = normalize_accelerator(requested)
    client = KaggleClient(verbose=verbose)
    client.validate_environment()
    username = kaggle_username(owner)

    store = JobStore(project.root)
    placeholder_id = "pending"
    slug_seed = new_kernel_slug(project.config.project.name, placeholder_id)
    kernel = f"{username}/{slug_seed}"
    job = store.create(kernel, project.root, project.entrypoint, machine_shape or "CPU")
    slug = new_kernel_slug(project.config.project.name, job.job_id)
    job.kernel = f"{username}/{slug}"
    store.save(job)
    workspace = store.directory(job.job_id) / "workspace"

    console.print("Scanning project...")
    package = prepare_workspace(project, workspace, list(ctx.args))
    console.print(f"[green]OK[/green] Entrypoint: {project.entrypoint.relative_to(project.root)}")
    console.print(f"[green]OK[/green] {package.file_count} project files packaged")
    write_kernel_metadata(
        workspace,
        job.kernel,
        slug.replace("-", " "),
        project.config.runtime.internet,
    )

    console.print("Submitting Kaggle kernel...")
    response = client.submit(workspace, machine_shape)
    job.status = "submitted"
    store.save(job)
    console.print(f"[green]Submitted[/green] {job.kernel}")
    console.print(f"Job ID: {job.job_id}")
    if verbose and response:
        console.print(response)


def run_cli() -> None:
    try:
        app()
    except KrunError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc


if __name__ == "__main__":
    run_cli()
