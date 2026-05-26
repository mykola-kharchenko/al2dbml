from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

_AL_HEADER_BYTES = 40
_SYMBOL_REFERENCE_NAME = "symbolreference.json"


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

    raw = path.read_bytes()
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        archive = zipfile.ZipFile(io.BytesIO(raw[_AL_HEADER_BYTES:]))

    with archive:
        member = _find_symbol_member(archive)
        payload = archive.read(member)

    if payload.startswith(b"\xef\xbb\xbf"):
        payload = payload[3:]
    return json.loads(payload.decode("utf-8"))


def _find_symbol_member(archive: zipfile.ZipFile) -> str:
    """Return the archive member name that matches ``SymbolReference.json`` case-insensitively."""
    for name in archive.namelist():
        if name.split("/")[-1].lower() == _SYMBOL_REFERENCE_NAME:
            return name
    sample = ", ".join(archive.namelist()[:10])
    raise KeyError(
        "SymbolReference.json not found in AL package. "
        f"First entries in archive: [{sample}]"
    )
