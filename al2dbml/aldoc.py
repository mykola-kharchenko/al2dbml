from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_QUOTED_NAME_RE = re.compile(r'"([^"]+)"')


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

    def is_empty(self) -> bool:
        return not self.table_summaries and not self.field_descriptions


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
    path = Path(directory)
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
    if text.startswith("﻿"):
        text = text[1:]
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None
