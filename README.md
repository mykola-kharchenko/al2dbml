# al2dbml

`al2dbml` is a small Python CLI that converts a compiled Microsoft Dynamics 365 Business Central AL package (`.app`) into a [DBML](https://dbml.dbdiagram.io/) schema you can paste straight into [dbdiagram.io](https://dbdiagram.io) or [dbdocs.io](https://dbdocs.io). The pipeline reads `SymbolReference.json` from the `.app` archive (tolerating AL's 40-byte header), normalises tables, extensions, enums, and `TableRelation`s, and emits one valid DBML document with `Table`, `Ref`, `Enum`, and `TableGroup` sections.

## Install

```bash
pip install -e ".[dev]"
```

Python 3.10+ is required. The runtime depends only on [`click`](https://click.palletsprojects.com/) and [`pydbml`](https://github.com/Vanderhoof/PyDBML).

## Quickstart

```bash
al2dbml MyApp.app -o schema.dbml
```

Drop `schema.dbml` into <https://dbdiagram.io>. Without `-o`, the DBML is streamed to stdout so you can pipe it elsewhere.

```bash
al2dbml MyApp.app | less
```

## Grouping

By default tables are bucketed into `TableGroup`s by their first whitespace-separated word, dropping any bucket smaller than two tables (so `Sales Header` + `Sales Line` become group `Sales`, while a lone `Customer` stays ungrouped).

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

`--no-auto-groups` switches off the first-word fallback so only your explicit `-g` rules apply.

## TableExtensions

Extensions are merged into their target tables by default. Use `--no-merge-extensions` to emit them as separate `<Target> (Extension)` tables instead.

## Public Python API

```python
from al2dbml import Generator, generate, GroupingConfig

# One-shot helper
dbml = generate("MyApp.app", output_path="schema.dbml")

# Or step-by-step for custom grouping
gen = Generator.from_app(
    "MyApp.app",
    grouping=GroupingConfig(rules={"Documents": ["Sales*", "Purch*"]}),
)
print(gen.dbml())
```

## Limitations (0.1.0)

- FlowFields are treated as regular fields — the underlying CalcFormula is not interpreted.
- Obsolete fields are emitted alongside active ones; no filtering by `ObsoleteState`.
- Multi-field primary keys are represented as multiple `[pk]` flags rather than a composite index, matching DBML's single-PK convention.
- Cross-package references (table relations that point to a table outside the current `.app`) are preserved as notes on the source column, since the target table is not present in the diagram.
- Complex `IF (...) ... ELSE ...` conditional `TableRelation` expressions fall back to a note rather than a fully-modeled reference.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
.venv/bin/ruff check .
```
