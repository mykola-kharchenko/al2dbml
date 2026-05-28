from __future__ import annotations

from pathlib import Path

import pytest

from al2dbml.aldoc import (
    AldocDocs,
    _extract_base_table_name,
    _unquote,
    load_docs,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "aldoc_sample"


def test_load_docs_indexes_table_summary_and_field_descriptions() -> None:
    docs = load_docs(_FIXTURE)
    assert docs.table_summaries["Test Table"] == "A test table for fixtures."
    assert (
        docs.field_descriptions[("Test Table", "No.")]
        == "Specifies the unique number of the record."
    )


def test_load_docs_handles_multiline_folded_description() -> None:
    # YAML folded scalar (>-) produces a single string with embedded newlines.
    docs = load_docs(_FIXTURE)
    desc = docs.field_descriptions[("Test Table", "Description")]
    assert desc.startswith("A multi-line description.")
    assert "additional context on a second paragraph" in desc


def test_load_docs_skips_fields_without_description() -> None:
    docs = load_docs(_FIXTURE)
    assert ("Test Table", "Flag No Description") not in docs.field_descriptions


def test_load_docs_handles_legacy_non_namespaced_tables() -> None:
    # Legacy table file with no 'namespace' key and no top-level 'summary';
    # the field index still picks up its fields.
    docs = load_docs(_FIXTURE)
    assert ("Legacy Table", "Counter") in docs.field_descriptions
    # No summary entry for this table because the YAML didn't provide one.
    assert "Legacy Table" not in docs.table_summaries


def test_load_docs_indexes_extension_fields_under_base_table() -> None:
    # The TableExtension YAML extends "Test Table"; its added field must be
    # indexed under the base table, not under the extension object.
    docs = load_docs(_FIXTURE)
    assert ("Test Table", "Extra Code") in docs.field_descriptions
    # And it should not leak under the extension's own name.
    assert ("Test Extension", "Extra Code") not in docs.field_descriptions


def test_load_docs_strips_field_name_quotes() -> None:
    # aldoc emits names as '"Foo"'; ours should be just 'Foo'.
    docs = load_docs(_FIXTURE)
    keys = {fname for _table, fname in docs.field_descriptions}
    assert "No." in keys  # period-trailing names preserved
    assert '"No."' not in keys


def test_load_docs_raises_for_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_docs(tmp_path / "does-not-exist")


def test_load_docs_expands_tilde_in_path(tmp_path: Path, monkeypatch) -> None:
    # Python API parity with the CLI: '~/...' paths should expand before
    # the is_dir() check fires.
    monkeypatch.setenv("HOME", str(tmp_path))
    docs_dir = tmp_path / "empty-docs"
    docs_dir.mkdir()
    # No tables/extensions inside; the directory just needs to resolve.
    result = load_docs("~/empty-docs")
    assert isinstance(result, AldocDocs)


def test_load_docs_returns_empty_when_no_reference_subtree(tmp_path: Path) -> None:
    # Directory exists but has no reference/*/Table/ structure inside.
    docs = load_docs(tmp_path)
    assert isinstance(docs, AldocDocs)
    assert not docs.table_summaries
    assert not docs.field_descriptions


@pytest.mark.parametrize(
    "raw, expected",
    [
        ('"Sales Header"', "Sales Header"),
        ('"No."', "No."),  # trailing period preserved
        ("UnquotedToken", "UnquotedToken"),
        ("", None),
        (None, None),
        (" '\"With Surrounding Spaces\"' ", "'\"With Surrounding Spaces\"'"),
        # Single dangling quote — too short to be a quoted form, returned verbatim.
        ('"', '"'),
    ],
)
def test_unquote_helper(raw, expected) -> None:
    assert _unquote(raw) == expected


def test_extract_base_table_name_from_namespaced_extends() -> None:
    assert _extract_base_table_name({"name": 'Microsoft.Finance.Currency."Foo Bar"'}) == "Foo Bar"


def test_extract_base_table_name_from_legacy_extends() -> None:
    assert _extract_base_table_name({"name": '"Foo Bar"'}) == "Foo Bar"


def test_extract_base_table_name_handles_missing_name() -> None:
    assert _extract_base_table_name({}) is None
    assert _extract_base_table_name(None) is None
