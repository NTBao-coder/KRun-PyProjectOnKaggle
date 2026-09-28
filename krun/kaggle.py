import json
import os
import re
import shutil
import subprocess
import sysconfig
import time
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


def _subprocess_environment() -> dict[str, str]:
    """Use UTF-8 for Kaggle's Python runtime, including redirected Windows I/O."""
    return {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


class KaggleClient:
    def __init__(self, executable: str | None = None, verbose: bool = False) -> None:
        # uv exposes KRun's entrypoint, but dependency scripts need not be on PATH.
        scripts = sysconfig.get_path("scripts")
        bundled = shutil.which("kaggle", path=scripts) if scripts else None
        self.executable = executable or bundled or shutil.which("kaggle") or ""
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

    def upload_package(self, archive: Path, dataset: str, timeout: float = 600) -> None:
        """Create a private, immutable per-job dataset and await processing."""
        metadata = {
            "id": dataset,
            "title": dataset.split("/")[1],
            "licenses": [{"name": "other"}],
            "description": "Private KRun job package. Original file licenses remain applicable.",
        }
        (archive.parent / "dataset-metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8",
        )
        # No --public: the official CLI creates private datasets by default.
        self._run(["datasets", "create", "--path", str(archive.parent), "--keep-tabular"])
        deadline = time.monotonic() + timeout
        while True:
            status = self._run(["datasets", "status", dataset]).strip().lower()
            if status == "ready":
                return
            if status not in {
                "queued", "processing", "not_yet_persisted", "blobs_received",
                "blobs_decompressed", "blobs_copied_to_sds",
                "individual_blobs_compressed", "reprocessing",
            }:
                raise CommandError(f"Package dataset {dataset} is not ready: {status}")
            if time.monotonic() >= deadline:
                raise CommandError(f"Timed out waiting for package dataset {dataset}. Inspect it before retrying.")
            time.sleep(5)

    def status(self, kernel: str) -> tuple[str, str]:
        output = self._run(["kernels", "status", kernel])
        match = re.search(r'has status "([^"]+)"', output)
        if not match:
            raise CommandError(f"Could not parse Kaggle kernel status:\n{output}")
        status = match.group(1).rsplit(".", maxsplit=1)[-1].lower()
        return status, output

    def wait_for_terminal_status(
        self,
        kernel: str,
        poll_interval: float = 5.0,
        timeout: float = 3600,
    ) -> tuple[str, str]:
        terminal_statuses = {"complete", "error", "cancelled"}
        deadline = time.monotonic() + timeout
        while True:
            status, detail = self.status(kernel)
            if status in terminal_statuses:
                return status, detail
            if time.monotonic() >= deadline:
                raise CommandError("Monitoring timed out. The remote job may still be running; use 'krun wait'.")
            time.sleep(poll_interval)

    def logs(self, kernel: str) -> str:
        content = self._run(["kernels", "logs", kernel])
        try:
            records = json.loads(content)
            if isinstance(records, list):
                return "".join(str(record.get("data", "")) for record in records if isinstance(record, dict))
        except json.JSONDecodeError:
            pass
        return content

    def login(self, force: bool = False) -> None:
        command = [self.executable, "auth", "login", "--no-launch-browser"]
        if force:
            command.append("--force")
        completed = subprocess.run(command, check=False, env=_subprocess_environment())
        if completed.returncode:
            if force or not has_credentials():
                raise CommandError("Kaggle login failed. Retry 'krun login'.")
            self.verify_auth()

    def verify_auth(self) -> str:
        self.validate_environment()
        self._run(["kernels", "list", "--mine", "--page-size", "1"])
        try:
            return kaggle_username()
        except KrunError:
            return "token account (set KAGGLE_USERNAME or pass --owner when running)"

    def follow_logs(self, kernel: str) -> None:
        command = [self.executable, "kernels", "logs", "--follow", kernel]
        try:
            completed = subprocess.run(command, check=False, env=_subprocess_environment())
        except OSError as exc:
            raise CommandError(f"Could not start Kaggle CLI: {exc}") from exc
        if completed.returncode != 0:
            raise CommandError(
                "Kaggle log streaming failed. Run 'krun logs <job-id>' to retry."
            )

    def download_output(self, kernel: str, destination: Path) -> str:
        destination.mkdir(parents=True, exist_ok=True)
        return self._run(
            [
                "kernels",
                "output",
                kernel,
                "--path",
                str(destination),
                "--force",
            ]
        )

    def _run(self, args: list[str]) -> str:
        command = [self.executable, *args]
        attempts = 1 if args[:2] in (["kernels", "push"], ["datasets", "create"]) else 3
        for attempt in range(attempts):
            try:
                completed = subprocess.run(
                    command, text=True, encoding="utf-8", capture_output=True,
                    check=False, timeout=120, env=_subprocess_environment(),
                )
            except subprocess.TimeoutExpired as exc:
                if attempt + 1 < attempts:
                    continue
                raise CommandError("Kaggle request timed out. Submission is not retried automatically; inspect the job on Kaggle before resubmitting.") from exc
            except OSError as exc:
                raise CommandError(f"Could not start Kaggle CLI: {exc}") from exc
            if completed.returncode == 0:
                return completed.stdout.strip()
            detail = completed.stderr.strip() or completed.stdout.strip() or "No details returned."
            transient = any(word in detail.lower() for word in ("timeout", "connection", "429", "502", "503", "504", "temporary"))
            if transient and attempt + 1 < attempts:
                time.sleep(2 ** attempt)
                continue
            raise CommandError(f"Kaggle command failed:\n{detail}\nCheck login, network, accelerator access and quota.")
        raise CommandError("Kaggle request failed.")


def write_kernel_metadata(
    workspace: Path,
    kernel: str,
    title: str,
    internet: bool,
    datasets: list[str] | None = None,
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
        "dataset_sources": datasets or [],
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
