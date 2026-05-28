r"""Reference resolution phase.

Converts the ``PendingRef`` entries collected by
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


def _format_filter_clause(raw: str) -> str:
    """Format an AL filter expression for rendering as a Ref comment.

    Inputs come from :func:`al2dbml.relations.parse_relation_string` already
    whitespace-normalised, so they're a single-line string like
    ``("a"=CONST(X), "b"=FIELD("b"))`` — but on real Base Application fields
    that comma-separated list can be very long. Splitting it onto multiple
    indented lines joined with ``AND`` keeps the rendered ``// where ...``
    block readable without inventing meaning the source didn't carry.

    Single-condition clauses render unchanged (kept parens) so the simple
    case stays inline. Multi-condition clauses lose the outer parens — the
    indent + ``AND`` makes the grouping obvious without them.
    """
    text = raw.strip()
    if not (text.startswith("(") and text.endswith(")")):
        return text
    inner = text[1:-1].strip()
    parts: list[str] = []
    depth = 0
    last = 0
    for i, ch in enumerate(inner):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(inner[last:i].strip())
            last = i + 1
    parts.append(inner[last:].strip())
    parts = [p for p in parts if p]
    if len(parts) <= 1:
        return text
    return "\n  " + " AND\n  ".join(parts)


class ReferenceResolver:
    """Resolves ``PendingRef`` entries into ``Reference`` objects.

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
            # as a pydbml comment, which renders as '//' lines above the
            # Ref { } block in DBML. Multi-condition WHEREs from real Base
            # Application fields are reformatted by ``_format_filter_clause``
            # into an indented, AND-joined block instead of inheriting the
            # AL source's multi-line continuation indent verbatim. ``when``
            # and ``where`` go on separate lines when both are present.
            comment_parts: list[str] = []
            if ref.if_condition:
                clause = _format_filter_clause(ref.if_condition)
                sep = "" if clause.startswith("\n") else " "
                comment_parts.append(f"when{sep}{clause}")
            if ref.condition:
                clause = _format_filter_clause(ref.condition)
                sep = "" if clause.startswith("\n") else " "
                comment_parts.append(f"where{sep}{clause}")
            comment = "\n".join(comment_parts) if comment_parts else None

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
