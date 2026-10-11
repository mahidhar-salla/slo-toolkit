"""Generate a Grafana dashboard (JSON model) that reads the recording rules from rules.py."""

from __future__ import annotations

import json
from typing import Any

from .rules import selector
from .spec import SLO, Spec

DS = {"type": "prometheus", "uid": "${datasource}"}


def _target(expr: str, legend: str, ref: str = "A") -> dict[str, Any]:
    return {"datasource": DS, "expr": expr, "legendFormat": legend, "refId": ref, "range": True}


def _stat(
    title: str,
    expr: str,
    unit: str,
    steps: list[dict[str, Any]],
    grid: dict[str, int],
    pid: int,
    description: str,
    decimals: int = 3,
) -> dict[str, Any]:
    return {
        "id": pid,
        "type": "stat",
        "title": title,
        "description": description,
        "datasource": DS,
        "gridPos": grid,
        "targets": [_target(expr, title)],
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "colorMode": "background",
            "graphMode": "area",
            "textMode": "value",
        },
        "fieldConfig": {
            "defaults": {"unit": unit, "decimals": decimals, "thresholds": {"mode": "absolute", "steps": steps}},
            "overrides": [],
        },
    }


def _timeseries(
    title: str,
    targets: list[dict[str, Any]],
    unit: str,
    grid: dict[str, int],
    pid: int,
    description: str,
    steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    defaults: dict[str, Any] = {"unit": unit, "custom": {"lineWidth": 2, "fillOpacity": 5}}
    if steps:
        defaults["thresholds"] = {"mode": "absolute", "steps": steps}
        defaults["custom"]["thresholdsStyle"] = {"mode": "line+area"}
    return {
        "id": pid,
        "type": "timeseries",
        "title": title,
        "description": description,
        "datasource": DS,
        "gridPos": grid,
        "targets": targets,
        "options": {"legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi"}},
        "fieldConfig": {"defaults": defaults, "overrides": []},
    }


def _slo_panels(spec: Spec, slo: SLO, y: int, pid: int) -> tuple[list[dict[str, Any]], int, int]:
    sel = selector(spec, slo)
    budget = f"{slo.budget:.10g}"
    objective = slo.objective / 100
    page_burn = max(s.burn_rate(slo.window) for s in slo.alerting.policy if s.severity == "page")
    panels: list[dict[str, Any]] = [
        {
            "id": pid,
            "type": "row",
            "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y},
            "title": f"{slo.name}: {slo.objective:g}% over {slo.window}. {slo.description}".strip(),
            "panels": [],
        },
    ]
    y += 1
    pid += 1
    panels.append(
        _stat(
            f"SLI ({slo.window})",
            f"1 - slo:period_error:ratio{sel}",
            "percentunit",
            [{"color": "red", "value": None}, {"color": "green", "value": objective}],
            {"h": 5, "w": 6, "x": 0, "y": y},
            pid,
            f"Share of good events over the SLO window. Target {slo.objective:g}%.",
        )
    )
    pid += 1
    panels.append(
        _stat(
            "Error budget remaining",
            f"slo:error_budget_remaining:ratio{sel}",
            "percentunit",
            [{"color": "red", "value": None}, {"color": "orange", "value": 0}, {"color": "green", "value": 0.25}],
            {"h": 5, "w": 6, "x": 6, "y": y},
            pid,
            "1 = untouched, 0 = spent. Below 0 the SLO is missed.",
            decimals=1,
        )
    )
    pid += 1
    panels.append(
        _stat(
            "Burn rate (1h)",
            f"slo:sli_error:ratio_rate1h{sel} / {budget}",
            "x",
            [{"color": "green", "value": None}, {"color": "orange", "value": 1}, {"color": "red", "value": page_burn}],
            {"h": 5, "w": 6, "x": 12, "y": y},
            pid,
            "1x spends exactly the budget over the window.",
            decimals=2,
        )
    )
    pid += 1
    panels.append(
        _stat(
            "Objective",
            f"slo:objective:ratio{sel}",
            "percentunit",
            [{"color": "blue", "value": None}],
            {"h": 5, "w": 6, "x": 18, "y": y},
            pid,
            "From the spec.",
        )
    )
    y += 5
    pid += 1
    windows = ["5m", "1h", "6h", "3d"]
    panels.append(
        _timeseries(
            "Burn rate by window",
            [_target(f"slo:sli_error:ratio_rate{w}{sel} / {budget}", w, chr(65 + i)) for i, w in enumerate(windows)],
            "x",
            {"h": 8, "w": 12, "x": 0, "y": y},
            pid,
            "Alerts page when both a long and a short window are above the line.",
            [
                {"color": "transparent", "value": None},
                {"color": "orange", "value": 1},
                {"color": "red", "value": page_burn},
            ],
        )
    )
    pid += 1
    panels.append(
        _timeseries(
            "Error budget remaining",
            [_target(f"slo:error_budget_remaining:ratio{sel}", "remaining")],
            "percentunit",
            {"h": 8, "w": 12, "x": 12, "y": y},
            pid,
            "Trend of the budget over the SLO window.",
            [{"color": "red", "value": None}, {"color": "transparent", "value": 0}],
        )
    )
    return panels, y + 8, pid + 1


def dashboard(spec: Spec) -> dict[str, Any]:
    panels: list[dict[str, Any]] = []
    y, pid = 0, 1
    for slo in spec.slos:
        new, y, pid = _slo_panels(spec, slo, y, pid)
        panels += new
    return {
        "uid": f"slo-{spec.service}"[:40],
        "title": f"SLOs / {spec.service}",
        "description": "Generated by slo-toolkit. Edit the spec, not this file.",
        "tags": ["slo", "slo-toolkit", spec.service],
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 1,
        "editable": True,
        "refresh": "1m",
        "time": {"from": "now-7d", "to": "now"},
        "templating": {
            "list": [
                {
                    "name": "datasource",
                    "label": "Prometheus",
                    "type": "datasource",
                    "query": "prometheus",
                    "current": {},
                    "hide": 0,
                    "refresh": 1,
                }
            ]
        },
        "annotations": {"list": []},
        "panels": panels,
    }


def render_dashboard(spec: Spec) -> str:
    return json.dumps(dashboard(spec), indent=2) + "\n"
