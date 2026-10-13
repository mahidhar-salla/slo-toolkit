"""Generate Prometheus recording and alerting rules from a spec.

Naming follows the Prometheus `level:metric:operations` convention:

  slo:sli_error:ratio_rate<window>    error ratio over each alerting window
  slo:sli_bad:rate5m                  bad events per second over 5m
  slo:sli_total:rate5m                all events per second over 5m
  slo:period_error:ratio              bad / total events over the SLO window (request-weighted)
  slo:objective:ratio                 e.g. 0.999
  slo:error_budget:ratio              e.g. 0.001
  slo:error_budget_remaining:ratio    1.0 = untouched, 0 = spent, < 0 = SLO missed

Every series carries `slo_service` and `slo_name` so alerts and dashboards can join on them.
"""

from __future__ import annotations

from typing import Any

import yaml

from .durations import to_seconds
from .spec import SLO, Spec


def _camel(*parts: str) -> str:
    return "".join(word.capitalize() for part in parts for word in part.replace("_", "-").split("-"))


def alert_windows(slo: SLO) -> list[str]:
    """Every window the alert policy needs, sorted short to long."""
    windows = {w for step in slo.alerting.policy for w in (step.long_window, step.short_window)}
    return sorted(windows, key=to_seconds)


def series_labels(spec: Spec, slo: SLO) -> dict[str, str]:
    labels = {"slo_service": spec.service, "slo_name": slo.name}
    if spec.owner:
        labels["slo_owner"] = spec.owner
    labels.update(spec.labels)
    return labels


def selector(spec: Spec, slo: SLO) -> str:
    return f'{{slo_service="{spec.service}", slo_name="{slo.name}"}}'


def _num(value: float) -> str:
    """Stable, readable numbers in PromQL (0.001, 14.4, not 0.0010000000000000002)."""
    return f"{value:.10g}"


def recording_rules(spec: Spec, slo: SLO) -> list[dict[str, Any]]:
    labels = series_labels(spec, slo)
    sel = selector(spec, slo)
    rules: list[dict[str, Any]] = []
    for window in alert_windows(slo):
        rules.append(
            {"record": f"slo:sli_error:ratio_rate{window}", "expr": slo.sli.error_ratio_expr(window), "labels": labels}
        )
    rules += [
        # Record bad and total rates separately and sum each over the window. Averaging the
        # 5m ratio instead would weight a quiet 5 minutes the same as a busy one, and a 0/0
        # sample (no traffic) would record NaN and blank the budget for the whole window.
        {"record": "slo:sli_bad:rate5m", "expr": slo.sli.bad_expr("5m"), "labels": labels},
        {"record": "slo:sli_total:rate5m", "expr": slo.sli.total_expr("5m"), "labels": labels},
        {
            "record": "slo:period_error:ratio",
            "expr": (
                f"sum_over_time(slo:sli_bad:rate5m{sel}[{slo.window}])\n/\n"
                f"sum_over_time(slo:sli_total:rate5m{sel}[{slo.window}])"
            ),
            "labels": {**labels, "slo_window": slo.window},
        },
        {"record": "slo:objective:ratio", "expr": f"vector({_num(slo.objective / 100)})", "labels": labels},
        {"record": "slo:error_budget:ratio", "expr": f"vector({_num(slo.budget)})", "labels": labels},
        {
            "record": "slo:error_budget_remaining:ratio",
            "expr": f"1 - (slo:period_error:ratio{sel} / {_num(slo.budget)})",
            "labels": {**labels, "slo_window": slo.window},
        },
    ]
    if "5m" not in alert_windows(slo):
        raise ValueError("alert policy must include a 5m window (used for the period error ratio)")
    return rules


def _condition(spec: Spec, slo: SLO, long_w: str, short_w: str, burn: float) -> str:
    sel = selector(spec, slo)
    threshold = f"({_num(burn)} * {_num(slo.budget)})"
    return (
        f"(\n  slo:sli_error:ratio_rate{long_w}{sel} > {threshold}\n"
        f"  and\n  slo:sli_error:ratio_rate{short_w}{sel} > {threshold}\n)"
    )


def alerting_rules(spec: Spec, slo: SLO) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for severity, extra_labels in (("page", slo.alerting.page_labels), ("ticket", slo.alerting.ticket_labels)):
        steps = [s for s in slo.alerting.policy if s.severity == severity]
        if not steps:
            continue
        expr = "\nor\n".join(
            _condition(spec, slo, s.long_window, s.short_window, s.burn_rate(slo.window)) for s in steps
        )
        explain = "; ".join(
            f"{s.budget_fraction:.0%} of the {slo.window} budget in {s.long_window} "
            f"(burn rate {_num(s.burn_rate(slo.window))}x, confirmed over {s.short_window})"
            for s in steps
        )
        annotations = {
            "summary": f"{spec.service} {slo.name} SLO is burning its error budget too fast",
            "description": (
                f"Objective {_num(slo.objective)}% over {slo.window}. Fires when the error rate would spend "
                f"{explain}. Long-window error ratio: {{{{ $value | humanizePercentage }}}}."
            ),
        }
        if slo.alerting.runbook_url:
            annotations["runbook_url"] = slo.alerting.runbook_url
        rules.append(
            {
                "alert": f"{_camel(spec.service, slo.name)}ErrorBudgetBurn",
                "expr": expr,
                "labels": {**extra_labels, "slo_service": spec.service, "slo_name": slo.name},
                "annotations": annotations,
            }
        )
    return rules


def rule_groups(spec: Spec) -> dict[str, Any]:
    # One group per SLO: rules in a group run in order, so alerts always see this
    # evaluation's recorded ratios (separate groups can lag each other by one interval).
    groups = [
        {"name": f"slo-{spec.service}-{slo.name}", "rules": recording_rules(spec, slo) + alerting_rules(spec, slo)}
        for slo in spec.slos
    ]
    return {"groups": groups}


class _Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:  # no &id001 anchors in generated files
        return True


def _str_presenter(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _str_presenter)


def to_yaml(data: Any) -> str:
    return yaml.dump(data, Dumper=_Dumper, sort_keys=False, width=4096, default_flow_style=False)


def render_rules(spec: Spec) -> str:
    header = (
        f"# Generated by slo-toolkit from the {spec.service} spec. Do not edit by hand;\n"
        "# change the spec and re-run `slo-toolkit generate`.\n"
    )
    return header + to_yaml(rule_groups(spec))
