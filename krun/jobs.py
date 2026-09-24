import json
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


class JobStore:
    def __init__(self, project_root: Path) -> None:
        self.root = project_root / ".krun" / "jobs"

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
        temporary = destination.with_suffix(".tmp")
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

    def directory(self, job_id: str) -> Path:
        return self.root / job_id


def new_kernel_slug(project_name: str, job_id: str) -> str:
    cleaned = "".join(char if char.isalnum() else "-" for char in project_name.lower())
    cleaned = "-".join(part for part in cleaned.split("-") if part) or "krun-job"
    return f"{cleaned[:45]}-{job_id.lower()}"

