# krun

Make Kaggle GPU feel like a local Python runtime.

`krun` packages a small local Python project, submits it as a private Kaggle
script through the official Kaggle CLI, follows its execution, and downloads
the resulting artifacts. It keeps normal local imports and project-relative
paths intact, so a training script does not need Kaggle-specific changes.

```console
$ krun run train.py --gpu T4 -- --epochs 10 --batch-size 32
Scanning project...
OK Entrypoint: train.py
OK 12 project files packaged
Submitting Kaggle kernel...
Submitted your-name/my-training-project-...
```

`krun` uses your own Kaggle account. It is subject to Kaggle's normal quotas,
accelerator availability, and platform limitations. It does not rotate
accounts, bypass quotas, or automate the Kaggle website.

## Why krun

Running local code on Kaggle normally involves creating a script or notebook,
moving files, preparing metadata, fixing import paths, submitting a kernel,
checking its status, and downloading output. `krun` turns those steps into a
repeatable CLI workflow while staying on Kaggle's supported API surface.

## Features

- Preserves the local directory tree and imports.
- Reads `requirements.txt`, or installs a root/nested `pyproject.toml` project.
- Supports CPU, NVIDIA T4, NVIDIA P100, and TPU runtime requests.
- Forwards arguments after `--` to the Python entrypoint.
- Includes small local inputs with `--input`.
- Streams logs using the Kaggle CLI's official `kernels logs --follow` command.
- Stores job metadata, logs, generated workspace, and downloaded output locally.
- Ignores common credential, key, cache, virtual environment, and Git files.
- Supports additional project exclusions through `.krunignore`.

## How it works

Kaggle's kernel API accepts a script as its `code_file`; it does not upload an
arbitrary source directory with that script. `krun` therefore creates one
generated runner containing a compressed archive of the project. On Kaggle,
the runner extracts that archive under `/kaggle/working/krun_project`, adds the
project root to `sys.path`, installs declared dependencies, and executes the
entrypoint with `runpy`.

Configured output paths are copied to
`/kaggle/working/krun_outputs`. After a successful run, the official
`kaggle kernels output` command downloads the kernel output into the local job
directory.

The local state layout is:

```text
.krun/
└── jobs/
    └── <job-id>/
        ├── metadata.json
        ├── logs.txt
        ├── workspace/
        │   ├── kernel-metadata.json
        │   └── runner.py
        └── output/
```

## Requirements

- Docker, or Python 3.10 or newer for a native installation.
- A Kaggle account with access to the requested accelerator.
- Internet access when the remote job needs to install dependencies.

## Installation

### Docker (recommended)

Docker keeps KRun and the official Kaggle CLI isolated from your project. Build
the image once; matching the host UID/GID ensures downloaded `.krun` files are
owned by your normal user:

```bash
git clone https://github.com/nhminh107/KRun-PyProjectOnKaggle.git
cd KRun-PyProjectOnKaggle
docker build \
  --build-arg USER_ID="$(id -u)" \
  --build-arg GROUP_ID="$(id -g)" \
  -t krun:local .
```

On Windows PowerShell, Docker Desktop handles mounted-file ownership, so the
default image user is sufficient:

```powershell
docker build -t krun:local .
docker run --rm -it `
  -v "${PWD}:/workspace" `
  -v "${HOME}/.kaggle:/home/krun/.kaggle" `
  krun:local --version
```

Create the host credential directory, then authenticate with either the native
Kaggle CLI or the container:

```bash
mkdir -p "$HOME/.kaggle"
docker run --rm -it \
  -v "$HOME/.kaggle:/home/krun/.kaggle" \
  --entrypoint kaggle \
  krun:local auth login
```

From any Python project, use the image like the normal `krun` command:

```bash
cd /path/to/my-project
docker run --rm -it \
  -v "$PWD:/workspace" \
  -v "$HOME/.kaggle:/home/krun/.kaggle" \
  krun:local init --entrypoint train.py

docker run --rm -it \
  -v "$PWD:/workspace" \
  -v "$HOME/.kaggle:/home/krun/.kaggle" \
  krun:local run train.py --gpu T4
```

For the shortest day-to-day command, add this function to `~/.bashrc` or
`~/.zshrc`:

```bash
krun() {
  docker run --rm -it \
    -v "$PWD:/workspace" \
    -v "$HOME/.kaggle:/home/krun/.kaggle" \
    krun:local "$@"
}
```

Open a new shell, then use KRun normally:

```bash
krun init --entrypoint train.py
krun run train.py --gpu T4
```

For API-token authentication instead of a credential directory:

```bash
docker run --rm -it \
  -e KAGGLE_API_TOKEN \
  -e KAGGLE_USERNAME \
  -v "$PWD:/workspace" \
  krun:local run train.py --gpu T4
```

Remove `-it` in CI or other non-interactive environments.

### Native Python

The Python package includes the official Kaggle CLI. Install both with one
command in an isolated environment:

```bash
git clone https://github.com/nhminh107/KRun-PyProjectOnKaggle.git
cd KRun-PyProjectOnKaggle
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

For development tools:

```bash
python -m pip install -e '.[dev]'
```

## Kaggle credentials

OAuth is the recommended authentication method in current Kaggle CLI releases:

```bash
kaggle auth login
```

The CLI also supports `KAGGLE_API_TOKEN`, `~/.kaggle/access_token`, and the
legacy `~/.kaggle/kaggle.json` file. Follow Kaggle's official authentication
instructions and never place a token in `krun.yaml` or source control.

With token-only authentication, pass `--owner YOUR_KAGGLE_USERNAME` if `krun`
cannot determine the account name locally. Docker users should mount the whole
`.kaggle` directory read-write because OAuth may refresh its cached token.

## Quick start

Initialize a project:

```bash
cd /path/to/my-project
krun init --entrypoint train.py
```

Review `krun.yaml`, then run on a T4:

```bash
krun run train.py --gpu T4
```

Forward script arguments after `--`:

```bash
krun run train.py --gpu T4 -- --epochs 10 --batch-size 32
```

By default, `run` follows logs and downloads output. Add `--detach` to return
after submission:

```bash
krun run train.py --accelerator CPU --detach
krun status
krun logs --follow
krun output
```

Each lifecycle command defaults to the most recent job. A specific job ID can
be supplied as its argument.

## Configuration

`krun init` creates a small `krun.yaml`:

```yaml
project:
  name: my-training-project
runtime:
  accelerator: cpu
  internet: true
entrypoint:
  file: train.py
dependencies:
  requirements: requirements.txt
  project: null
outputs:
  - outputs/
  - checkpoints/
  - metrics.json
```

Set `dependencies.requirements` to `null` when the project has no requirements
file. KRun installs a root `pyproject.toml` automatically. If exactly one nested
manifest exists, such as `BackEnd/pyproject.toml`, KRun installs that project
instead. For repositories containing several manifests, select one explicitly:

```yaml
dependencies:
  requirements: null
  project: BackEnd
```

`requirements` and `project` are mutually exclusive. Accelerator values are
`cpu`, `T4`, `P100`, or `TPU`; command-line values take precedence over config.

All entrypoint, input, requirements, and output paths must remain inside the
project root.

## Commands

```text
krun init [--name NAME] [--entrypoint FILE] [--force]
krun run [ENTRYPOINT] [--gpu T4|P100] [--accelerator TYPE]
         [--input PATH]... [--owner USERNAME] [--detach] [--verbose]
         [-- ENTRYPOINT_ARGS...]
krun status [JOB_ID] [--verbose]
krun logs [JOB_ID] [--follow]
krun output [JOB_ID] [--path DESTINATION]
```

Examples:

```bash
krun run train.py --accelerator CPU
krun run train.py --gpu P100 --input data/sample -- --seed 42
krun status 20260924-093000-a1b2c3
krun logs 20260924-093000-a1b2c3
krun output 20260924-093000-a1b2c3 --path ./downloaded
```

## Project structure support

`krun` packages files without flattening the directory tree. Imports such as
`from src.model import MyModel` continue to work:

```text
my-project/
├── krun.yaml
├── train.py
├── src/
│   ├── model.py
│   └── dataset.py
├── config/
│   └── model.yaml
└── requirements.txt
```

Use `.krunignore` for generated or large files that should not be uploaded. Its
MVP syntax accepts blank lines, `#` comments, names such as `build`, glob names
such as `*.csv`, and paths such as `data/raw/`. An explicit `--input` overrides
`.krunignore` for that path.

## Outputs

Only paths listed under `outputs` are copied into `krun_outputs` by the remote
runner. Missing output paths are skipped. Kaggle may include other standard
kernel files in its output download; configured artifacts remain grouped under
the `krun_outputs/` directory.

## Example project

The GPU check in `examples/hello_gpu` prints the selected device and writes a
JSON artifact:

```bash
cd examples/hello_gpu
krun run main.py --gpu T4
```

Use `--accelerator CPU` to exercise the flow without consuming GPU quota.

## Limitations

- The embedded-project transport is intended for small projects and inputs.
  The current package limit is 20 MB before compression. Large datasets should
  be published as a Kaggle Dataset and attached through a future integration.
- `.krunignore` intentionally implements a small, predictable glob subset; it
  is not a complete Git ignore parser.
- Repositories with multiple unrelated nested `pyproject.toml` files must select
  one with `dependencies.project` unless the entrypoint is inside one of them.
- Dependency installation requires internet access unless packages are already
  present in Kaggle's image.
- Accelerator requests can fail because of account access, availability, or
  quota. `krun` does not fall back silently.
- Live logs depend on the current Kaggle CLI streaming endpoint. Persisted logs
  remain available through `krun logs` after execution.
- Kaggle integration is not exercised by the unit test suite.

## Security

The packager excludes `.env*`, `kaggle.json`, private-key extensions, common
SSH key names, Git metadata, virtual environments, caches, and `.krun` state.
Symlinks are never followed or uploaded. Paths supplied through config or CLI
cannot escape the project root.

Always inspect `krun.yaml` and `.krunignore` before submitting sensitive
projects. Credentials remain managed by the official Kaggle CLI and are not
copied into the generated workspace.

## Development

The implementation is deliberately small:

```text
krun/
├── cli.py          # Typer commands and terminal output
├── config.py       # YAML schema and validation
├── project.py      # Root and path discovery
├── packaging.py    # Source collection and remote runner generation
├── kaggle.py       # Safe Kaggle CLI wrapper
├── jobs.py         # Local job metadata
└── errors.py       # User-facing exceptions
```

See [docs/design.md](docs/design.md) for the main engineering decisions.

## Testing

Tests never contact Kaggle:

```bash
python -m pytest -q
```

They cover config validation, project discovery, path containment, packaging,
local imports in the generated runner, explicit inputs, output collection,
command construction, status parsing, and job metadata.

## Docker

The image contains only KRun, its Python dependencies, and the official Kaggle
CLI. Your source stays in the host project and is mounted at `/workspace`; job
metadata and downloaded artifacts therefore persist in the project's `.krun/`
directory. Kaggle still executes the submitted job remotely—Docker does not
emulate Kaggle hardware or bypass its quotas.

Useful checks:

```bash
docker run --rm krun:local --version
docker run --rm krun:local --help
```

## Roadmap

- Create or update Kaggle Datasets for large local inputs.
- Attach existing Kaggle datasets and competition sources through config.
- Add job listing and cleanup commands.
- Add package-size analysis and upload previews.
- Add opt-in integration tests for authenticated CPU jobs.
- Publish signed releases to PyPI.

## Contributing

Bug reports and focused pull requests are welcome. Keep changes small, add tests
for behavior that does not require a live Kaggle account, and never commit
credentials or generated `.krun` job data. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
