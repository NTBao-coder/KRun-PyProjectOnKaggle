import json
from pathlib import Path

import pytest

from krun.errors import KrunError
from krun.kaggle import KaggleClient, normalize_accelerator, write_kernel_metadata


def test_package_upload_is_private_and_waits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "package.bin"
    archive.write_bytes(b"archive")
    calls = []
    responses = iter(["created", "processing", "ready"])
    client = KaggleClient(executable="kaggle")
    def run(args):
        calls.append(args)
        return next(responses)
    monkeypatch.setattr(client, "_run", run)
    monkeypatch.setattr("krun.kaggle.time.sleep", lambda seconds: None)
    client.upload_package(archive, "owner/krun-test")
    assert calls[0] == ["datasets", "create", "--path", str(tmp_path), "--keep-tabular"]
    assert calls[1:] == [["datasets", "status", "owner/krun-test"]] * 2
    assert json.loads((tmp_path / "dataset-metadata.json").read_text())["licenses"] == [{"name": "other"}]


@pytest.mark.parametrize("status", ["error", "processing"])
def test_package_upload_failure_or_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str) -> None:
    client = KaggleClient(executable="kaggle")
    monkeypatch.setattr(client, "_run", lambda args: status)
    with pytest.raises(KrunError, match="not ready|Timed out"):
        client.upload_package(tmp_path / "package.bin", "owner/krun-test", timeout=0)


def test_kaggle_uses_tool_environment_before_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    tool_bin = tmp_path / "tool"
    other_bin = tmp_path / "other"
    filename = "kaggle.exe" if os.name == "nt" else "kaggle"
    for directory in (tool_bin, other_bin):
        directory.mkdir()
        executable = directory / filename
        executable.touch()
        executable.chmod(0o755)
    monkeypatch.setattr("krun.kaggle.sysconfig.get_path", lambda name: str(tool_bin))
    monkeypatch.setenv("PATH", str(other_bin))
    assert Path(KaggleClient().executable).samefile(tool_bin / filename)
    assert KaggleClient(executable="custom-kaggle").executable == "custom-kaggle"


def test_kaggle_falls_back_to_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    executable = tmp_path / ("kaggle.exe" if os.name == "nt" else "kaggle")
    executable.touch()
    executable.chmod(0o755)
    monkeypatch.setattr("krun.kaggle.sysconfig.get_path", lambda name: str(tmp_path / "missing"))
    monkeypatch.setenv("PATH", str(tmp_path))
    assert Path(KaggleClient().executable).samefile(executable)


def test_normalize_accelerator() -> None:
    assert normalize_accelerator("CPU") == ""
    assert normalize_accelerator("T4") == "NvidiaTeslaT4"
    assert normalize_accelerator("NvidiaTeslaP100") == "NvidiaTeslaP100"
    assert normalize_accelerator("TPU") == "Tpu1VmV38"


def test_normalize_accelerator_rejects_unknown_value() -> None:
    with pytest.raises(KrunError, match="Unsupported accelerator"):
        normalize_accelerator("H100")


def test_write_kernel_metadata(tmp_path: Path) -> None:
    (tmp_path / "runner.py").touch()

    path = write_kernel_metadata(tmp_path, "owner/demo", "demo job", False)
    metadata = json.loads(path.read_text(encoding="utf-8"))

    assert metadata["id"] == "owner/demo"
    assert metadata["code_file"] == "runner.py"
    assert metadata["enable_internet"] is False
    assert metadata["is_private"] is True


def test_submit_builds_safe_argument_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> object:
        recorded["command"] = command

        class Result:
            returncode = 0
            stdout = "submitted"
            stderr = ""

        return Result()

    monkeypatch.setattr("krun.kaggle.subprocess.run", fake_run)
    client = KaggleClient(executable="/usr/bin/kaggle")

    assert client.submit(tmp_path, "NvidiaTeslaT4") == "submitted"
    assert recorded["command"] == [
        "/usr/bin/kaggle",
        "kernels",
        "push",
        "--path",
        str(tmp_path),
        "--accelerator",
        "NvidiaTeslaT4",
    ]


def test_status_parses_cli_response(monkeypatch: pytest.MonkeyPatch) -> None:
    client = KaggleClient(executable="kaggle")
    monkeypatch.setattr(
        client,
        "_run",
        lambda args: 'owner/kernel has status "running"',
    )

    status, raw = client.status("owner/kernel")

    assert status == "running"
    assert "owner/kernel" in raw


def test_status_normalizes_kaggle_enum(monkeypatch: pytest.MonkeyPatch) -> None:
    client = KaggleClient(executable="kaggle")
    monkeypatch.setattr(
        client,
        "_run",
        lambda args: 'owner/kernel has status "KernelWorkerStatus.COMPLETE"',
    )

    status, _ = client.status("owner/kernel")

    assert status == "complete"


def test_wait_for_terminal_status_polls(monkeypatch: pytest.MonkeyPatch) -> None:
    client = KaggleClient(executable="kaggle")
    responses = iter(
        [
            ("queued", "queued detail"),
            ("running", "running detail"),
            ("complete", "complete detail"),
        ]
    )
    monkeypatch.setattr(client, "status", lambda kernel: next(responses))
    monkeypatch.setattr("krun.kaggle.time.sleep", lambda interval: None)

    assert client.wait_for_terminal_status("owner/kernel") == (
        "complete",
        "complete detail",
    )


def test_download_output_builds_destination_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []
    client = KaggleClient(executable="kaggle")
    monkeypatch.setattr(client, "_run", lambda args: commands.append(args) or "done")

    client.download_output("owner/kernel", tmp_path / "output")

    assert commands == [[
        "kernels",
        "output",
        "owner/kernel",
        "--path",
        str(tmp_path / "output"),
        "--force",
    ]]
