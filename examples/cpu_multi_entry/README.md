# CPU multi-entry inventory demo

A tiny, deterministic project with two independent Python entrypoints. Neither
file is named `main.py`. Both import the shared `inventory` package, and its
storage module imports PyYAML from `requirements.txt`. There is no `krun.yaml`,
GPU, model download, or training workload.

From the KRun repository root, run each file as a separate CPU job:

```bash
./bin/krun run examples/cpu_multi_entry/stock_report.py --project examples/cpu_multi_entry --internet
./bin/krun run examples/cpu_multi_entry/reorder_report.py --project examples/cpu_multi_entry --internet
```

KRun detects `requirements.txt` and installs its dependency on Kaggle. Internet
is enabled for that installation. Add `--dry-run` to preview without submitting.
Do not add `--gpu`: CPU is the default for this project.

Expected results:

- `stock_summary.json`: 3 products, 16 units, stock value `"181.00"`.
- `reorder_summary.json`: order 6 Pens and 3 Mice, 9 units total.

After each job, its JSON is downloaded to:

```text
examples/cpu_multi_entry/.krun/jobs/<job-id>/output/krun_outputs/outputs/
```

The two commands have different job IDs. Each job generates only the report
selected by its entrypoint; one file does not execute the other.
