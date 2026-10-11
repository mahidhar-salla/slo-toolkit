"""Render slo-toolkit output to SVG for README screenshots (runs the CLI in-process).

python scripts/render_terminal.py docs/img/report.svg report examples/.../checkout-api.slo.yaml --data out/samples.csv
"""

from __future__ import annotations

import os
import sys

from rich.console import Console

from slo_toolkit import cli

WIDTH = 100  # with height set too, rich skips terminal detection (TERM=dumb would force 80)


def main() -> None:
    out, args = sys.argv[1], sys.argv[2:]
    with open(os.devnull, "w") as sink:
        console = Console(record=True, width=WIDTH, height=60, force_terminal=True, highlight=False, file=sink)
        cli.console = console
        console.print(f"[bold green]$[/bold green] slo-toolkit {' '.join(args)}")
        try:
            cli.app(args, standalone_mode=False)
        finally:
            console.save_svg(out, title=f"slo-toolkit {args[0]}")


if __name__ == "__main__":
    main()
