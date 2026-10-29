"""`calc` reports a bad objective or window as a usage error, not a traceback.

`calc` passed --objective and --window straight to the budget math, so an objective the
spec would reject (100, 0, or one so close to 100 that the budget rounds to 0, which
259ab1a turned into a ValueError) or a malformed window crashed with a Python traceback
and exit 1. It now prints the same readable message and exits 2, like an unknown --profile.
"""

import pytest
from typer.testing import CliRunner

from slo_toolkit.cli import app

runner = CliRunner()


@pytest.mark.parametrize(
    ("objective", "message"),
    [
        ("100", "between 0 and 100"),
        ("0", "between 0 and 100"),
        ("150", "between 0 and 100"),
        ("99.99999999999", "too close to 100%"),
    ],
)
def test_calc_rejects_objective_without_traceback(objective, message):
    result = runner.invoke(app, ["calc", "--objective", objective])
    assert result.exit_code == 2
    assert isinstance(result.exception, SystemExit)
    assert message in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize("window", ["30x", "0d"])
def test_calc_rejects_window_without_traceback(window):
    result = runner.invoke(app, ["calc", "--window", window])
    assert result.exit_code == 2
    assert isinstance(result.exception, SystemExit)
    assert "duration" in result.output


@pytest.mark.parametrize("objective", ["99.9999", "99.99999999"])
def test_calc_still_accepts_objectives_near_100(objective):
    result = runner.invoke(app, ["calc", "--objective", objective])
    assert result.exit_code == 0, result.output
    assert "error budget" in result.output
