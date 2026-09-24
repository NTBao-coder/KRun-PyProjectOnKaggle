import json
import os
import shutil
import subprocess
from pathlib import Path

from krun.errors import CommandError, KrunError

ACCELERATORS = {
    "cpu": "",
    "gpu": "NvidiaTeslaT4",
    "t4": "NvidiaTeslaT4",
    "nvidiateslat4": "NvidiaTeslaT4",
    "p100": "NvidiaTeslaP100",
    "nvidiateslap100": "NvidiaTeslaP100",
    "tpu": "Tpu1VmV38",
    "tpu1vmv38": "Tpu1VmV38",
}


class KaggleClient:
    def __init__(self, executable: str | None = None, verbose: bool = False) -> None:
        self.executable = executable or shutil.which("kaggle") or ""
        self.verbose = verbose

    def validate_environment(self) -> None:
        if not self.executable:
            raise KrunError(
                "Kaggle CLI was not found. Install the official 'kaggle' package "
                "and ensure the 'kaggle' command is on PATH."
            )
        if not has_credentials():
            raise KrunError(
                "Kaggle credentials were not found. Run 'kaggle auth login', set "
                "KAGGLE_API_TOKEN, or configure ~/.kaggle/kaggle.json first."
            )

    def submit(self, workspace: Path, accelerator: str) -> str:
        args = ["kernels", "push", "--path", str(workspace)]
        if accelerator:
            args.extend(["--accelerator", accelerator])
        return self._run(args)

    def _run(self, args: list[str]) -> str:
        command = [self.executable, *args]
        try:
            completed = subprocess.run(
                command,
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            raise CommandError(f"Could not start Kaggle CLI: {exc}") from exc

        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "No details returned."
            raise CommandError(
                "Kaggle command failed.\n\n"
                f"Kaggle response:\n{detail}\n\n"
                "Check your credentials, network connection, accelerator access, and quota."
            )
        return completed.stdout.strip()


def write_kernel_metadata(
    workspace: Path,
    kernel: str,
    title: str,
    internet: bool,
) -> Path:
    metadata = {
        "id": kernel,
        "title": title,
        "code_file": "runner.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": False,
        "enable_tpu": False,
        "enable_internet": internet,
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }
    path = workspace / "kernel-metadata.json"
    path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return path


def normalize_accelerator(value: str) -> str:
    key = value.lower().replace("-", "").replace("_", "")
    try:
        return ACCELERATORS[key]
    except KeyError as exc:
        choices = "CPU, T4, P100, TPU"
        raise KrunError(f"Unsupported accelerator '{value}'. Choose one of: {choices}.") from exc


def kaggle_username(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    if username := os.environ.get("KAGGLE_USERNAME"):
        return username
    for path in (
        Path.home() / ".kaggle" / "credentials.json",
        Path.home() / ".kaggle" / "kaggle.json",
    ):
        if not path.is_file():
            continue
        try:
            username = json.loads(path.read_text(encoding="utf-8")).get("username")
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(username, str) and username:
            return username
    raise KrunError(
        "Could not determine your Kaggle username. Pass --owner or set KAGGLE_USERNAME."
    )


def has_credentials() -> bool:
    if os.environ.get("KAGGLE_API_TOKEN"):
        return True
    if os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY"):
        return True
    return any(
        path.is_file()
        for path in (
            Path.home() / ".kaggle" / "access_token",
            Path.home() / ".kaggle" / "credentials.json",
            Path.home() / ".kaggle" / "kaggle.json",
        )
    )

