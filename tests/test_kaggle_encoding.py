"""Exercise real subprocess I/O under a legacy Windows-style encoding."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from krun.errors import CommandError
from krun.kaggle import KaggleClient


@pytest.fixture
def unicode_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> KaggleClient:
    script = tmp_path / "fake_kaggle.py"
    script.write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "assert os.environ['KAGGLE_API_TOKEN'] == 'unused-test-token'\n"
        "args = sys.argv[1:]\n"
        "message = 'Tự học: điểm dự đoán của học sinh'\n"
        "if args[:2] == ['kernels', 'logs']:\n"
        "    if '--follow' in args:\n"
        "        print(message)\n"
        "    else:\n"
        "        print(json.dumps([{'data': message + '\\n'}], ensure_ascii=False))\n"
        "elif args[:2] == ['kernels', 'output']:\n"
        "    target = Path(args[args.index('--path') + 1]) / 'kết quả.txt'\n"
        "    target.write_text(message)\n"
        "    print(str(target))\n"
        "elif args[:2] == ['auth', 'login']:\n"
        "    print(message)\n"
        "else:\n"
        "    print(message, file=sys.stderr)\n"
        "    sys.exit(2)\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHONIOENCODING", "cp1252")
    monkeypatch.setenv("PYTHONUTF8", "0")
    monkeypatch.setenv("KAGGLE_API_TOKEN", "unused-test-token")
    original_run = subprocess.run

    def run_fake_cli(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        # Replace only the external service. Keep actual pipes, decoding and env.
        return original_run([sys.executable, str(script), *command[1:]], **kwargs)

    monkeypatch.setattr("krun.kaggle.subprocess.run", run_fake_cli)
    return KaggleClient(executable="fake-kaggle")


def test_logs_preserve_vietnamese_with_legacy_host_encoding(unicode_client: KaggleClient) -> None:
    assert unicode_client.logs("owner/job") == "Tự học: điểm dự đoán của học sinh\n"
    assert os.environ["PYTHONIOENCODING"] == "cp1252"
    assert os.environ["PYTHONUTF8"] == "0"


def test_download_preserves_unicode_paths_and_file_contents(
    unicode_client: KaggleClient, tmp_path: Path,
) -> None:
    destination = tmp_path / "Kết quả học sinh"
    output = unicode_client.download_output("owner/job", destination)
    target = destination / "kết quả.txt"
    assert output == str(target)
    assert target.read_text(encoding="utf-8") == "Tự học: điểm dự đoán của học sinh"


def test_cli_error_preserves_unicode_stderr(unicode_client: KaggleClient) -> None:
    with pytest.raises(CommandError, match="Tự học: điểm dự đoán của học sinh"):
        unicode_client._run(["fail"])


def test_login_and_streaming_preserve_unicode(
    unicode_client: KaggleClient, capfd: pytest.CaptureFixture[str],
) -> None:
    unicode_client.login(force=True)
    unicode_client.follow_logs("owner/job")
    captured = capfd.readouterr()
    assert captured.out.count("Tự học: điểm dự đoán của học sinh") == 2
