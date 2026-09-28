"""Exercise host argument/mount handling without requiring Docker."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

LAUNCHER = Path(__file__).resolve().parents[1] / "bin" / "krun"
pytestmark = pytest.mark.skipif(os.name == "nt" or not shutil.which("bash"), reason="Bash host launcher test")


def fake_docker(tmp_path: Path) -> dict[str, str]:
    tool = tmp_path / "docker"
    tool.write_text(
        f"#!{sys.executable}\nimport json, sys\n"
        "if sys.argv[1] == 'run': print(json.dumps(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    tool.chmod(0o755)
    return {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "HOME": str(tmp_path / "home"), "KRUN_IMAGE": "krun:test"}


def test_launcher_external_path_and_literal_arguments(tmp_path: Path) -> None:
    project = tmp_path / "project with spaces"
    project.mkdir()
    script = project / "hello.py"
    script.touch()
    completed = subprocess.run(
        ["bash", str(LAUNCHER), "run", str(script), "--", "--message", "hello world", "$(not-executed)"],
        env=fake_docker(tmp_path), capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    args = json.loads(completed.stdout)
    assert f"type=bind,source={project},target=/workspace" in args
    assert args[-6:] == ["run", "/workspace/hello.py", "--", "--message", "hello world", "$(not-executed)"]
    assert "-it" not in args


def test_launcher_project_option_preserves_module_arguments(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    completed = subprocess.run(
        ["bash", str(LAUNCHER), "run", "-m", "demo", "--project", str(project), "--", "--count", "10"],
        env=fake_docker(tmp_path), capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    args = json.loads(completed.stdout)
    assert args[-8:] == ["run", "-m", "demo", "--project", "/workspace", "--", "--count", "10"]


def test_launcher_relative_file_with_explicit_project(tmp_path: Path) -> None:
    project = tmp_path / "external"
    project.mkdir()
    (project / "entry.py").touch()
    completed = subprocess.run(
        ["bash", str(LAUNCHER), "run", "entry.py", "--project", str(project), "--dry-run"],
        cwd=tmp_path, env=fake_docker(tmp_path), capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    args = json.loads(completed.stdout)
    assert args[-5:] == ["run", "/workspace/entry.py", "--project", "/workspace", "--dry-run"]


def test_launcher_without_arguments_or_credentials(tmp_path: Path) -> None:
    environment = fake_docker(tmp_path)
    for name in ("KAGGLE_API_TOKEN", "KAGGLE_USERNAME", "KAGGLE_KEY"):
        environment.pop(name, None)
    completed = subprocess.run(
        ["bash", str(LAUNCHER)], cwd=tmp_path, env=environment,
        capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    args = json.loads(completed.stdout)
    assert args[:2] == ["run", "--rm"]
    assert args[-1] == "krun:test"
    assert "" not in args
    assert "-it" not in args


def test_launcher_login_keeps_stdin_and_passes_environment_names(tmp_path: Path) -> None:
    environment = fake_docker(tmp_path)
    environment["KAGGLE_API_TOKEN"] = "unused-test-token"
    completed = subprocess.run(
        ["bash", str(LAUNCHER), "login"], cwd=tmp_path, env=environment,
        capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    args = json.loads(completed.stdout)
    assert "-i" in args
    assert args[args.index("KAGGLE_API_TOKEN") - 1] == "-e"
    assert "unused-test-token" not in args
    assert args[-2:] == ["krun:test", "login"]
