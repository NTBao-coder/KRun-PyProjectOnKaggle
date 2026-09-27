# Module job

Run `./bin/krun demo module -- --count 7` from the repository root.
The package uses a relative import and writes `outputs/result.json` containing
the squares `[0, 1, 4, 9, 16, 25, 36]`.

Equivalent from this directory with the installed launcher:
`krun run -m report_job -- --count 7`. No YAML is required.
