"""Create writable demo projects from installed package resources."""

from enum import Enum
from importlib.resources import as_file, files
from importlib.resources.abc import Traversable
from pathlib import Path
from shutil import copyfile

from krun.errors import KrunError


class DemoName(str, Enum):
    """Bundled examples available without a repository checkout."""

    sales_report = "sales-report"
    module = "module"
    notebook = "notebook"


DEMO_TEMPLATES = {
    DemoName.sales_report: ("sales_report", ["main.py"]),
    DemoName.module: ("module_job", ["-m", "report_job"]),
    DemoName.notebook: ("notebook_job", ["report.ipynb"]),
}


def create_demo(name: DemoName, destination: Path | None = None) -> tuple[Path, list[str]]:
    """Copy a template to a new directory; never overwrite existing user files."""
    folder, entrypoint = DEMO_TEMPLATES[name]
    root = (destination or Path.cwd() / f"krun-demo-{name.value}").absolute()
    if root.exists() or root.is_symlink():
        raise KrunError(
            f"Demo destination already exists: {root}. Use --destination with a new "
            "directory, or run the existing project with 'krun run'."
        )
    template = files("krun").joinpath("demo_templates", folder)
    root.mkdir(parents=True, exist_ok=False)

    def copy_tree(source: Traversable, target: Path) -> None:
        for item in source.iterdir():
            if item.name in {"__pycache__", ".krun", "outputs"} or item.name.endswith((".pyc", ".pyo")):
                continue
            output = target / item.name
            if item.is_dir():
                output.mkdir()
                copy_tree(item, output)
            else:
                with as_file(item) as path:
                    copyfile(path, output)

    copy_tree(template, root)
    # Resolve file entrypoints here so a same-named file in the caller's
    # directory cannot take precedence over the freshly copied template.
    command = list(entrypoint)
    if len(command) == 1:
        command[0] = str(root / command[0])
    return root, command
