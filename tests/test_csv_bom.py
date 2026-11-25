"""A CSV saved with a UTF-8 byte order mark must read the same as one without.

Excel's "CSV UTF-8" and Windows PowerShell's Export-Csv write a BOM before the header.
load_csv opened the file without an encoding, so the BOM stuck to the first column name
("\\ufefftimestamp") and `report --data` failed with "missing CSV columns: timestamp"
on a header that has that column.
"""

from typer.testing import CliRunner

from slo_toolkit.cli import app
from slo_toolkit.report import load_csv

from .conftest import ROOT

SPEC = str(ROOT / "examples/http-api/checkout-api.slo.yaml")
CSV = "timestamp,slo,good,total\n" + "".join(
    f"2026-09-01T00:{m:02d}:00Z,{slo},999,1000\n" for slo in ("availability", "latency") for m in range(60)
)


def test_load_csv_ignores_utf8_bom(tmp_path):
    plain, bom = tmp_path / "plain.csv", tmp_path / "bom.csv"
    plain.write_bytes(CSV.encode())
    bom.write_bytes(b"\xef\xbb\xbf" + CSV.encode())
    assert load_csv(bom) == load_csv(plain)


def test_report_reads_csv_with_bom_like_without(tmp_path):
    plain, bom = tmp_path / "plain.csv", tmp_path / "bom.csv"
    plain.write_bytes(CSV.encode())
    bom.write_bytes(b"\xef\xbb\xbf" + CSV.encode())
    runner = CliRunner()
    want = runner.invoke(app, ["report", SPEC, "--data", str(plain), "--format", "json"])
    got = runner.invoke(app, ["report", SPEC, "--data", str(bom), "--format", "json"])
    assert want.exit_code == 0, want.output
    assert got.exit_code == want.exit_code, got.output
    assert "missing CSV columns" not in got.output
    assert got.stdout.replace("bom.csv", "plain.csv") == want.stdout


def test_bom_csv_still_needs_every_column(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_bytes(b"\xef\xbb\xbfwhen,slo,good,total\n2026-09-01T00:00:00Z,availability,1,1\n")
    result = CliRunner().invoke(app, ["report", SPEC, "--data", str(path)])
    assert result.exit_code == 1
    assert "missing CSV columns: timestamp" in " ".join(result.output.split())
