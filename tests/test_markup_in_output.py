"""Square brackets in paths, options or data are printed as typed, not read as Rich markup.

The CLI prints through Rich, which reads `[...]` as style markup. User text went into
those strings unescaped, so a closing tag such as `[/x]` in a spec path, an `-o` path, a
CSV value or an option crashed with a MarkupError traceback (exit 1), and a tag-like part
such as `[prod]` in a path was silently dropped from the message.
"""

import re
import shutil

import pytest
from typer.testing import CliRunner

from slo_toolkit.cli import app

from .conftest import ROOT

runner = CliRunner()
# Strip colour codes: CI forces colour.
ANSI = re.compile(r"\x1b\[[0-9;]*m")
SPEC = ROOT / "examples/http-api/checkout-api.slo.yaml"


def _run(args, exit_code):
    result = runner.invoke(app, [str(a) for a in args])
    text = ANSI.sub("", result.output)
    assert result.exit_code == exit_code, text
    assert "Traceback" not in text and "MarkupError" not in text, text
    if exit_code:
        assert isinstance(result.exception, SystemExit), repr(result.exception)
    return text


def _has(needle, text):
    """Rich wraps long paths anywhere, so compare with all whitespace removed."""
    return "".join(str(needle).split()) in "".join(text.split())


@pytest.fixture
def bracket_dir(tmp_path):
    path = tmp_path / "[prod]" / "[/x]"
    path.mkdir(parents=True)
    return path


def test_validate_missing_spec_keeps_brackets(bracket_dir):
    missing = bracket_dir / "api.slo.yaml"
    text = _run(["validate", missing], 1)
    assert _has(f"✗ {missing}: file not found", text), text


def test_validate_ok_spec_keeps_brackets(bracket_dir):
    spec = bracket_dir / SPEC.name
    shutil.copy(SPEC, spec)
    text = _run(["validate", spec], 0)
    assert _has(f"✓ {spec}: checkout-api", text), text


def test_invalid_yaml_in_bracket_path(bracket_dir):
    spec = bracket_dir / "bad.slo.yaml"
    spec.write_text("apiVersion: slo-toolkit/v1\nslos: [\n")
    text = _run(["generate", spec, "-o", bracket_dir / "out"], 1)
    assert _has(f"✗ {spec}: invalid YAML", text), text


def test_generate_out_dir_with_brackets(bracket_dir):
    out = bracket_dir / "out"
    text = _run(["generate", SPEC, "-o", out, "--helm-values"], 0)
    for name in ("checkout-api.rules.yaml", "checkout-api.dashboard.json", "checkout-api.values.yaml"):
        assert _has(f"✓ {out / name}", text), text
        assert (out / name).is_file()


def test_simulate_and_report_with_bracket_csv(bracket_dir):
    csv = bracket_dir / "samples[prod].csv"
    text = _run(["simulate", SPEC, "-o", csv, "--days", "2"], 0)
    assert _has(f"✓ {csv}: ", text), text
    result = runner.invoke(app, ["report", str(SPEC), "--data", str(csv)])
    text = ANSI.sub("", result.output)
    assert result.exit_code in (0, 3), text
    assert "MarkupError" not in text
    assert _has("csv:samples[prod].csv", text), text


def test_report_missing_csv_keeps_brackets(bracket_dir):
    csv = bracket_dir / "nope.csv"
    text = _run(["report", SPEC, "--data", csv], 1)
    assert _has(f"{csv}", text), text


def test_report_bad_csv_value_keeps_brackets(tmp_path):
    csv = tmp_path / "c.csv"
    csv.write_text("timestamp,slo,good,total\n2026-01-01T00:00:00Z,availability,[/x],1\n")
    text = _run(["report", SPEC, "--data", csv], 1)
    assert _has("good '[/x]' is not a number", text), text


def test_report_unknown_slo_keeps_brackets():
    text = _run(["report", SPEC, "--slo", "[/x]", "--data", "x.csv"], 2)
    assert _has("unknown SLO(s): [/x]", text), text


def test_calc_bad_window_keeps_brackets():
    text = _run(["calc", "--window", "[/x]"], 2)
    assert _has("invalid duration '[/x]'", text), text


def test_calc_unknown_profile_keeps_brackets():
    text = _run(["calc", "--profile", "[/x]"], 2)
    assert _has("unknown profile '[/x]'", text), text
