"""A spec path that can't be read as text is a clean error (exit 1), not a traceback.

A directory, or a file that isn't UTF-8 text, crashed `load_spec` with an
IsADirectoryError or UnicodeDecodeError traceback in every command that takes a spec,
and `validate a b` stopped at the bad path without checking the rest. These now print
one `✗` line naming the path, the same way a missing spec does, and still exit 1.
"""

import re

import pytest
from typer.testing import CliRunner

from slo_toolkit.cli import app
from slo_toolkit.spec import SpecError, load_spec

from .conftest import ROOT

runner = CliRunner()
# Strip colour codes: CI forces colour.
ANSI = re.compile(r"\x1b\[[0-9;]*m")
SPEC = str(ROOT / "examples/http-api/checkout-api.slo.yaml")


@pytest.fixture
def not_text(tmp_path):
    path = tmp_path / "binary.slo.yaml"
    path.write_bytes(b"\xff\xfe\x00not text")
    return path


def _clean_error(result, path):
    text = ANSI.sub("", result.output)
    assert result.exit_code == 1, text
    assert isinstance(result.exception, SystemExit), repr(result.exception)
    assert "Traceback" not in text
    assert f"✗ {path}: " in text
    return text


def test_load_spec_directory(tmp_path):
    with pytest.raises(SpecError, match="is a directory"):
        load_spec(tmp_path)


def test_load_spec_not_text(not_text):
    with pytest.raises(SpecError, match="not utf-8 text"):
        load_spec(not_text)


@pytest.mark.parametrize(
    "command",
    [["validate"], ["generate", "-o", "out"], ["report", "--data", "x.csv"], ["simulate", "-o", "out/x.csv"]],
)
def test_directory_spec(tmp_path, monkeypatch, command):
    monkeypatch.chdir(tmp_path)
    spec_dir = tmp_path / "specs"
    spec_dir.mkdir()
    result = runner.invoke(app, [command[0], str(spec_dir), *command[1:]])
    _clean_error(result, spec_dir)


def test_validate_not_text(not_text):
    result = runner.invoke(app, ["validate", str(not_text)])
    _clean_error(result, not_text)


def test_validate_keeps_checking_after_unreadable_spec(tmp_path):
    result = runner.invoke(app, ["validate", str(tmp_path), SPEC])
    text = _clean_error(result, tmp_path)
    assert "✓" in text and "checkout-api" in text
