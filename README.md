# AL-to-DBML

[![PyPI version](https://img.shields.io/pypi/v/al2dbml.svg)](https://pypi.org/project/al2dbml/)
[![Python versions](https://img.shields.io/pypi/pyversions/al2dbml.svg)](https://pypi.org/project/al2dbml/)
[![CI](https://github.com/mykola-kharchenko/al2dbml/actions/workflows/ci.yml/badge.svg)](https://github.com/mykola-kharchenko/al2dbml/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

`al2dbml` is a small Python CLI that converts a compiled Microsoft Dynamics 365 Business Central AL package (`.app`) into a [DBML](https://dbml.dbdiagram.io/) schema you can paste straight into [dbdiagram.io](https://dbdiagram.io) or [dbdocs.io](https://dbdocs.io). The pipeline reads `SymbolReference.json` from the `.app` archive (tolerating AL's 40-byte header), normalises tables, extensions, enums, and `TableRelation`s, and emits one valid DBML document with `Table`, `Ref`, `Enum`, and `TableGroup` sections.

Release history and per-version notes live in [CHANGELOG.md](CHANGELOG.md).

## Install

Python 3.10+ is required. The runtime depends only on [`click`](https://click.palletsprojects.com/) and [`pydbml`](https://github.com/Vanderhoof/PyDBML).

### Recommended: `uv tool install`

[`uv`](https://docs.astral.sh/uv/) installs CLI tools into isolated environments and puts the entry point on your `PATH`, so `al2dbml` is available globally without touching your system Python.

```bash
uv tool install al2dbml
```

If you don't already have `uv`:

```bash
# Fedora / RHEL / CentOS
sudo dnf install uv

# macOS (Homebrew)
brew install uv

# Anywhere (standalone installer)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Upgrade later with `uv tool upgrade al2dbml`, uninstall with `uv tool uninstall al2dbml`.

### Alternative: pipx

```bash
pipx install al2dbml
```

### Alternative: plain pip

Works inside an activated virtualenv. On modern distros that mark system Python as externally-managed (PEP 668), prefer `uv tool` or `pipx` instead.

```bash
pip install al2dbml
```

### Verify

```bash
al2dbml --version
al2dbml --help
```

## Quickstart

```bash
al2dbml MyApp.app -o schema.dbml
```

Drop `schema.dbml` into <https://dbdiagram.io>. Without `-o`, the DBML is streamed to stdout so you can pipe it elsewhere.

```bash
al2dbml MyApp.app | less
```

## Grouping

By default tables are bucketed into `TableGroup`s by the last segment of their AL namespace (so `Microsoft.Finance.GeneralLedger` -> group `GeneralLedger`). Tables that have no namespace tag fall back to the first whitespace-separated word in their name (so `Sales Header` + `Sales Line` -> group `Sales`). Buckets smaller than two tables are dropped so single-table groups don't clutter the diagram.

Override the source with `--group-by`:

```bash
al2dbml MyApp.app --group-by namespace   # default
al2dbml MyApp.app --group-by word        # legacy first-word grouping
al2dbml MyApp.app --group-by none        # no auto groups (only explicit --group rules apply)
```

```bash
# Auto grouping (default)
al2dbml MyApp.app -o schema.dbml

# Explicit rules; the value is NAME=PATTERN[,PATTERN...] and -g is repeatable
al2dbml MyApp.app -g "Documents=Sales*,Purch*" -g "Master=Customer,Vendor,Item"

# Disable grouping entirely
al2dbml MyApp.app --no-groups

# Keep singleton groups too
al2dbml MyApp.app --min-group-size 1
```

## Rich field descriptions (aldoc overlay)

By default, column notes are built from the AL `Caption` property in `SymbolReference.json` — which is usually just the field name itself. Real BC field documentation (the "Specifies the customer number..." sentences you see on [Microsoft Learn](https://learn.microsoft.com/dynamics365/business-central/dev-itpro)) lives in the AL `ToolTip` property and `/// <summary>` XML doc comments, neither of which the compiled `.app` package preserves.

To get those rich descriptions into your diagram, run [`aldoc`](https://learn.microsoft.com/dynamics365/business-central/dev-itpro/developer/devenv-al-doc) (Microsoft's official AL documentation generator, bundled with the AL Language VS Code extension) once to produce a YAML reference tree, then point `al2dbml` at it with `-d`/`--docs`:

```bash
# Step 1: generate docs from your .app (slow, but only once per release)
aldoc generate MyApp.app -o ./myapp-docs/

# Step 2: render the DBML with descriptions overlaid (fast)
al2dbml MyApp.app --docs ./myapp-docs/ -o schema.dbml
```

The result:

- Each table block gets a `Note { ... }` body sourced from the AL `/// <summary>` of the table — e.g. *"Stores document-level information for sales quotes, orders, invoices, credit memos, blanket orders, and return orders."*
- Each column note leads with the AL `ToolTip` text — e.g. *"Specifies the customer number to whom the goods or services are sold."*
- Existing condition / `**References**` sections still follow, separated by `<br><br>`

Coverage is uneven: active-document tables (Sales Header, Customer, Item, etc.) are richly documented in real BC; history and buffer tables often have nothing. Where aldoc has no entry, the original Caption-based note (or no note) is used.

## TableExtensions

Extensions are merged into their target tables by default. Use `--no-merge-extensions` to emit them as separate `<Target> (Extension)` tables instead.

## Public Python API

```python
from al2dbml import Diagram, generate, GroupingConfig

# One-shot helper
dbml = generate("MyApp.app", output_path="schema.dbml")

# Or step-by-step for custom grouping
diagram = Diagram.from_app(
    "MyApp.app",
    grouping=GroupingConfig(rules={"Documents": ["Sales*", "Purch*"]}),
)
print(diagram.dbml())
```

## Limitations

- FlowFields are treated as regular fields — the underlying CalcFormula is not interpreted.
- Obsolete fields are emitted alongside active ones; no filtering by `ObsoleteState`.
- Multi-field primary keys are represented as multiple `[pk]` flags rather than a composite index, matching DBML's single-PK convention.
- Multi-column secondary keys are not yet emitted as DBML indexes; only single-column secondary keys are surfaced (as `[unique]` on the column).
- Cross-package references (table relations that point to a table outside the current `.app`) are preserved as notes on the source column, since the target table is not present in the diagram.
- `IF (...) ... ELSE IF (...) ... ELSE ...` conditional `TableRelation` expressions are parsed into one DBML `Ref` per resolved branch, with each branch's condition recorded in the source column's note. Branches whose target table is missing from the current `.app` degrade to notes only.
- Render time scales quadratically with the table count inside the underlying `pydbml` library. Small/medium packages (up to a few hundred tables) finish in under a second. Microsoft's full Base Application (~1,500 tables) currently takes several minutes to render, even though parsing itself is fast. A custom DBML emitter is on the roadmap to remove this cliff.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
.venv/bin/ruff check .
```
