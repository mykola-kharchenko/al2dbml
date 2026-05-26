from __future__ import annotations

import pytest
from pydbml.classes import Table

from al2dbml.grouping import GroupingConfig, build_table_groups, parse_rule_strings


def _t(name: str) -> Table:
    return Table(name=name)


def test_auto_fallback_groups_by_first_word() -> None:
    config = GroupingConfig()
    groups = build_table_groups([_t("Sales Header"), _t("Sales Line")], config)

    assert [g.name for g in groups] == ["Sales"]
    assert {t.name for t in groups[0].items} == {"Sales Header", "Sales Line"}


def test_min_group_size_drops_singletons() -> None:
    config = GroupingConfig()
    groups = build_table_groups([_t("Customer")], config)
    assert groups == []


def test_explicit_rule_takes_precedence_over_auto() -> None:
    config = GroupingConfig(rules={"Documents": ["Sales*", "Purch*"]})
    groups = build_table_groups(
        [_t("Sales Header"), _t("Sales Line"), _t("Purchase Header")],
        config,
    )

    assert [g.name for g in groups] == ["Documents"]
    assert {t.name for t in groups[0].items} == {
        "Sales Header",
        "Sales Line",
        "Purchase Header",
    }


def test_first_matching_rule_wins() -> None:
    config = GroupingConfig(
        rules={"Sales": ["Sales*"], "Documents": ["Sales*"]},
    )
    groups = build_table_groups([_t("Sales Header"), _t("Sales Line")], config)

    assert [g.name for g in groups] == ["Sales"]


def test_no_auto_fallback_drops_unmatched_tables() -> None:
    config = GroupingConfig(rules={"Sales": ["Sales*"]}, auto_fallback=False)
    groups = build_table_groups(
        [_t("Sales Header"), _t("Sales Line"), _t("Customer")],
        config,
    )

    assert [g.name for g in groups] == ["Sales"]
    assert {t.name for t in groups[0].items} == {"Sales Header", "Sales Line"}


def test_disabled_yields_empty_list() -> None:
    config = GroupingConfig(enabled=False)
    assert build_table_groups([_t("Sales Header"), _t("Sales Line")], config) == []


def test_groups_returned_sorted_by_name() -> None:
    config = GroupingConfig()
    groups = build_table_groups(
        [
            _t("Sales Header"),
            _t("Sales Line"),
            _t("Purchase Header"),
            _t("Purchase Line"),
        ],
        config,
    )

    assert [g.name for g in groups] == ["Purchase", "Sales"]


def test_min_group_size_one_keeps_singletons() -> None:
    config = GroupingConfig(min_group_size=1)
    groups = build_table_groups([_t("Customer")], config)
    assert [g.name for g in groups] == ["Customer"]


def test_parse_rule_strings_single_pattern() -> None:
    assert parse_rule_strings(["Sales=Sales*"]) == {"Sales": ["Sales*"]}


def test_parse_rule_strings_multiple_patterns() -> None:
    assert parse_rule_strings(["Sales=Sales*,SO*"]) == {"Sales": ["Sales*", "SO*"]}


def test_parse_rule_strings_merges_duplicates() -> None:
    parsed = parse_rule_strings(["Docs=Sales*", "Docs=Purch*"])
    assert parsed == {"Docs": ["Sales*", "Purch*"]}


def test_parse_rule_strings_trims_whitespace() -> None:
    assert parse_rule_strings(["  Sales = Sales* , SO*  "]) == {
        "Sales": ["Sales*", "SO*"]
    }


@pytest.mark.parametrize("bad", ["=foo", "Sales=", "Sales", "Sales=,,"])
def test_parse_rule_strings_rejects_malformed(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_rule_strings([bad])
