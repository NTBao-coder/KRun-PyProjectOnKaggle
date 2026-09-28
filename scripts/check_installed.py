"""Smoke-test a wheel using the Python interpreter from its uv tool environment."""

import json
import os
import subprocess
import sys
import sysconfig
import tempfile
from importlib.metadata import version
from pathlib import Path

import krun
from krun.kaggle import KaggleClient


def main() -> None:
    """Verify commands, packaged demos, and dependency lookup outside the checkout."""
    repository = Path(__file__).resolve().parents[1]
    installed = Path(krun.__file__).resolve()
    assert not installed.is_relative_to(repository), f"Using source checkout: {installed}"
    assert version("krun-cli") == krun.__version__
    scripts = Path(sysconfig.get_path("scripts"))
    executable = scripts / ("krun.exe" if os.name == "nt" else "krun")
    with tempfile.TemporaryDirectory(prefix="krun-wheel-check-") as directory:
        root = Path(directory)
        # A tool install only exposes krun; Kaggle must resolve without a PATH entry.
        environment = {**os.environ, "PATH": str(root), "PYTHONPATH": ""}
        os.environ["PATH"] = str(root)
        client = KaggleClient()
        assert client.executable, "Installed dependency executable is missing"
        assert Path(client.executable).parent == scripts

        def run(*args: str) -> str:
            result = subprocess.run(
                [str(executable), *args], cwd=root, env=environment,
                capture_output=True, text=True, timeout=60,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            return result.stdout

        assert krun.__version__ in run("--version")
        assert "demo" in run("--help")
        (root / "main.py").write_text("raise AssertionError('Caller file must not run')\n")
        (root / "report.ipynb").write_text("Caller file must not be used\n")
        for name in ("sales-report", "module", "notebook"):
            output = run("demo", name, "--dry-run")
            assert "Accelerator: CPU" in output
            assert not (root / f"krun-demo-{name}" / ".krun").exists()
        run("demo", "module", "--destination", str(root / "with arguments"),
            "--dry-run", "--", "--count", "7")
        for folder, args, output, expected in (
            ("krun-demo-sales-report", ["main.py"], "summary.json", "213.00"),
            ("krun-demo-module", ["-m", "report_job", "--count", "7"], "result.json", None),
        ):
            project = root / folder
            completed = subprocess.run(
                [sys.executable, *args], cwd=project, env=environment,
                capture_output=True, text=True, timeout=60,
            )
            assert completed.returncode == 0, completed.stderr
            result = json.loads((project / "outputs" / output).read_text())
            if expected:
                assert result["total_revenue"] == expected
            else:
                assert result["squares"] == [0, 1, 4, 9, 16, 25, 36]
    print("Installed package checks passed (no Kaggle requests).")


if __name__ == "__main__":
    main()
