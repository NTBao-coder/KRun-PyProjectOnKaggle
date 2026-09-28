"""User-facing commands for preparing and managing Kaggle jobs."""

import json
import os
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from typer.core import TyperCommand
from typer.main import get_command

from krun import __version__
from krun.config import CONFIG_FILE, write_default_config
from krun.errors import KrunError
from krun.demos import DemoName, create_demo
from krun.jobs import Job, JobStore, new_kernel_slug
from krun.kaggle import KaggleClient, kaggle_username, normalize_accelerator, write_kernel_metadata
from krun.packaging import package_files, prepare_workspace
from krun.project import discover_project, find_project_root, resolve_project_path

console = Console()
app = typer.Typer(
    name="krun", help="Run Python scripts, modules and notebooks on Kaggle.",
    no_args_is_help=True,
)
auth_app = typer.Typer(help="Manage Kaggle authentication.")
app.add_typer(auth_app, name="auth")


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"krun {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", callback=version_callback, is_eager=True
    ),
) -> None:
    """Run Python jobs using your own Kaggle account."""


def host_path(path: Path) -> str:
    """Translate mounted paths back to the host for terminal messages."""
    root = os.environ.get("KRUN_HOST_ROOT")
    resolved = path.resolve()
    if root and resolved.is_relative_to(Path("/workspace")):
        relative = resolved.relative_to("/workspace").as_posix()
        return root if relative == "." else root.rstrip("/\\") + "/" + relative
    return str(resolved)


def _store(project: Path | None = None) -> JobStore:
    return JobStore(project.resolve() if project else find_project_root(Path.cwd()))


def _download(client: KaggleClient, store: JobStore, job: Job, destination: Path) -> None:
    try:
        client.download_output(job.kernel, destination)
    except KrunError as exc:
        job.download_status = "error"
        job.error = str(exc)
        store.save(job)
        raise
    job.download_status = "complete"
    job.error = None
    store.save(job)
    console.print(f"Downloaded artifacts: {host_path(destination)}")


def _monitor(client: KaggleClient, store: JobStore, job: Job, timeout: int) -> None:
    """Poll bounded requests so a broken log stream cannot strand a job."""
    deadline = time.monotonic() + timeout
    previous_logs = ""
    previous_status = None
    log_warning = False
    try:
        while True:
            current, detail = client.status(job.kernel)
            job.status = current
            store.save(job)
            if current != previous_status:
                console.print(f"Status: {current.upper()}")
                previous_status = current
            try:
                content = client.logs(job.kernel)
                if content != previous_logs:
                    new = content[len(previous_logs):] if content.startswith(previous_logs) else content
                    console.print(new, markup=False, end="" if new.endswith("\n") else "\n")
                    previous_logs = content
                (store.directory(job.job_id) / "logs.txt").write_text(content, encoding="utf-8")
            except KrunError:
                if not log_warning:
                    console.print("Logs temporarily unavailable; continuing status monitoring. Retry 'krun logs' later.")
                    log_warning = True
            if current in {"complete", "error", "cancelled", "canceled"}:
                break
            if time.monotonic() >= deadline:
                raise KrunError(f"Monitoring timed out. Resume with: krun wait {job.job_id}")
            time.sleep(min(5, max(0, deadline - time.monotonic())))
        destination = store.directory(job.job_id) / "output"
        if current == "complete":
            _download(client, store, job, destination)
            console.print("[green]Completed successfully.[/green]")
        else:
            try:
                _download(client, store, job, destination)
            except KrunError:
                pass  # The remote failure remains the primary error.
            raise KrunError(f"Kaggle job finished with status '{current}'. {detail}")
    except KeyboardInterrupt:
        console.print(f"Monitoring stopped; remote job may still run. Resume: krun wait {job.job_id}")
        raise typer.Exit(130)
    except KrunError as exc:
        job.error = str(exc)
        store.save(job)
        raise


@app.command()
def login(force: bool = typer.Option(False, "--force", help="Sign in again.")) -> None:
    """Sign in once using a browser verification code."""
    client = KaggleClient()
    if not client.executable:
        raise KrunError("Kaggle CLI is missing. Reinstall KRun with its declared dependencies.")
    client.login(force)


@auth_app.command("status")
def auth_status() -> None:
    """Verify credentials with Kaggle without printing tokens."""
    client = KaggleClient()
    username = client.verify_auth()
    console.print(f"Authenticated as {username}")


@app.command()
def doctor() -> None:
    """Check runtime, write access and Kaggle authentication."""
    console.print(f"KRun {__version__}; workspace: {host_path(Path.cwd())}")
    if not os.access(Path.cwd(), os.W_OK):
        raise KrunError("Workspace is not writable. Check directory permissions.")
    auth_status()
    console.print("Checks passed. Accelerator availability and quota are checked when Kaggle accepts the job.")


@app.command()
def init(
    project_name: Optional[str] = typer.Option(None, "--name"),
    entrypoint: str = typer.Option("main.py", "--entrypoint"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Optionally save defaults in krun.yaml; run does not require it."""
    path = Path.cwd() / CONFIG_FILE
    if path.exists() and not force:
        raise KrunError("Configuration already exists. Use --force to replace it.")
    write_default_config(path, project_name or Path.cwd().name, entrypoint)
    console.print(f"Created {host_path(path)}")


@app.command(context_settings={"allow_extra_args": True})
def run(
    ctx: typer.Context,
    entrypoint: Optional[str] = typer.Argument(None, help=".py or .ipynb file."),
    module: Optional[str] = typer.Option(None, "--module", "-m"),
    project: Optional[Path] = typer.Option(None, "--project", help="Explicit project root."),
    gpu: Optional[str] = typer.Option(None, "--gpu"),
    accelerator: Optional[str] = typer.Option(None, "--accelerator"),
    owner: Optional[str] = typer.Option(None, "--owner"),
    requirements: Optional[Path] = typer.Option(None, "--requirements"),
    dependency_project: Optional[Path] = typer.Option(None, "--dependency-project"),
    packages: Optional[list[str]] = typer.Option(None, "--package", help="Explicit extra pip requirement; repeatable."),
    output_paths: Optional[list[str]] = typer.Option(None, "--output", help="Project-relative artifact path; repeatable."),
    input_paths: Optional[list[Path]] = typer.Option(None, "--input"),
    datasets: Optional[list[str]] = typer.Option(None, "--dataset", help="Existing Kaggle dataset owner/slug; repeatable."),
    secret_names: Optional[list[str]] = typer.Option(None, "--secret", help="Enabled Kaggle Secret name; never a value."),
    cwd: str = typer.Option(".", "--cwd", help="Project-relative execution directory."),
    timeout: int = typer.Option(3600, "--timeout", min=1, help="Local monitoring deadline in seconds."),
    cell_timeout: int = typer.Option(600, "--cell-timeout", min=1),
    internet: Optional[bool] = typer.Option(None, "--internet/--no-internet"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    detach: bool = typer.Option(False, "--detach"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    """Run a file/module without changing project source. Forward arguments after --."""
    args = list(ctx.args)
    if module and entrypoint:
        args.insert(0, str(entrypoint))
        entrypoint = None
    selected = discover_project(
        Path.cwd(), Path(entrypoint) if entrypoint else None,
        project, module, requirements, dependency_project, output_paths,
    )
    workdir = resolve_project_path(selected.root, Path(cwd), "working directory")
    if not workdir.is_dir():
        raise KrunError("Working directory does not exist.")
    inputs = [resolve_project_path(selected.root, path, "input") for path in input_paths or []]
    for path in inputs:
        if not path.exists():
            raise KrunError(f"Input not found: {path}")
    if gpu and accelerator:
        raise KrunError("Use --gpu or --accelerator, not both.")
    shape = normalize_accelerator(gpu or accelerator or selected.config.runtime.accelerator)
    for dataset in datasets or []:
        if len(dataset.split("/")) != 2 or not all(dataset.split("/")):
            raise KrunError("Dataset must be owner/slug.")
    for name in secret_names or []:
        if not name.isidentifier():
            raise KrunError("Secret names must be environment-variable identifiers, not token values.")
    for package in packages or []:
        if not package or package.startswith("-"):
            raise KrunError("--package accepts a pip requirement, not pip command options.")
    files = package_files(selected, inputs)
    console.print(f"Project: {host_path(selected.root)}")
    console.print(f"Entrypoint: {module or selected.entrypoint.relative_to(selected.root)}")
    console.print(f"Accelerator: {shape or 'CPU'}; {len(files)} files; {sum(path.stat().st_size for path in files)} bytes")
    console.print(f"Dependencies: {selected.requirements or selected.pyproject or 'none declared'}")
    network_enabled = selected.config.runtime.internet if internet is None else internet
    console.print(f"Internet: {network_enabled}")
    if packages:
        console.print(f"Extra packages: {packages}", markup=False)
    if selected.entrypoint.suffix == ".ipynb":
        if args:
            raise KrunError("Notebook arguments are not supported. Use notebook code/configuration; script/module arguments go after --.")
        notebook = json.loads(selected.entrypoint.read_text(encoding="utf-8"))
        language = notebook.get("metadata", {}).get("kernelspec", {}).get("language", "python")
        if language != "python":
            raise KrunError("Only Python notebooks are supported.")
    if dry_run:
        console.print("Dry run: no submission, no credentials needed, no job created.")
        for path in files:
            console.print(path.relative_to(selected.root).as_posix(), markup=False)
        console.print(f"Outputs: {selected.config.outputs}")
        return
    client = KaggleClient(verbose=verbose)
    client.validate_environment()
    username = kaggle_username(owner)
    store = JobStore(selected.root)
    job = store.create("pending", selected.root, selected.entrypoint, shape or "CPU")
    slug = new_kernel_slug(selected.config.project.name, job.job_id)
    job.kernel = f"{username}/{slug}"
    store.save(job)
    workspace = store.directory(job.job_id) / "workspace"
    try:
        prepare_workspace(
            selected, workspace, args, inputs, cell_timeout,
            workdir.relative_to(selected.root).as_posix(), secret_names, packages,
        )
        write_kernel_metadata(workspace, job.kernel, slug.replace("-", " "), network_enabled, datasets)
        job.status = "submitting"
        store.save(job)
        response = client.submit(workspace, shape)
    except (KrunError, OSError, ValueError) as exc:
        job.status = "submission_unknown" if job.status == "submitting" else "preparation_error"
        job.error = str(exc)
        store.save(job)
        raise KrunError(f"{exc}\nInspect https://www.kaggle.com/code/{job.kernel} before submitting again.") from exc
    job.status = "submitted"
    store.save(job)
    console.print(f"Submitted https://www.kaggle.com/code/{job.kernel}")
    console.print(f"Job ID: {job.job_id}")
    if verbose:
        console.print(response, markup=False)
    if not detach:
        _monitor(client, store, job, timeout)


@app.command("jobs")
def list_jobs(project: Optional[Path] = typer.Option(None, "--project")) -> None:
    """List local jobs and download state."""
    jobs = _store(project).list_jobs()
    if not jobs:
        console.print("No jobs found.")
    for job in jobs:
        console.print(f"{job.job_id}  {job.status}  download={job.download_status}  {job.entrypoint}")


@app.command("wait")
def wait_job(
    job_id: Optional[str] = typer.Argument(None),
    project: Optional[Path] = typer.Option(None, "--project"),
    timeout: int = typer.Option(3600, "--timeout", min=1),
) -> None:
    """Resume monitoring and download artifacts without resubmitting."""
    store = _store(project)
    job = store.load(job_id) if job_id else store.latest()
    client = KaggleClient()
    client.validate_environment()
    _monitor(client, store, job, timeout)


@app.command()
def status(
    job_id: Optional[str] = typer.Argument(None),
    project: Optional[Path] = typer.Option(None, "--project"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    """Fetch job status; defaults to the latest job."""
    store = _store(project)
    job = store.load(job_id) if job_id else store.latest()
    client = KaggleClient(verbose=verbose)
    client.validate_environment()
    job.status, detail = client.status(job.kernel)
    store.save(job)
    console.print(f"Job: {job.job_id}\nStatus: {job.status.upper()}\nDownload: {job.download_status}")
    if verbose:
        console.print(detail, markup=False)


@app.command()
def logs(
    job_id: Optional[str] = typer.Argument(None),
    project: Optional[Path] = typer.Option(None, "--project"),
    follow: bool = typer.Option(False, "--follow", "-f"),
    timeout: int = typer.Option(3600, "--timeout", min=1),
) -> None:
    """Read logs, or follow the job to completion and download results."""
    store = _store(project)
    job = store.load(job_id) if job_id else store.latest()
    client = KaggleClient()
    client.validate_environment()
    if follow:
        _monitor(client, store, job, timeout)
    else:
        content = client.logs(job.kernel)
        (store.directory(job.job_id) / "logs.txt").write_text(content, encoding="utf-8")
        console.print(content, markup=False)


@app.command()
def output(
    job_id: Optional[str] = typer.Argument(None),
    project: Optional[Path] = typer.Option(None, "--project"),
    path: Optional[Path] = typer.Option(None, "--path"),
) -> None:
    """Download artifacts independently of monitoring."""
    store = _store(project)
    job = store.load(job_id) if job_id else store.latest()
    client = KaggleClient()
    client.validate_environment()
    _download(client, store, job, path.resolve() if path else store.directory(job.job_id) / "output")


class DemoCommand(TyperCommand):
    """Keep the script argument boundary when forwarding to the run command."""

    def parse_args(self, ctx: typer.Context, args: list[str]) -> list[str]:
        if "--" in args:
            boundary = args.index("--")
            ctx.meta["demo_script_args"] = args[boundary:]
            args = args[:boundary]
        return super().parse_args(ctx, args)


@app.command(cls=DemoCommand, context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def demo(
    ctx: typer.Context,
    name: DemoName = typer.Argument(DemoName.sales_report),
    destination: Optional[Path] = typer.Option(
        None, "--destination", help="New directory for the demo (must not exist)."
    ),
    copy_only: bool = typer.Option(False, "--copy-only", help="Create files without submitting a job."),
) -> None:
    """Copy a bundled demo, then run it. Additional options are passed to 'run'."""
    extra = list(ctx.args)
    # Project and entrypoint are fixed by the selected template.
    for value in extra:
        if value.split("=", 1)[0] in {"--project", "--module", "-m"}:
            raise KrunError("Demo selects its own project and entrypoint. Use 'krun run' for custom projects.")
    extra.extend(ctx.meta.get("demo_script_args", []))
    if copy_only and extra:
        raise KrunError("--copy-only does not accept run options or script arguments.")
    root, entrypoint = create_demo(name, destination)
    console.print(f"Demo project: {host_path(root)}")
    if not copy_only:
        get_command(app).main(
            args=["run", *entrypoint, "--project", str(root), *extra],
            prog_name="krun", standalone_mode=False,
        )


def run_cli() -> None:
    try:
        app()
    except (KrunError, OSError, ValueError) as exc:
        console.print(f"Error: {exc}", markup=False)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    run_cli()
