# KRun

Run Python scripts, packages and notebooks on Kaggle from your terminal.
KRun packages the project, submits a private Kaggle job, follows its status and
logs, then downloads the results. Your Kaggle account's quotas and accelerator
availability apply. Docker runs the local CLI; Kaggle runs your workload.

## Start here

Install Git and Docker. Start Docker Desktop on Windows/macOS, or Docker Engine
on Linux. `docker info` must work. Host Python and a local GPU are not required.

### Linux / macOS

```bash
git clone https://github.com/nhminh107/KRun-PyProjectOnKaggle.git
cd KRun-PyProjectOnKaggle
./bin/krun login
./bin/krun demo sales-report
```

The launcher builds the image on first use. Login prints a browser URL: open
it, authorize your Kaggle account and paste the verification code into the
terminal. Existing credentials in `~/.kaggle` are reused.

The CPU demo reads bundled order CSV data and writes four reports. Expect
`total_revenue: "213.00"`, eight paid orders and two rejected rows. After
`Completed successfully.`, find the files at:

```text
examples/sales_report/.krun/jobs/<job-id>/output/krun_outputs/outputs/
```

### Windows PowerShell

Start Docker Desktop in Linux-container mode:

```powershell
git clone https://github.com/nhminh107/KRun-PyProjectOnKaggle.git
cd KRun-PyProjectOnKaggle
.\krun.ps1 login
.\krun.ps1 demo sales-report
```

If your PowerShell execution policy blocks local scripts, invoke the launcher
with `powershell -ExecutionPolicy Bypass -File .\krun.ps1 login` (or the demo
command). This changes policy for that process only. Linux is locally tested;
Windows/macOS CI is configured but those platforms must be verified before a
release claims full support.

## Run your project

No YAML is needed. The launcher accepts a path to a project outside this repo:

```bash
./bin/krun run /path/to/my-project/main.py
./bin/krun run /path/to/my-project/scripts/report.py --project /path/to/my-project
./bin/krun run /path/to/my-project/main.py --gpu T4 -- --epochs 10
```

CPU is the default unless `krun.yaml` specifies otherwise. Use `--gpu T4`,
`--gpu P100`, or `--accelerator TPU` when your Kaggle account supports it.
KRun never silently switches your requested accelerator to CPU.

An explicit `--project` is useful for monorepos and scripts without a project
marker. Otherwise KRun looks for `krun.yaml` or existing `.krun/jobs`, then
`pyproject.toml`, `requirements.txt` or Git metadata, then uses the script's
directory. Mount only the project you intend to upload.

### Optional short command

```bash
./scripts/install.sh
```

This creates `~/.local/bin/krun` as a symlink to the launcher. Ensure that
directory is on PATH. The installer does not overwrite another `krun` command
or edit your shell configuration. Keep the cloned repository in place.

Then, from your project root:

```bash
krun run main.py
krun run scripts/report.py -- --input data/orders.csv
```

In PowerShell, call the launcher by its full path when working in another
project, e.g. `& 'C:\tools\KRun-PyProjectOnKaggle\krun.ps1' run main.py`.

## Scripts, modules and notebooks

```bash
./bin/krun demo module
./bin/krun demo notebook
./bin/krun run -m my_package.report --project /path/to/project -- --count 10
./bin/krun run /path/to/project/analysis.ipynb --cell-timeout 900
```

Modules run with package context, supporting relative imports. The selected
module must be a `.py` file or a package with `__main__.py` inside the project.
Modules can be rooted at the project directory or in its `src/` directory.

Python notebooks execute through Jupyter/nbclient on Kaggle. Their original
files remain untouched. Old cell outputs are removed from the uploaded copy.
The executed notebook is saved at
`output/krun_outputs/notebooks/<name>.executed.ipynb`, including cell results up
to a failure. Notebook execution requires `nbclient`, `nbformat` and a Python
kernel in the remote environment; Kaggle's managed image normally includes
them. Declare them in your requirements if using a different environment.

The default working directory is the project root. Use `--cwd notebooks` for a
notebook expecting relative paths from that subdirectory. `--cell-timeout`
controls each notebook cell, while `--timeout` controls local job monitoring.
The notebook's own code determines its device usage. Interactive prompts,
desktop GUI code and long-lived servers are not supported batch workloads.
Arguments after `--` are supported for scripts/modules; notebook CLI arguments
are rejected instead of silently ignored.

## Dependencies and inputs

Without YAML, KRun detects root `requirements.txt`, otherwise root
`pyproject.toml`, a single nested manifest, or one containing the entrypoint.
Ambiguous manifests require an explicit selection:

```bash
./bin/krun run /path/to/project/main.py --requirements /path/to/project/requirements.txt
./bin/krun run /path/to/project/main.py --dependency-project /path/to/project/backend
./bin/krun run /path/to/project/main.py --input data/sample.csv
```

These files/directories must remain inside the selected project. Dependencies
install on Kaggle, not in your local venv. Set `--internet` when installation
or model/data downloads need internet. `--no-internet` requests offline use.
KRun does not infer a reliable dependency list from imports or copy your venv.

Use repeatable `--package` to explicitly request extra pip dependencies without
adding a requirements file. For example, preview your HandsOnLLM notebook:

```bash
./bin/krun run /data/HandsOnLLM/Chapter4_TextClassification.ipynb \
  --package transformers --package datasets --package scikit-learn --package tqdm \
  --gpu T4 --internet --dry-run
```

Remove `--dry-run` to submit after reviewing the package. The notebook may also
require model access or account quota; explicit package names alone do not
guarantee arbitrary notebook code will complete. Pin versions for reproducible
runs, e.g. `--package 'some-library==1.2.3'`.

Small local inputs are included in the project archive. The limit is 20 MB
before compression; the error lists the largest files. For larger data, attach
an **existing** Kaggle Dataset:

```bash
./bin/krun run main.py --dataset owner/dataset-slug
```

Read attached data from `/kaggle/input/` in your script. KRun does not currently
create/upload datasets for you. Access to private datasets still depends on
your Kaggle account.

## Preview before submitting

```bash
./bin/krun run /path/to/project/main.py --dry-run
./bin/krun doctor
./bin/krun auth status
```

Dry-run lists the root, entrypoint, dependencies, accelerator, file count,
package size and filenames. It requires no Kaggle login and creates no job.
Doctor checks local write access and makes an authenticated Kaggle request;
it cannot guarantee accelerator availability or remaining quota.

## Logs and results

Run lifecycle commands from the project root, or pass `--project`:

```bash
krun run main.py --detach
krun jobs
krun status
krun logs
krun wait
krun output
```

Commands default to the newest local job. Supply a job ID to select another:

```bash
krun wait 20260927-120000-a1b2c3 --timeout 7200
krun output 20260927-120000-a1b2c3 --path downloaded
```

The launcher allows download paths inside the mounted project. Select a common
root with `--project` if your desired destination is elsewhere. Native installs
can download directly to other host paths.

Monitoring polls status and readable logs. Unavailable logs do not stop status
monitoring. Ctrl-C stops local monitoring; the remote job may continue. Resume
with `wait` without resubmitting. Monitoring defaults to one hour; bounded
network requests may take additional time. Read/download requests retry only
transient failures; submission is never retried automatically.

Remote job status and download status are stored separately. If the job has
completed but download failed, retry `output`. Failed jobs also attempt to
download diagnostic artifacts when Kaggle makes them available.

```text
.krun/jobs/<job-id>/
├── metadata.json
├── logs.txt
├── workspace/runner.py
├── workspace/kernel-metadata.json
└── output/krun_outputs/
```

Files under `outputs/` are collected by default. Add repeatable `--output`
options for other locations. Notebook results are saved automatically.

## Optional configuration

`krun init --entrypoint main.py` saves reusable defaults. Existing YAML remains
supported. CLI options override YAML, then discovery/defaults apply:

```yaml
project:
  name: sales-report
runtime:
  accelerator: cpu
  internet: true
entrypoint:
  file: main.py
dependencies:
  requirements: requirements.txt
  project: null
outputs:
  - outputs/
  - metrics.json
```

Set `requirements` to `null` when no requirements file is used. `requirements`
and `project` are mutually exclusive. Paths must stay inside the project;
output paths cannot be absolute, contain `..`, or select the project root or
`.krun` state. `--output` replaces the configured output list.

## Credentials and secrets

The launcher mounts `~/.kaggle` read-write for OAuth refresh. It forwards
existing `KAGGLE_API_TOKEN`, `KAGGLE_USERNAME` and `KAGGLE_KEY` environment
variables. Token users should set `KAGGLE_USERNAME` or pass `--owner` when the
username cannot be resolved. Never paste a token into a command argument,
source file, YAML or Git commit.

`--secret NAME` asks the remote runner to read an **already enabled** Kaggle
Secret into an environment variable. It sends only the name, never the value.
Enabling a secret for the generated kernel is a separate Kaggle permission:
KRun cannot grant it through the supported submission metadata. Thus this
option alone does not make a fresh kernel able to call Groq or another private
API; configure access through Kaggle before expecting the secret to resolve.

Known credential/key filenames, `.kaggle`, virtual environments, Git metadata
and `.krun` state are always excluded, including with `--input`. Hardcoded
credentials inside ordinary source files cannot be reliably detected: inspect
the dry-run list and source before submitting sensitive projects.

Root `.gitignore` and `.krunignore` accept a small glob subset: comments,
filenames, glob patterns, directory paths and ordered `!` negations. This is
not Git's complete ignore specification; nested ignore files and escaped
patterns are not implemented. `--input` overrides these user exclusions but
not mandatory credential exclusions. Symlinks are not uploaded or followed
while collecting artifacts.

## Updating and advanced Docker use

`git pull` then run the launcher: it rebuilds a local image when source or
runtime requirements change. `./bin/krun build` explicitly rebuilds it.
The Docker dependency list pins runtime versions and the image records resolved
versions in `/opt/venv/resolved-requirements.txt`.

After a release image has actually been published, set `KRUN_IMAGE` to its
versioned GHCR tag to pull it instead of building locally. The release workflow
defines `ghcr.io/nhminh107/krun-pyprojectonkaggle:<release-tag>`; its presence is
not assumed until the workflow completes. Custom images are not rebuilt by
the launcher. Force an update with `docker pull` when appropriate.

For manual use, matching host ownership:

```bash
docker build --build-arg USER_ID="$(id -u)" --build-arg GROUP_ID="$(id -g)" -t krun:local .
cd /path/to/project
docker run --rm -it -v "$PWD:/workspace" -v "$HOME/.kaggle:/home/krun/.kaggle" krun:local run main.py
```

## Troubleshooting

- Docker daemon error: start Docker and check `docker info` and permissions.
- Bind mount error: use a real project directory shared with Docker Desktop.
  Docker `--mount` source paths containing commas are not supported by the launcher.
- Permission denied: verify host folder ownership. The launcher sets runtime
  UID/GID and a writable temporary home; do not make credential files public.
- Missing/expired credentials: run `login --force`, then `auth status`.
- Missing imports: declare dependencies explicitly; ensure internet is enabled.
- Wrong project root: pass `--project`; inspect `--dry-run` first.
- Unknown CLI option: KRun flags precede `--`; program arguments follow it.
- Queued/unavailable GPU: inspect the Kaggle job URL and account quota.
- Submission error: inspect the printed kernel URL before submitting again;
  a network timeout does not prove the remote submission was rejected.

## Development and validation

Native development requires Python 3.11+:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
```

Tests cover discovery, packaging exclusions, local imports, modules, notebook
execution/error artifacts, job state and monitor/download recovery. Normal CI
does not contact Kaggle. Authenticated CPU checks use the three demo commands.
GPU and real notebooks with model downloads require separate account-aware
testing. See [docs/design.md](docs/design.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

MIT license. See [LICENSE](LICENSE).
