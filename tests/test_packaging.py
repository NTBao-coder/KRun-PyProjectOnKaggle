import os
import subprocess
import sys
from pathlib import Path

from krun.packaging import collect_project_files, prepare_workspace
from krun.project import discover_project


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
