# Design notes

## Official integration boundary

`krun` wraps the official `kaggle` executable with argument lists and never uses
`shell=True`. It relies on these supported commands:

- `kaggle kernels push`
- `kaggle kernels status`
- `kaggle kernels logs`
- `kaggle kernels output`

The wrapper is isolated in `krun/kaggle.py` so CLI presentation and project
packaging do not depend on subprocess details.

## Source transport

The kernels API reads the configured `code_file`; sibling project files are not
an arbitrary source upload mechanism. For the small-project MVP, a tar archive
is embedded in the generated Python runner. This is less operationally complex
than automatically maintaining a separate Kaggle Dataset for every run.

The design deliberately has a package-size ceiling. Dataset creation and
versioning is the intended next transport for large inputs, rather than raising
the ceiling or depending on undocumented endpoints.

## Local imports and dependencies

The runner recreates the project tree and makes its root both the working
directory and the first import path. A configured requirements file is installed
with the running Python interpreter. If no requirements file is configured,
KRun installs a root manifest, the sole nested `pyproject.toml`, or the nested
project selected explicitly in config. Local virtual environments are excluded:
their binaries are not portable to Kaggle and dependency metadata is the
repeatable source of truth.

YAML is optional. Root discovery first searches for reusable configuration or
job state, then dependency/Git markers, with the entrypoint directory as a
fallback. Explicit `--project` takes precedence. The Bash/PowerShell launcher
mirrors these rules on the host, mounts the selected root at `/workspace`, and
translates file arguments before starting the Python CLI. Arguments after `--`
are forwarded literally. An empty `.git` directory is not a repository marker.

Script execution adds the script directory and project root to the import path.
Module execution uses `run_module`, retaining package context and supporting
root and `src/` layouts. Notebook execution uses nbclient, saves the executed
notebook in a finally block, and does not modify the original notebook. The
uploaded copy contains code/markdown but no previous cell outputs.

The execution working directory defaults to the project root and can be
selected explicitly. Dependency installation runs from the project root so
project-relative requirements and editable local packages work.

## Job identity

Each submission receives a timestamp-plus-random local ID and a unique Kaggle
kernel slug. Local metadata is written atomically. Keeping each generated
workspace makes failed submissions inspectable without mixing it with source.

Monitoring polls bounded Kaggle status/log requests. Log failures are non-fatal
to status tracking. A local timeout/interrupt never cancels the remote job;
`wait` resumes it. Remote execution and download states are separate. Read and
download commands can retry transient network errors; push is never retried
automatically because a failed response may still correspond to a successful
remote submission. Failed jobs attempt diagnostic artifact download.

## Safety choices

Project-relative paths are resolved before packaging and cannot escape the
root. Symlinks are skipped to avoid accidentally following a path outside the
project. Known credential and private-key filenames are ignored independently
of user ignore rules. The credential material itself remains owned by the
Kaggle CLI.

Mandatory filename exclusions cannot be overridden by `--input` or user ignore
negations. Normal root `.gitignore`/`.krunignore` rules use a documented glob
subset. Traversal prunes mandatory directories, plus user-ignored directories
when no negation could restore descendants. Output collection validates paths
again in the remote runner and skips symlinked entries.

Existing datasets attach through official `dataset_sources`. Optional secret
references resolve only already enabled Kaggle Secrets. The CLI cannot grant
per-kernel secret access through submission metadata, and never copies host
Kaggle credentials into the workload archive.

## Distribution

The launcher needs Docker and Bash/PowerShell, not host Python. Local image
fingerprints detect source/runtime-lock changes. A custom `KRUN_IMAGE` selects
a prebuilt image without rebuilding it. Credentials remain on the host; a
temporary writable container home and matching UID/GID handle local ownership.
CI runs Python behavior tests and Docker dry-run smoke tests. A release-triggered
workflow publishes versioned amd64/arm64 images; it does not publish on ordinary
test runs. Actual platform/E2E validation must be recorded before a release.
