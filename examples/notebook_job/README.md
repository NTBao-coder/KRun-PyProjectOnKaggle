# Notebook job

Run `./bin/krun demo notebook` from the repository root. No YAML is required.
The notebook exercises two code cells and IPython `%time`, writes an artifact
with `count: 4` and `sum: 20`, and returns an executed notebook.

Find the JSON under `.krun/jobs/<job-id>/output/krun_outputs/outputs/` and the
executed notebook under `output/krun_outputs/notebooks/` in that job directory.
