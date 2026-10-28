# Changelog

All notable changes to this project are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed
- `slo:period_error:ratio` now divides the bad and total event counts over the SLO window
  (new `slo:sli_bad:rate5m` and `slo:sli_total:rate5m` recording rules) instead of averaging
  5m error ratios. The average over-weighted quiet periods, so uneven traffic could report an
  error ratio many times too high, and a 5m stretch with no traffic recorded NaN and blanked
  error budget remaining until it left the window. A `bad` query that matches nothing now
  reads as zero errors. Thanks to Mike Dabydeen for the report and repro.
- Spec `labels` can no longer set `slo_service`, `slo_name`, `slo_owner` or `slo_window`.
  A custom label with one of these names overrode the identity on the generated recording
  rules while the derived rules still selected on the real service and SLO name, so
  `slo:period_error:ratio` and budget remaining silently matched nothing. `validate` and
  `generate` now reject the spec with a readable error. Other custom labels are unchanged.
- `validate --promtool` now fails (exit 1) when `promtool` is not on PATH. It used to print
  a skip notice and exit 0, so a requested rule lint could pass without running. Without
  `--promtool`, `validate` does not need promtool and behaves as before.
- `report --data` now rejects CSV rows whose `good` or `total` is NaN, infinite, negative or
  not a number, or where `good` is greater than `total`, and names the file, line and SLO
  (exit 1). One such row used to pass through, and the report showed status OK with an SLI
  of NaN or several hundred percent and exited 0. Zero and fractional counts are still accepted.
- Spec `labels`, `page_labels` and `ticket_labels` now reject empty label names and names
  starting with `__`, which Prometheus reserves for internal use. `validate` and `generate`
  used to accept `__name__` or `""` and write rules that promtool rejects with "invalid label
  name", so the rule group would not load. Other names, including UTF-8 names that
  Prometheus 3 accepts, are unchanged.
- An objective so close to 100% that its error budget rounds to 0 (e.g. `99.99999999999`) is
  now rejected by `validate`, `generate` and `report`. It used to pass validation and generate
  rules that divide by zero for budget remaining and page on any error at all, and `report`
  crashed with a ZeroDivisionError. `99.99999999` (a 1e-10 budget) and every ordinary
  objective are unchanged.

## [0.1.0] - 2026-10-11

First public release.

### Added
- `slo-toolkit/v1` spec: ratio SLIs (`good` or `bad` over `total`), per-SLO objective and window,
  alert labels and runbook links. Strict validation with readable errors.
- `calc`: error budget, allowed downtime and burn-rate thresholds for any objective and window.
- `generate`: Prometheus recording rules for every alert window, SLO metadata rules, and
  multiwindow, multi-burn-rate page/ticket alerts following the Google SRE Workbook (ch. 5).
  Burn rates are derived from budget share, so 28d and 7d windows scale correctly.
- `generate`: Grafana dashboard JSON (SLI, budget remaining, burn rate by window).
- `generate --helm-values` and the `charts/slo-rules` Helm chart (PrometheusRule + dashboard ConfigMap).
- `validate`: schema checks, warnings for objectives the policy can't defend, optional `promtool check rules`.
- `report`: budget and burn-rate report from a CSV or a live Prometheus; for CSV data, a replay of
  which alerts would have fired. Text, Markdown and JSON output.
- `simulate`: deterministic synthetic traffic with a blip, an outage and a slow burn.
- Four example specs (HTTP API, gRPC API, batch job, Kafka consumer) with committed outputs.
- Demo stack: synthetic service with failure injection, Prometheus and Grafana via Docker Compose.
- CI: ruff, mypy, pytest on Python 3.11 to 3.13, promtool rule tests, helm lint/template.

[0.1.0]: https://github.com/mahidhar-salla/slo-toolkit/releases/tag/v0.1.0
