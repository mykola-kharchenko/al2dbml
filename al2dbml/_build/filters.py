"""Table include/exclude filtering phase."""

from __future__ import annotations

from fnmatch import fnmatchcase

from .context import BuildContext


class TableFilter:
    """Drops tables that don't match the include/exclude glob patterns.

    Runs after :class:`TableBuilder` and :class:`ExtensionBuilder` so that
    merged extension fields can still be attached to their target table
    before the target is potentially filtered out. Refs into a removed
    target degrade naturally to cross-package notes via the existing
    :class:`ReferenceResolver` path, since the target table is gone from
    ``ctx.tables``.

    Filter semantics:

    - ``includes``: positive filter; when non-empty, tables matching *none*
      of the patterns are removed
    - ``excludes``: negative filter applied after includes; tables matching
      *any* exclude pattern are removed (exclude wins over include)
    """

    @classmethod
    def apply(cls, ctx: BuildContext) -> None:
        includes = ctx.config.includes
        excludes = ctx.config.excludes
        if not includes and not excludes:
            return

        def keep(name: str) -> bool:
            if includes and not any(fnmatchcase(name, p) for p in includes):
                return False
            if excludes and any(fnmatchcase(name, p) for p in excludes):
                return False
            return True

        dropped = {name for name in ctx.tables if not keep(name)}
        for name in dropped:
            table = ctx.tables.pop(name)
            ctx.table_namespaces.pop(name, None)
            # Remove column entries for this table so references can't accidentally
            # rebind to a column on a filtered-out table.
            for key in list(ctx.columns):
                if key[0] == name:
                    del ctx.columns[key]
            try:
                ctx.db.delete_table(table)
            except Exception:  # noqa: BLE001 — defensive against pydbml internal changes
                pass
