"""`validate --promtool` must fail closed when promtool is missing.

Asking for promtool and not getting it is a failed check, not a pass. Without the flag,
validation never needs promtool and the exit code is unchanged.
"""

import stat

from typer.testing import CliRunner

from slo_toolkit import cli
from slo_toolkit.cli import app

from .conftest import ROOT

runner = CliRunner()
SPEC = str(ROOT / "examples/http-api/checkout-api.slo.yaml")


def _no_promtool(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name, *a, **k: None)


def test_requested_promtool_missing_fails(monkeypatch):
    _no_promtool(monkeypatch)
    result = runner.invoke(app, ["validate", "--promtool", SPEC])
    assert result.exit_code == 1, result.output
    assert "promtool not found" in result.output
    assert "skipping" not in result.output


def test_requested_promtool_missing_fails_for_every_spec(monkeypatch):
    _no_promtool(monkeypatch)
    result = runner.invoke(app, ["validate", "--promtool", SPEC, SPEC])
    assert result.exit_code == 1, result.output


def test_without_flag_promtool_is_not_needed(monkeypatch):
    _no_promtool(monkeypatch)
    result = runner.invoke(app, ["validate", SPEC])
    assert result.exit_code == 0, result.output
    assert "promtool not found" not in result.output


def _fake_promtool(tmp_path, monkeypatch, exit_code: int):
    fake = tmp_path / "promtool"
    message = "SUCCESS: 30 rules found" if exit_code == 0 else "FAILED: bad rule"
    fake.write_text(f"#!/bin/sh\necho '{message}'\nexit {exit_code}\n")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(cli.shutil, "which", lambda name, *a, **k: str(fake))


def test_requested_promtool_present_and_passing(tmp_path, monkeypatch):
    _fake_promtool(tmp_path, monkeypatch, 0)
    result = runner.invoke(app, ["validate", "--promtool", SPEC])
    assert result.exit_code == 0, result.output
    assert "SUCCESS" in result.output


def test_requested_promtool_present_and_failing(tmp_path, monkeypatch):
    _fake_promtool(tmp_path, monkeypatch, 1)
    result = runner.invoke(app, ["validate", "--promtool", SPEC])
    assert result.exit_code == 1, result.output
