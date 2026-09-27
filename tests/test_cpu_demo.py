"""Verify both non-main entrypoints and requirements auto-discovery."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from krun.project import discover_project

DEMO = Path(__file__).resolve().parents[1] / "examples" / "cpu_multi_entry"


@pytest.mark.parametrize(
    ("entrypoint", "filename", "expected"),
    [
        ("stock_report.py", "stock_summary.json", {
            "product_count": 3, "total_units": 16, "stock_value": "181.00",
        }),
        ("reorder_report.py", "reorder_summary.json", {
            "items": [{"name": "Pen", "units_to_order": 6}, {"name": "Mouse", "units_to_order": 3}],
            "total_units_to_order": 9,
        }),
    ],
)
def test_cpu_demo_entrypoints(
    tmp_path: Path, entrypoint: str, filename: str, expected: dict,
) -> None:
    selected = discover_project(DEMO, Path(entrypoint), project_root=DEMO)
    assert selected.requirements == DEMO / "requirements.txt"
    assert selected.entrypoint.name == entrypoint
    completed = subprocess.run(
        [sys.executable, str(selected.entrypoint), "--output-dir", str(tmp_path)],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads((tmp_path / filename).read_text()) == expected
    assert len(list(tmp_path.glob("*.json"))) == 1
