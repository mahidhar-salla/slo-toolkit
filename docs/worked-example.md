# Worked example: test an objective against history before deploying

Before you load new alert rules into Prometheus, you can check what they would have done
over past traffic: how much error budget the objective leaves, whether it is already
missed, and which page and ticket alerts would have fired. This walk-through does that for
the example `checkout-api` spec with four commands: `simulate`, `report -f markdown`,
`generate` and `promtool test rules`.

**All data here is synthetic.** `simulate` writes deterministic traffic (seed 7) for
30 days ending 2026-10-01 00:00 UTC, with three planted incidents
([`simulate.py`](../src/slo_toolkit/simulate.py)): a short blip that should not page, a
40-minute partial outage that should page, and a two-day slow burn that should open a
ticket. No numbers below come from a real system. With your own data you would pass a
CSV export (`timestamp,slo,good,total`) to `report --data`, or use `--prometheus-url`.

The output below was captured on 2026-11-05 from a fresh clone at commit `c5db22f`, with
Python 3.13 and promtool 3.5.0 (the version CI pins), after `make install` and with
`.venv/bin` on `PATH`. Run it from the repository root.

## 1. Get some history

```text
$ slo-toolkit simulate examples/http-api/checkout-api.slo.yaml -o out/samples.csv
✓ out/samples.csv: 86,400 synthetic rows over 30d for 2 SLO(s)
$ head -4 out/samples.csv
timestamp,slo,good,total
2026-09-01T00:00:00Z,availability,2961,2962
2026-09-01T00:01:00Z,availability,2965,2966
2026-09-01T00:02:00Z,availability,2859,2860
```

Each row is one minute of good and total events for one SLO.

## 2. Report on the objective you plan to ship

```text
$ slo-toolkit report examples/http-api/checkout-api.slo.yaml --data out/samples.csv -f markdown; echo "exit $?"
## SLO report: checkout-api

| SLO | Objective | SLI | Budget left | 1h burn | Status |
|---|---|---|---|---|---|
| availability | 99.9% / 30d | 99.9482% | 48.2% | 0.358x | OK |
| latency | 99% / 30d | 99.5060% | 50.6% | 0.3x | OK |

**availability: replayed alerts**

| Alert | Started | Ended | Triggered by |
|---|---|---|---|
| page | 2026-09-14 14:45Z | 2026-09-14 15:07Z | 1h/5m @ 14.4x |
| ticket | 2026-09-22 22:28Z | 2026-09-24 04:02Z | 3d/6h @ 1x |

**latency: replayed alerts**

| Alert | Started | Ended | Triggered by |
|---|---|---|---|
| page | 2026-09-14 14:45Z | 2026-09-14 15:07Z | 1h/5m @ 14.4x |
| ticket | 2026-09-22 22:58Z | 2026-09-24 04:04Z | 3d/6h @ 1x |

exit 0
```

At 99.9% the availability SLO keeps 48.2% of its budget. The replay shows the 40-minute
outage paging and the slow burn opening a ticket, while the short blip on 2026-09-07 does
not page. That is the behaviour the planted incidents were designed for. Exit code 0 means
no SLO is missed.

## 3. Try a tighter objective against the same history

Change only the availability objective, then run the same report:

```text
$ sed 's/objective: 99.9$/objective: 99.95/' examples/http-api/checkout-api.slo.yaml > out/tighter.slo.yaml
$ slo-toolkit report out/tighter.slo.yaml --data out/samples.csv -f markdown --slo availability; echo "exit $?"
## SLO report: checkout-api

| SLO | Objective | SLI | Budget left | 1h burn | Status |
|---|---|---|---|---|---|
| availability | 99.95% / 30d | 99.9482% | -3.6% | 0.717x | SLO MISSED |

**availability: replayed alerts**

| Alert | Started | Ended | Triggered by |
|---|---|---|---|
| page | 2026-09-07 09:40Z | 2026-09-07 09:45Z | 1h/5m @ 14.4x |
| page | 2026-09-14 14:34Z | 2026-09-14 15:32Z | 1h/5m @ 14.4x |
| ticket | 2026-09-14 14:44Z | 2026-09-14 21:02Z | 3d/6h @ 1x |
| ticket | 2026-09-22 05:56Z | 2026-09-24 05:27Z | 3d/6h @ 1x |

exit 3
```

The same traffic misses 99.95% (budget left -3.6%), and the report exits 3, so a pipeline
step can stop on it. With half the budget, the replay now also pages for the 2026-09-07
blip, the outage opens a ticket as well as a page, and the outage page and the slow-burn
ticket start earlier and end later. If you wanted 99.95%,
this is the history you would have to defend; if not, keep 99.9%.

## 4. Generate the rules and test them with promtool

```text
$ slo-toolkit generate examples/http-api/checkout-api.slo.yaml -o out
✓ out/checkout-api.rules.yaml
✓ out/checkout-api.dashboard.json
$ diff out/checkout-api.rules.yaml examples/http-api/out/checkout-api.rules.yaml && echo "identical to the committed example"
identical to the committed example
$ promtool --version | head -1
promtool, version 3.5.0 (branch: HEAD, revision: 8be3a9560fbdd18a94dedec4b747c35178177202)
$ promtool check rules out/checkout-api.rules.yaml
Checking out/checkout-api.rules.yaml
  SUCCESS: 30 rules found
$ promtool test rules tests/promtool/checkout-api.test.yaml
  SUCCESS
```

`promtool check rules` lints the generated file. `promtool test rules` runs the unit tests
in [`tests/promtool/`](../tests/promtool/) against the committed copy of these rules
(`examples/http-api/out/`), which the `diff` above shows is identical to what was just
generated. Those tests feed synthetic series and assert when the page and ticket alerts
fire and that the page clears once errors stop.

## What this does and does not tell you

- `report --data` replays the CSV in Python with the same windows and burn rates as the
  generated rules. It is a preview, not a run of Prometheus. The promtool tests in step 4
  are what exercise the actual rule expressions.
- The verdict is only as good as the history: a quiet month says little about a bad one.
  `report` does not yet flag gaps inside a CSV (coverage is measured from the first to the
  last row), so check that your export is complete.
- Output was captured at `c5db22f`. Later commits may change the numbers; re-run the
  commands rather than trusting this page.
