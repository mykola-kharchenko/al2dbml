"""``TableExtensions`` merge / stub phase."""

from __future__ import annotations

from pydbml.classes import Table

from .context import BuildContext
from .tables import TableBuilder


class ExtensionBuilder:
    """Applies AL ``TableExtensions`` either by merging or by emitting stubs.

    Two policies, controlled by :attr:`BuildConfig.merge_extensions`:

    - **merge** (default): each extension's fields are appended to the base
      ``Table`` they extend. If the base table isn't in the current package
      (cross-package extension), a stub base table is created on the fly so
      the diagram still shows where the extension lives.
    - **stub**: each extension renders as its own ``<Target> (Extension)``
      table containing only the added fields. Useful for understanding what
      each extension contributes without the base table noise.
    """

    @classmethod
    def merge(cls, ctx: BuildContext) -> None:
        for ext in ctx.symbols.get("TableExtensions") or []:
            target = ext.get("TargetObject") or ext.get("Target")
            if not target:
                continue
            table = ctx.tables.get(target)
            if table is None:
                table = Table(
                    name=target,
                    schema=ctx.config.table_schema,
                    note=f"Stub for cross-package target {target}",
                )
                ctx.tables[target] = table
                ctx.db.add(table)
            for f in ext.get("Fields") or []:
                col = TableBuilder.build_column(ctx, target, f, set())
                if col is not None:
                    table.add_column(col)
                    ctx.columns[(target, col.name)] = col

    @classmethod
    def stub(cls, ctx: BuildContext) -> None:
        for ext in ctx.symbols.get("TableExtensions") or []:
            target = ext.get("TargetObject") or ext.get("Target")
            if not target:
                continue
            stub_name = f"{target} (Extension)"
            stub = Table(
                name=stub_name,
                schema=ctx.config.table_schema,
                note=f"Extension of {target}",
            )
            for f in ext.get("Fields") or []:
                col = TableBuilder.build_column(ctx, stub_name, f, set())
                if col is not None:
                    stub.add_column(col)
                    ctx.columns[(stub_name, col.name)] = col
            ctx.tables[stub_name] = stub
            ctx.db.add(stub)
