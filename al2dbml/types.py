from __future__ import annotations

from typing import Any

_SIMPLE_TYPES: dict[str, str] = {
    "integer": "int",
    "biginteger": "bigint",
    "decimal": "decimal",
    "boolean": "boolean",
    "date": "date",
    "time": "time",
    "datetime": "datetime",
    "duration": "bigint",
    "guid": "uuid",
    "recordid": "varchar",
    "blob": "blob",
    "media": "uuid",
    "mediaset": "uuid",
    "option": "varchar",
}


def map_al_type(field: dict[str, Any]) -> str:
    """Map an AL field definition to a DBML column type string.

    The mapping covers the AL primitive scalar types, length-bearing strings
    (``Code``/``Text``), enum-typed fields (quoted enum name), and a permissive
    fallback for unrecognised types (lowercased original name).

    Args:
        field: A single ``Fields[i]`` entry from a ``SymbolReference.json`` table.

    Returns:
        A DBML-ready type string such as ``"varchar(20)"``, ``"int"``, or ``'"Customer Type"'``.
    """
    raw_type = (field.get("TypeDefinition") or {}).get("Name") or field.get("Type") or ""
    type_name = str(raw_type).strip()
    key = type_name.lower()

    if key in ("code", "text"):
        type_args = (field.get("TypeDefinition") or {}).get("TypeArguments")
        length = _first_int(type_args)
        return f"varchar({length})" if length is not None else "varchar"

    if key == "enum":
        subtype = (field.get("TypeDefinition") or {}).get("Subtype") or {}
        enum_name = subtype.get("Name")
        if enum_name:
            return f'"{enum_name}"'
        return "varchar"

    if key in _SIMPLE_TYPES:
        return _SIMPLE_TYPES[key]

    return key or "varchar"


def _first_int(args: Any) -> int | None:
    """Return the first integer-convertible entry in ``args``, or ``None``.

    Tolerates ``None``, empty sequences, and non-numeric entries: AL ``TypeArguments``
    can be missing, empty, or carry strings like ``"MaxStrLen"`` placeholders.
    """
    if not args:
        return None
    if not isinstance(args, (list, tuple)):
        return None
    for entry in args:
        try:
            return int(entry)
        except (TypeError, ValueError):
            continue
    return None
