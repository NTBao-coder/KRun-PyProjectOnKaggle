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


def test_discovers_one_nested_dependency_project(tmp_path: Path) -> None:
    make_project(tmp_path)
    backend = tmp_path / "BackEnd"
    backend.mkdir()
    manifest = backend / "pyproject.toml"
    manifest.write_text("[project]\nname = 'demo'\nversion = '0.1.0'\n", encoding="utf-8")

    project = discover_project(tmp_path)

    assert project.pyproject == manifest


def test_configured_dependency_project_disambiguates_manifests(tmp_path: Path) -> None:
    make_project(tmp_path)
    (tmp_path / "krun.yaml").write_text(
        "project:\n  name: demo\nentrypoint:\n  file: train.py\n"
        "dependencies:\n  project: services/trainer\n",
        encoding="utf-8",
    )
    selected = tmp_path / "services" / "trainer"
    other = tmp_path / "services" / "api"
    selected.mkdir(parents=True)
    other.mkdir(parents=True)
    (selected / "pyproject.toml").touch()
    (other / "pyproject.toml").touch()

    project = discover_project(tmp_path)

    assert project.pyproject == selected / "pyproject.toml"
