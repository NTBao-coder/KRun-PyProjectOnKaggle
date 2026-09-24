from pathlib import Path

import pytest

from krun.config import ConfigError, load_config, write_default_config


def test_write_and_load_default_config(tmp_path: Path) -> None:
    path = tmp_path / "krun.yaml"

    write_default_config(path, "sample-project", "main.py")
    config = load_config(path)

    assert config.project.name == "sample-project"
    assert config.entrypoint.file == "main.py"
    assert config.runtime.accelerator == "cpu"
    assert config.dependencies.requirements == "requirements.txt"
    assert config.outputs == ["outputs/", "checkpoints/"]


def test_load_config_rejects_invalid_project_name(tmp_path: Path) -> None:
    path = tmp_path / "krun.yaml"
    path.write_text("project:\n  name: ''\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="project.name"):
        load_config(path)


def test_load_config_rejects_non_boolean_internet(tmp_path: Path) -> None:
    path = tmp_path / "krun.yaml"
    path.write_text(
        "project:\n  name: demo\nruntime:\n  internet: yes please\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="runtime.internet"):
        load_config(path)
