"""Entry point 1: summarize stock value on CPU."""

import argparse
from pathlib import Path

from inventory.analysis import stock_summary
from inventory.storage import load_products, save_report


def run() -> None:
    """Read the input and write the stock summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    products = load_products(Path(__file__).resolve().parent / "stock.yaml")
    save_report(args.output_dir / "stock_summary.json", stock_summary(products))


if __name__ == "__main__":
    run()
