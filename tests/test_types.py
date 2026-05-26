from __future__ import annotations

from typing import Any

import pytest

from al2dbml.types import _first_int, map_al_type


def _field(name: str, *, args: list[Any] | None = None, subtype: str | None = None) -> dict:
    type_def: dict[str, Any] = {"Name": name}
    if args is not None:
        type_def["TypeArguments"] = args
    if subtype is not None:
        type_def["Subtype"] = {"Name": subtype}
    return {"TypeDefinition": type_def}


@pytest.mark.parametrize(
    "field, expected",
    [
        (_field("Code", args=[20]), "varchar(20)"),
        (_field("Text", args=[50]), "varchar(50)"),
        (_field("Code"), "varchar"),
        (_field("Text"), "varchar"),
        (_field("Integer"), "int"),
        (_field("BigInteger"), "bigint"),
        (_field("Decimal"), "decimal"),
        (_field("Boolean"), "boolean"),
        (_field("Date"), "date"),
        (_field("Time"), "time"),
        (_field("DateTime"), "datetime"),
        (_field("Duration"), "bigint"),
        (_field("Guid"), "uuid"),
        (_field("RecordId"), "varchar"),
        (_field("Blob"), "blob"),
        (_field("Media"), "uuid"),
        (_field("MediaSet"), "uuid"),
        (_field("Option"), "varchar"),
        (_field("Enum", subtype="Customer Type"), '"Customer Type"'),
        (_field("Enum"), "varchar"),
        (_field("Variant"), "variant"),
    ],
)
def test_map_al_type(field: dict, expected: str) -> None:
    assert map_al_type(field) == expected


def test_case_insensitive_type_lookup() -> None:
    assert map_al_type(_field("INTEGER")) == "int"
    assert map_al_type(_field("dateTime")) == "datetime"


@pytest.mark.parametrize("args", [None, [], ["abc"], [None]])
def test_code_text_without_usable_length(args: list[Any] | None) -> None:
    assert map_al_type(_field("Code", args=args)) == "varchar"
    assert map_al_type(_field("Text", args=args)) == "varchar"


def test_code_text_picks_first_int_when_args_mixed() -> None:
    assert map_al_type(_field("Code", args=["x", "30", 40])) == "varchar(30)"


def test_falls_back_to_root_type_field() -> None:
    assert map_al_type({"Type": "Integer"}) == "int"


def test_empty_field_returns_varchar() -> None:
    assert map_al_type({}) == "varchar"


def test_first_int_helper() -> None:
    assert _first_int([10]) == 10
    assert _first_int([None, "5", 7]) == 5
    assert _first_int(None) is None
    assert _first_int([]) is None
    assert _first_int("notalist") is None
    assert _first_int(["nope"]) is None
