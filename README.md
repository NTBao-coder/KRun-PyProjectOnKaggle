# KRun

Run Python scripts, modules, and notebooks on Kaggle from your terminal.
KRun packages your project, submits a private job, follows its logs, and downloads
the results. You do not need a file named `main.py` or a `krun.yaml` configuration.

**Docker runs the CLI on your computer. Kaggle runs your project.**
With the Docker workflow, your computer does not need Python or a GPU.
Kaggle account quotas, runtime limits, and accelerator availability still apply.

## Step 1: Clone, start Docker, and sign in

You need Git, Docker, and a Kaggle account. Start Docker Desktop on Windows/macOS
or Docker Engine on Linux, then check:

```bash
docker info
```

If this fails, fix Docker access before continuing.

### Linux / macOS

```bash
git clone https://github.com/nhminh107/KRun-PyProjectOnKaggle.git
cd KRun-PyProjectOnKaggle
./bin/krun login
./bin/krun doctor
```

On first use, the launcher builds the Docker image. This needs internet access
and may take a few minutes. Login prints a URL: open it in your browser,
authorize your Kaggle account, and paste the verification code into the terminal.
Existing credentials in `~/.kaggle` are reused.

**Run the `./bin/krun` commands below from the cloned KRun repository.**
You do not need to switch into an external project. Replace `/path/to/...`
with real paths on your computer, and quote paths containing spaces.

### Windows PowerShell

Start Docker Desktop in Linux-container mode:

```powershell
git clone https://github.com/nhminh107/KRun-PyProjectOnKaggle.git
cd KRun-PyProjectOnKaggle
.\krun.ps1 login
.\krun.ps1 doctor
.\krun.ps1 demo sales-report
```

For the examples below, replace `./bin/krun` with `.krun.ps1`.
If execution policy blocks the script, use
`powershell -ExecutionPolicy Bypass -File .\krun.ps1 login`;
this changes policy only for that process.
Linux has been tested locally. Windows/macOS CI is configured, but its results
have not yet been verified.

## Step 2: Try a small CPU demo

This bundled demo does not need a GPU, model downloads, or external data:

```bash
./bin/krun demo sales-report
```

Expected results: `total_revenue: "213.00"`, eight paid orders, and two
rejected rows. After `Completed successfully.`, find the four reports here:

```text
examples/sales_report/.krun/jobs/<job-id>/output/krun_outputs/outputs/
```

Replace `<job-id>` with the ID printed for your run.

### Test two entrypoints, shared imports, and requirements.txt

The [multi-entry CPU demo](examples/cpu_multi_entry/README.md) contains YAML data,
a `requirements.txt`, and a shared `inventory/` package.
It has no `main.py` or `krun.yaml`:

```bash
./bin/krun run examples/cpu_multi_entry/stock_report.py \
  --project examples/cpu_multi_entry --internet

./bin/krun run examples/cpu_multi_entry/reorder_report.py \
  --project examples/cpu_multi_entry --internet
```

KRun automatically installs PyYAML from the requirements file on Kaggle.
Each command creates a separate job:

| Entrypoint | Output file | Expected result |
| --- | --- | --- |
| `stock_report.py` | `stock_summary.json` | 3 products, 16 units, value `"181.00"` |
| `reorder_report.py` | `reorder_summary.json` | Order 6 Pens and 3 Mice: 9 units total |

Results are saved under
`examples/cpu_multi_entry/.krun/jobs/<job-id>/output/krun_outputs/outputs/`.
Add `--dry-run` to preview packaging without submitting a job.

## Step 3: Run your project

### Python scripts

You do not need to turn your code into a notebook or rename it to `main.py`:

```bash
./bin/krun run /path/to/my-project/report.py \
  --project /path/to/my-project --internet
```

`--project` selects the project root to upload. Local modules, dependency
files, and inputs needed by your code must be inside that directory.
Set it explicitly when starting out to avoid selecting the wrong root.

CPU is the default unless your YAML configuration selects another accelerator.
To request a GPU:

```bash
./bin/krun run /path/to/my-project/train.py \
  --project /path/to/my-project --gpu T4 --internet --timeout 14400
```

You can also request `--gpu P100` or `--accelerator TPU` when your account
supports them. KRun does not silently fall back to CPU. Your code must still use
the accelerator correctly; requesting a GPU does not make CPU-only code use it.

Put KRun options before `--` and your script's arguments after it:

```bash
./bin/krun run /path/to/my-project/train.py \
  --project /path/to/my-project --gpu T4 --internet -- --epochs 10
```

Your script must implement `--epochs`; KRun only forwards the argument.

### Modules and notebooks

```bash
./bin/krun demo module
./bin/krun demo notebook

./bin/krun run -m my_package.report \
  --project /path/to/my-project -- --count 10

./bin/krun run /path/to/my-project/analysis.ipynb \
  --project /path/to/my-project --internet --cell-timeout 900
```

Modules run with package context, supporting relative imports. The module must
be a local `.py` file or a package with `__main__.py`, rooted at the project
directory or its `src/` directory.

Python notebooks run through Jupyter/nbclient. The original file is not modified.
The executed notebook is saved under `output/krun_outputs/notebooks/`,
including cell results before a failure. The remote environment needs
`nbclient`, `nbformat`, and a Python kernel; declare them if they are not available.

The working directory defaults to the project root. Use `--cwd notebooks`
if your code expects relative paths from that folder. Notebooks do not accept
arguments after `--`. Desktop GUIs, interactive prompts, and long-lived servers
are not suitable batch workloads.

## Step 4: Declare dependencies

**KRun installs packages automatically, but it needs a dependency list.**
It does not guess package names or versions from imports, or copy your local
venv/Conda environment.

Without YAML, KRun first looks for a root `requirements.txt`. Otherwise,
it looks for a root or suitable nested `pyproject.toml`. If multiple projects
are found, choose explicitly:

```bash
./bin/krun run /path/to/my-project/report.py \
  --project /path/to/my-project \
  --requirements /path/to/my-project/requirements.txt --internet

./bin/krun run /path/to/my-project/backend/report.py \
  --project /path/to/my-project \
  --dependency-project /path/to/my-project/backend --internet
```

If you only have a Python file, request packages directly:

```bash
./bin/krun run /path/to/my-project/report.py \
  --project /path/to/my-project --internet --package 'PyYAML==6.0.2'
```

Repeat `--package` for additional libraries. They install **on Kaggle**,
not in your host Python or the local CLI image. Enable `--internet` when
installing packages or downloading models/data; use `--no-internet` for offline jobs.

Pinning versions helps reproducibility, but they must still match Kaggle's Python,
PyTorch, CUDA, and existing packages. Successful installation does not guarantee
successful execution. Changing workload dependencies **does not require a Docker rebuild**.

## Step 5: Preview before submitting

```bash
./bin/krun run /path/to/my-project/report.py \
  --project /path/to/my-project --internet --dry-run
```

Dry-run lists the root, entrypoint, dependencies, accelerator, size, and files
to upload. It needs no Kaggle login and creates no job. The launcher still needs
Docker and may build its image on first use.

**Dry-run does not execute your code, install remote dependencies, test CUDA,
or guarantee training will succeed.** Review the list, then remove `--dry-run`
to submit. `doctor` checks local setup and authentication, not quota or GPU availability.

## Step 6: Read logs and find results

From the KRun repository, select the project you ran:

```bash
./bin/krun jobs --project /path/to/my-project
./bin/krun status --project /path/to/my-project
./bin/krun logs --project /path/to/my-project
```

Commands default to the newest local job **in that project**.
To select another job, put its ID after the command name.
The local log is at `.krun/jobs/<job-id>/logs.txt`.

```text
my-project/.krun/jobs/<job-id>/
├── metadata.json                 # Job and download status
├── logs.txt                      # Logs fetched from Kaggle
├── workspace/runner.py           # Runner submitted to Kaggle
└── output/
    ├── krun_project/             # Uploaded source, not training results
    └── krun_outputs/
        ├── outputs/              # Files your code writes into outputs/
        └── notebooks/            # Executed notebooks, when applicable
```

Kaggle may return extra logs/artifacts; not every folder appears in every job.
**`download_status: complete` means files were downloaded, not that the job
succeeded.** A job may still have status `error`. Check remote status and the
final traceback in the log.

KRun collects the project's `outputs/` directory by default. For another location:

```bash
./bin/krun run /path/to/my-project/report.py \
  --project /path/to/my-project --internet --output reports
```

`--output` selects what to collect; it does not change where your script saves
files. Repeat it to collect multiple paths. It replaces the entire default/YAML
output list. Paths must be project-relative, not `/kaggle/working/results`.
To use KRun's collection, save into a relative folder such as `outputs/`.

### Resume waiting or download again

Ctrl-C stops local monitoring; the Kaggle job may continue. `--detach`
submits without waiting. `wait` resumes monitoring **without creating another job**,
and `output` downloads artifacts again:

```bash
./bin/krun wait --project /path/to/my-project --timeout 14400
./bin/krun output --project /path/to/my-project
```

`--timeout` limits local monitoring (one hour by default), not Kaggle runtime
or quota. Network requests may take additional time. `--cell-timeout` limits each
notebook cell. Temporarily unavailable logs do not stop monitoring.
Read/download requests retry transient failures; submission is not retried
automatically to avoid duplicate jobs.

## Step 7: Update KRun and Docker

From the KRun repository:

```bash
git pull
./bin/krun build
./bin/krun doctor
```

You normally **do not need to delete the old image**. The launcher rebuilds when
CLI source or dependencies change; `build` explicitly requests a build.
If you want to remove and recreate the local image, first check for containers
using it:

```bash
docker ps -a --filter ancestor=krun:local
docker image rm krun:local
./bin/krun build
```

Only the `krun:local` image is targeted, not your project or results.
Docker may refuse removal if a container uses the image.
Do not force removal or use system prune for this workflow.

## Troubleshooting

- **Docker is unavailable / permission denied:** check `docker info`, Docker
  access, and project ownership. Do not make credentials public.
- **Bind mount error:** use a real folder shared with Docker Desktop.
  The launcher does not support mount paths containing commas.
- **Expired credentials:** run `./bin/krun login --force`, then `./bin/krun auth status`.
- **Missing imports:** declare dependencies and enable internet. For local
  modules, check `--project` and the dry-run file list.
- **CUDA/bitsandbytes/Triton errors:** choose versions compatible with Kaggle's
  environment. Rebuilding local Docker does not change remote CUDA.
  Do not pin an old version just because a tutorial uses it.
- **W&B says `No API key configured`:** if you do not use W&B, set
  `report_to="none"` in your script's `TrainingArguments`.
  This is workload logging configuration, not Kaggle authentication.
- **Warnings but unclear job status:** check `status` and the final traceback.
  Warnings and download/install messages alone do not prove failure.
- **Unknown CLI option:** KRun flags go before `--`; script arguments go after it.
- **GPU queued / unavailable:** inspect the printed job URL and your account quota.
- **Submission timeout:** check the URL before submitting again; a local timeout
  does not prove Kaggle did not receive the job.
- **Job finished but download failed:** retry `output`, not the workload.
  Failed jobs also attempt to download diagnostics when Kaggle provides them.

## Advanced options

### Optional short command

```bash
./scripts/install.sh
```

This creates a symlink at `~/.local/bin/krun`; that directory must be on PATH.
It does not overwrite an existing command or edit your shell profile.
Keep the cloned repository in place. You can then run `krun run report.py`
from your own project. In PowerShell, use the full launcher path:
`& 'C:\tools\KRun-PyProjectOnKaggle\krun.ps1' run report.py`.

### Inputs and upload limits

The limit is 20 MB before compression; errors list the largest files.
Small project inputs are uploaded with your code. `--input` includes files
excluded by user ignore rules, but does not bypass size limits or secret exclusions:

```bash
./bin/krun run /path/to/my-project/report.py \
  --project /path/to/my-project --input /path/to/my-project/data/sample.csv
```

For larger data, attach an **existing** Kaggle Dataset using
`--dataset owner/dataset-slug` and read it from `/kaggle/input/`.
KRun does not create/upload datasets for you. Private dataset access still
depends on your account.

### Optional YAML configuration

Without `--project`, KRun searches for `krun.yaml` or `.krun/jobs`,
then requirements, pyproject, or Git markers, and finally uses the script's folder.
Use `--project` for multi-directory projects.

`init` writes YAML into the working directory and does not accept `--project`.
Switch into your project and call the launcher by its full path:

```bash
cd /path/to/my-project
/path/to/KRun-PyProjectOnKaggle/bin/krun init --entrypoint report.py
cd /path/to/KRun-PyProjectOnKaggle
```

CLI options override YAML, then discovery/defaults apply. Example `krun.yaml`:

```yaml
project:
  name: my-project
runtime:
  accelerator: cpu
  internet: true
entrypoint:
  file: report.py
dependencies:
  requirements: requirements.txt
  project: null
outputs:
  - outputs/
```

Set `requirements: null` when no requirements file is used.
`requirements` and `project` are mutually exclusive.
Output paths cannot be absolute, contain `..`, or select the project root
or `.krun`. Symlinks are not uploaded or followed during artifact collection.

### Credentials, secrets, and ignore files

The launcher mounts `~/.kaggle` read-write for OAuth refresh and forwards
existing `KAGGLE_API_TOKEN`, `KAGGLE_USERNAME`, and `KAGGLE_KEY` variables.
Token users may need `KAGGLE_USERNAME` or `--owner` if the username cannot be resolved.
Never put tokens in command arguments, source, YAML, or Git.

`--secret NAME` reads an **already enabled** Kaggle Secret into a remote
environment variable. Only its name is sent, not its value.
KRun cannot grant secret access through submission metadata; this option alone
does not give a new kernel access to a private API.

Known credential filenames, `.kaggle`, virtual environments, Git metadata,
and `.krun` are always excluded, even with `--input`.
Hardcoded secrets are not reliably detected: review your source and dry-run list.
Root `.gitignore`/`.krunignore` support a subset of globs, directory patterns,
and ordered `!` negations, not full Git semantics.
Nested ignore files and escaped patterns are not supported.

### Release images and development

Only after a release image has actually been published, set `KRUN_IMAGE` to
`ghcr.io/nhminh107/krun-pyprojectonkaggle:<release-tag>` to pull instead of building.
Do not assume this image already exists. Custom images are not rebuilt;
use `docker pull` to update them.
CLI dependencies are pinned in `requirements-docker.txt`; resolved versions
are recorded at `/opt/venv/resolved-requirements.txt`.

Native development requires Python 3.11+. This is not required for Docker users:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
```

Normal CI does not call Kaggle. Local tests and dry-runs do not replace real GPU
or workload tests. See [design notes](docs/design.md),
[contributing](CONTRIBUTING.md), and the [MIT License](LICENSE).
