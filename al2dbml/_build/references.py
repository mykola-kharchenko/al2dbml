r"""Reference resolution phase.

Converts the ``_PendingRef`` entries collected by
:class:`al2dbml._build.tables.TableBuilder` and
:class:`al2dbml._build.extensions.ExtensionBuilder` into pydbml ``Reference``
objects on the database. Handles three kinds of degradation:

- **Cross-package targets** (target table not in this package): degrade to
  a ``**References** \`X\` (cross-package)`` note on the source column.
- **Targets with no PK**: degrade to a ``**References** \`X.f\``` note.
- **Self-references** (``T.f > T.f``): silently dropped.

Plus several dedupes — see method docstrings below.
"""

from __future__ import annotations

from pydbml.classes import Column, Note, Reference

from .context import BuildContext


class ReferenceResolver:
    """Resolves ``_PendingRef`` entries into ``Reference`` objects.

    Bypasses ``pydbml.Database.add_reference``'s built-in duplicate check
    (which is O(n) per add via recursive ``__eq__`` and ballooned build time
    to several minutes on Base Application's ~8k refs). We dedupe by
    ``(id(source_col), id(target_col))`` ourselves, then inline the cheap
    parts of ``add_reference`` directly.
    """

    @classmethod
    def resolve(cls, ctx: BuildContext) -> None:
        # Pair-level dedupe of resolved Refs.
        seen: set[tuple[int, int]] = set()
        # Note-level dedupe: a 6-branch IF/ELSE all pointing at the same
        # missing target leaves one '**References** X (cross-package)' note
        # per column, not six.
        noted_targets: dict[int, set[str]] = {}

        for ref in ctx.pending_refs:
            source_col = ctx.columns.get((ref.source_table, ref.source_field))
            if source_col is None:
                continue

            target_table = ctx.tables.get(ref.target_table)
            if target_table is None:
                cls._note_unresolved(
                    source_col,
                    noted_targets,
                    target=ref.target_table,
                    field=ref.target_field,
                    kind="cross-package",
                )
                continue

            target_col = None
            if ref.target_field is not None:
                target_col = ctx.columns.get((ref.target_table, ref.target_field))
            if target_col is None:
                pk_cols = [c for c in target_table.columns if c.pk]
                if not pk_cols:
                    cls._note_unresolved(
                        source_col,
                        noted_targets,
                        target=ref.target_table,
                        field=ref.target_field,
                        kind="pkless",
                    )
                    continue
                target_col = pk_cols[0]

            if source_col is target_col:
                # Self-referential TableRelation (some BC tables declare a
                # field that references itself, e.g. 'refers to original').
                # Skip emitting a no-op Ref that just adds visual noise.
                continue
            key = (id(source_col), id(target_col))
            if key in seen:
                continue
            seen.add(key)

            # Carry the IF condition and any WHERE filter onto the Ref itself
            # as a pydbml comment, which renders as a '//' line above the
            # Ref { } block in DBML. The diagram thus shows *why* each arrow
            # exists when a column has multiple conditional branches.
            comment_parts: list[str] = []
            if ref.if_condition:
                comment_parts.append(f"when {ref.if_condition}")
            if ref.condition:
                comment_parts.append(f"where {ref.condition}")
            comment = "; ".join(comment_parts) if comment_parts else None

            ref_obj = Reference(type=">", col1=source_col, col2=target_col, comment=comment)
            ref_obj.database = ctx.db
            ctx.db.refs.append(ref_obj)

    @staticmethod
    def _note_unresolved(
        source_col: Column,
        noted_targets: dict[int, set[str]],
        *,
        target: str,
        field: str | None,
        kind: str,
    ) -> None:
        """Append a '**References** ...' note to ``source_col``, deduped per column.

        ``kind`` distinguishes 'cross-package' (target table absent) from
        'pkless' (target present but no PK to point at); only the former
        gets the '(cross-package)' suffix on the rendered note.
        """
        target_label = f'`{target}."{field}"`' if field else f"`{target}`"
        suffix = " (cross-package)" if kind == "cross-package" else ""
        key_label = f"{kind}:{target_label}"
        col_noted = noted_targets.setdefault(id(source_col), set())
        if key_label in col_noted:
            return
        col_noted.add(key_label)
        line = f"**References** {target_label}{suffix}"
        existing = source_col.note.text if source_col.note else ""
        # '<br><br>' renders as a paragraph gap in dbdiagram/dbdocs Markdown;
        # plain '\n' breaks because pydbml's textwrap.indent prepends 4 spaces
        # to continuation lines, which Markdown then treats as a code block.
        source_col.note = Note(f"{existing}<br><br>{line}" if existing else line)
