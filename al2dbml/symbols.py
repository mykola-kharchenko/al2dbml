from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

_AL_HEADER_BYTES = 40
_SYMBOL_REFERENCE_NAME = "symbolreference.json"

# Object collections that the generator consumes at the top level. Modern BC
# nests these inside Namespaces[...].Namespaces[...]; we flatten them so the
# generator can stay namespace-agnostic.
_FLATTENED_KEYS = ("Tables", "TableExtensions", "EnumTypes", "EnumExtensionTypes")


def load_symbols(app_path: str | Path) -> dict[str, Any]:
    """Load and parse ``SymbolReference.json`` from a compiled AL ``.app`` package.

    The AL compiler prefixes packages with a 40-byte header before the ZIP central
    directory; we transparently strip it on the retry path. The filename casing of
    ``SymbolReference.json`` varies across compiler versions, so we look it up in a
    case-insensitive way. A UTF-8 BOM, if present, is stripped before parsing.

    Args:
        app_path: Filesystem path to the ``.app`` file.

    Returns:
        The decoded ``SymbolReference.json`` document as a dictionary.

    Raises:
        FileNotFoundError: ``app_path`` does not exist.
        KeyError: The archive does not contain ``SymbolReference.json``.
        zipfile.BadZipFile: The file is neither a ZIP nor a header-prefixed ZIP.
        json.JSONDecodeError: The JSON payload is malformed.
    """
    path = Path(app_path)
    if not path.is_file():
        raise FileNotFoundError(f"AL package not found: {path}")

    return _load_symbols_from_bytes(path.read_bytes())


def _load_symbols_from_bytes(raw: bytes, *, depth: int = 0) -> dict[str, Any]:
    """Open ``raw`` as an AL ZIP and return its decoded ``SymbolReference.json``.

    Handles three real-world shapes:

    1. A plain ZIP with ``SymbolReference.json`` at the top level (or nested under a
       subdirectory).
    2. A ZIP prefixed with the 40-byte AL compiler header; we strip and retry.
    3. A "Ready-To-Run" wrapper that contains a nested ``.app`` (plus pre-compiled DLLs);
       we recurse into the nested package exactly once.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        archive = zipfile.ZipFile(io.BytesIO(raw[_AL_HEADER_BYTES:]))

    with archive:
        try:
            member = _find_symbol_member(archive)
        except KeyError:
            # Ready-To-Run packages bundle the actual .app alongside DLLs; recurse once.
            if depth >= 1:
                raise
            nested = _find_nested_app(archive)
            if nested is None:
                raise
            return _load_symbols_from_bytes(archive.read(nested), depth=depth + 1)
        payload = archive.read(member)

    if payload.startswith(b"\xef\xbb\xbf"):
        payload = payload[3:]
    return _flatten_namespaces(json.loads(payload.decode("utf-8")))


def _flatten_namespaces(data: dict[str, Any]) -> dict[str, Any]:
    """Hoist namespace-nested object collections to the top level.

    Modern Business Central (v25+) organizes objects by namespace, so the schema looks
    like ``Namespaces[i].Namespaces[j].Tables[k]`` recursively. Older BC put everything
    at the top level. This walker visits the namespace tree once and concatenates every
    ``Tables`` / ``TableExtensions`` / ``EnumTypes`` / ``EnumExtensionTypes`` array it
    finds into the corresponding top-level array, so downstream code sees one flat
    shape regardless of which compiler version produced the file.
    """
    if not isinstance(data, dict):
        return data

    collected: dict[str, list[Any]] = {key: [] for key in _FLATTENED_KEYS}

    def walk(node: Any, namespace: str) -> None:
        if not isinstance(node, dict):
            return
        for key in _FLATTENED_KEYS:
            entries = node.get(key)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                # Tag each object with the namespace it lived under so the
                # generator can later group tables by namespace without
                # having to re-walk the tree. Items at the top level get an
                # empty namespace; nested ones get the dotted path.
                if isinstance(entry, dict) and "__namespace" not in entry:
                    entry["__namespace"] = namespace
                collected[key].append(entry)
        for child in node.get("Namespaces") or []:
            child_name = child.get("Name") if isinstance(child, dict) else None
            if namespace and child_name:
                next_ns = f"{namespace}.{child_name}"
            else:
                next_ns = child_name or namespace
            walk(child, next_ns)

    walk(data, "")

    result = dict(data)
    for key, items in collected.items():
        # Only set the key when it was already present in the input or when
        # namespace walking actually found something; otherwise leave the
        # output dict alone so legacy/empty-shape inputs keep their shape.
        if items or key in data:
            result[key] = items
    return result


def _find_symbol_member(archive: zipfile.ZipFile) -> str:
    """Return the archive member name that matches ``SymbolReference.json`` case-insensitively."""
    for name in archive.namelist():
        if name.split("/")[-1].lower() == _SYMBOL_REFERENCE_NAME:
            return name
    sample = ", ".join(archive.namelist()[:10])
    raise KeyError(
        f"SymbolReference.json not found in AL package. First entries in archive: [{sample}]"
    )


def _find_nested_app(archive: zipfile.ZipFile) -> str | None:
    """Return the first archive member whose filename ends with ``.app``, or ``None``."""
    for name in archive.namelist():
        if name.lower().endswith(".app"):
            return name
    return None
