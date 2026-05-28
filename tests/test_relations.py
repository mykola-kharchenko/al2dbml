from __future__ import annotations

import pytest

from al2dbml.relations import (
    find_matching_paren,
    parse_conditional_relation,
    parse_qualified,
    parse_relation_string,
)

# ---------------------------------------------------------------------------
# parse_qualified
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ('"Customer"."No."', ("Customer", "No.")),
        ('"Sales Header"."Document Type"', ("Sales Header", "Document Type")),
        ("Customer.No.", ("Customer", "No")),
        ("Customer", ("Customer", None)),
        ('"Customer"', ("Customer", None)),
        ("", (None, None)),
        ("   ", (None, None)),
    ],
)
def test_parse_qualified(text: str, expected: tuple[str | None, str | None]) -> None:
    assert parse_qualified(text) == expected


# ---------------------------------------------------------------------------
# find_matching_paren
# ---------------------------------------------------------------------------


def test_find_matching_paren_simple() -> None:
    text = "(abc)"
    assert find_matching_paren(text, 0) == 4


def test_find_matching_paren_nested() -> None:
    text = "(a(b)c)"
    assert find_matching_paren(text, 0) == 6


def test_find_matching_paren_unmatched_returns_minus_one() -> None:
    text = "(abc"
    assert find_matching_paren(text, 0) == -1


def test_find_matching_paren_starts_mid_string() -> None:
    text = "abc(de)f"
    assert find_matching_paren(text, 3) == 6


# ---------------------------------------------------------------------------
# parse_relation_string
# ---------------------------------------------------------------------------


def test_parse_relation_string_quoted_qualified() -> None:
    assert parse_relation_string('"Customer"."No."') == ("Customer", "No.", None)


def test_parse_relation_string_bare_table_only() -> None:
    assert parse_relation_string("Customer") == ("Customer", None, None)


def test_parse_relation_string_with_where_clause() -> None:
    table, field, cond = parse_relation_string('"Customer"."No." WHERE("Blocked"=CONST(" "))')
    assert table == "Customer"
    assert field == "No."
    assert cond == '("Blocked"=CONST(" "))'


def test_parse_relation_string_strips_where_keyword_from_condition() -> None:
    # The returned condition must NOT include the WHERE keyword itself.
    _, _, cond = parse_relation_string('Tbl."f" WHERE("X"=CONST(""))')
    assert cond is not None
    assert "WHERE" not in cond
    assert cond.startswith("(") and cond.endswith(")")


def test_parse_relation_string_nested_parens_in_condition() -> None:
    table, field, cond = parse_relation_string(
        'Item."No." WHERE(Type=CONST(Item),Blocked=CONST(FALSE))'
    )
    assert table == "Item"
    assert field == "No."
    assert cond == "(Type=CONST(Item),Blocked=CONST(FALSE))"


def test_parse_relation_string_dict_form() -> None:
    result = parse_relation_string(
        {"Table": "Customer", "Field": "No.", "Condition": '("Blocked"=CONST(""))'}
    )
    assert result == ("Customer", "No.", '("Blocked"=CONST(""))')


def test_parse_relation_string_dict_with_alternative_keys() -> None:
    # Some AL compiler versions use TableName / FieldName instead of Table / Field.
    result = parse_relation_string({"TableName": "Customer", "FieldName": "No."})
    assert result == ("Customer", "No.", None)


def test_parse_relation_string_list_form_takes_first_entry() -> None:
    assert parse_relation_string(['"Customer"."No."']) == ("Customer", "No.", None)


def test_parse_relation_string_empty_inputs() -> None:
    assert parse_relation_string("") == (None, None, None)
    assert parse_relation_string("   ") == (None, None, None)
    assert parse_relation_string([]) == (None, None, None)


# ---------------------------------------------------------------------------
# parse_conditional_relation
# ---------------------------------------------------------------------------


def test_parse_conditional_relation_single_if() -> None:
    branches = parse_conditional_relation('IF (Type=CONST(Item)) Item."No."')
    assert branches == [("(Type=CONST(Item))", "Item", "No.", None)]


def test_parse_conditional_relation_two_branches() -> None:
    branches = parse_conditional_relation(
        'IF (Type=CONST(Item)) Item."No." ELSE IF (Type=CONST(Resource)) Resource."No."'
    )
    assert branches == [
        ("(Type=CONST(Item))", "Item", "No.", None),
        ("(Type=CONST(Resource))", "Resource", "No.", None),
    ]


def test_parse_conditional_relation_default_else_branch_has_no_condition() -> None:
    branches = parse_conditional_relation('IF (Cond1) "T1"."f1" ELSE "T2"."f2"')
    assert branches is not None
    assert len(branches) == 2
    assert branches[0] == ("(Cond1)", "T1", "f1", None)
    # ELSE branch has if_condition = None (no IF keyword precedes it).
    assert branches[1][0] is None
    assert branches[1][1:3] == ("T2", "f2")


def test_parse_conditional_relation_per_branch_where() -> None:
    branches = parse_conditional_relation('IF (T=CONST(A)) Tbl."F" WHERE("X"=CONST(""))')
    assert branches is not None
    if_cond, table, field, where = branches[0]
    assert if_cond == "(T=CONST(A))"
    assert table == "Tbl"
    assert field == "F"
    assert where == '("X"=CONST(""))'


def test_parse_conditional_relation_returns_none_for_non_if_input() -> None:
    # Non-IF strings should signal "not my problem, use parse_relation_string".
    assert parse_conditional_relation('"Customer"."No."') is None
    assert parse_conditional_relation("Customer.No.") is None
    assert parse_conditional_relation("") is None


def test_parse_conditional_relation_returns_none_for_non_string_input() -> None:
    assert parse_conditional_relation(None) is None
    assert parse_conditional_relation({"Table": "X"}) is None
    assert parse_conditional_relation(123) is None


# ---------------------------------------------------------------------------
# Whitespace normalisation on captured clauses
# ---------------------------------------------------------------------------


def test_parse_relation_string_normalises_multiline_where_clause() -> None:
    # AL sometimes wraps a long TableRelation across multiple lines with
    # continuation indent; capturing the slice verbatim used to leak the
    # source layout into Ref comments. The parser now collapses every
    # whitespace run to a single space so downstream consumers get a
    # single-line clause they can reformat deliberately.
    raw = (
        'Customer."No." WHERE("Contract Type" = const(Contract),\n'
        '                    "Customer No." = field("Customer No."),\n'
        '                    "Ship-to Code" = field("Ship-to Code"))'
    )
    table, field, condition = parse_relation_string(raw)
    assert table == "Customer"
    assert field == "No."
    assert condition is not None
    assert "\n" not in condition
    assert condition == (
        '("Contract Type" = const(Contract), '
        '"Customer No." = field("Customer No."), '
        '"Ship-to Code" = field("Ship-to Code"))'
    )


def test_parse_conditional_relation_normalises_if_clause_whitespace() -> None:
    raw = 'IF ("Document Type"\n      = CONST(Order)) Tbl."F"'
    branches = parse_conditional_relation(raw)
    assert branches is not None
    if_cond, _table, _field, _where = branches[0]
    assert if_cond == '("Document Type" = CONST(Order))'
