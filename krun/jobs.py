import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from krun.errors import KrunError


@dataclass
class Job:
    job_id: str
    kernel: str
    project_root: str
    entrypoint: str
    accelerator: str
    submitted_at: str
    status: str
    download_status: str = "pending"
    error: str | None = None


class JobStore:
    def __init__(self, project_root: Path) -> None:
        self.root = project_root / ".krun" / "jobs"
        if not self.root.resolve().is_relative_to(project_root.resolve()):
            raise KrunError("Job state cannot be symlinked outside the project.")

    def create(
        self,
        kernel: str,
        project_root: Path,
        entrypoint: Path,
        accelerator: str,
    ) -> Job:
        now = datetime.now(timezone.utc)
        job_id = f"{now:%Y%m%d-%H%M%S}-{uuid4().hex[:6]}"
        job = Job(
            job_id=job_id,
            kernel=kernel,
            project_root=str(project_root),
            entrypoint=str(entrypoint.relative_to(project_root)),
            accelerator=accelerator,
            submitted_at=now.isoformat(),
            status="preparing",
        )
        self.save(job)
        return job

    def save(self, job: Job) -> None:
        directory = self.directory(job.job_id)
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / "metadata.json"
        temporary = destination.with_name(f"metadata.{uuid4().hex}.tmp")
        temporary.write_text(json.dumps(asdict(job), indent=2) + "\n", encoding="utf-8")
        temporary.replace(destination)

    def load(self, job_id: str) -> Job:
        path = self.directory(job_id) / "metadata.json"
        if not path.is_file():
            raise KrunError(f"Unknown job: {job_id}")
        try:
            return Job(**json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError) as exc:
            raise KrunError(f"Invalid job metadata: {path}") from exc

    def latest(self) -> Job:
        if not self.root.is_dir():
            raise KrunError("No krun jobs were found in this project.")
        job_ids = sorted(
            path.name
            for path in self.root.iterdir()
            if path.is_dir() and (path / "metadata.json").is_file()
        )
        if not job_ids:
            raise KrunError("No krun jobs were found in this project.")
        return self.load(job_ids[-1])

    def directory(self, job_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", job_id):
            raise KrunError("Invalid job ID. Use a job ID shown by 'krun jobs'.")
        path = self.root / job_id
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise KrunError("Job directory escapes the state directory.")
        return path

    def list_jobs(self) -> list[Job]:
        if not self.root.is_dir():
            return []
        return [
            self.load(path.name) for path in sorted(self.root.iterdir())
            if path.is_dir() and (path / "metadata.json").is_file()
        ]


def new_kernel_slug(project_name: str, job_id: str) -> str:
    cleaned = "".join(
        char if char.isascii() and char.isalnum() else "-"
        for char in project_name.lower()
    )
    cleaned = "-".join(part for part in cleaned.split("-") if part) or "krun-job"
    return f"{cleaned[:24]}-{job_id.lower()}"
