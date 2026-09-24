from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from krun.errors import ConfigError

CONFIG_FILE = "krun.yaml"


@dataclass(frozen=True)
class ProjectConfig:
    name: str


@dataclass(frozen=True)
class RuntimeConfig:
    accelerator: str = "cpu"
    internet: bool = True


@dataclass(frozen=True)
class EntrypointConfig:
    file: str = "train.py"


@dataclass(frozen=True)
class DependenciesConfig:
    requirements: str | None = None


@dataclass(frozen=True)
class Config:
    project: ProjectConfig
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    entrypoint: EntrypointConfig = field(default_factory=EntrypointConfig)
    dependencies: DependenciesConfig = field(default_factory=DependenciesConfig)
    outputs: list[str] = field(default_factory=lambda: ["outputs/"])


def load_config(path: Path) -> Config:
    if not path.is_file():
        raise ConfigError(f"Configuration file not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("Configuration must be a YAML mapping.")

    project = _mapping(raw, "project", required=True)
    name = project.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError("project.name must be a non-empty string.")

    runtime = _mapping(raw, "runtime")
    accelerator = runtime.get("accelerator", "cpu")
    if not isinstance(accelerator, str):
        raise ConfigError("runtime.accelerator must be a string.")
    internet = runtime.get("internet", True)
    if not isinstance(internet, bool):
        raise ConfigError("runtime.internet must be true or false.")

    entrypoint = _mapping(raw, "entrypoint")
    entrypoint_file = entrypoint.get("file", "train.py")
    if not isinstance(entrypoint_file, str) or not entrypoint_file:
        raise ConfigError("entrypoint.file must be a non-empty string.")

    dependencies = _mapping(raw, "dependencies")
    requirements = dependencies.get("requirements")
    if requirements is not None and not isinstance(requirements, str):
        raise ConfigError("dependencies.requirements must be a string or null.")

    outputs = raw.get("outputs", ["outputs/"])
    if not isinstance(outputs, list) or not all(isinstance(item, str) and item for item in outputs):
        raise ConfigError("outputs must be a list of non-empty paths.")

    return Config(
        project=ProjectConfig(name=name.strip()),
        runtime=RuntimeConfig(accelerator=accelerator, internet=internet),
        entrypoint=EntrypointConfig(file=entrypoint_file),
        dependencies=DependenciesConfig(requirements=requirements),
        outputs=outputs,
    )


def write_default_config(path: Path, project_name: str, entrypoint: str) -> None:
    document = {
        "project": {"name": project_name},
        "runtime": {"accelerator": "cpu", "internet": True},
        "entrypoint": {"file": entrypoint},
        "dependencies": {"requirements": "requirements.txt"},
        "outputs": ["outputs/", "checkpoints/"],
    }
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def _mapping(data: dict[str, Any], key: str, required: bool = False) -> dict[str, Any]:
    value = data.get(key)
    if value is None and not required:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{key} must be a YAML mapping.")
    return value

