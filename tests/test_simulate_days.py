"""`simulate --days` below 1 is a usage error, not an empty CSV reported as a success.

`simulate --days 0` or `--days -1` wrote a header-only CSV, printed
"✓ ... 0 synthetic rows over -1d" and exited 0, so the failure only showed up later as
`report` saying the file has no rows. It now exits 2 like other bad command-line input,
and writes nothing.
"""

import pytest
from typer.testing import CliRunner

from slo_toolkit.cli import app

from .conftest import ROOT

runner = CliRunner()
SPEC = str(ROOT / "examples/http-api/checkout-api.slo.yaml")


@pytest.mark.parametrize("days", ["0", "-1"])
def test_simulate_rejects_days_below_one(tmp_path, days):
    out = tmp_path / "samples.csv"
    result = runner.invoke(app, ["simulate", SPEC, "-o", str(out), f"--days={days}"])
    assert result.exit_code == 2, result.output
    assert "--days" in result.output
    assert not out.exists()


def test_simulate_one_day_still_works(tmp_path):
    out = tmp_path / "samples.csv"
    result = runner.invoke(app, ["simulate", SPEC, "-o", str(out), "--days", "1"])
    assert result.exit_code == 0, result.output
    assert len(out.read_text().splitlines()) == 1 + 2 * 1440
