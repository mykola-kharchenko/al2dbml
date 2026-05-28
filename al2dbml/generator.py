"""High-level orchestrator: AL ``SymbolReference.json`` -> DBML.

This module owns the ``Generator`` class (the public entry point) plus the
pipeline coordination. The per-phase work lives in :mod:`al2dbml._build`;
each phase is a focused module operating on a shared :class:`BuildContext`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydbml import Database
from pydbml.classes import Column, Enum, Table

from . import properties, relations
from ._build.context import BuildConfig, BuildContext, _PendingRef
from ._build.enums import EnumBuilder
from ._build.extensions import ExtensionBuilder
from ._build.filters import TableFilter
from ._build.groups import GroupBuilder
from ._build.references import ReferenceResolver
from ._build.tables import TableBuilder
from .aldoc import AldocDocs
from .grouping import GroupingConfig
from .symbols import load_symbols

# Re-exports kept on the module for the (small) set of external consumers
# reaching for them directly; the in-pipeline call sites use the package
# names (BuildContext, etc.) above.
__all__ = ["Generator", "generate"]


@dataclass
class Generator:
    """Build a ``pydbml.Database`` from a parsed AL ``SymbolReference.json`` document.

    The pipeline runs in phases, each owned by one module under
    :mod:`al2dbml._build`:

    1. :class:`EnumBuilder` — enums and enum extensions
    2. :class:`TableBuilder` — tables, columns, PK flags, secondary-key
       uniques, pending references
    3. :class:`ExtensionBuilder` — merge ``TableExtensions`` (or emit stubs
       per ``merge_extensions``)
    4. :class:`TableFilter` — apply include/exclude patterns when supplied
    5. :class:`ReferenceResolver` — resolve pending refs into pydbml
       ``Reference`` objects with graceful cross-package degradation
    6. :class:`GroupBuilder` — emit ``TableGroup`` blocks
    """

    symbols: dict[str, Any]
    merge_extensions: bool = True
    grouping: GroupingConfig = field(default_factory=GroupingConfig)
    table_schema: str = "dbo"
    enum_schema: str = "meta"
    includes: list[str] = field(default_factory=list)
    excludes: list[str] = field(default_factory=list)
    docs: AldocDocs = field(default_factory=AldocDocs)
    db: Database = field(default_factory=Database)

    _ctx: BuildContext | None = field(init=False, default=None)
    _built: bool = field(init=False, default=False)

    @classmethod
    def from_app(cls, path: str | Path, **kwargs: Any) -> Generator:
        """Construct a :class:`Generator` directly from a compiled AL ``.app`` package."""
        return cls(symbols=load_symbols(path), **kwargs)

    def build(self) -> Database:
        """Run the full pipeline and return the populated :class:`pydbml.Database`."""
        if self._built:
            return self.db
        ctx = self._context()
        EnumBuilder.build(ctx)
        TableBuilder.build(ctx)
        if self.merge_extensions:
            ExtensionBuilder.merge(ctx)
        else:
            ExtensionBuilder.stub(ctx)
        TableFilter.apply(ctx)
        ReferenceResolver.resolve(ctx)
        GroupBuilder.build(ctx)
        self._built = True
        return self.db

    def dbml(self) -> str:
        """Build (if needed) and render the database as a DBML string with a header comment."""
        body = self.build().dbml
        return self._header_comment() + body

    def stats(self) -> dict[str, int]:
        """Return a snapshot of how many of each object kind the build produced.

        Useful as a quick sanity check on any ``.app``: an extension with only
        codeunits produces ``{'tables': 0, ...}`` and explains an empty diagram.
        """
        self.build()
        ctx = self._context()
        return {
            "tables": len(ctx.tables),
            "columns": len(ctx.columns),
            "enums": len(ctx.enums),
            "refs": len(self.db.refs),
            "groups": len(self.db.table_groups),
        }

    # ------------------------------------------------------------------ #
    # Backwards-compatibility accessors for tests / external callers     #
    # that reach into the old private dicts.                             #
    # ------------------------------------------------------------------ #

    @property
    def _enums(self) -> dict[str, Enum]:
        return self._context().enums

    @property
    def _tables(self) -> dict[str, Table]:
        return self._context().tables

    @property
    def _columns(self) -> dict[tuple[str, str], Column]:
        return self._context().columns

    @property
    def _pending_refs(self) -> list[_PendingRef]:
        return self._context().pending_refs

    @property
    def _table_namespaces(self) -> dict[str, str]:
        return self._context().table_namespaces

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    def _context(self) -> BuildContext:
        """Return the lazily-created :class:`BuildContext` for this generator.

        Created on first access; subsequent build phases share the same
        instance so ``stats()`` and the backwards-compat property accessors
        all read the same state.
        """
        if self._ctx is None:
            self._ctx = BuildContext(
                symbols=self.symbols,
                config=BuildConfig(
                    merge_extensions=self.merge_extensions,
                    grouping=self.grouping,
                    table_schema=self.table_schema,
                    enum_schema=self.enum_schema,
                    includes=list(self.includes),
                    excludes=list(self.excludes),
                    docs=self.docs,
                ),
                db=self.db,
            )
        return self._ctx

    def _header_comment(self) -> str:
        """Return a short provenance preamble identifying the tool + source package."""
        from . import __version__

        name = self.symbols.get("Name")
        version = self.symbols.get("Version")
        publisher = self.symbols.get("Publisher")
        app_id = self.symbols.get("AppId")

        descriptor_parts: list[str] = []
        if name:
            descriptor_parts.append(str(name))
        if version:
            descriptor_parts.append(str(version))
        descriptor = " ".join(descriptor_parts)
        publisher_suffix = f" by {publisher}" if publisher else ""

        if descriptor:
            first = f"// Generated by al2dbml {__version__} from {descriptor}{publisher_suffix}\n"
        else:
            first = f"// Generated by al2dbml {__version__}\n"

        second = f"// AppId: {app_id}\n" if app_id else ""
        return first + second + ("\n" if first or second else "")

    # ------------------------------------------------------------------ #
    # Shims for legacy access patterns                                   #
    # ------------------------------------------------------------------ #

    _properties = staticmethod(properties.normalize)
    _parse_relation_string = staticmethod(relations.parse_relation_string)
    _parse_conditional_relation = staticmethod(relations.parse_conditional_relation)
    _parse_qualified = staticmethod(relations.parse_qualified)
    _find_matching_paren = staticmethod(relations.find_matching_paren)


def generate(app_path: str | Path, output_path: str | Path | None = None) -> str:
    """Convenience wrapper: load ``app_path``, render DBML, optionally write to ``output_path``."""
    gen = Generator.from_app(app_path)
    rendered = gen.dbml()
    if output_path is not None:
        Path(output_path).write_text(rendered, encoding="utf-8")
    return rendered
