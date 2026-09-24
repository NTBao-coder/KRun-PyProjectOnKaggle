from pathlib import Path

from krun.jobs import JobStore, new_kernel_slug


def test_job_store_round_trip(tmp_path: Path) -> None:
    entrypoint = tmp_path / "train.py"
    entrypoint.touch()
    store = JobStore(tmp_path)

    created = store.create("owner/kernel", tmp_path, entrypoint, "CPU")
    loaded = store.load(created.job_id)

    assert loaded == created
    assert store.directory(created.job_id).name == created.job_id


def test_kernel_slug_is_safe_and_unique() -> None:
    assert new_kernel_slug("My Training_Project!", "ABC123") == "my-training-project-abc123"
