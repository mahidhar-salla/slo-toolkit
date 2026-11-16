"""An unusable `-o` path is a clean error (exit 1), not a Python traceback.

`generate -o <existing file>` and `simulate -o <file>/x.csv` crashed in `mkdir` with a
FileExistsError traceback, and `simulate -o <directory>` with an IsADirectoryError
traceback. They now print one line naming the path and exit 1, the same way `report`
handles a CSV it cannot read.
"""

import re

from typer.testing import CliRunner

from slo_toolkit.cli import app

from .conftest import ROOT

runner = CliRunner()
# Strip colour codes: CI forces colour.
ANSI = re.compile(r"\x1b\[[0-9;]*m")
SPEC = str(ROOT / "examples/http-api/checkout-api.slo.yaml")


def _clean_error(result, path):
    text = ANSI.sub("", result.output)
    assert result.exit_code == 1, text
    assert isinstance(result.exception, SystemExit), repr(result.exception)
    assert "Traceback" not in text
    assert "✗" in text and str(path) in text


def test_generate_onto_existing_file(tmp_path):
    target = tmp_path / "afile"
    target.write_text("keep me\n")
    result = runner.invoke(app, ["generate", SPEC, "-o", str(target)])
    _clean_error(result, target)
    assert target.read_text() == "keep me\n"


def test_simulate_under_existing_file(tmp_path):
    parent = tmp_path / "afile"
    parent.write_text("keep me\n")
    result = runner.invoke(app, ["simulate", SPEC, "-o", str(parent / "x.csv"), "--days", "1"])
    _clean_error(result, parent)
    assert parent.read_text() == "keep me\n"


def test_simulate_onto_directory(tmp_path):
    result = runner.invoke(app, ["simulate", SPEC, "-o", str(tmp_path), "--days", "1"])
    _clean_error(result, tmp_path)


def test_generate_and_simulate_into_new_dirs_still_work(tmp_path):
    out = tmp_path / "a" / "b"
    assert runner.invoke(app, ["generate", SPEC, "-o", str(out)]).exit_code == 0
    assert (out / "checkout-api.rules.yaml").exists()
    csv = tmp_path / "c" / "samples.csv"
    assert runner.invoke(app, ["simulate", SPEC, "-o", str(csv), "--days", "1"]).exit_code == 0
    assert len(csv.read_text().splitlines()) == 1 + 2 * 1440
