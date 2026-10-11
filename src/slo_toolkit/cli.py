"""Command-line interface: `slo-toolkit` (alias `slo`)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .budget import POLICIES, allowed_downtime_seconds, burn_threshold, error_budget
from .dashboard import render_dashboard
from .durations import humanize, to_seconds
from .report import SLOReport, report_from_csv, report_from_prometheus
from .rules import render_rules
from .simulate import simulate as run_simulation
from .spec import Spec, SpecError, load_spec, warnings_for

app = typer.Typer(
    help="Define SLOs once in YAML; get error budgets, burn-rate alerts, dashboards and reports.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console(highlight=False)
err = Console(stderr=True, highlight=False)

SpecArg = Annotated[Path, typer.Argument(help="Path to an SLO spec (*.slo.yaml).", exists=False)]


class Format(StrEnum):
    text = "text"
    markdown = "markdown"
    json = "json"


def _version(value: bool) -> None:
    if value:
        typer.echo(f"slo-toolkit {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[bool, typer.Option("--version", callback=_version, is_eager=True, help="Show version.")] = False,
) -> None:
    """slo-toolkit"""


def _load(path: Path) -> Spec:
    try:
        return load_spec(path)
    except SpecError as exc:
        err.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1) from exc


@app.command()
def calc(
    objective: Annotated[float, typer.Option(help="Objective in percent.")] = 99.9,
    window: Annotated[str, typer.Option(help="SLO window, e.g. 30d or 28d.")] = "30d",
    profile: Annotated[str, typer.Option(help="Alert policy: workbook or workbook-table.")] = "workbook",
) -> None:
    """Show the error budget and burn-rate alert thresholds for an objective."""
    if profile not in POLICIES:
        err.print(f"[red]unknown profile {profile!r}[/red]; choose from {', '.join(POLICIES)}")
        raise typer.Exit(2)
    budget = error_budget(objective)
    console.print(
        f"[bold]{objective:g}% over {window}[/bold]: error budget {budget:.4%} "
        f"= {humanize(allowed_downtime_seconds(objective, window))} of full outage"
    )
    table = Table(
        "Severity",
        "Long / short window",
        "Burn rate",
        "Fires above error ratio",
        "Budget spent at fire",
        "Full budget gone in",
    )
    for step in POLICIES[profile]:
        rate = step.burn_rate(window)
        table.add_row(
            step.severity,
            f"{step.long_window} / {step.short_window}",
            f"{rate:.4g}x",
            f"{burn_threshold(objective, rate):.4%}",
            f"{step.budget_fraction:.0%}",
            humanize(to_seconds(window) / rate),
        )
    console.print(table)


@app.command()
def validate(
    specs: Annotated[list[Path], typer.Argument(help="One or more spec files.")],
    promtool: Annotated[bool, typer.Option(help="Also run `promtool check rules` on the generated rules.")] = False,
) -> None:
    """Check specs for errors (and optionally lint the generated rules with promtool)."""
    failed = False
    for path in specs:
        try:
            spec = load_spec(path)
        except SpecError as exc:
            err.print(f"[red]✗[/red] {exc}")
            failed = True
            continue
        console.print(f"[green]✓[/green] {path}: {spec.service}, {len(spec.slos)} SLO(s)")
        for warning in warnings_for(spec):
            console.print(f"  [yellow]![/yellow] {warning}")
        if promtool:
            failed |= not _promtool_check(spec)
    if failed:
        raise typer.Exit(1)


def _promtool_check(spec: Spec) -> bool:
    binary = shutil.which("promtool")
    if not binary:
        err.print("  [yellow]promtool not found on PATH; skipping rule lint[/yellow]")
        return True
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".rules.yaml", delete=False) as fh:
        fh.write(render_rules(spec))
    result = subprocess.run([binary, "check", "rules", fh.name], capture_output=True, text=True)
    Path(fh.name).unlink(missing_ok=True)
    ok = result.returncode == 0
    mark = "[green]✓[/green]" if ok else "[red]✗[/red]"
    console.print(f"  {mark} promtool check rules: {(result.stdout or result.stderr).strip().splitlines()[-1]}")
    return ok


@app.command()
def generate(
    spec_path: SpecArg,
    out: Annotated[Path, typer.Option("--out", "-o", help="Output directory.")] = Path("out"),
    helm_values: Annotated[bool, typer.Option(help="Also write values for the charts/slo-rules Helm chart.")] = False,
) -> None:
    """Generate Prometheus rules and a Grafana dashboard from a spec."""
    spec = _load(spec_path)
    out.mkdir(parents=True, exist_ok=True)
    rules = out / f"{spec.service}.rules.yaml"
    dash = out / f"{spec.service}.dashboard.json"
    rules.write_text(render_rules(spec))
    dash.write_text(render_dashboard(spec))
    console.print(f"[green]✓[/green] {rules}")
    console.print(f"[green]✓[/green] {dash}")
    if helm_values:
        from .helm import render_values

        values = out / f"{spec.service}.values.yaml"
        values.write_text(render_values(spec))
        console.print(f"[green]✓[/green] {values}")
    for warning in warnings_for(spec):
        console.print(f"[yellow]![/yellow] {warning}")


def _print_text(spec: Spec, reports: list[SLOReport]) -> None:
    colours = {"OK": "green", "AT RISK": "yellow", "SLO MISSED": "red"}
    for r in reports:
        colour = colours[r.status]
        console.rule(f"[bold]{spec.service} / {r.slo}[/bold]  {r.objective:g}% over {r.window}")
        console.print(
            f"SLI [bold]{r.sli:.4%}[/bold]  ·  budget remaining [bold {colour}]{r.budget_remaining:.1%}[/bold {colour}]"
            f"  ·  status [bold {colour}]{r.status}[/bold {colour}]"
        )
        console.print(f"[dim]{humanize(r.coverage_s)} of data from {r.source}[/dim]")
        rates = " · ".join(f"{w} {v:.2f}x" for w, v in r.burn_rates.items())
        console.print(f"Burn rate now: {rates}")
        if r.time_to_exhaustion_s is not None and r.time_to_exhaustion_s < to_seconds(r.window):
            console.print(
                f"[yellow]At the 1h burn rate, the remaining budget is gone in "
                f"{humanize(r.time_to_exhaustion_s)}.[/yellow]"
            )
        elif r.budget_remaining > 0:
            console.print("At the current 1h burn rate the budget lasts the rest of the window.")
        if r.episodes:
            table = Table("Alert", "Started", "Ended", "Lasted", "Triggered by", title="Replayed alerts")
            for e in r.episodes:
                sev = "[red]page[/red]" if e.severity == "page" else "[yellow]ticket[/yellow]"
                table.add_row(sev, e.start, e.end, humanize(e.duration_s), e.trigger)
            console.print(table)
        elif r.source.startswith("csv"):
            console.print("Replayed alerts: none would have fired.")
        console.print()


def _markdown(spec: Spec, reports: list[SLOReport]) -> str:
    lines = [
        f"## SLO report: {spec.service}",
        "",
        "| SLO | Objective | SLI | Budget left | 1h burn | Status |",
        "|---|---|---|---|---|---|",
    ]
    for r in reports:
        lines.append(
            f"| {r.slo} | {r.objective:g}% / {r.window} | {r.sli:.4%} | {r.budget_remaining:.1%} | "
            f"{r.burn_rates.get('1h', 0):g}x | {r.status} |"
        )
    for r in reports:
        if r.episodes:
            lines += [
                "",
                f"**{r.slo}: replayed alerts**",
                "",
                "| Alert | Started | Ended | Triggered by |",
                "|---|---|---|---|",
            ]
            lines += [f"| {e.severity} | {e.start} | {e.end} | {e.trigger} |" for e in r.episodes]
    return "\n".join(lines) + "\n"


@app.command()
def report(
    spec_path: SpecArg,
    data: Annotated[Path | None, typer.Option(help="CSV with timestamp,slo,good,total rows.")] = None,
    prometheus_url: Annotated[str | None, typer.Option(help="Query a live Prometheus instead of a CSV.")] = None,
    fmt: Annotated[Format, typer.Option("--format", "-f", help="Output format.")] = Format.text,
    slo: Annotated[list[str] | None, typer.Option("--slo", help="Only these SLOs (repeatable).")] = None,
) -> None:
    """Error budget, burn rates and (for CSV data) a replay of which alerts would have fired."""
    spec = _load(spec_path)
    if slo:
        unknown = set(slo) - {s.name for s in spec.slos}
        if unknown:
            err.print(f"[red]unknown SLO(s): {', '.join(sorted(unknown))}[/red]")
            raise typer.Exit(2)
        spec = spec.model_copy(update={"slos": [s for s in spec.slos if s.name in slo]})
    if (data is None) == (prometheus_url is None):
        err.print("[red]pass exactly one of --data or --prometheus-url[/red]")
        raise typer.Exit(2)
    try:
        reports = report_from_csv(spec, data) if data else report_from_prometheus(spec, prometheus_url or "")
    except (OSError, ValueError, RuntimeError) as exc:
        err.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1) from exc
    if fmt is Format.json:
        typer.echo(json.dumps({"service": spec.service, "slos": [r.to_dict() for r in reports]}, indent=2))
    elif fmt is Format.markdown:
        typer.echo(_markdown(spec, reports))
    else:
        _print_text(spec, reports)
    if any(r.status == "SLO MISSED" for r in reports):
        raise typer.Exit(3)


@app.command()
def simulate(
    spec_path: SpecArg,
    out: Annotated[Path, typer.Option("--out", "-o", help="CSV file to write.")] = Path("out/samples.csv"),
    days: Annotated[int, typer.Option(help="Days of history.")] = 30,
    seed: Annotated[int, typer.Option(help="Random seed (output is deterministic).")] = 7,
) -> None:
    """Write synthetic traffic with a blip, an outage and a slow burn, for demos and testing."""
    spec = _load(spec_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = run_simulation(spec, out, days=days, seed=seed)
    console.print(f"[green]✓[/green] {out}: {rows:,} synthetic rows over {days}d for {len(spec.slos)} SLO(s)")


def run() -> None:  # pragma: no cover
    sys.exit(app())


if __name__ == "__main__":  # pragma: no cover
    app()
