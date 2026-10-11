import pytest

from slo_toolkit.budget import (
    WORKBOOK_POLICY,
    WORKBOOK_TABLE_POLICY,
    allowed_downtime_minutes,
    allowed_downtime_seconds,
    budget_remaining,
    burn_rate,
    burn_threshold,
    error_budget,
    time_to_exhaustion_seconds,
)
from slo_toolkit.durations import humanize, to_duration, to_seconds


def test_error_budget():
    assert error_budget(99.9) == pytest.approx(0.001)


def test_downtime_30d_three_nines():
    # The classic number: 99.9% over 30 days allows 43.2 minutes.
    assert allowed_downtime_minutes(99.9, 30) == pytest.approx(43.2)
    assert allowed_downtime_seconds(99.9, "30d") == pytest.approx(43.2 * 60)


def test_fast_burn_threshold():
    assert burn_threshold(99.9, 14.4) == pytest.approx(0.0144)


@pytest.mark.parametrize("objective", [0, 100, -1, 101])
def test_bad_objective(objective):
    with pytest.raises(ValueError):
        error_budget(objective)


def test_workbook_burn_rates_for_30d():
    # SRE Workbook ch.5: 14.4 / 6 / 3 / 1 for a 30-day window.
    assert [s.burn_rate("30d") for s in WORKBOOK_POLICY] == [14.4, 6.0, 3.0, 1.0]


def test_table_policy_is_three_rows():
    assert [(s.long_window, s.short_window) for s in WORKBOOK_TABLE_POLICY] == [
        ("1h", "5m"),
        ("6h", "30m"),
        ("3d", "6h"),
    ]


def test_burn_rates_scale_with_window():
    # Same share of budget per hour means a lower multiplier over 28 days.
    assert WORKBOOK_POLICY[0].burn_rate("28d") == pytest.approx(13.44)


def test_short_window_is_one_twelfth():
    for step in WORKBOOK_POLICY:
        assert to_seconds(step.long_window) == 12 * to_seconds(step.short_window)


def test_burn_and_remaining():
    assert burn_rate(0.002, 99.9) == pytest.approx(2)
    assert budget_remaining(0.0005, 99.9) == pytest.approx(0.5)
    assert budget_remaining(0.002, 99.9) == pytest.approx(-1)


def test_time_to_exhaustion():
    assert time_to_exhaustion_seconds(99.9, "30d", 1000) == pytest.approx(43.2 * 60)
    assert time_to_exhaustion_seconds(99.9, "30d", 0) is None


@pytest.mark.parametrize(("text", "seconds"), [("5m", 300), ("1h", 3600), ("3d", 259200), ("4w", 2419200)])
def test_durations(text, seconds):
    assert to_seconds(text) == seconds


@pytest.mark.parametrize("bad", ["", "5", "1h30m", "0m", "-1h", "1y"])
def test_bad_durations(bad):
    with pytest.raises(ValueError):
        to_seconds(bad)


def test_to_duration_and_humanize():
    assert to_duration(86400) == "1d"
    assert to_duration(1800) == "30m"
    assert humanize(2592) == "43.2 min"
    assert humanize(30) == "30s"
