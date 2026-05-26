from __future__ import annotations

from al2dbml.generator import Generator, _PendingRef
from al2dbml.grouping import GroupingConfig

from .fixtures.sample_symbols import sample_symbols


def _build(**kwargs) -> str:
    gen = Generator(symbols=sample_symbols(), **kwargs)
    return gen.dbml()


def test_enum_includes_extension_values() -> None:
    dbml = _build()
    assert 'Enum "Customer Type"' in dbml
    assert "Person" in dbml
    assert "Company" in dbml
    assert "Government" in dbml


def test_customer_table_contains_merged_extension_field() -> None:
    dbml = _build()
    # The extension field appears as a column on the base Customer table
    assert '"Loyalty Points" int' in dbml
    # And the Customer table block exists
    assert 'Table "Customer"' in dbml


def test_sales_header_references_customer_no() -> None:
    dbml = _build()
    # pydbml emits each reference as a ``Ref { ... }`` block
    assert "Ref {" in dbml
    assert '"Sales Header"."Sell-to Customer No." > "Customer"."No."' in dbml


def test_sales_line_references_sales_header_no() -> None:
    dbml = _build()
    assert '"Sales Line"."Document No." > "Sales Header"."No."' in dbml


def test_table_groups_emitted_for_sales_and_purchase() -> None:
    dbml = _build()
    assert 'TableGroup "Sales"' in dbml
    assert '"Sales Header"' in dbml
    assert '"Sales Line"' in dbml
    assert 'TableGroup "Purchase"' in dbml
    assert '"Purchase Header"' in dbml
    assert '"Purchase Line"' in dbml


def test_no_table_group_for_lone_customer() -> None:
    dbml = _build()
    assert 'TableGroup "Customer"' not in dbml


def test_conditional_relation_note_strips_where_keyword() -> None:
    dbml = _build()
    assert 'Condition: ("Blocked"=CONST(" "))' in dbml
    assert "WHERE(WHERE" not in dbml
    assert 'WHERE("Blocked"' not in dbml  # raw WHERE form should not survive


def test_merge_extensions_false_emits_stub_table() -> None:
    dbml = _build(merge_extensions=False)
    assert 'Table "Customer (Extension)"' in dbml
    assert '"Loyalty Points"' in dbml
    # The base Customer table should not have Loyalty Points
    customer_block_start = dbml.index('Table "Customer" ')
    customer_block_end = dbml.index("}", customer_block_start)
    customer_block = dbml[customer_block_start:customer_block_end]
    assert "Loyalty Points" not in customer_block


def test_cross_package_reference_does_not_crash_and_is_noted() -> None:
    dbml = _build()
    # Sales Line.Vendor No. -> Vendor (Vendor table is not in this fixture)
    assert '"Vendor No."' in dbml
    assert "Vendor" in dbml  # appears at least in note text
    assert "cross-package" in dbml.lower()


def test_disabled_grouping_emits_no_table_groups() -> None:
    dbml = _build(grouping=GroupingConfig(enabled=False))
    assert "TableGroup" not in dbml


def test_pending_refs_are_collected() -> None:
    gen = Generator(symbols=sample_symbols())
    gen.build()
    targets = {(r.source_table, r.source_field, r.target_table) for r in gen._pending_refs}
    assert ("Sales Header", "Sell-to Customer No.", "Customer") in targets
    assert ("Sales Line", "Document No.", "Sales Header") in targets
    assert ("Sales Line", "Vendor No.", "Vendor") in targets


def test_from_app_classmethod_has_docstring() -> None:
    # Smoke check: the public API is importable and documented.
    assert Generator.from_app.__doc__ is not None
    assert "compiled" in Generator.from_app.__doc__.lower()


def test_parse_relation_string_dict_form() -> None:
    table, field, cond = Generator._parse_relation_string(
        {"Table": "Customer", "Field": "No.", "Condition": '("Blocked"=CONST(""))'}
    )
    assert (table, field, cond) == (
        "Customer",
        "No.",
        '("Blocked"=CONST(""))',
    )


def test_parse_relation_string_quoted_qualified_with_where() -> None:
    table, field, cond = Generator._parse_relation_string(
        '"Customer"."No." WHERE("Blocked"=CONST(" "))'
    )
    assert table == "Customer"
    assert field == "No."
    assert cond == '("Blocked"=CONST(" "))'


def test_parse_relation_string_bare_table_only() -> None:
    table, field, cond = Generator._parse_relation_string("Customer")
    assert (table, field, cond) == ("Customer", None, None)


def test_parse_relation_string_nested_parens_in_condition() -> None:
    table, field, cond = Generator._parse_relation_string(
        'Item."No." WHERE(Type=CONST(Item),Blocked=CONST(FALSE))'
    )
    assert table == "Item"
    assert field == "No."
    assert cond == "(Type=CONST(Item),Blocked=CONST(FALSE))"


def test_pending_ref_dataclass_is_internal() -> None:
    # Sanity: the helper dataclass is exposed for tests only.
    ref = _PendingRef("A", "a", "B", "b", None)
    assert ref.target_table == "B"


def test_dbml_is_idempotent() -> None:
    gen = Generator(symbols=sample_symbols())
    first = gen.dbml()
    second = gen.dbml()
    assert first == second
