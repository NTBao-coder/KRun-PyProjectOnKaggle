"""Exercise installed demo resources and CLI argument forwarding."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from krun.cli import app
from krun.demos import DemoName, create_demo
from krun.errors import KrunError


@pytest.mark.parametrize("name", list(DemoName))
def test_demo_dry_run_without_auth(name: DemoName, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("krun.cli.KaggleClient", lambda: pytest.fail("Dry-run must not authenticate"))
    result = CliRunner().invoke(app, ["demo", name.value, "--dry-run"])
    assert result.exit_code == 0, result.output
    root = tmp_path / f"krun-demo-{name.value}"
    assert root.is_dir()
    assert not (root / ".krun").exists()
    assert "Accelerator: CPU" in result.output


def test_demo_does_not_overwrite_existing_files(tmp_path: Path) -> None:
    marker = tmp_path / "main.py"
    marker.write_text("user changes")
    with pytest.raises(KrunError, match="already exists"):
        create_demo(DemoName.sales_report, tmp_path)
    assert marker.read_text() == "user changes"


def test_copy_only_and_custom_destination(tmp_path: Path) -> None:
    root = tmp_path / "my example"
    result = CliRunner().invoke(app, ["demo", "--destination", str(root), "--copy-only"])
    assert result.exit_code == 0, result.output
    assert (root / "data" / "orders.csv").is_file()
    assert (root / ".krunignore").is_file()
    assert not (root / ".krun").exists()


@pytest.mark.parametrize(
    ("name", "filename"), [("sales-report", "main.py"), ("notebook", "report.ipynb")],
)
def test_demo_ignores_same_named_file_in_callers_directory(
    name: str, filename: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    original = tmp_path / filename
    original.write_text("This is the user's file, not the demo.")
    result = CliRunner().invoke(app, ["demo", name, "--dry-run"])
    assert result.exit_code == 0, result.output
    assert original.read_text() == "This is the user's file, not the demo."


def test_module_demo_forwards_arguments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from krun.kaggle import KaggleClient

    monkeypatch.setattr(KaggleClient, "validate_environment", lambda client: None)
    remote = tmp_path / "remote"

    def submit(client: KaggleClient, workspace: Path, accelerator: str) -> str:
        result = subprocess.run(
            [sys.executable, str(workspace / "runner.py")],
            env={**os.environ, "KRUN_WORKING_DIR": str(remote)},
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        return "submitted"

    monkeypatch.setattr(KaggleClient, "submit", submit)
    result = CliRunner().invoke(app, [
        "demo", "module", "--destination", str(tmp_path / "module"),
        "--owner", "tester", "--detach", "--", "--count", "7",
    ])
    assert result.exit_code == 0, result.output
    output = remote / "krun_outputs" / "outputs" / "result.json"
    assert json.loads(output.read_text())["squares"] == [0, 1, 4, 9, 16, 25, 36]


def test_demo_rejects_project_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["demo", "module", "--project", str(tmp_path)])
    assert isinstance(result.exception, KrunError)
    assert not (tmp_path / "krun-demo-module").exists()
