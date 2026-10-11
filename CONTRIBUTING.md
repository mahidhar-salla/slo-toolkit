# Contributing

Thanks for taking a look. Issues and small PRs are welcome.

## Setup

```bash
make install   # creates .venv with dev tools
make ci        # what CI runs: ruff, mypy, pytest, promtool, helm
```

`promtool` and `helm` are only needed for `make check-rules` and `make helm`.

## Making a change

1. Open an issue first for anything bigger than a bug fix, so we can agree on the shape.
2. Keep generated output stable. If your change alters rules or dashboards, run `make examples`
   and commit the updated files under `examples/*/out/`; CI fails if they are stale.
3. Add or update tests. Rule behaviour changes should come with a `promtool` unit test in
   `tests/promtool/`.
4. Keep examples synthetic. Please don't paste real metrics, hostnames or company names.

## Style

- `make fmt` before pushing (ruff format + autofix).
- Plain, short docs. If a reader needs the SRE Workbook to follow a change, link the section.
