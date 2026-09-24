import json
from pathlib import Path

import pytest

from krun.errors import KrunError
from krun.kaggle import KaggleClient, normalize_accelerator, write_kernel_metadata


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
