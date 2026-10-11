"""Synthetic traffic for demos and tests. Nothing here comes from a real system.

The default scenario is built to show the alert policy doing its job:
  * a steady baseline well inside budget,
  * a short sharp blip that should NOT page,
  * a 40-minute partial outage that SHOULD page,
  * a two-day slow burn that should open a ticket, not wake anyone up.
Incident sizes are expressed as burn-rate multiples so they scale with each SLO's budget.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .spec import Spec

DEFAULT_END = datetime(2026, 10, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Incident:
    label: str
    start_day: float  # days after the start of the series
    minutes: float
    burn: float  # error ratio as a multiple of the budget


DEFAULT_SCENARIO = (
    Incident("short blip (should not page)", 6.40, 4, 100),
    Incident("partial outage (should page)", 13.60, 40, 40),
    Incident("slow burn (should ticket)", 21.00, 2 * 24 * 60, 2.5),
)


def simulate(
    spec: Spec,
    out: str | Path,
    days: int = 30,
    step_s: int = 60,
    rps: float = 50.0,
    baseline_burn: float = 0.3,
    seed: int = 7,
    end: datetime = DEFAULT_END,
    scenario: tuple[Incident, ...] = DEFAULT_SCENARIO,
) -> int:
    rng = random.Random(seed)  # noqa: S311 - synthetic demo data, not security-sensitive
    start = int(end.timestamp()) - days * 86400
    buckets = days * 86400 // step_s
    per_bucket = rps * step_s
    rows = 0
    with open(out, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["timestamp", "slo", "good", "total"])
        for slo in spec.slos:
            for i in range(buckets):
                ts = start + i * step_s
                day = i * step_s / 86400
                burn = baseline_burn
                for inc in scenario:
                    if inc.start_day <= day < inc.start_day + inc.minutes / 1440:
                        burn = max(burn, inc.burn)
                p = min(1.0, burn * slo.budget)
                total = max(1, round(rng.gauss(per_bucket, per_bucket * 0.05)))
                mean, sd = total * p, (total * p * (1 - p)) ** 0.5
                bad = min(total, max(0, round(rng.gauss(mean, sd))))
                writer.writerow(
                    [datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), slo.name, total - bad, total]
                )
                rows += 1
    return rows
