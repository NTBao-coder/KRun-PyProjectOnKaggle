import os
import subprocess
import sys
import shutil
from pathlib import Path

from krun.packaging import collect_project_files, prepare_workspace
from krun.project import discover_project


def test_large_package_runs_from_dataset_and_rejects_corruption(tmp_path: Path) -> None:
    from krun.packaging import MAX_RUNNER_BYTES

    root = tmp_path / "source"
    root.mkdir()
    create_sample_project(root)
    (root / "data.bin").write_bytes(os.urandom(800_000))
    (root / ".env").write_text("SECRET=excluded")
    result = prepare_workspace(discover_project(root), tmp_path / "job/workspace", [])
    assert result.archive is not None
    assert result.runner.stat().st_size < MAX_RUNNER_BYTES
    inputs = tmp_path / "input/datasets/owner/package"
    inputs.mkdir(parents=True)
    uploaded = inputs / result.archive.name
    shutil.copyfile(result.archive, uploaded)
    remote = tmp_path / "remote"
    env = {**os.environ, "KRUN_INPUT_DIR": str(tmp_path / "input"), "KRUN_WORKING_DIR": str(remote)}
    completed = subprocess.run([sys.executable, str(result.runner)], env=env, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert (remote / "krun_outputs/outputs/result.txt").read_text() == "local import works"
    assert (remote / "krun_project/data.bin").read_bytes() == (root / "data.bin").read_bytes()
    assert not (remote / "krun_project/.env").exists()
    uploaded.write_bytes(b"corrupt")
    completed = subprocess.run([sys.executable, str(result.runner)], env=env, capture_output=True, text=True)
    assert completed.returncode != 0
    assert "checksum mismatch" in completed.stderr


def create_sample_project(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "message.py").write_text("VALUE = 'local import works'\n", encoding="utf-8")
    (root / "main.py").write_text(
        "from pathlib import Path\n"
        "from src.message import VALUE\n"
        "Path('outputs').mkdir()\n"
        "Path('outputs/result.txt').write_text(VALUE)\n",
        encoding="utf-8",
    )
    (root / "krun.yaml").write_text(
        "project:\n  name: sample\nentrypoint:\n  file: main.py\noutputs:\n  - outputs/\n",
        encoding="utf-8",
    )


def test_collect_project_files_excludes_secrets_and_custom_ignores(tmp_path: Path) -> None:
    create_sample_project(tmp_path)
    (tmp_path / ".env").write_text("SECRET=value", encoding="utf-8")
    (tmp_path / "notes.txt").touch()
    (tmp_path / ".krunignore").write_text("notes.txt\n", encoding="utf-8")

    names = {path.relative_to(tmp_path).as_posix() for path in collect_project_files(tmp_path)}

    assert ".env" not in names
    assert "notes.txt" not in names
    assert "main.py" in names


def test_generated_runner_preserves_imports_and_collects_outputs(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    create_sample_project(root)
    workspace = tmp_path / "workspace"
    result = prepare_workspace(discover_project(root), workspace, [])
    remote_working = tmp_path / "remote"
    env = {**os.environ, "KRUN_WORKING_DIR": str(remote_working)}

    completed = subprocess.run(
        [sys.executable, str(result.runner)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    artifact = remote_working / "krun_outputs" / "outputs" / "result.txt"
    assert artifact.read_text(encoding="utf-8") == "local import works"


def test_explicit_input_overrides_ignore_file(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    create_sample_project(root)
    data = root / "data"
    data.mkdir()
    (data / "sample.csv").write_text("value\n1\n", encoding="utf-8")
    (root / ".krunignore").write_text("data/\n", encoding="utf-8")

    workspace = tmp_path / "workspace"
    result = prepare_workspace(
        discover_project(root),
        workspace,
        [],
        input_paths=[data],
    )
    remote_working = tmp_path / "remote"
    env = {**os.environ, "KRUN_WORKING_DIR": str(remote_working)}

    completed = subprocess.run(
        [sys.executable, str(result.runner)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (remote_working / "krun_project" / "data" / "sample.csv").is_file()


def test_runner_installs_nested_dependency_project(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    create_sample_project(root)
    backend = root / "BackEnd"
    backend.mkdir()
    (backend / "pyproject.toml").write_text(
        "[project]\nname = 'nested-demo'\nversion = '0.1.0'\n",
        encoding="utf-8",
    )

    result = prepare_workspace(discover_project(root), tmp_path / "workspace", [])
    runner = result.runner.read_text(encoding="utf-8")

    assert "DEPENDENCY_PROJECT = 'BackEnd'" in runner
