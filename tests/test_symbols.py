from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from al2dbml.symbols import load_symbols


def _build_zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_load_plain_zip(tmp_path: Path) -> None:
    payload = json.dumps({"Tables": [], "Note": "hi"}).encode("utf-8")
    app = _write(tmp_path, "plain.app", _build_zip({"SymbolReference.json": payload}))

    assert load_symbols(app) == {"Tables": [], "Note": "hi"}


def test_load_strips_40_byte_al_header(tmp_path: Path) -> None:
    payload = json.dumps({"Tables": [1, 2, 3]}).encode("utf-8")
    zip_bytes = _build_zip({"SymbolReference.json": payload})
    header = b"\x00" * 40
    app = _write(tmp_path, "header.app", header + zip_bytes)

    assert load_symbols(app) == {"Tables": [1, 2, 3]}


def test_load_handles_utf8_bom(tmp_path: Path) -> None:
    payload = b"\xef\xbb\xbf" + json.dumps({"Tables": ["bom"]}).encode("utf-8")
    app = _write(tmp_path, "bom.app", _build_zip({"SymbolReference.json": payload}))

    assert load_symbols(app) == {"Tables": ["bom"]}


def test_load_is_case_insensitive(tmp_path: Path) -> None:
    payload = json.dumps({"Tables": ["case"]}).encode("utf-8")
    app = _write(tmp_path, "case.app", _build_zip({"symbolreference.JSON": payload}))

    assert load_symbols(app) == {"Tables": ["case"]}


def test_load_finds_symbol_in_subdirectory(tmp_path: Path) -> None:
    payload = json.dumps({"Tables": ["sub"]}).encode("utf-8")
    app = _write(
        tmp_path,
        "sub.app",
        _build_zip({"some/dir/SymbolReference.json": payload}),
    )

    assert load_symbols(app) == {"Tables": ["sub"]}


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_symbols(tmp_path / "nope.app")


def test_zip_without_symbol_reference_raises_key_error(tmp_path: Path) -> None:
    app = _write(tmp_path, "empty.app", _build_zip({"README.txt": b"hello"}))

    with pytest.raises(KeyError) as exc:
        load_symbols(app)
    assert "README.txt" in str(exc.value)


def test_path_argument_accepts_string(tmp_path: Path) -> None:
    payload = json.dumps({"Tables": ["str"]}).encode("utf-8")
    app = _write(tmp_path, "str.app", _build_zip({"SymbolReference.json": payload}))

    assert load_symbols(str(app)) == {"Tables": ["str"]}


def test_load_recurses_into_ready_to_run_nested_app(tmp_path: Path) -> None:
    # Ready-To-Run packages wrap the real .app inside an outer ZIP that also
    # carries a manifest and pre-compiled DLLs. The SymbolReference.json lives
    # in the nested .app, not at the top of the outer archive.
    inner_payload = json.dumps({"Tables": ["from-nested"]}).encode("utf-8")
    inner_app_bytes = _build_zip({"SymbolReference.json": inner_payload})
    outer = _build_zip(
        {
            "readytorunappmanifest.json": b"{}",
            "abcd1234_1.0.0.0_28_28014.app": inner_app_bytes,
            "publishedartifacts/some.dll": b"\x00\x01\x02",
            "[Content_Types].xml": b"<Types/>",
        }
    )
    app = _write(tmp_path, "r2r.app", outer)

    assert load_symbols(app) == {"Tables": ["from-nested"]}


def test_load_only_recurses_one_level_deep(tmp_path: Path) -> None:
    # Nested .app that itself has no SymbolReference.json should propagate
    # the KeyError, not recurse infinitely.
    empty_inner = _build_zip({"README.txt": b"no symbols here"})
    outer = _build_zip(
        {
            "readytorunappmanifest.json": b"{}",
            "inner.app": empty_inner,
        }
    )
    app = _write(tmp_path, "double.app", outer)

    with pytest.raises(KeyError):
        load_symbols(app)


def test_load_prefers_top_level_symbol_over_nested_app(tmp_path: Path) -> None:
    # If the outer archive has both a SymbolReference.json and a nested .app,
    # the top-level symbols win (no surprise recursion).
    top_payload = json.dumps({"Tables": ["from-top"]}).encode("utf-8")
    inner_payload = json.dumps({"Tables": ["from-nested"]}).encode("utf-8")
    inner_app_bytes = _build_zip({"SymbolReference.json": inner_payload})
    outer = _build_zip(
        {
            "SymbolReference.json": top_payload,
            "inner.app": inner_app_bytes,
        }
    )
    app = _write(tmp_path, "both.app", outer)

    assert load_symbols(app) == {"Tables": ["from-top"]}
