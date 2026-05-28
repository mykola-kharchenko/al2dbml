"""Table + column build phase.

Constructs pydbml ``Table`` and ``Column`` objects from the ``Tables``
section of a normalized symbols document. Collects deferred references
into ``ctx.pending_refs`` for later resolution by
:mod:`al2dbml._build.references`.
"""

from __future__ import annotations

from typing import Any

from pydbml.classes import Column, Note, Table

from .. import properties, relations
from ..types import map_al_type
from .context import BuildContext, _PendingRef


class TableBuilder:
    """Builds the ``Table``/``Column`` graph and queues pending references."""

    @classmethod
    def build(cls, ctx: BuildContext) -> None:
        for table_def in ctx.symbols.get("Tables") or []:
            name = table_def.get("Name")
            if not name:
                continue
            table = cls._make_table(ctx, table_def)
            ctx.tables[name] = table
            ctx.table_namespaces[name] = str(table_def.get("__namespace") or "")
            ctx.db.add(table)

    @classmethod
    def _make_table(cls, ctx: BuildContext, table_def: dict[str, Any]) -> Table:
        name = table_def["Name"]
        props = properties.normalize(table_def.get("Properties"))
        caption = props.get("Caption")
        # aldoc summary (sourced from AL /// <summary> doc comments) is
        # strictly richer prose than the bare Caption; prefer it when present.
        # pydbml.Table(note=None) is equivalent to omitting the kwarg.
        table_note = ctx.config.docs.table_summaries.get(name) or caption
        table = Table(name=name, schema=ctx.config.table_schema, note=table_note)

        keys = table_def.get("Keys") or []
        pk_names: set[str] = set()
        if keys and isinstance(keys, list):
            first_key = keys[0]
            if isinstance(first_key, dict):
                pk_names = set(first_key.get("FieldNames") or [])

        for f in table_def.get("Fields") or []:
            col = cls.build_column(ctx, name, f, pk_names)
            if col is not None:
                table.add_column(col)
                ctx.columns[(name, col.name)] = col

        # Single-field secondary keys imply uniqueness; multi-field keys are
        # deliberately deferred to a future "secondary keys as indexes" slice.
        for key in keys[1:] if isinstance(keys, list) else []:
            if not isinstance(key, dict):
                continue
            field_names = key.get("FieldNames") or []
            if len(field_names) != 1:
                continue
            sole = field_names[0]
            col = ctx.columns.get((name, sole))
            if col is not None and not col.pk:
                col.unique = True

        return table

    @staticmethod
    def build_column(
        ctx: BuildContext,
        table_name: str,
        field_def: dict[str, Any],
        pk_names: set[str],
    ) -> Column | None:
        """Construct one ``Column`` from an AL field definition.

        Side effect: appends deferred ``_PendingRef`` entries to
        ``ctx.pending_refs`` for any ``TableRelation`` clauses on the field.
        Returns ``None`` for fields without a usable ``Name``.

        Shared by :meth:`TableBuilder.build` (from the table-fields loop) and
        :class:`al2dbml._build.extensions.ExtensionBuilder` (from both the
        merge and stub branches); column construction is the truly stateless
        inner loop common to table and extension paths.
        """
        fname = field_def.get("Name")
        if not fname:
            return None

        type_def = field_def.get("TypeDefinition") or {}
        type_str = map_al_type(field_def)
        col_type: Any = type_str
        if str(type_def.get("Name") or "").lower() == "enum":
            subtype_name = (type_def.get("Subtype") or {}).get("Name")
            if subtype_name and subtype_name in ctx.enums:
                col_type = ctx.enums[subtype_name]

        is_pk = fname in pk_names
        field_props = properties.normalize(field_def.get("Properties"))
        # AL spells the non-nullable signal as 'NotBlank'; tolerate 'NotNull' too.
        # DBML PK already implies not-null, so don't double-mark PK columns.
        not_null = not is_pk and bool(field_props.get("NotBlank") or field_props.get("NotNull"))

        col = Column(name=fname, type=col_type, pk=is_pk, not_null=not_null)

        notes_parts: list[str] = []

        # aldoc description (when --docs supplies one) is the richest prose
        # available: it comes from the AL ToolTip property and /// XML doc
        # comments parsed by the real AL compiler. It takes priority over
        # Caption, which is then suppressed entirely as redundant.
        aldoc_description = ctx.config.docs.field_descriptions.get((table_name, fname))
        if aldoc_description:
            notes_parts.append(aldoc_description)

        caption = field_props.get("Caption")
        # Skip caption when it just restates the field name (~96% of Base
        # Application fields), and also when an aldoc description has already
        # claimed the leading slot.
        if not aldoc_description and caption and str(caption) != fname:
            notes_parts.append(str(caption))

        relation = field_props.get("TableRelation") or field_def.get("TableRelation")
        if relation:
            branches = relations.parse_conditional_relation(relation)
            if branches is not None:
                branch_parts: list[str] = []
                for if_cond, br_table, br_field, br_where in branches:
                    if br_table:
                        ctx.pending_refs.append(
                            _PendingRef(
                                source_table=table_name,
                                source_field=fname,
                                target_table=br_table,
                                target_field=br_field,
                                condition=br_where,
                                if_condition=if_cond,
                            )
                        )
                    label = (
                        f'{br_table}."{br_field}"'
                        if (br_table and br_field)
                        else (br_table or "?")
                    )
                    head = f"`IF {if_cond}`" if if_cond else "`ELSE`"
                    piece = f"{head} → `{label}`"
                    if br_where:
                        piece += f" where `{br_where}`"
                    branch_parts.append(piece)
                if branch_parts:
                    # HTML <br> renders as a visible line break in dbdiagram/
                    # dbdocs Markdown without triggering pydbml's multi-line
                    # indent bug; one branch per visual line is much more
                    # readable than the 6-branch one-liners on real BC fields.
                    bullets = "<br>".join(f"• {p}" for p in branch_parts)
                    notes_parts.append(f"**Conditional reference:**<br>{bullets}")
            else:
                target_table, target_field, condition = relations.parse_relation_string(relation)
                if target_table:
                    ctx.pending_refs.append(
                        _PendingRef(
                            source_table=table_name,
                            source_field=fname,
                            target_table=target_table,
                            target_field=target_field,
                            condition=condition,
                        )
                    )
                    if condition:
                        notes_parts.append(f"**Condition:** `{condition}`")

        if notes_parts:
            # Single physical line (avoids pydbml's textwrap.indent breaking
            # Markdown inside multi-line [note: '''...''']); '<br><br>' renders
            # as a paragraph-style gap in dbdiagram/dbdocs Markdown so sections
            # (caption / condition / references) look visually separated.
            col.note = Note("<br><br>".join(notes_parts))
        return col
