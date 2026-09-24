# Contributing to krun

Thanks for helping improve `krun`.

1. Create an isolated Python 3.11+ environment.
2. Install the project with `python -m pip install -e '.[dev]'`.
3. Make a focused change with tests.
4. Run `python -m pytest -q`.
5. Check that no credential, `.krun` state, output, or large data file is staged.

Unit tests must not contact Kaggle. Put authenticated checks behind an explicit
integration-test opt-in and use CPU unless accelerator behavior itself is under
test.

By submitting a contribution, you agree that it may be distributed under the
MIT License.
