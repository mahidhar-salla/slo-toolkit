"""Parse and format Prometheus-style durations (5m, 1h, 3d, 4w)."""

from __future__ import annotations

import re

_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
_RE = re.compile(r"^(\d+)([smhdw])$")


def to_seconds(duration: str) -> int:
    """'30m' -> 1800. Only single-unit durations are accepted, to keep rule names readable."""
    match = _RE.match(duration.strip())
    if not match:
        raise ValueError(f"invalid duration {duration!r}; use forms like 5m, 1h, 3d, 4w")
    value, unit = match.groups()
    seconds = int(value) * _UNITS[unit]
    if seconds <= 0:
        raise ValueError(f"duration must be positive: {duration!r}")
    return seconds


def to_duration(seconds: int) -> str:
    """1800 -> '30m'. Picks the largest unit that divides evenly (weeks are shown as days)."""
    for unit in ("d", "h", "m", "s"):
        size = _UNITS[unit]
        if seconds % size == 0:
            return f"{seconds // size}{unit}"
    raise ValueError(seconds)  # pragma: no cover


def humanize(seconds: float) -> str:
    """43.2 min style output for reports."""
    if seconds < 120:
        return f"{seconds:.0f}s"
    if seconds < 2 * 3600:
        return f"{seconds / 60:.1f} min"
    if seconds < 2 * 86400:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 86400:.1f} d"
