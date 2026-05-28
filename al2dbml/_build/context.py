"""Shared state and configuration for the build pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydbml import Database
from pydbml.classes import Column, Enum, Table

from ..aldoc import AldocDocs
from ..grouping import GroupingConfig


@dataclass
class _PendingRef:
    """A reference that's been parsed out of an AL ``TableRelation`` but not
    yet resolved to a pydbml ``Reference``.

    Resolution happens in :mod:`al2dbml._build.references` after all tables
    and columns have been built; cross-package targets degrade to notes.
    """

    source_table: str
    source_field: str
    target_table: str
    target_field: str | None
    condition: str | None  # the AL WHERE(...) filter, when present
    if_condition: str | None = None  # the IF (...) clause for conditional refs


@dataclass
class BuildConfig:
    """Immutable configuration knobs for one build pipeline pass.

    Bundles every user-facing setting that controls how a ``Generator``
    transforms symbols into a DBML database. The set of fields here is the
    same as the corresponding subset of the ``Generator`` dataclass.
    """

    merge_extensions: bool = True
    grouping: GroupingConfig = field(default_factory=GroupingConfig)
    table_schema: str = "dbo"
    enum_schema: str = "meta"
    includes: list[str] = field(default_factory=list)
    excludes: list[str] = field(default_factory=list)
    docs: AldocDocs = field(default_factory=AldocDocs)


@dataclass
class BuildContext:
    """Mutable state threaded through the build pipeline.

    Each phase reads what previous phases wrote and writes new state for
    later phases. Keeping the state in one dataclass means a builder can be
    unit-tested by feeding it a minimal ``BuildContext`` without spinning up
    the whole pipeline.
    """

    symbols: dict[str, Any]
    config: BuildConfig
    db: Database = field(default_factory=Database)
    enums: dict[str, Enum] = field(default_factory=dict)
    tables: dict[str, Table] = field(default_factory=dict)
    columns: dict[tuple[str, str], Column] = field(default_factory=dict)
    pending_refs: list[_PendingRef] = field(default_factory=list)
    table_namespaces: dict[str, str] = field(default_factory=dict)
