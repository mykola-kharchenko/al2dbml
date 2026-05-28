"""High-level orchestrator: AL ``SymbolReference.json`` -> DBML.

This module owns the :class:`Diagram` class (the public entry point) plus the
pipeline coordination. The per-phase work lives in :mod:`al2dbml._build`;
each phase is a focused module operating on a shared
:class:`al2dbml._build.context.BuildContext`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydbml import Database

from .__meta__ import __version__
from ._build.context import BuildConfig, BuildContext
from ._build.enums import EnumBuilder
from ._build.extensions import ExtensionBuilder
from ._build.filters import TableFilter
from ._build.groups import GroupBuilder
from ._build.references import ReferenceResolver
from ._build.tables import TableBuilder
from .aldoc import AldocDocs
from .grouping import GroupingConfig
from .symbols import load_symbols

__all__ = ["Diagram", "generate"]


@dataclass
class Diagram:
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
    def from_app(cls, path: str | Path, **kwargs: Any) -> Diagram:
        """Construct a :class:`Diagram` directly from a compiled AL ``.app`` package."""
        return cls(symbols=load_symbols(path), **kwargs)

    def build(self) -> Database:
        """Run the full pipeline and return the populated :class:`pydbml.Database`."""
        if self._built:
            return self.db
        ctx = self.context
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
        ctx = self.context
        return {
            "tables": len(ctx.tables),
            "columns": len(ctx.columns),
            "enums": len(ctx.enums),
            "refs": len(self.db.refs),
            "groups": len(self.db.table_groups),
        }

    # ------------------------------------------------------------------ #
    # Public inspection surface                                          #
    # ------------------------------------------------------------------ #

    @property
    def context(self) -> BuildContext:
        """Read-only view of the live :class:`BuildContext` for this Diagram.

        Lazily created on first access; subsequent build phases and external
        callers all share the same instance. The property exposes the
        build state (tables, columns, enums, pending refs, table namespaces)
        for inspection without leaking the dataclass implementation detail
        of ``_ctx`` directly.

        **Empty before ``build()``**: the collections (``context.tables``,
        ``context.enums``, etc.) are populated by the pipeline phases that
        :meth:`build` runs. Accessing ``context.tables`` before calling
        ``build()`` returns an empty dict, not the tables in the source
        ``.app`` — call ``build()`` (or any of the methods that invoke it
        like ``dbml()`` or ``stats()``) first.

        The property has no setter, so ``diagram.context = ...`` raises
        :class:`AttributeError`. To rebuild against different inputs,
        construct a new :class:`Diagram` instance.
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


def generate(
    app_path: str | Path,
    output_path: str | Path | None = None,
    **kwargs: Any,
) -> str:
    """Convenience wrapper: load ``app_path``, render DBML, optionally write to ``output_path``.

    Any additional keyword arguments are forwarded to :meth:`Diagram.from_app`,
    so the full configuration surface (``docs``, ``table_schema``, ``includes``,
    ``grouping``, etc.) is reachable from the one-shot helper:

    .. code-block:: python

        generate("MyApp.app", output_path="schema.dbml",
                 docs=load_docs("./docs"), includes=["Sales*"])
    """
    diagram = Diagram.from_app(app_path, **kwargs)
    rendered = diagram.dbml()
    if output_path is not None:
        # expanduser so '~/schema.dbml' works the same here as in the CLI
        Path(output_path).expanduser().write_text(rendered, encoding="utf-8")
    return rendered
