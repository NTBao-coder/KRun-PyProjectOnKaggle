"""Run with python -m report_job or KRun's --module option."""

import argparse
import json
from pathlib import Path

from .calculation import squares

parser = argparse.ArgumentParser()
parser.add_argument("--count", type=int, default=5)
args = parser.parse_args()
result = {"squares": squares(args.count)}
Path("outputs").mkdir(exist_ok=True)
Path("outputs/result.json").write_text(json.dumps(result) + "\n", encoding="utf-8")
print(json.dumps(result))
