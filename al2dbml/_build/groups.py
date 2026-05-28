"""``TableGroup`` build phase."""

from __future__ import annotations

from ..grouping import build_table_groups
from .context import BuildContext


class GroupBuilder:
    """Builds ``TableGroup`` blocks from the configured ``GroupingConfig``.

    Thin shim over :func:`al2dbml.grouping.build_table_groups`; here so the
    pipeline reads as ``GroupBuilder.build(ctx)`` alongside the other
    phases rather than mixing direct function calls into the orchestrator.
    """

    @classmethod
    def build(cls, ctx: BuildContext) -> None:
        for tg in build_table_groups(
            ctx.tables.values(), ctx.config.grouping, namespaces=ctx.table_namespaces
        ):
            ctx.db.add(tg)
