"""The SLO spec: one YAML file per service, validated with Pydantic."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .budget import POLICIES, PolicyStep, error_budget
from .durations import to_seconds

_NAME = re.compile(r"^[a-z][a-z0-9-]*$")
WINDOW_PLACEHOLDER = "{{window}}"
# Identity labels the generator writes on every series and later rules select on.
RESERVED_LABELS = ("slo_service", "slo_name", "slo_owner", "slo_window")


def _check_label_names(value: dict[str, str]) -> dict[str, str]:
    """Reject label names Prometheus won't load: empty, or starting with `__` (reserved)."""
    bad = sorted(repr(name) for name in value if name == "" or name.startswith("__"))
    if bad:
        raise ValueError(
            f"invalid label name(s) {', '.join(bad)}: label names can't be empty, and names "
            "starting with '__' are reserved for Prometheus internal use"
        )
    return value


class SpecError(Exception):
    """Raised with a readable message when a spec file can't be loaded."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SLI(_Strict):
    """A ratio SLI. Give `total` plus exactly one of `good` or `bad`.

    Queries must contain {{window}}; the generator substitutes each alerting window.
    """

    type: Literal["ratio"] = "ratio"
    good: str | None = None
    bad: str | None = None
    total: str

    @model_validator(mode="after")
    def _one_of_good_bad(self) -> SLI:
        if (self.good is None) == (self.bad is None):
            raise ValueError("set exactly one of 'good' or 'bad'")
        for field in ("good", "bad", "total"):
            query = getattr(self, field)
            if query is not None and WINDOW_PLACEHOLDER not in query:
                raise ValueError(f"'{field}' query must contain {WINDOW_PLACEHOLDER}")
        return self

    def total_expr(self, window: str) -> str:
        """PromQL for the total event rate over `window`."""
        return self.total.replace(WINDOW_PLACEHOLDER, window).strip()

    def bad_expr(self, window: str) -> str:
        """PromQL for the bad event rate over `window`.

        A `bad` query falls back to 0 when it matches nothing (no 5xx series yet), so the
        budget doesn't go blank on a clean service. A `good` query is turned into total - good.
        """
        if self.bad is not None:
            return f"({self.bad.replace(WINDOW_PLACEHOLDER, window).strip()}) or vector(0)"
        good = (self.good or "").replace(WINDOW_PLACEHOLDER, window).strip()
        return f"({self.total_expr(window)})\n-\n({good})"

    def error_ratio_expr(self, window: str) -> str:
        """PromQL for the error ratio over `window`."""
        total = self.total.replace(WINDOW_PLACEHOLDER, window).strip()
        if self.bad is not None:
            bad = self.bad.replace(WINDOW_PLACEHOLDER, window).strip()
            return f"({bad})\n/\n({total})"
        good = (self.good or "").replace(WINDOW_PLACEHOLDER, window).strip()
        return f"1 - (\n  ({good})\n  /\n  ({total})\n)"


class Alerting(_Strict):
    profile: Literal["workbook", "workbook-table"] = "workbook"
    page_labels: dict[str, str] = Field(default_factory=lambda: {"severity": "page"})
    ticket_labels: dict[str, str] = Field(default_factory=lambda: {"severity": "ticket"})
    runbook_url: str | None = None

    @field_validator("page_labels", "ticket_labels")
    @classmethod
    def _label_names(cls, value: dict[str, str]) -> dict[str, str]:
        return _check_label_names(value)

    @property
    def policy(self) -> tuple[PolicyStep, ...]:
        return POLICIES[self.profile]


class SLO(_Strict):
    name: str
    description: str = ""
    objective: float = Field(gt=0, lt=100, description="Target in percent, e.g. 99.9")
    window: str = "30d"
    sli: SLI
    alerting: Alerting = Field(default_factory=Alerting)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not _NAME.match(value):
            raise ValueError("use lowercase letters, digits and dashes, starting with a letter")
        return value

    @field_validator("window")
    @classmethod
    def _window(cls, value: str) -> str:
        if to_seconds(value) < 86400:
            raise ValueError("SLO window should be at least 1d (30d or 28d is typical)")
        return value

    @property
    def budget(self) -> float:
        return error_budget(self.objective)


class Spec(_Strict):
    apiVersion: Literal["slo-toolkit/v1"]
    service: str
    owner: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    slos: list[SLO] = Field(min_length=1)

    @field_validator("service")
    @classmethod
    def _service(cls, value: str) -> str:
        if not _NAME.match(value):
            raise ValueError("use lowercase letters, digits and dashes, starting with a letter")
        return value

    @field_validator("labels")
    @classmethod
    def _no_reserved_labels(cls, value: dict[str, str]) -> dict[str, str]:
        _check_label_names(value)
        clash = sorted(set(value) & set(RESERVED_LABELS))
        if clash:
            raise ValueError(
                f"reserved label name(s) {', '.join(clash)}: the generator sets these on every series "
                "and its rules select on them. Use 'service' or 'owner', or pick another label name"
            )
        return value

    @model_validator(mode="after")
    def _unique(self) -> Spec:
        names = [slo.name for slo in self.slos]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(f"duplicate SLO names: {', '.join(dupes)}")
        return self


def warnings_for(spec: Spec) -> list[str]:
    """Things that are valid but probably not what you want."""
    out: list[str] = []
    for slo in spec.slos:
        for step in slo.alerting.policy:
            threshold = step.burn_rate(slo.window) * slo.budget
            if threshold >= 1:
                out.append(
                    f"{slo.name}: the {step.long_window}/{step.short_window} {step.severity} alert can never "
                    f"fire (needs error ratio {threshold:.0%} at objective {slo.objective}%). "
                    "Consider a longer window or different policy."
                )
        if slo.objective >= 99.99:
            out.append(
                f"{slo.name}: at {slo.objective}% a full outage spends the budget in minutes; "
                "alerting alone can't defend this, so lean on canaries and fast rollback."
            )
    return out


def load_spec(path: str | Path) -> Spec:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text())
    except FileNotFoundError as exc:
        raise SpecError(f"{path}: file not found") from exc
    except yaml.YAMLError as exc:
        raise SpecError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise SpecError(f"{path}: expected a mapping at the top level")
    try:
        return Spec.model_validate(raw)
    except ValidationError as exc:
        lines = [f"{path}: {exc.error_count()} problem(s)"]
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "(root)"
            lines.append(f"  - {loc}: {err['msg']}")
        raise SpecError("\n".join(lines)) from exc
