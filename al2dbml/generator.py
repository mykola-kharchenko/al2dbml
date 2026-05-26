from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydbml import Database
from pydbml.classes import Column, Enum, EnumItem, Note, Reference, Table

from .grouping import GroupingConfig, build_table_groups
from .symbols import load_symbols
from .types import map_al_type

_IDENT_RE = re.compile(r'\s*(?:"([^"]+)"|([A-Za-z_]\w*))\s*')
_WHERE_RE = re.compile(r"\bWHERE\s*\(", re.IGNORECASE)


@dataclass
class _PendingRef:
    source_table: str
    source_field: str
    target_table: str
    target_field: str | None
    condition: str | None


@dataclass
class Generator:
    """Build a ``pydbml.Database`` from a parsed AL ``SymbolReference.json`` document.

    The pipeline:

    1. Build enums (skipping empty ones — DBML requires at least one item).
    2. Apply enum extensions on top.
    3. Build tables with PK flags and column notes, collecting deferred references.
    4. Either merge ``TableExtensions`` into their target tables or emit them as separate
       stub tables, depending on ``merge_extensions``.
    5. Resolve references with graceful fallbacks for cross-package or missing-field cases.
    6. Build ``TableGroup``s according to ``GroupingConfig``.
    """

    symbols: dict[str, Any]
    merge_extensions: bool = True
    grouping: GroupingConfig = field(default_factory=GroupingConfig)
    schema: str = "dbo"
    db: Database = field(default_factory=Database)

    _enums: dict[str, Enum] = field(init=False, default_factory=dict)
    _tables: dict[str, Table] = field(init=False, default_factory=dict)
    _columns: dict[tuple[str, str], Column] = field(init=False, default_factory=dict)
    _pending_refs: list[_PendingRef] = field(init=False, default_factory=list)
    _built: bool = field(init=False, default=False)

    @classmethod
    def from_app(cls, path: str | Path, **kwargs: Any) -> Generator:
        """Construct a :class:`Generator` directly from a compiled AL ``.app`` package."""
        return cls(symbols=load_symbols(path), **kwargs)

    def build(self) -> Database:
        """Run the full pipeline and return the populated :class:`pydbml.Database`."""
        if self._built:
            return self.db
        self._build_enums()
        self._extend_enums()
        self._build_tables()
        if self.merge_extensions:
            self._merge_table_extensions()
        else:
            self._build_extension_stubs()
        self._resolve_references()
        self._build_groups()
        self._built = True
        return self.db

    def dbml(self) -> str:
        """Build (if needed) and render the database as a DBML string."""
        return self.build().dbml

    def _build_enums(self) -> None:
        for entry in self.symbols.get("EnumTypes") or []:
            name = entry.get("Name")
            if not name:
                continue
            items_raw = entry.get("Values") or entry.get("Items") or []
            items = [
                EnumItem(name=str(v["Name"]))
                for v in items_raw
                if isinstance(v, dict) and v.get("Name") is not None
            ]
            if not items:
                continue
            enum_obj = Enum(name=name, items=items)
            self._enums[name] = enum_obj
            self.db.add(enum_obj)

    def _extend_enums(self) -> None:
        for ext in self.symbols.get("EnumExtensionTypes") or []:
            target = ext.get("TargetObject") or ext.get("Target")
            enum_obj = self._enums.get(target) if target else None
            if enum_obj is None:
                continue
            for v in ext.get("Values") or ext.get("Items") or []:
                if isinstance(v, dict) and v.get("Name") is not None:
                    enum_obj.items.append(EnumItem(name=str(v["Name"])))

    def _build_tables(self) -> None:
        for table_def in self.symbols.get("Tables") or []:
            name = table_def.get("Name")
            if not name:
                continue
            table = self._make_table(table_def)
            self._tables[name] = table
            self.db.add(table)

    def _make_table(self, table_def: dict[str, Any]) -> Table:
        name = table_def["Name"]
        props = self._properties(table_def.get("Properties"))
        caption = props.get("Caption")
        table = (
            Table(name=name, schema=self.schema, note=caption)
            if caption
            else Table(name=name, schema=self.schema)
        )

        keys = table_def.get("Keys") or []
        pk_names: set[str] = set()
        if keys and isinstance(keys, list):
            first_key = keys[0]
            if isinstance(first_key, dict):
                pk_names = set(first_key.get("FieldNames") or [])

        for f in table_def.get("Fields") or []:
            col = self._make_column(name, f, pk_names)
            if col is not None:
                table.add_column(col)
                self._columns[(name, col.name)] = col
        return table

    def _make_column(
        self, table_name: str, field_def: dict[str, Any], pk_names: set[str]
    ) -> Column | None:
        fname = field_def.get("Name")
        if not fname:
            return None

        type_def = field_def.get("TypeDefinition") or {}
        type_str = map_al_type(field_def)
        col_type: Any = type_str
        if str(type_def.get("Name") or "").lower() == "enum":
            subtype_name = (type_def.get("Subtype") or {}).get("Name")
            if subtype_name and subtype_name in self._enums:
                col_type = self._enums[subtype_name]

        col = Column(name=fname, type=col_type, pk=(fname in pk_names))

        notes_parts: list[str] = []
        field_props = self._properties(field_def.get("Properties"))
        caption = field_props.get("Caption")
        if caption:
            notes_parts.append(str(caption))

        relation = field_props.get("TableRelation") or field_def.get("TableRelation")
        if relation:
            target_table, target_field, condition = self._parse_relation_string(relation)
            if target_table:
                self._pending_refs.append(
                    _PendingRef(
                        source_table=table_name,
                        source_field=fname,
                        target_table=target_table,
                        target_field=target_field,
                        condition=condition,
                    )
                )
                if condition:
                    notes_parts.append(f"Condition: {condition}")

        if notes_parts:
            col.note = Note("\n".join(notes_parts))
        return col

    def _merge_table_extensions(self) -> None:
        for ext in self.symbols.get("TableExtensions") or []:
            target = ext.get("TargetObject") or ext.get("Target")
            if not target:
                continue
            table = self._tables.get(target)
            if table is None:
                table = Table(
                    name=target,
                    schema=self.schema,
                    note=f"Stub for cross-package target {target}",
                )
                self._tables[target] = table
                self.db.add(table)
            for f in ext.get("Fields") or []:
                col = self._make_column(target, f, set())
                if col is not None:
                    table.add_column(col)
                    self._columns[(target, col.name)] = col

    def _build_extension_stubs(self) -> None:
        for ext in self.symbols.get("TableExtensions") or []:
            target = ext.get("TargetObject") or ext.get("Target")
            if not target:
                continue
            stub_name = f"{target} (Extension)"
            stub = Table(name=stub_name, schema=self.schema, note=f"Extension of {target}")
            for f in ext.get("Fields") or []:
                col = self._make_column(stub_name, f, set())
                if col is not None:
                    stub.add_column(col)
                    self._columns[(stub_name, col.name)] = col
            self._tables[stub_name] = stub
            self.db.add(stub)

    def _resolve_references(self) -> None:
        for ref in self._pending_refs:
            source_col = self._columns.get((ref.source_table, ref.source_field))
            if source_col is None:
                continue

            target_table = self._tables.get(ref.target_table)
            if target_table is None:
                self._append_note(
                    source_col,
                    "References "
                    + ref.target_table
                    + (f'."{ref.target_field}"' if ref.target_field else "")
                    + " (cross-package)",
                )
                continue

            target_col = None
            if ref.target_field is not None:
                target_col = self._columns.get((ref.target_table, ref.target_field))
            if target_col is None:
                pk_cols = [c for c in target_table.columns if c.pk]
                if not pk_cols:
                    self._append_note(
                        source_col,
                        "References "
                        + ref.target_table
                        + (f'."{ref.target_field}"' if ref.target_field else ""),
                    )
                    continue
                target_col = pk_cols[0]

            self.db.add(Reference(type=">", col1=source_col, col2=target_col))

    def _build_groups(self) -> None:
        for tg in build_table_groups(self._tables.values(), self.grouping):
            self.db.add(tg)

    @staticmethod
    def _append_note(col: Column, line: str) -> None:
        existing = col.note.text if col.note else ""
        col.note = Note(f"{existing}\n{line}".strip() if existing else line)

    @staticmethod
    def _properties(raw: Any) -> dict[str, Any]:
        """Normalise an AL ``Properties`` field, which may be a list or a dict."""
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

    @staticmethod
    def _parse_relation_string(
        value: Any,
    ) -> tuple[str | None, str | None, str | None]:
        """Parse an AL ``TableRelation`` value, returning ``(table, field, condition)``.

        ``condition`` is the parenthesised expression that follows ``WHERE`` — without the
        ``WHERE`` keyword itself — or ``None`` if no condition is present.
        """
        if isinstance(value, dict):
            return (
                value.get("Table") or value.get("TableName"),
                value.get("Field") or value.get("FieldName"),
                value.get("Condition"),
            )
        if isinstance(value, list):
            return Generator._parse_relation_string(value[0] if value else "")

        text = str(value).strip()
        if not text:
            return (None, None, None)

        condition: str | None = None
        match = _WHERE_RE.search(text)
        if match:
            paren_start = match.end() - 1
            depth = 0
            end_index = paren_start
            for i in range(paren_start, len(text)):
                if text[i] == "(":
                    depth += 1
                elif text[i] == ")":
                    depth -= 1
                    if depth == 0:
                        end_index = i
                        break
            condition = text[paren_start : end_index + 1]
            text = text[: match.start()].strip()

        table, field_name = Generator._parse_qualified(text)
        return table, field_name, condition

    @staticmethod
    def _parse_qualified(text: str) -> tuple[str | None, str | None]:
        text = text.strip()
        if not text:
            return (None, None)
        first_match = _IDENT_RE.match(text)
        if not first_match:
            return (None, None)
        first = first_match.group(1) or first_match.group(2)
        rest = text[first_match.end() :]
        if not rest.startswith("."):
            return (first, None)
        rest = rest[1:]
        second_match = _IDENT_RE.match(rest)
        if not second_match:
            return (first, None)
        second = second_match.group(1) or second_match.group(2)
        return (first, second)


def generate(app_path: str | Path, output_path: str | Path | None = None) -> str:
    """Convenience wrapper: load ``app_path``, render DBML, optionally write to ``output_path``."""
    gen = Generator.from_app(app_path)
    rendered = gen.dbml()
    if output_path is not None:
        Path(output_path).write_text(rendered, encoding="utf-8")
    return rendered
