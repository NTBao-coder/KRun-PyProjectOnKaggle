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
