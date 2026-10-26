"""Error-budget reports from recorded data (CSV) or a live Prometheus.

CSV input has one row per time bucket per SLO:

    timestamp,slo,good,total
    2026-09-01T00:00:00Z,availability,2998,3000

From CSV we can also *replay* the alert policy over the history ("would this have paged?"),
which is the quickest way to sanity-check an objective before you wire up real alerts.
"""

from __future__ import annotations

import csv
import json
import math
import urllib.parse
import urllib.request
from bisect import bisect_right
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from itertools import accumulate
from pathlib import Path
from typing import Any

from .budget import budget_remaining, burn_rate, time_to_exhaustion_seconds
from .durations import to_seconds
from .rules import alert_windows
from .spec import SLO, Spec


@dataclass
class AlertEpisode:
    severity: str
    start: str
    end: str
    duration_s: int
    trigger: str  # which long/short pair fired first


@dataclass
class SLOReport:
    slo: str
    objective: float
    window: str
    source: str
    coverage_s: int  # how much data the report is based on
    error_ratio: float
    sli: float
    budget_remaining: float
    burn_rates: dict[str, float]
    time_to_exhaustion_s: float | None
    status: str
    episodes: list[AlertEpisode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _status(remaining: float, burn_1h: float, page_burn: float) -> str:
    if remaining < 0:
        return "SLO MISSED"
    if burn_1h >= page_burn or remaining < 0.25:
        return "AT RISK"
    return "OK"


def _parse_ts(value: str) -> int:
    value = value.strip()
    if value.isdigit():
        return int(value)
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d %H:%MZ")


def _parse_row(row: dict[str, str], where: str) -> tuple[int, float, float]:
    """One CSV row as (ts, good, total). Rejects counts that would silently corrupt the report."""
    try:
        ts = _parse_ts(row["timestamp"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{where}: bad timestamp {row['timestamp']!r}") from exc
    counts: dict[str, float] = {}
    for column in ("good", "total"):
        try:
            value = float(row[column])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{where}: {column} {row[column]!r} is not a number") from exc
        # NaN/Inf and negative counts would flow into the window sums and come out as status OK
        # with an SLI of NaN or far above 100%.
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{where}: {column} must be a finite count >= 0, got {row[column]!r}")
        counts[column] = value
    if counts["good"] > counts["total"]:
        raise ValueError(f"{where}: good ({row['good']}) is greater than total ({row['total']})")
    return ts, counts["good"], counts["total"]


def load_csv(path: str | Path) -> dict[str, list[tuple[int, float, float]]]:
    series: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        missing = {"timestamp", "slo", "good", "total"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing CSV columns: {', '.join(sorted(missing))}")
        for row in reader:
            where = f"{path}, line {reader.line_num} (SLO {row['slo']!r})"
            series[row["slo"]].append(_parse_row(row, where))
    for rows in series.values():
        rows.sort()
    return series


class _Window:
    """Prefix sums so any trailing-window error ratio is O(log n)."""

    def __init__(self, rows: list[tuple[int, float, float]]):
        self.ts = [r[0] for r in rows]
        self.bad = [0.0, *accumulate(r[2] - r[1] for r in rows)]
        self.total = [0.0, *accumulate(r[2] for r in rows)]

    def ratio(self, i: int, seconds: int) -> float:
        """Error ratio over buckets with ts in (ts[i] - seconds, ts[i]]."""
        lo = bisect_right(self.ts, self.ts[i] - seconds)
        total = self.total[i + 1] - self.total[lo]
        return (self.bad[i + 1] - self.bad[lo]) / total if total else 0.0


def _replay(slo: SLO, rows: list[tuple[int, float, float]]) -> list[AlertEpisode]:
    win = _Window(rows)
    step = (rows[1][0] - rows[0][0]) if len(rows) > 1 else 60
    episodes: list[AlertEpisode] = []
    for severity in ("page", "ticket"):
        steps = [s for s in slo.alerting.policy if s.severity == severity]
        firing_since: int | None = None
        trigger = ""
        for i, (ts, _, _) in enumerate(rows):
            hit = ""
            for s in steps:
                threshold = s.burn_rate(slo.window) * slo.budget
                if (
                    win.ratio(i, to_seconds(s.long_window)) > threshold
                    and win.ratio(i, to_seconds(s.short_window)) > threshold
                ):
                    hit = f"{s.long_window}/{s.short_window} @ {s.burn_rate(slo.window):g}x"
                    break
            if hit and firing_since is None:
                firing_since, trigger = ts, hit
            elif not hit and firing_since is not None:
                episodes.append(AlertEpisode(severity, _iso(firing_since), _iso(ts), ts - firing_since, trigger))
                firing_since = None
        if firing_since is not None:
            end = rows[-1][0] + step
            episodes.append(AlertEpisode(severity, _iso(firing_since), "still firing", end - firing_since, trigger))
    episodes.sort(key=lambda e: e.start)
    return episodes


def report_from_rows(slo: SLO, rows: list[tuple[int, float, float]], source: str) -> SLOReport:
    if not rows:
        raise ValueError(f"no data for SLO {slo.name!r}")
    win = _Window(rows)
    last = len(rows) - 1
    step = (rows[1][0] - rows[0][0]) if len(rows) > 1 else 60
    period = to_seconds(slo.window)
    coverage = min(period, rows[-1][0] - rows[0][0] + step)
    error_ratio = win.ratio(last, period)
    rates = {w: round(burn_rate(win.ratio(last, to_seconds(w)), slo.objective), 3) for w in alert_windows(slo)}
    return _finish(slo, source, coverage, error_ratio, rates, _replay(slo, rows))


def _finish(
    slo: SLO, source: str, coverage: int, error_ratio: float, rates: dict[str, float], episodes: list[AlertEpisode]
) -> SLOReport:
    remaining = budget_remaining(error_ratio, slo.objective)
    page_burn = max(s.burn_rate(slo.window) for s in slo.alerting.policy if s.severity == "page")
    current = rates.get("1h", 0.0)
    tte = None
    if remaining > 0 and current > 0:
        full = time_to_exhaustion_seconds(slo.objective, slo.window, current)
        tte = full * remaining if full is not None else None
    return SLOReport(
        slo=slo.name,
        objective=slo.objective,
        window=slo.window,
        source=source,
        coverage_s=coverage,
        error_ratio=error_ratio,
        sli=1 - error_ratio,
        budget_remaining=remaining,
        burn_rates=rates,
        time_to_exhaustion_s=tte,
        status=_status(remaining, current, page_burn),
        episodes=episodes,
    )


def report_from_csv(spec: Spec, path: str | Path) -> list[SLOReport]:
    data = load_csv(path)
    out = []
    for slo in spec.slos:
        if slo.name not in data:
            raise ValueError(f"{path}: no rows for SLO {slo.name!r} (found: {', '.join(sorted(data))})")
        out.append(report_from_rows(slo, data[slo.name], f"csv:{Path(path).name}"))
    return out


def _prom_query(base_url: str, query: str, timeout: float = 15.0) -> float | None:
    url = base_url.rstrip("/") + "/api/v1/query?" + urllib.parse.urlencode({"query": query})
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - user-supplied Prometheus URL
        payload = json.load(resp)
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {payload.get('error', payload)}")
    result = payload["data"]["result"]
    if not result:
        return None
    if len(result) > 1:
        raise RuntimeError(f"query returned {len(result)} series; SLI queries must aggregate to one: {query}")
    value = float(result[0]["value"][1])
    return None if value != value else value  # NaN -> no traffic


def report_from_prometheus(spec: Spec, base_url: str) -> list[SLOReport]:
    """Query the raw SLI expressions directly, so this works before the rules are deployed.

    No history replay here; use the generated alert rules for that.
    """
    out = []
    for slo in spec.slos:
        error_ratio = _prom_query(base_url, slo.sli.error_ratio_expr(slo.window)) or 0.0
        rates = {}
        for w in alert_windows(slo):
            ratio = _prom_query(base_url, slo.sli.error_ratio_expr(w)) or 0.0
            rates[w] = round(burn_rate(ratio, slo.objective), 3)
        out.append(_finish(slo, f"prometheus:{base_url}", to_seconds(slo.window), error_ratio, rates, []))
    return out
