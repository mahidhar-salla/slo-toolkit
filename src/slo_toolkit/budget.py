"""Error-budget and burn-rate math. Pure functions, no I/O.

The alert policy follows the Google SRE Workbook, chapter 5 ("Alerting on SLOs"),
approach 6: multiwindow, multi-burn-rate alerts. A policy step is expressed as
"page/ticket when X% of the budget is spent within the long window", and the burn
rate is derived from that, so a 28d or 7d SLO window gets correctly scaled thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass

from .durations import to_seconds


@dataclass(frozen=True)
class PolicyStep:
    severity: str  # "page" or "ticket"
    long_window: str
    short_window: str
    budget_fraction: float  # share of the whole-window budget spent when this fires

    def burn_rate(self, slo_window: str) -> float:
        """Burn rate that spends `budget_fraction` of the budget in `long_window`."""
        return round(self.budget_fraction * to_seconds(slo_window) / to_seconds(self.long_window), 6)


# Workbook Table 5-8 (2% / 1h, 5% / 6h, 10% / 3d) plus the 24h/2h ticket step from the
# workbook's own example configuration for approach 6. For a 30d window these give burn
# rates of 14.4, 6, 3 and 1.
WORKBOOK_POLICY: tuple[PolicyStep, ...] = (
    PolicyStep("page", "1h", "5m", 0.02),
    PolicyStep("page", "6h", "30m", 0.05),
    PolicyStep("ticket", "1d", "2h", 0.10),
    PolicyStep("ticket", "3d", "6h", 0.10),
)

# Strictly the three rows of Table 5-8.
WORKBOOK_TABLE_POLICY: tuple[PolicyStep, ...] = (
    WORKBOOK_POLICY[0],
    WORKBOOK_POLICY[1],
    WORKBOOK_POLICY[3],
)

POLICIES = {"workbook": WORKBOOK_POLICY, "workbook-table": WORKBOOK_TABLE_POLICY}


def error_budget(objective_pct: float) -> float:
    """Allowed error ratio, e.g. 99.9 -> 0.001."""
    if not 0 < objective_pct < 100:
        raise ValueError("objective must be between 0 and 100 (exclusive)")
    budget = round(1 - objective_pct / 100, 10)
    if budget <= 0:
        # Rounding to 10 places turns objectives within 5e-9 % of 100 into a zero budget,
        # which would divide by zero in rules and reports and alert on any error at all.
        raise ValueError(
            f"objective {objective_pct}% is too close to 100%: the error budget rounds to 0 "
            "at 10 decimal places (99.99999999 still works)"
        )
    return budget


def allowed_downtime_seconds(objective_pct: float, window: str) -> float:
    """Seconds of full outage the budget allows over the SLO window."""
    return error_budget(objective_pct) * to_seconds(window)


def allowed_downtime_minutes(objective_pct: float, window_days: float) -> float:
    """Minutes of full outage over `window_days` (kept for the simple calc path)."""
    return error_budget(objective_pct) * window_days * 24 * 60


def burn_threshold(objective_pct: float, burn_rate: float) -> float:
    """Error-ratio threshold for an alert at the given burn rate."""
    return burn_rate * error_budget(objective_pct)


def burn_rate(error_ratio: float, objective_pct: float) -> float:
    """How fast the budget is being spent: 1.0 means exactly on budget for the window."""
    return error_ratio / error_budget(objective_pct)


def budget_remaining(error_ratio_over_window: float, objective_pct: float) -> float:
    """Share of the error budget left (can go negative when the SLO is blown)."""
    return 1 - burn_rate(error_ratio_over_window, objective_pct)


def time_to_exhaustion_seconds(objective_pct: float, window: str, rate: float) -> float | None:
    """At a constant burn rate, how long until a full budget is gone. None when not burning."""
    if rate <= 0:
        return None
    return to_seconds(window) / rate
