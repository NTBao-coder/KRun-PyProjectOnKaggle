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

## Job identity

Each submission receives a timestamp-plus-random local ID and a unique Kaggle
kernel slug. Local metadata is written atomically. Keeping each generated
workspace makes failed submissions inspectable without mixing it with source.

## Safety choices

Project-relative paths are resolved before packaging and cannot escape the
root. Symlinks are skipped to avoid accidentally following a path outside the
project. Known credential and private-key filenames are ignored independently
of user ignore rules. The credential material itself remains owned by the
Kaggle CLI.
