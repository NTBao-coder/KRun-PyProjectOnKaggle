"""Read YAML input using the dependency declared in requirements.txt."""

import json
from pathlib import Path
from typing import Any

import yaml


def load_products(path: Path) -> list[dict[str, Any]]:
    """Load the bundled inventory fixture."""
    with path.open(encoding="utf-8") as stream:
        document = yaml.safe_load(stream)
    return document["products"]


def save_report(path: Path, report: dict[str, Any]) -> None:
    """Save a report as readable JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Saved report: {path}")
