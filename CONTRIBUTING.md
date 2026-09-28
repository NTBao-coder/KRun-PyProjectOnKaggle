# Contributing to krun

Thanks for helping improve `krun`.

1. Create an isolated Python 3.11+ environment.
2. Install the project with `python -m pip install -e '.[dev]'`.
3. Make a focused change with tests.
4. Run `python -m pytest -q`.
   Notebook tests start a local Jupyter kernel and require loopback sockets.
   Validate launchers with `bash -n bin/krun scripts/install.sh` and the Docker
   demo dry-runs. Keep Windows/macOS support claims tied to actual CI results.
5. Check that no credential, `.krun` state, output, or large data file is staged.

Unit tests must not contact Kaggle. Put authenticated checks behind an explicit
integration-test opt-in and use CPU unless accelerator behavior itself is under
test.

By submitting a contribution, you agree that it may be distributed under the
MIT License.

## Package checks

The native CLI is the primary distribution. Keep runtime dependencies in
`pyproject.toml`; Docker-only pins remain in `requirements-docker.txt`.
Demo source files live in `krun/demo_templates/` and are included as package
data. Do not add generated demo outputs, job state, or credentials there.

Build an sdist and a wheel from that sdist, then test a fresh tool installation:

```bash
uv build
UV_TOOL_DIR=/tmp/krun-tools UV_TOOL_BIN_DIR=/tmp/krun-bin \
  uv tool install --from dist/krun_cli-*-py3-none-any.whl krun-cli
/tmp/krun-tools/krun-cli/bin/python scripts/check_installed.py
```

Use fresh tool directories for each verification. The smoke test runs outside
the checkout, verifies packaged resources and Kaggle executable discovery with
an empty PATH, previews all demos, and executes the two standard-library demos
locally. It never authenticates or submits a Kaggle job. On Windows, use the
tool environment's `Scripts/python.exe` instead of `bin/python`.
CI runs this check on Linux, Windows, and macOS with Python 3.11 and 3.12.

## Publishing a Python release

1. Confirm ownership/availability of `krun-cli` on PyPI. Do not assume this
   repository owns an existing package with the same name.
2. Keep the version in `pyproject.toml` and `krun/__init__.py` in sync and use
   a new version for each published release.
3. Run the full tests, build, and installed-package checks above. Inspect the
   archive contents; no credentials or generated workload outputs may ship.
4. Publish only with explicit release authorization: `uv publish dist/*`.
   Configure PyPI authentication securely outside the repository.
5. Verify installation from PyPI in a fresh tool environment before presenting
   `uv tool install krun-cli` as an available public installation route.

The `Publish to PyPI` workflow (`publish-pypi.yml`) is started manually on `main`
with an exact version. It checks version consistency, runs tests, verifies an
installed wheel, publishes those artifacts, and installs the published version
from PyPI for a final smoke test. It supports either a GitHub Actions secret
named `PYPI_API_TOKEN` or PyPI Trusted Publishing:

- Project: `krun-cli`
- Repository owner: `nhminh107`
- Repository: `KRun-PyProjectOnKaggle`
- Workflow filename: `publish-pypi.yml`
- Environment: `pypi`

For the first release, register a pending publisher in PyPI's account settings,
or use a token with permission to create the project. Never commit a token or
paste it into workflow source. See the
[PyPI pending-publisher documentation](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

The separate GitHub-release workflow retains wheel/sdist artifacts and publishes
the optional Docker image. Git and local-path installs work before a PyPI
release; a Git install only includes pushed changes.
