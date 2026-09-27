import os
from dataclasses import dataclass, replace
from pathlib import Path

from krun.config import CONFIG_FILE, Config, ProjectConfig, load_config
from krun.errors import KrunError


@dataclass(frozen=True)
class Project:
    root: Path
    config: Config
    entrypoint: Path
    requirements: Path | None
    pyproject: Path | None
    module: str | None = None
    module_path: str = "."


def discover_project(
    start: Path,
    entrypoint_override: Path | None = None,
    project_root: Path | None = None,
    module: str | None = None,
    requirements_override: Path | None = None,
    dependency_project: Path | None = None,
    output_paths: list[str] | None = None,
) -> Project:
    if module and entrypoint_override:
        raise KrunError("Use a file or --module, not both.")
    target = (start / entrypoint_override).resolve() if entrypoint_override else start
    if (
        project_root and entrypoint_override and not entrypoint_override.is_absolute()
        and not target.is_file()
    ):
        target = (project_root / entrypoint_override).resolve()
    current_root = find_project_root(start)
    if project_root:
        root = project_root.resolve()
    elif (current_root / CONFIG_FILE).is_file() or (current_root / ".krun/jobs").is_dir():
        root = current_root
    else:
        root = find_project_root(target)
    config_path = root / CONFIG_FILE
    config = (
        load_config(config_path) if config_path.is_file()
        else Config(project=ProjectConfig(
            os.environ.get("KRUN_HOST_ROOT", str(root)).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        ))
    )
    module_path = "."
    if module:
        if not all(part.isidentifier() for part in module.split(".")):
            raise KrunError("Module must be a dotted Python module name.")
        relative = Path(*module.split("."))
        candidates = [
            base / path
            for base in (root, root / "src")
            for path in (relative.with_suffix(".py"), relative / "__main__.py")
        ]
        entrypoint_override = next((path for path in candidates if path.is_file()), None)
        if entrypoint_override is None:
            raise KrunError(f"Local module '{module}' was not found under {root}.")
        module_path = "src" if entrypoint_override.is_relative_to(root / "src") else "."
    elif entrypoint_override:
        entrypoint_override = target
    elif not config_path.is_file():
        candidates = [path for path in (root / "main.py", root / "train.py") if path.is_file()]
        if not candidates:
            candidates = sorted(root.glob("*.py")) + sorted(root.glob("*.ipynb"))
        if len(candidates) != 1:
            raise KrunError("Specify a .py/.ipynb entrypoint or --module; no unique default was found.")
        entrypoint_override = candidates[0]
    entrypoint = resolve_project_path(
        root,
        entrypoint_override or Path(config.entrypoint.file),
        "entrypoint",
    )
    if not entrypoint.is_file() or entrypoint.suffix not in {".py", ".ipynb"}:
        raise KrunError(f"Entrypoint must be an existing .py or .ipynb file: {entrypoint}")

    if output_paths is not None:
        config = replace(config, outputs=output_paths)

    for output in config.outputs:
        if Path(output).is_absolute() or ".." in Path(output).parts:
            raise KrunError("Output paths must be project-relative without '..'.")
        resolved = resolve_project_path(root, Path(output), "output path")
        if resolved == root or ".krun" in resolved.relative_to(root).parts:
            raise KrunError("Output paths cannot be the project root or .krun state.")

    requirements = None
    selected_requirements = requirements_override or (
        config.dependencies.requirements if dependency_project is None else None
    )
    if requirements_override and dependency_project:
        raise KrunError("Use --requirements or --dependency-project, not both.")
    if not selected_requirements and not dependency_project and not config_path.is_file():
        selected_requirements = "requirements.txt" if (root / "requirements.txt").is_file() else None
    if selected_requirements:
        requirements = resolve_project_path(
            root,
            Path(selected_requirements),
            "requirements file",
        )
        if not requirements.is_file():
            raise KrunError(f"Requirements file not found: {requirements}")

    if dependency_project:
        config = replace(
            config,
            dependencies=replace(
                config.dependencies, project=str(dependency_project), requirements=None
            ),
        )
        requirements = None
    pyproject_path = None if requirements else _find_dependency_project(root, config, entrypoint)
    return Project(
        root=root,
        config=config,
        entrypoint=entrypoint,
        requirements=requirements,
        pyproject=pyproject_path,
        module=module,
        module_path=module_path,
    )


def find_project_root(start: Path) -> Path:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / CONFIG_FILE).is_file() or (candidate / ".krun" / "jobs").is_dir():
            return candidate
    for candidate in (current, *current.parents):
        markers = ("pyproject.toml", "requirements.txt", ".git", ".git/HEAD")
        if any((candidate / name).is_file() for name in markers):
            return candidate
    return current


def resolve_project_path(root: Path, path: Path, label: str) -> Path:
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise KrunError(f"{label.capitalize()} must be inside the project root: {path}")
    return resolved


def _find_dependency_project(
    root: Path,
    config: Config,
    entrypoint: Path,
) -> Path | None:
    configured = config.dependencies.project
    if configured:
        path = resolve_project_path(root, Path(configured), "dependency project")
        path = path / "pyproject.toml" if path.is_dir() else path
        if path.name != "pyproject.toml" or not path.is_file():
            raise KrunError(f"Dependency project not found: {path}")
        return path

    root_manifest = root / "pyproject.toml"
    if root_manifest.is_file():
        return root_manifest

    ignored_parts = {".git", ".krun", ".venv", "venv", "__pycache__"}
    candidates = sorted(
        path
        for path in root.rglob("pyproject.toml")
        if not any(part in ignored_parts for part in path.relative_to(root).parts)
    )
    if len(candidates) == 1:
        return candidates[0]

    entrypoint_parents = {entrypoint.parent, *entrypoint.parents}
    ancestors = [path for path in candidates if path.parent in entrypoint_parents]
    if ancestors:
        return max(ancestors, key=lambda path: len(path.parts))
    if len(candidates) > 1:
        raise KrunError(
            "Multiple dependency projects found. Select --dependency-project "
            "or configure dependencies.project."
        )
    return None
