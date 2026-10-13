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
