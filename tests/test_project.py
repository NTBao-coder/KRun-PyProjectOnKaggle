from pathlib import Path

import pytest

from krun.errors import KrunError
from krun.project import discover_project, find_project_root


def make_project(root: Path) -> None:
    (root / "krun.yaml").write_text(
        "project:\n  name: demo\nentrypoint:\n  file: train.py\n",
        encoding="utf-8",
    )
    (root / "train.py").touch()


def test_discovers_project_from_nested_directory(tmp_path: Path) -> None:
    make_project(tmp_path)
    nested = tmp_path / "src" / "package"
    nested.mkdir(parents=True)

    assert find_project_root(nested) == tmp_path
    assert discover_project(nested).entrypoint == tmp_path / "train.py"


def test_rejects_entrypoint_outside_project(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    make_project(root)
    outside = tmp_path / "outside.py"
    outside.touch()

    with pytest.raises(KrunError, match="inside the project root"):
        discover_project(root, outside)

