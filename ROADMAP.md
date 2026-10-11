# Roadmap

Rough order, not promises. Ideas and votes welcome in issues.

## v0.2
- Latency SLIs from histograms without hand-writing the bucket query (`type: latency`, `threshold: 300ms`).
- Per-label SLOs (e.g. one SLO per `route`) with grouping carried through rules and dashboards.
- `report --since/--until` and a weekly Markdown summary suitable for a reliability review.
- Low-traffic guard: optional minimum request count before an alert can fire.

## v0.3
- `slo-toolkit diff`: show how a spec change alters thresholds and rules before merging.
- OpenSLO import/export for the subset the tool supports.
- Optional Alertmanager inhibition snippet so a page suppresses the matching ticket.

## Later
- Error-budget policy helpers (freeze/unfreeze signals from remaining budget).
- Multi-service roll-up dashboard.

## Not planned
- A UI or a Kubernetes operator. [Pyrra](https://github.com/pyrra-dev/pyrra) and
  [Sloth](https://github.com/slok/sloth) do those well.
