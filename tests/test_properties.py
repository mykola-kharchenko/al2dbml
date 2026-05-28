from __future__ import annotations

from al2dbml.properties import normalize


def test_normalize_none_returns_empty_dict() -> None:
    assert normalize(None) == {}


def test_normalize_empty_list_returns_empty_dict() -> None:
    assert normalize([]) == {}


def test_normalize_empty_dict_returns_empty_dict() -> None:
    assert normalize({}) == {}


def test_normalize_plain_dict_passes_through() -> None:
    # Older AL compiler shape: a flat dict. Returns a shallow copy so callers
    # can mutate freely without leaking back into the symbols document.
    raw = {"Caption": "Customer", "NotBlank": True}
    result = normalize(raw)
    assert result == {"Caption": "Customer", "NotBlank": True}
    assert result is not raw  # shallow copy


def test_normalize_returned_dict_is_isolated_from_input() -> None:
    # Pins the shallow-copy contract from the docstring: mutating the
    # returned dict must not bleed back into the input dict.
    raw = {"Caption": "Customer"}
    result = normalize(raw)
    result["new_key"] = "added"
    assert "new_key" not in raw
    del result["Caption"]
    assert raw == {"Caption": "Customer"}


def test_normalize_list_of_name_value_dicts() -> None:
    # Current AL compiler shape (BC v25+).
    raw = [
        {"Name": "Caption", "Value": "Customer"},
        {"Name": "NotBlank", "Value": True},
    ]
    assert normalize(raw) == {"Caption": "Customer", "NotBlank": True}


def test_normalize_list_silently_skips_non_dict_entries() -> None:
    raw = [
        {"Name": "Caption", "Value": "X"},
        "not a dict",
        42,
        {"Name": "Other", "Value": "Y"},
    ]
    assert normalize(raw) == {"Caption": "X", "Other": "Y"}


def test_normalize_list_entry_without_name_is_skipped() -> None:
    # An entry without a 'Name' key carries no information; drop it silently.
    raw = [{"Value": "no key"}, {"Name": "ok", "Value": "kept"}]
    assert normalize(raw) == {"ok": "kept"}


def test_normalize_list_entry_with_missing_value_yields_none() -> None:
    # An entry with 'Name' but no 'Value' maps to None — the caller decides
    # whether None means "explicitly absent" or "empty".
    raw = [{"Name": "Caption"}]
    assert normalize(raw) == {"Caption": None}


def test_normalize_unknown_shape_returns_empty_dict() -> None:
    # Permissive fallback: AL compiler versions vary; never raise.
    assert normalize("a string") == {}
    assert normalize(42) == {}
    assert normalize(object()) == {}
