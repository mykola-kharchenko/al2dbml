"""AL ``Properties`` shape normaliser.

The AL compiler emits per-object property collections in two different shapes
across versions:

- **list-of-dicts**: ``[{"Name": "Caption", "Value": "Sales Header"}, ...]``
  (current convention; used by the BC v25+ SymbolReference format)
- **dict**: ``{"Caption": "Sales Header", ...}``
  (older convention; still occasionally appears on extension files)

Callers want a plain ``dict[str, Any]`` either way so they can do
``props.get("Caption")``. :func:`normalize` does that coercion.
"""

from __future__ import annotations

from typing import Any


def normalize(raw: Any) -> dict[str, Any]:
    """Coerce an AL ``Properties`` value into a flat ``dict[str, Any]``.

    Falsy inputs (``None``, ``[]``, ``{}``) return ``{}`` so callers can
    chain ``.get(...)`` without a guard. Unknown shapes are also flattened
    to ``{}`` rather than raising; AL compiler versions vary enough that
    permissive parsing has earned its keep.
    """
    if not raw:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, list):
        out: dict[str, Any] = {}
        for item in raw:
            if isinstance(item, dict) and "Name" in item:
                out[item["Name"]] = item.get("Value")
        return out
    return {}
