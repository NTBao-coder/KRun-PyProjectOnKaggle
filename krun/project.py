from dataclasses import dataclass
from pathlib import Path

from krun.config import CONFIG_FILE, Config, load_config
from krun.errors import ConfigError, KrunError


@dataclass(frozen=True)
class Project:
    root: Path
    config: Config
    entrypoint: Path
    requirements: Path | None
    pyproject: Path | None


def discover_project(start: Path, entrypoint_override: Path | None = None) -> Project:
    root = find_project_root(start)
    config = load_config(root / CONFIG_FILE)
    entrypoint = resolve_project_path(
        root,
        entrypoint_override or Path(config.entrypoint.file),
        "entrypoint",
    )
    if not entrypoint.is_file() or entrypoint.suffix != ".py":
        raise KrunError(f"Entrypoint must be an existing Python file: {entrypoint}")

    for output in config.outputs:
        resolve_project_path(root, Path(output), "output path")

    requirements = None
    if config.dependencies.requirements:
        requirements = resolve_project_path(
            root,
            Path(config.dependencies.requirements),
            "requirements file",
        )
        if not requirements.is_file():
            raise KrunError(f"Requirements file not found: {requirements}")

    pyproject_path = root / "pyproject.toml"
    return Project(
        root=root,
        config=config,
        entrypoint=entrypoint,
        requirements=requirements,
        pyproject=pyproject_path if pyproject_path.is_file() else None,
    )


def find_project_root(start: Path) -> Path:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / CONFIG_FILE).is_file():
            return candidate
    raise ConfigError(f"Could not find {CONFIG_FILE}. Run 'krun init' first.")


def resolve_project_path(root: Path, path: Path, label: str) -> Path:
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise KrunError(f"{label.capitalize()} must be inside the project root: {path}")
    return resolved
