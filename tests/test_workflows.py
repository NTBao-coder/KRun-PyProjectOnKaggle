"""Behavioral tests for zero-config jobs, entrypoints and recovery."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from krun.cli import app, _monitor
from krun.errors import KrunError
from krun.jobs import JobStore
from krun.kaggle import KaggleClient
from krun.packaging import package_files, prepare_workspace
from krun.project import discover_project


@pytest.mark.parametrize("upload_fails", [False, True])
def test_large_project_dataset_attachment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, upload_fails: bool) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.py").write_text("print('large project')\n")
    (tmp_path / "data.bin").write_bytes(os.urandom(800_000))
    monkeypatch.setattr(KaggleClient, "validate_environment", lambda client: None)
    calls = []
    def upload(client, archive, dataset):
        assert archive.is_file()
        job = JobStore(tmp_path).latest()
        assert job.package_dataset == dataset
        calls.append("upload")
        if upload_fails:
            raise KrunError("upload failed")
    def submit(client, workspace, accelerator):
        metadata = json.loads((workspace / "kernel-metadata.json").read_text())
        assert metadata["dataset_sources"] == ["owner/existing", JobStore(tmp_path).latest().package_dataset]
        assert metadata["enable_internet"] is False
        calls.append("submit")
        return "submitted"
    monkeypatch.setattr(KaggleClient, "upload_package", upload)
    monkeypatch.setattr(KaggleClient, "submit", submit)
    result = CliRunner().invoke(app, ["run", "main.py", "--owner", "owner", "--dataset", "owner/existing", "--no-internet", "--detach"])
    if upload_fails:
        assert result.exit_code != 0
        assert calls == ["upload"]
        assert JobStore(tmp_path).latest().package_dataset is not None
    else:
        assert result.exit_code == 0, result.output
        assert calls == ["upload", "submit"]


def execute_runner(root: Path, work: Path, module: str | None = None) -> subprocess.CompletedProcess[str]:
    project = discover_project(root, None if module else Path("main.py"), project_root=root, module=module)
    package = prepare_workspace(project, work / "workspace", [])
    return subprocess.run(
        [sys.executable, str(package.runner)],
        env={**os.environ, "KRUN_WORKING_DIR": str(work / "remote")},
        capture_output=True, text=True, check=False,
    )


def test_script_without_yaml_and_sibling_import(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "helper.py").write_text("VALUE = 42\n")
    (scripts / "main.py").write_text("from helper import VALUE\nprint(VALUE)\n")
    project = discover_project(tmp_path, scripts / "main.py", project_root=tmp_path)
    package = prepare_workspace(project, tmp_path / ".krun/workspace", [])
    completed = subprocess.run([sys.executable, str(package.runner)], env={**os.environ, "KRUN_WORKING_DIR": str(tmp_path / ".krun/remote")}, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert "42" in completed.stdout
    assert not (tmp_path / "krun.yaml").exists()


def test_module_relative_imports_and_arguments(tmp_path: Path) -> None:
    package = tmp_path / "demo"
    package.mkdir()
    (package / "__init__.py").touch()
    (package / "helper.py").write_text("VALUE = 7\n")
    (package / "__main__.py").write_text("from .helper import VALUE\nimport sys\nprint(VALUE, sys.argv[1:])\n")
    project = discover_project(tmp_path, project_root=tmp_path, module="demo")
    runner = prepare_workspace(project, tmp_path / ".krun/workspace", ["hello world"])
    completed = subprocess.run([sys.executable, str(runner.runner)], env={**os.environ, "KRUN_WORKING_DIR": str(tmp_path / ".krun/remote")}, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert "7 ['hello world']" in completed.stdout


def test_src_layout_module(tmp_path: Path) -> None:
    package = tmp_path / "src" / "demo"
    package.mkdir(parents=True)
    (package / "__init__.py").touch()
    (package / "__main__.py").write_text("print('src works')\n")
    project = discover_project(tmp_path, project_root=tmp_path, module="demo")
    assert project.module_path == "src"
    runner = prepare_workspace(project, tmp_path / ".krun/workspace", [])
    completed = subprocess.run([sys.executable, str(runner.runner)], env={**os.environ, "KRUN_WORKING_DIR": str(tmp_path / ".krun/remote")}, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert "src works" in completed.stdout


def test_dry_run_without_credentials_does_not_create_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.py").write_text("print('hello')\n")
    result = CliRunner().invoke(app, ["run", "main.py", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "no credentials needed" in result.output
    assert not (tmp_path / ".krun").exists()


def test_module_cli_preserves_first_forwarded_argument(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "demo.py").write_text("import sys\nprint(repr(sys.argv[1:]))\n")
    monkeypatch.setattr(KaggleClient, "validate_environment", lambda client: None)
    results: list[str] = []
    def fake_submit(client: KaggleClient, workspace: Path, accelerator: str) -> str:
        completed = subprocess.run(
            [sys.executable, str(workspace / "runner.py")],
            env={**os.environ, "KRUN_WORKING_DIR": str(tmp_path / ".krun/remote")},
            capture_output=True, text=True,
        )
        assert completed.returncode == 0, completed.stderr
        results.append(completed.stdout)
        return "submitted"
    monkeypatch.setattr(KaggleClient, "submit", fake_submit)
    result = CliRunner().invoke(app, ["run", "-m", "demo", "--owner", "tester", "--detach", "--", "a//b", "hello world"])
    assert result.exit_code == 0, result.output
    assert "['a//b', 'hello world']" in results[0]


def test_notebook_rejects_ignored_arguments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import nbformat
    monkeypatch.chdir(tmp_path)
    nbformat.write(nbformat.v4.new_notebook(), tmp_path / "demo.ipynb")
    result = CliRunner().invoke(app, ["run", "demo.ipynb", "--dry-run", "--", "--unused"])
    assert isinstance(result.exception, KrunError)
    assert "Notebook arguments are not supported" in str(result.exception)


def test_input_cannot_override_secret_filter(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print('hello')\n")
    data = tmp_path / "data"
    data.mkdir()
    (data / ".env").write_text("SECRET=not-a-real-secret\n")
    (data / "credentials.json").write_text("{}")
    (data / "safe.csv").write_text("value\n1\n")
    (tmp_path / ".krunignore").write_text("data/\n")
    files = package_files(discover_project(tmp_path), [data])
    assert data / "safe.csv" in files
    assert data / ".env" not in files
    assert data / "credentials.json" not in files


def test_gitignore_and_negation(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print('hello')\n")
    (tmp_path / "hidden.txt").touch()
    (tmp_path / "keep.txt").touch()
    (tmp_path / ".gitignore").write_text("*.txt\n!keep.txt\n")
    names = {path.name for path in package_files(discover_project(tmp_path))}
    assert "hidden.txt" not in names
    assert "keep.txt" in names


@pytest.mark.parametrize("value", ["../outside", "/tmp/outside", ".", ".krun"])
def test_unsafe_outputs_rejected(tmp_path: Path, value: str) -> None:
    (tmp_path / "main.py").touch()
    with pytest.raises(KrunError):
        discover_project(tmp_path, output_paths=[value])


@pytest.mark.parametrize("job_id", ["../outside", "/tmp/outside", "a/b", ".."])
def test_job_ids_reject_path_traversal(tmp_path: Path, job_id: str) -> None:
    with pytest.raises(KrunError):
        JobStore(tmp_path).directory(job_id)


@pytest.mark.skipif(os.name == "nt", reason="Windows symlink privilege varies")
def test_job_state_cannot_escape_via_symlink(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / ".krun").symlink_to(outside, target_is_directory=True)
    with pytest.raises(KrunError, match="symlinked outside"):
        JobStore(root)


def test_monitor_survives_logs_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    entry = tmp_path / "main.py"
    entry.touch()
    store = JobStore(tmp_path)
    job = store.create("owner/job", tmp_path, entry, "CPU")
    client = KaggleClient(executable="kaggle")
    monkeypatch.setattr(client, "status", lambda kernel: ("complete", "done"))
    def fail_logs(kernel: str) -> str:
        raise KrunError("logs unavailable")
    monkeypatch.setattr(client, "logs", fail_logs)
    monkeypatch.setattr(client, "download_output", lambda kernel, destination: "downloaded")
    _monitor(client, store, job, 30)
    assert store.load(job.job_id).status == "complete"
    assert store.load(job.job_id).download_status == "complete"


def test_download_failure_preserves_remote_complete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    entry = tmp_path / "main.py"
    entry.touch()
    store = JobStore(tmp_path)
    job = store.create("owner/job", tmp_path, entry, "CPU")
    client = KaggleClient(executable="kaggle")
    monkeypatch.setattr(client, "status", lambda kernel: ("complete", "done"))
    monkeypatch.setattr(client, "logs", lambda kernel: "hello")
    def fail_download(kernel: str, destination: Path) -> str:
        raise KrunError("network unavailable")
    monkeypatch.setattr(client, "download_output", fail_download)
    with pytest.raises(KrunError, match="network unavailable"):
        _monitor(client, store, job, 30)
    saved = store.load(job.job_id)
    assert saved.status == "complete"
    assert saved.download_status == "error"


def test_notebook_saves_executed_cells_and_failure(tmp_path: Path) -> None:
    import nbformat
    nbformat_path = tmp_path / "demo.ipynb"
    notebook = nbformat.v4.new_notebook(cells=[
        nbformat.v4.new_code_cell("%time value = 21 * 2\nprint(value)"),
        nbformat.v4.new_code_cell("raise ValueError('expected failure')"),
    ])
    nbformat.write(notebook, nbformat_path)
    project = discover_project(tmp_path, nbformat_path)
    runner = prepare_workspace(project, tmp_path / ".krun/workspace", [])
    completed = subprocess.run([sys.executable, str(runner.runner)], env={**os.environ, "KRUN_WORKING_DIR": str(tmp_path / ".krun/remote")}, capture_output=True, text=True)
    assert completed.returncode != 0
    executed = nbformat.read(tmp_path / ".krun/remote/krun_outputs/notebooks/demo.executed.ipynb", as_version=4)
    assert any("42" in output.get("text", "") for output in executed.cells[0].outputs), completed.stderr
    assert executed.cells[1].outputs[0].ename == "ValueError"


def test_logs_are_readable_json_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    client = KaggleClient(executable="kaggle")
    monkeypatch.setattr(client, "_run", lambda args: json.dumps([{"data": "hello\n"}, {"data": "world\n"}]))
    assert client.logs("owner/job") == "hello\nworld\n"
