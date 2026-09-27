"""Entry point 2: create a replenishment report on CPU."""

import argparse
from pathlib import Path

from inventory.analysis import reorder_summary
from inventory.storage import load_products, save_report


def run() -> None:
    """Read the input and write the replenishment report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    products = load_products(Path(__file__).resolve().parent / "stock.yaml")
    save_report(args.output_dir / "reorder_summary.json", reorder_summary(products))


if __name__ == "__main__":
    run()
