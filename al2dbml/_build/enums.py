"""Enum + EnumExtension build phase."""

from __future__ import annotations

from typing import Any

from pydbml.classes import Enum, EnumItem

from .context import BuildContext


class EnumBuilder:
    """Builds enums from ``EnumTypes`` and applies ``EnumExtensionTypes``.

    Empty enums (no values) are skipped because DBML requires at least one
    item per enum. Items get their AL ordinal attached as a DBML
    ``[note: '<n>']`` so the integer-to-name mapping that BC stores in SQL
    is visible in the diagram.
    """

    @classmethod
    def build(cls, ctx: BuildContext) -> None:
        cls._build_enums(ctx)
        cls._extend_enums(ctx)

    @classmethod
    def _build_enums(cls, ctx: BuildContext) -> None:
        for entry in ctx.symbols.get("EnumTypes") or []:
            name = entry.get("Name")
            if not name:
                continue
            items_raw = entry.get("Values") or entry.get("Items") or []
            items: list[EnumItem] = []
            for v in items_raw:
                if not isinstance(v, dict):
                    continue
                item = cls._enum_item(v)
                if item is not None:
                    items.append(item)
            if not items:
                continue
            # Enums get their own schema (default 'meta') rather than sharing
            # the table schema. BC enums are AL-language metadata that doesn't
            # actually exist in SQL Server, so a separate namespace tells the
            # reader 'this is descriptor, not data' while still being a real
            # DBML object the column types can reference unambiguously.
            enum_obj = Enum(name=name, schema=ctx.config.enum_schema, items=items)
            ctx.enums[name] = enum_obj
            ctx.db.add(enum_obj)

    @classmethod
    def _extend_enums(cls, ctx: BuildContext) -> None:
        for ext in ctx.symbols.get("EnumExtensionTypes") or []:
            target = ext.get("TargetObject") or ext.get("Target")
            enum_obj = ctx.enums.get(target) if target else None
            if enum_obj is None:
                continue
            for v in ext.get("Values") or ext.get("Items") or []:
                if not isinstance(v, dict):
                    continue
                item = cls._enum_item(v)
                if item is not None:
                    enum_obj.items.append(item)

    @staticmethod
    def _enum_item_name(raw: Any) -> str | None:
        """Coerce an AL enum value name into something DBML can render.

        AL's ``Enum`` literals are often named with a literal space (``" "``) to
        represent the default/blank slot, which DBML accepts as a quoted item.
        An empty string (``""``) however breaks DBML's parser; substitute a
        single space so the slot still appears in its expected position.
        """
        if raw is None:
            return None
        text = str(raw)
        if text == "":
            return " "
        return text

    @staticmethod
    def _enum_item(value_def: dict[str, Any]) -> EnumItem | None:
        """Build a pydbml ``EnumItem`` from one AL enum value definition.

        Returns ``None`` when the value has no usable ``Name``. AL omits the
        ``Ordinal`` key when the value is at position 0, so missing -> 0.
        """
        item_name = EnumBuilder._enum_item_name(value_def.get("Name"))
        if item_name is None:
            return None
        ordinal = value_def.get("Ordinal", 0)
        return EnumItem(name=item_name, note=str(ordinal))
