"""Turn `slo-toolkit simulate` output into OpenMetrics so it can be backfilled into Prometheus.

    slo-toolkit simulate examples/http-api/checkout-api.slo.yaml -o out/samples.csv
    python scripts/csv_to_openmetrics.py out/samples.csv > out/history.om
    promtool tsdb create-blocks-from openmetrics out/history.om <prometheus-data-dir>

Maps the checkout-api example: `availability` rows become http_requests_total{code=200|500},
`latency` rows become the le="0.3" / +Inf buckets of http_request_duration_seconds.
Synthetic data only.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime


def main(path: str, job: str = "checkout-api") -> None:
    rows: dict[str, list[tuple[int, int, int]]] = defaultdict(list)
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            ts = int(datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")).timestamp())
            rows[r["slo"]].append((ts, int(r["good"]), int(r["total"])))

    out = sys.stdout
    if "availability" in rows:
        out.write("# TYPE http_requests counter\n")
        for code, pick in (("200", lambda g, t: g), ("500", lambda g, t: t - g)):
            acc = 0
            for ts, good, total in rows["availability"]:
                acc += pick(good, total)
                out.write(f'http_requests_total{{job="{job}",code="{code}"}} {acc} {ts}\n')
    if "latency" in rows:
        out.write("# TYPE http_request_duration_seconds histogram\n")
        for suffix, le, pick in (
            ("_bucket", "0.3", lambda g, t: g),
            ("_bucket", "+Inf", lambda g, t: t),
            ("_count", None, lambda g, t: t),
        ):
            acc = 0
            labels = f'job="{job}"' + (f',le="{le}"' if le else "")
            for ts, good, total in rows["latency"]:
                acc += pick(good, total)
                out.write(f"http_request_duration_seconds{suffix}{{{labels}}} {acc} {ts}\n")
    out.write("# EOF\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
