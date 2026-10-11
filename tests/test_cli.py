import json

from typer.testing import CliRunner

from slo_toolkit.cli import app

from .conftest import ROOT

runner = CliRunner()
SPEC = str(ROOT / "examples/http-api/checkout-api.slo.yaml")


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0 and "0.1.0" in result.output


def test_calc():
    result = runner.invoke(app, ["calc", "--objective", "99.9", "--window", "30d"])
    assert result.exit_code == 0
    assert "43.2 min" in result.output and "14.4x" in result.output


def test_calc_bad_profile():
    assert runner.invoke(app, ["calc", "--profile", "nope"]).exit_code == 2


def test_validate_ok_and_bad(tmp_path):
    assert runner.invoke(app, ["validate", SPEC]).exit_code == 0
    bad = tmp_path / "bad.slo.yaml"
    bad.write_text("apiVersion: slo-toolkit/v1\nservice: Bad Name\nslos: []\n")
    result = runner.invoke(app, ["validate", str(bad)])
    assert result.exit_code == 1


def test_generate_writes_files(tmp_path):
    result = runner.invoke(app, ["generate", SPEC, "-o", str(tmp_path), "--helm-values"])
    assert result.exit_code == 0, result.output
    assert {p.name for p in tmp_path.iterdir()} == {
        "checkout-api.rules.yaml",
        "checkout-api.dashboard.json",
        "checkout-api.values.yaml",
    }


def test_simulate_then_report_json_and_markdown(tmp_path):
    csv_path = tmp_path / "s.csv"
    assert runner.invoke(app, ["simulate", SPEC, "-o", str(csv_path), "--days", "30"]).exit_code == 0
    result = runner.invoke(app, ["report", SPEC, "--data", str(csv_path), "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert [s["slo"] for s in payload["slos"]] == ["availability", "latency"]
    md = runner.invoke(app, ["report", SPEC, "--data", str(csv_path), "--format", "markdown"])
    assert "| availability |" in md.output and "replayed alerts" in md.output


def test_report_needs_one_source():
    assert runner.invoke(app, ["report", SPEC]).exit_code == 2


def test_report_slo_filter(tmp_path):
    csv_path = tmp_path / "s.csv"
    runner.invoke(app, ["simulate", SPEC, "-o", str(csv_path), "--days", "3"])
    result = runner.invoke(app, ["report", SPEC, "--data", str(csv_path), "--slo", "latency", "-f", "json"])
    assert [s["slo"] for s in json.loads(result.output)["slos"]] == ["latency"]
    assert runner.invoke(app, ["report", SPEC, "--data", str(csv_path), "--slo", "nope"]).exit_code == 2
