from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import Protocol

from pydbml.classes import TableGroup


class _NamedTable(Protocol):
    """Structural protocol for anything with a ``.name`` attribute (e.g. ``pydbml.Table``)."""

    name: str


@dataclass
class GroupingConfig:
    """User-facing configuration for DBML ``TableGroup`` emission.

    Attributes:
        enabled: Master switch; when ``False`` no groups are produced.
        rules: Mapping of group name to a list of glob patterns matched against table names
            with ``fnmatch.fnmatchcase``. First rule with a matching pattern wins.
        auto_fallback: When no explicit rule matches, derive the group from the first
            whitespace-separated word in the table name (so ``Sales Header`` -> ``Sales``).
        min_group_size: Buckets containing fewer than this many tables are dropped. Defaults
            to 2 so single-table groups do not clutter the diagram.
    """

    enabled: bool = True
    rules: dict[str, list[str]] = field(default_factory=dict)
    auto_fallback: bool = True
    min_group_size: int = 2

    def group_for(self, table_name: str) -> str | None:
        """Return the group name a table belongs to, or ``None`` if it should not be grouped."""
        for group_name, patterns in self.rules.items():
            for pattern in patterns:
                if fnmatchcase(table_name, pattern):
                    return group_name
        if self.auto_fallback:
            first_word = table_name.split()[0] if table_name.split() else None
            return first_word
        return None


def build_table_groups(
    tables: Iterable[_NamedTable], config: GroupingConfig
) -> list[TableGroup]:
    """Bucket ``tables`` by group name and return ``TableGroup`` objects sorted by name.

    Buckets smaller than ``config.min_group_size`` are dropped entirely. Returns an empty
    list when grouping is disabled.
    """
    if not config.enabled:
        return []

    buckets: dict[str, list[_NamedTable]] = {}
    for table in tables:
        bucket = config.group_for(table.name)
        if bucket is None:
            continue
        buckets.setdefault(bucket, []).append(table)

    groups = [
        TableGroup(name=name, items=list(items))
        for name, items in buckets.items()
        if len(items) >= config.min_group_size
    ]
    groups.sort(key=lambda g: g.name)
    return groups


def parse_rule_strings(entries: Iterable[str]) -> dict[str, list[str]]:
    """Parse CLI ``--group NAME=pat1,pat2`` strings into a rule map.

    Multiple entries with the same group name have their patterns merged in order.

    Raises:
        ValueError: When an entry has no ``=``, an empty name, or no usable patterns.
    """
    rules: dict[str, list[str]] = {}
    for entry in entries:
        if "=" not in entry:
            raise ValueError(
                f"Invalid --group value {entry!r}: expected 'Name=pattern[,pattern...]'"
            )
        name, _, patterns_raw = entry.partition("=")
        name = name.strip()
        if not name:
            raise ValueError(f"Invalid --group value {entry!r}: group name is empty")

        patterns = [p.strip() for p in patterns_raw.split(",") if p.strip()]
        if not patterns:
            raise ValueError(
                f"Invalid --group value {entry!r}: at least one pattern is required"
            )
        rules.setdefault(name, []).extend(patterns)
    return rules
