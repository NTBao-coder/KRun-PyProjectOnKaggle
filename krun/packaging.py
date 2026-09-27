import base64
import fnmatch
import io
import json
import os
import tarfile
from dataclasses import dataclass
from pathlib import Path

from krun.errors import KrunError
from krun.project import Project

DEFAULT_IGNORES = (
    ".git",
    ".git-data",
    ".krun",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".env*",
    "kaggle.json",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa",
    "id_ed25519",
    "*.pyc",
    ".kaggle",
    "credentials.json",
    "access_token",
    ".idea",
    ".vscode",
)
MAX_PACKAGE_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class PackageResult:
    runner: Path
    file_count: int
    source_bytes: int


def package_files(project: Project, input_paths: list[Path] | None = None) -> list[Path]:
    """Select files without allowing explicit inputs to bypass mandatory exclusions."""
    files = collect_project_files(project.root)
    for input_path in input_paths or []:
        if not input_path.resolve().is_relative_to(project.root.resolve()) or input_path.is_symlink():
            raise KrunError("Inputs must be regular files/directories inside the project.")
        candidates = _walk_files(input_path) if input_path.is_dir() else [input_path]
        for path in candidates:
            if (
                path.is_file() and not path.is_symlink()
                and not _is_ignored(path.relative_to(project.root), list(DEFAULT_IGNORES))
            ):
                files.append(path)
    files = sorted(set(files))
    required = [project.entrypoint, project.requirements, project.pyproject]
    for path in required:
        if path is not None and path not in files:
            raise KrunError(f"Required file excluded from package: {path.relative_to(project.root)}")
    source_bytes = sum(path.stat().st_size for path in files)
    if source_bytes > MAX_PACKAGE_BYTES:
        largest = sorted(files, key=lambda path: path.stat().st_size, reverse=True)[:5]
        detail = ", ".join(
            f"{path.relative_to(project.root)} ({path.stat().st_size} bytes)"
            for path in largest
        )
        raise KrunError(
            f"Project exceeds the 20 MB package limit. Largest files: {detail}. "
            "Use --dataset for large inputs."
        )
    return files


def prepare_workspace(
    project: Project,
    workspace: Path,
    arguments: list[str],
    input_paths: list[Path] | None = None,
    notebook_timeout: int = 600,
    working_directory: str = ".",
    secret_names: list[str] | None = None,
    extra_packages: list[str] | None = None,
) -> PackageResult:
    files = package_files(project, input_paths)
    workspace.mkdir(parents=True, exist_ok=True)
    source_bytes = sum(path.stat().st_size for path in files)
    payload = _archive(project.root, files)
    entrypoint = project.entrypoint.relative_to(project.root).as_posix()
    requirements = (
        project.requirements.relative_to(project.root).as_posix()
        if project.requirements
        else None
    )
    dependency_project = (
        project.pyproject.parent.relative_to(project.root).as_posix()
        if project.pyproject
        else None
    )
    runner_path = workspace / "runner.py"
    runner_path.write_text(
        _render_runner(
            payload=payload,
            entrypoint=entrypoint,
            arguments=arguments,
            requirements=requirements,
            dependency_project=dependency_project,
            outputs=project.config.outputs,
            module=project.module,
            module_path=project.module_path,
            notebook_timeout=notebook_timeout,
            working_directory=working_directory,
            secret_names=secret_names or [],
            extra_packages=extra_packages or [],
        ),
        encoding="utf-8",
    )
    return PackageResult(runner=runner_path, file_count=len(files), source_bytes=source_bytes)


def collect_project_files(root: Path) -> list[Path]:
    patterns: list[str] = []
    for name in (".gitignore", ".krunignore"):
        ignore_file = root / name
        if ignore_file.is_file():
            patterns.extend(
                line.strip() for line in ignore_file.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )

    files: list[Path] = []
    for path in _walk_files(root, patterns):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root)
        if not _is_ignored(relative, list(DEFAULT_IGNORES)) and not _is_ignored(relative, patterns):
            files.append(path)
    return files


def _walk_files(root: Path, patterns: list[str] | None = None) -> list[Path]:
    files: list[Path] = []
    prune_patterns = list(DEFAULT_IGNORES)
    if patterns and not any(pattern.startswith("!") for pattern in patterns):
        prune_patterns += patterns
    for current, directories, names in os.walk(root, followlinks=False):
        directory = Path(current)
        directories[:] = [
            name for name in directories
            if not (directory / name).is_symlink()
            and not _is_ignored((directory / name).relative_to(root), prune_patterns)
        ]
        files.extend(directory / name for name in names)
    return sorted(files)


def _is_ignored(path: Path, patterns: list[str]) -> bool:
    value = path.as_posix()
    parts = path.parts
    ignored = False
    for raw_pattern in patterns:
        negate = raw_pattern.startswith("!")
        raw_pattern = raw_pattern[1:] if negate else raw_pattern
        anchored = raw_pattern.startswith("/")
        pattern = raw_pattern.strip().lstrip("/").rstrip("/")
        if not pattern:
            continue
        matches = (
            not anchored and "/" not in pattern
            and any(fnmatch.fnmatch(part, pattern) for part in parts)
        )
        if matches or fnmatch.fnmatch(value, pattern) or fnmatch.fnmatch(value, f"{pattern}/**"):
            ignored = not negate
    return ignored


def _archive(root: Path, files: list[Path]) -> str:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path in files:
            if path.suffix == ".ipynb":
                try:
                    notebook = json.loads(path.read_text(encoding="utf-8"))
                    for cell in notebook["cells"]:
                        if cell.get("cell_type") == "code":
                            cell["outputs"] = []
                            cell["execution_count"] = None
                    data = json.dumps(notebook).encode("utf-8")
                except (ValueError, KeyError, TypeError) as exc:
                    raise KrunError(f"Invalid notebook: {path.relative_to(root)}") from exc
                info = tarfile.TarInfo(path.relative_to(root).as_posix())
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
            else:
                archive.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _render_runner(
    payload: str,
    entrypoint: str,
    arguments: list[str],
    requirements: str | None,
    dependency_project: str | None,
    outputs: list[str],
    module: str | None = None,
    module_path: str = ".",
    notebook_timeout: int = 600,
    working_directory: str = ".",
    secret_names: list[str] | None = None,
    extra_packages: list[str] | None = None,
) -> str:
    return f'''# Generated by krun. Do not edit.
import base64
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tarfile

PAYLOAD = {payload!r}
ENTRYPOINT = {entrypoint!r}
ARGUMENTS = {json.dumps(arguments)!r}
REQUIREMENTS = {requirements!r}
DEPENDENCY_PROJECT = {dependency_project!r}
OUTPUTS = {json.dumps(outputs)!r}
MODULE = {module!r}
MODULE_PATH = {module_path!r}
NOTEBOOK_TIMEOUT = {notebook_timeout!r}
WORKING_DIRECTORY = {working_directory!r}
SECRET_NAMES = {json.dumps(secret_names or [])!r}
EXTRA_PACKAGES = {json.dumps(extra_packages or [])!r}

working = Path(os.environ.get("KRUN_WORKING_DIR", "/kaggle/working"))
project = working / "krun_project"
artifacts = working / "krun_outputs"
project.mkdir(parents=True, exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(base64.b64decode(PAYLOAD)), mode="r:gz") as archive:
    try:
        archive.extractall(project, filter="data")
    except TypeError:
        # Python 3.10 lacks extraction filters. The archive is generated by
        # krun from regular files with project-relative names only.
        archive.extractall(project)

os.chdir(project)
if REQUIREMENTS:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(project / REQUIREMENTS)])
elif DEPENDENCY_PROJECT is not None:
    subprocess.check_call([
        sys.executable,
        "-m",
        "pip",
        "install",
        str(project / DEPENDENCY_PROJECT),
    ])
if json.loads(EXTRA_PACKAGES):
    subprocess.check_call([sys.executable, "-m", "pip", "install", *json.loads(EXTRA_PACKAGES)])

os.chdir(project)
sys.path.insert(0, str(project))
sys.argv = [ENTRYPOINT, *json.loads(ARGUMENTS)]
execution_directory = (project / WORKING_DIRECTORY).resolve()
if not execution_directory.is_relative_to(project.resolve()) or not execution_directory.is_dir():
    raise ValueError("Working directory must be inside the project")
os.chdir(execution_directory)
if json.loads(SECRET_NAMES):
    from kaggle_secrets import UserSecretsClient
    secrets = UserSecretsClient()
    for name in json.loads(SECRET_NAMES):
        os.environ[name] = secrets.get_secret(name)
try:
    if MODULE:
        sys.path.insert(0, str(project / MODULE_PATH))
        runpy.run_module(MODULE, run_name="__main__", alter_sys=True)
    elif ENTRYPOINT.endswith(".ipynb"):
        import nbformat
        from nbclient import NotebookClient
        notebook = nbformat.read(project / ENTRYPOINT, as_version=4)
        executed = artifacts / "notebooks" / (Path(ENTRYPOINT).stem + ".executed.ipynb")
        executed.parent.mkdir(parents=True, exist_ok=True)
        client = NotebookClient(notebook, timeout=NOTEBOOK_TIMEOUT, kernel_name="python3",
                                resources={{"metadata": {{"path": str(execution_directory)}}}})
        client.on_cell_start = lambda cell, cell_index, **kwargs: print("Cell", cell_index + 1, flush=True)
        try:
            client.execute()
        finally:
            nbformat.write(notebook, executed)
    else:
        sys.path.insert(0, str((project / ENTRYPOINT).parent))
        runpy.run_path(str(project / ENTRYPOINT), run_name="__main__")
finally:
    artifacts.mkdir(parents=True, exist_ok=True)
    for configured in json.loads(OUTPUTS):
        source = project / configured
        if source.is_symlink():
            continue
        if Path(configured).is_absolute() or ".." in Path(configured).parts:
            raise ValueError("Output must be project-relative")
        if not source.resolve().is_relative_to(project.resolve()) or source.resolve() == project.resolve():
            raise ValueError("Output escapes the project or selects the project root")
        if not source.exists():
            continue
        destination = artifacts / configured.rstrip("/")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            def skip_symlinks(directory, names):
                return [name for name in names if Path(directory, name).is_symlink()]
            shutil.copytree(source, destination, dirs_exist_ok=True, ignore=skip_symlinks)
        else:
            shutil.copy2(source, destination)
'''
