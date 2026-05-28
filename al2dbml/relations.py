"""AL ``TableRelation`` parsers.

Pure string-level parsers that extract structured tuples from the raw AL
``TableRelation`` property forms. Used by the generator's reference resolution
stage; isolated here so each parser can be tested without instantiating a
whole :class:`~al2dbml.diagram.Diagram`.

The shapes we handle:

- ``"Customer"."No."`` — quoted qualified
- ``Customer.No.`` — bare qualified
- ``Customer`` — bare table only (target field falls back to PK at resolve time)
- ``"Customer"."No." WHERE("Blocked"=CONST(" "))`` — with WHERE filter
- ``IF (Cond1) Tbl1."f1" ELSE IF (Cond2) Tbl2."f2" ELSE Tbl3."f3"`` — conditional
- Dict / list forms produced by some AL compiler versions
"""

from __future__ import annotations

import re
from typing import Any

_IDENT_RE = re.compile(r'\s*(?:"([^"]+)"|([A-Za-z_]\w*))\s*')
_WHERE_RE = re.compile(r"\bWHERE\s*\(", re.IGNORECASE)
_LEADING_IF_RE = re.compile(r"^\s*IF\b", re.IGNORECASE)
_IF_HEAD_RE = re.compile(r"\s*(?:ELSE\s+)?IF\s*\(", re.IGNORECASE)
_ELSE_HEAD_RE = re.compile(r"\s*ELSE\b", re.IGNORECASE)
_NEXT_ELSE_RE = re.compile(r"\bELSE\b", re.IGNORECASE)
_WHITESPACE_RUN = re.compile(r"\s+")


def _normalize_clause(text: str) -> str:
    """Collapse internal whitespace in a captured parenthesised clause.

    AL source sometimes wraps long ``IF`` or ``WHERE`` clauses across many
    lines with continuation indent; capturing the slice verbatim leaks that
    formatting into Ref comments and column notes. Collapsing every
    whitespace run to a single space gives downstream consumers a clean
    single-line string to work with — the Ref-comment renderer can then
    reformat it into a multi-line block deliberately, instead of inheriting
    the source layout.
    """
    return _WHITESPACE_RUN.sub(" ", text).strip()


def find_matching_paren(text: str, open_index: int) -> int:
    """Return the index of the ``)`` that matches the ``(`` at ``open_index``.

    Returns ``-1`` when no matching close paren exists.
    """
    depth = 0
    for i in range(open_index, len(text)):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def parse_qualified(text: str) -> tuple[str | None, str | None]:
    """Parse ``Table.Field`` / ``"Table"."Field"`` / bare ``Table`` into a tuple.

    Either side may be quoted (so a field name containing a period like
    ``"No."`` survives intact). Returns ``(None, None)`` for unparseable input
    and ``(Table, None)`` for table-only references.
    """
    text = text.strip()
    if not text:
        return (None, None)
    first_match = _IDENT_RE.match(text)
    if not first_match:
        return (None, None)
    first = first_match.group(1) or first_match.group(2)
    rest = text[first_match.end() :]
    if not rest.startswith("."):
        return (first, None)
    rest = rest[1:]
    second_match = _IDENT_RE.match(rest)
    if not second_match:
        return (first, None)
    second = second_match.group(1) or second_match.group(2)
    return (first, second)


def parse_relation_string(
    value: Any,
) -> tuple[str | None, str | None, str | None]:
    """Parse a non-conditional AL ``TableRelation`` value.

    Returns ``(table, field, condition)`` where ``condition`` is the
    parenthesised expression that follows ``WHERE`` (without the keyword),
    or ``None`` when no ``WHERE`` clause is present.

    For dict / list inputs (some AL compiler versions wrap the relation in a
    structured form) we read the ``Table`` / ``Field`` / ``Condition`` keys
    directly and skip the string-level parsing entirely.
    """
    if isinstance(value, dict):
        return (
            value.get("Table") or value.get("TableName"),
            value.get("Field") or value.get("FieldName"),
            value.get("Condition"),
        )
    if isinstance(value, list):
        return parse_relation_string(value[0] if value else "")

    text = str(value).strip()
    if not text:
        return (None, None, None)

    condition: str | None = None
    match = _WHERE_RE.search(text)
    if match:
        paren_start = match.end() - 1
        end_index = find_matching_paren(text, paren_start)
        if end_index == -1:
            end_index = len(text) - 1
        condition = _normalize_clause(text[paren_start : end_index + 1])
        text = text[: match.start()].strip()

    table, field_name = parse_qualified(text)
    return table, field_name, condition


def parse_conditional_relation(
    value: Any,
) -> list[tuple[str | None, str | None, str | None, str | None]] | None:
    """Parse an AL ``IF (...) Tbl.Field ELSE IF (...) ... ELSE ...`` relation.

    Returns one tuple per branch of ``(if_condition, target_table,
    target_field, where_condition)``. ``if_condition`` is ``None`` for a
    trailing bare ``ELSE`` default branch. Returns ``None`` when ``value`` is
    not a string or does not start with the ``IF`` keyword, so callers can
    fall back to :func:`parse_relation_string` for the regular form.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not _LEADING_IF_RE.match(text):
        return None

    branches: list[tuple[str | None, str | None, str | None, str | None]] = []
    pos = 0
    while pos < len(text):
        if_head = _IF_HEAD_RE.match(text, pos)
        if if_head:
            open_paren = if_head.end() - 1
            close_paren = find_matching_paren(text, open_paren)
            if close_paren == -1:
                return branches or None
            if_cond = _normalize_clause(text[open_paren : close_paren + 1])
            pos = close_paren + 1
            next_else = _NEXT_ELSE_RE.search(text, pos)
            if next_else:
                ref_chunk = text[pos : next_else.start()]
                pos = next_else.start()
            else:
                ref_chunk = text[pos:]
                pos = len(text)
            table, field_name, where = parse_relation_string(ref_chunk)
            branches.append((if_cond, table, field_name, where))
            continue
        else_head = _ELSE_HEAD_RE.match(text, pos)
        if else_head:
            ref_chunk = text[else_head.end() :]
            table, field_name, where = parse_relation_string(ref_chunk)
            branches.append((None, table, field_name, where))
            break
        break
    return branches or None
