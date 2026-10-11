# Runbook: error budget burn alert

The `*ErrorBudgetBurn` alerts come from `slo-toolkit` rules. They fire when a service is spending
its error budget fast enough to matter, measured over a long and a short window at the same time.

## Page (fast burn: 1h/5m at 14.4x, or 6h/30m at 6x for a 30-day SLO)

Users are being hurt right now and the budget will be gone in about 2–5 days at this rate.

1. Open the SLO dashboard for the service (`SLOs / <service>` in Grafana). Check the **Burn rate by
   window** panel: is the 5m line still high (ongoing) or already dropping (recovering)?
2. Check what changed: recent deploys, config or feature-flag changes, dependency incidents,
   certificate or network changes.
3. Mitigate first, diagnose later: roll back the last change, fail over, shed load, or disable the
   failing feature. Declare an incident if customer impact is visible.
4. When the 5m burn rate drops below the threshold the page clears on its own within minutes.

## Ticket (slow burn: 1d/2h at 3x, or 3d/6h at 1x)

Nothing is on fire, but at this pace the SLO will be missed before the window ends.

1. Look for a slow regression: a new error class, a degraded dependency, a capacity trend.
2. Decide with the owning team whether to fix now or accept the spend; record the decision in the ticket.
3. If the budget is close to zero, apply the team's error-budget policy (for example, pause risky
   releases until reliability work lands).

## Not useful? Fix the SLO, not the alert

If this alert fired and nobody needed to act, the objective or the SLI is wrong. Change the spec and
regenerate; don't add `for:` clauses or silence it permanently.
