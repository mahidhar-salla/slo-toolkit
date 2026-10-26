"""CSV report input must hold usable counts: one bad row must not turn into a healthy report.

Before this check, a single row with NaN, Inf, a negative count or good > total went
straight into the prefix sums. The report then said status OK with an SLI of NaN or
several hundred percent and exited 0.
"""

import pytest
from typer.testing import CliRunner

from slo_toolkit.cli import app
from slo_toolkit.report import load_csv

from .conftest import ROOT

SPEC = str(ROOT / "examples/http-api/checkout-api.slo.yaml")
GOOD_ROWS = "".join(f"2026-09-01T00:{m:02d}:00Z,availability,999,1000\n" for m in range(60))
HEADER = "timestamp,slo,good,total\n"
BAD_LINE = 62  # header + 60 good rows, then the bad one


def _csv(tmp_path, last_row: str):
    path = tmp_path / "samples.csv"
    path.write_text(HEADER + GOOD_ROWS + last_row + "\n")
    return path


INVALID = [
    pytest.param("nan,1000", "good", id="good-nan"),
    pytest.param("1000,nan", "total", id="total-nan"),
    pytest.param("inf,inf", "good", id="inf"),
    pytest.param("10,-inf", "total", id="total-minus-inf"),
    pytest.param("-1,1000", "good", id="good-negative"),
    pytest.param("0,-50000", "total", id="total-negative"),
    pytest.param("90000,1000", "good", id="good-above-total"),
    pytest.param("abc,1000", "good", id="good-not-a-number"),
]


@pytest.mark.parametrize(("counts", "column"), INVALID)
def test_load_csv_rejects_unusable_counts_with_location(tmp_path, counts, column):
    path = _csv(tmp_path, f"2026-09-01T01:00:00Z,availability,{counts}")
    with pytest.raises(ValueError) as exc:
        load_csv(path)
    message = str(exc.value)
    assert f"line {BAD_LINE}" in message
    assert "availability" in message
    assert column in message


@pytest.mark.parametrize(("counts", "column"), INVALID)
def test_report_cli_fails_instead_of_reporting_ok(tmp_path, counts, column):
    path = _csv(tmp_path, f"2026-09-01T01:00:00Z,availability,{counts}")
    result = CliRunner().invoke(app, ["report", SPEC, "--slo", "availability", "--data", str(path), "-f", "json"])
    assert result.exit_code == 1, result.output
    output = " ".join(result.output.split())  # rich may wrap the long tmp path
    assert '"status"' not in output
    assert f"line {BAD_LINE}" in output


def test_load_csv_rejects_bad_timestamp_with_location(tmp_path):
    path = _csv(tmp_path, "yesterday,availability,999,1000")
    with pytest.raises(ValueError, match=f"line {BAD_LINE}.*timestamp"):
        load_csv(path)


@pytest.mark.parametrize(
    "counts",
    [
        pytest.param("0,0", id="zero-traffic"),
        pytest.param("1000,1000", id="good-equals-total"),
        pytest.param("2.5,3.75", id="fractional"),  # e.g. counts exported from rate() * step
        pytest.param("999 , 1000", id="spaces"),
    ],
)
def test_load_csv_keeps_valid_edge_rows(tmp_path, counts):
    path = _csv(tmp_path, f"2026-09-01T01:00:00Z,availability,{counts}")
    rows = load_csv(path)["availability"]
    assert len(rows) == 61
    good, total = (float(v) for v in counts.split(","))
    assert rows[-1][1:] == (good, total)
