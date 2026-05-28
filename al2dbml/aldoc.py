"""Load AL-language documentation from an ``aldoc generate`` output tree.

``aldoc`` (Microsoft's official AL documentation generator, bundled with the
AL Language VS Code extension) parses ``.al`` source via the real AL compiler
frontend and emits a docfx-compatible directory of per-object YAML files. We
consume the ``Table`` and ``TableExtension`` subtrees to extract two indexes
that the generator uses to enrich the rendered DBML:

- ``AldocDocs.table_summaries`` — table name -> top-level ``summary`` prose,
  rendered as a ``Note { ... }`` body on the corresponding DBML ``Table``.
- ``AldocDocs.field_descriptions`` — ``(table, field)`` -> per-field
  ``description`` text (derived by aldoc from AL ``ToolTip`` and
  ``/// <summary>`` XML doc comments), rendered as the leading section of
  the column's ``[note: ...]`` block.

Coverage is uneven in real BC packages — active-document tables like
``Sales Header`` are richly documented; history / buffer / setup tables
often have nothing. Where aldoc has no entry, the generator falls back to
its existing caption-based logic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_QUOTED_NAME_RE = re.compile(r'"([^"]+)"')

# UTF-8 byte order mark (U+FEFF). aldoc prefixes every YAML file with one,
# and PyYAML's safe_load doesn't strip it consistently across versions, so
# we trim it ourselves before parsing. Kept as a named constant — and
# constructed via chr() so the source is visibly self-documenting rather
# than holding a literal U+FEFF that renders as an empty character.
_UTF8_BOM = chr(0xFEFF)


@dataclass
class AldocDocs:
    """Documentation loaded from an ``aldoc generate`` YAML output directory.

    Two indexes populated by :func:`load_docs`:

    - ``table_summaries`` maps a table name to its top-level ``summary`` prose.
    - ``field_descriptions`` maps ``(table_name, field_name)`` to the per-field
      ``description`` text (which aldoc derives from the AL ``ToolTip``
      property and/or ``///`` XML doc comments).

    An ``AldocDocs()`` with both maps empty is the no-op default — the
    generator falls back to its current caption-based notes when nothing
    matches a given (table, field) lookup.
    """

    table_summaries: dict[str, str] = field(default_factory=dict)
    field_descriptions: dict[tuple[str, str], str] = field(default_factory=dict)


def load_docs(directory: str | Path) -> AldocDocs:
    """Walk an aldoc output directory and index field/table documentation.

    aldoc emits one YAML file per AL object under
    ``<directory>/reference/<module-slug>/<ObjectKind>/<Slug>.yml``. We only
    consume ``Table`` and ``TableExtension`` subtrees; the others (Codeunit,
    Page, Report, Query, XmlPort, Profile, Permission*) don't map to DBML.

    Returns an empty :class:`AldocDocs` if the directory exists but has no
    matching files; that way callers can pass the result unconditionally
    into the generator and the rest of the pipeline degrades gracefully.

    Args:
        directory: Path to the aldoc output (the directory containing
            ``aldoc.json``, ``toc.yml``, and the ``reference/`` subtree).

    Raises:
        FileNotFoundError: ``directory`` does not exist or is not a directory.
    """
    # expanduser so Python API callers can pass '~/...' paths and get the
    # same behaviour the CLI already gives them.
    path = Path(directory).expanduser()
    if not path.is_dir():
        raise FileNotFoundError(f"aldoc docs directory not found: {path}")

    docs = AldocDocs()
    for yml_path in path.glob("reference/*/Table/*.yml"):
        _ingest_table_yaml(yml_path, docs)
    for yml_path in path.glob("reference/*/TableExtension/*.yml"):
        _ingest_table_extension_yaml(yml_path, docs)
    return docs


def _ingest_table_yaml(yml_path: Path, docs: AldocDocs) -> None:
    data = _safe_load(yml_path)
    if not isinstance(data, dict):
        return
    table_name = _unquote(data.get("name"))
    if not table_name:
        return
    summary = data.get("summary")
    if isinstance(summary, str) and summary.strip():
        docs.table_summaries[table_name] = summary.strip()
    _ingest_field_list(table_name, data.get("fields"), docs)


def _ingest_table_extension_yaml(yml_path: Path, docs: AldocDocs) -> None:
    data = _safe_load(yml_path)
    if not isinstance(data, dict):
        return
    base = _extract_base_table_name(data.get("extends"))
    if not base:
        return
    _ingest_field_list(base, data.get("fields"), docs)


def _ingest_field_list(table_name: str, fields: Any, docs: AldocDocs) -> None:
    if not isinstance(fields, list):
        return
    for entry in fields:
        if not isinstance(entry, dict):
            continue
        fname = _unquote(entry.get("name"))
        if not fname:
            continue
        description = entry.get("description")
        if isinstance(description, str) and description.strip():
            docs.field_descriptions[(table_name, fname)] = description.strip()


def _unquote(raw: Any) -> str | None:
    """Strip the surrounding double quotes from aldoc's name fields.

    aldoc emits names as YAML strings containing the AL-quoted form, so the
    value loaded from PyYAML looks like ``'"Sales Header"'``. We want just
    ``Sales Header``.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    return text


def _extract_base_table_name(extends: Any) -> str | None:
    """Pull the base table name out of a TableExtension's ``extends`` block.

    The ``name`` value looks like ``Microsoft.Finance.Currency."Foo Bar"``;
    we want just ``Foo Bar``. Legacy non-namespaced bases come through as
    ``"Foo Bar"`` (no namespace prefix) and are handled identically.
    """
    if not isinstance(extends, dict):
        return None
    raw = extends.get("name")
    if not isinstance(raw, str):
        return None
    match = _QUOTED_NAME_RE.search(raw)
    if match:
        return match.group(1)
    return raw.rsplit(".", 1)[-1] or None


def _safe_load(yml_path: Path) -> Any:
    try:
        text = yml_path.read_text(encoding="utf-8")
    except OSError:
        return None
    if text.startswith(_UTF8_BOM):
        text = text[1:]
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None
