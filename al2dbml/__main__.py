from __future__ import annotations

from pathlib import Path
from typing import cast

import click

from . import __version__
from .aldoc import AldocDocs, load_docs
from .diagram import Diagram
from .grouping import GroupingConfig, GroupSource, parse_rule_strings


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument(
    "app",
    type=click.Path(exists=True, dir_okay=False, file_okay=True, path_type=Path),
)
@click.option(
    "-o",
    "--output",
    "output",
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    default=None,
    help="Write DBML to this file instead of stdout.",
)
@click.option(
    "--merge-extensions/--no-merge-extensions",
    default=True,
    show_default=True,
    help="Merge TableExtensions into their target tables (vs. emit separate stub tables).",
)
@click.option(
    "-g",
    "--group",
    "groups",
    multiple=True,
    metavar="NAME=PATTERN[,PATTERN...]",
    help="Add an explicit grouping rule. Repeatable.",
)
@click.option(
    "--no-groups",
    is_flag=True,
    default=False,
    help="Do not emit any TableGroup blocks.",
)
@click.option(
    "--group-by",
    "group_by",
    type=click.Choice(["namespace", "word", "none"], case_sensitive=False),
    default="namespace",
    show_default=True,
    help=(
        "How to derive group names when no explicit --group rule matches. "
        "'namespace' uses the last segment of the AL namespace path "
        "(falls back to first-word for un-namespaced tables); "
        "'word' uses the first whitespace-separated word; "
        "'none' disables auto-grouping entirely."
    ),
)
@click.option(
    "--no-auto-groups",
    is_flag=True,
    default=False,
    help="Deprecated alias for --group-by none.",
)
@click.option(
    "--min-group-size",
    type=click.IntRange(min=1),
    default=2,
    show_default=True,
    help="Drop groups containing fewer than this many tables.",
)
@click.option(
    "--table-schema",
    "table_schema",
    metavar="NAME",
    default="dbo",
    show_default=True,
    help="Schema to render Table declarations under. BC's SQL Server uses 'dbo'.",
)
@click.option(
    "--enum-schema",
    "enum_schema",
    metavar="NAME",
    default="meta",
    show_default=True,
    help=(
        "Schema to render Enum declarations under. BC enums are AL-language "
        "metadata, not SQL objects, so by default they live in 'meta' separate "
        "from the 'dbo' table schema."
    ),
)
@click.option(
    "-d",
    "--docs",
    "docs_dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help=(
        "Directory of aldoc-generated YAML documentation; field descriptions "
        "and table summaries overlay onto the diagram. Run "
        "'aldoc generate <app> -o <dir>' first to produce it."
    ),
)
@click.option(
    "--include",
    "includes",
    multiple=True,
    metavar="PATTERN",
    help="Only keep tables whose name matches at least one PATTERN (fnmatch). Repeatable.",
)
@click.option(
    "--exclude",
    "excludes",
    multiple=True,
    metavar="PATTERN",
    help=(
        "Drop tables whose name matches any PATTERN (fnmatch). Applied after --include. Repeatable."
    ),
)
@click.option(
    "--stats",
    "show_stats",
    is_flag=True,
    default=False,
    help=(
        "Print object counts (tables, enums, refs, groups) to stderr. "
        "When used without -o, skips the DBML render entirely for a fast probe."
    ),
)
@click.version_option(__version__, prog_name="al2dbml")
def main(
    app: Path,
    output: Path | None,
    merge_extensions: bool,
    groups: tuple[str, ...],
    no_groups: bool,
    group_by: str,
    no_auto_groups: bool,
    min_group_size: int,
    table_schema: str,
    enum_schema: str,
    docs_dir: Path | None,
    includes: tuple[str, ...],
    excludes: tuple[str, ...],
    show_stats: bool,
) -> None:
    """Convert a compiled AL package APP into a DBML schema."""
    try:
        rules = parse_rule_strings(groups)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="-g/--group") from exc

    source = cast(GroupSource, "none" if no_auto_groups else group_by.lower())
    grouping = GroupingConfig(
        enabled=not no_groups,
        rules=rules,
        source=source,
        min_group_size=min_group_size,
    )

    docs = AldocDocs()
    if docs_dir is not None:
        try:
            docs = load_docs(docs_dir)
        except FileNotFoundError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(
            f"loaded docs for {len(docs.table_summaries)} tables, "
            f"{len(docs.field_descriptions)} fields",
            err=True,
        )

    # If the user only wants stats (no -o and no DBML stream to consumers),
    # skip the expensive DBML render entirely; build() alone is O(n) while
    # the pydbml render path is O(n^2) on table count.
    needs_render = output is not None or not show_stats

    try:
        diagram = Diagram.from_app(
            app,
            merge_extensions=merge_extensions,
            grouping=grouping,
            table_schema=table_schema,
            enum_schema=enum_schema,
            includes=list(includes),
            excludes=list(excludes),
            docs=docs,
        )
        if needs_render:
            rendered: str | None = diagram.dbml()
        else:
            diagram.build()
            rendered = None
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc

    counts = diagram.stats()
    if show_stats:
        click.echo(
            ", ".join(f"{name}={value}" for name, value in counts.items()),
            err=True,
        )
    if counts["tables"] == 0 and counts["enums"] == 0:
        click.echo(
            "warning: parsed 0 tables and 0 enums — output is effectively empty",
            err=True,
        )

    if rendered is None:
        return

    # POSIX text-file convention: terminate output with a newline. Without it,
    # zsh shows a trailing '%' marker after stdout output. pydbml's renderer
    # does not append one itself.
    if not rendered.endswith("\n"):
        rendered = rendered + "\n"

    if output is not None:
        output.write_text(rendered, encoding="utf-8")
        click.echo(f"wrote {output} ({len(rendered)} bytes)", err=True)
    else:
        click.echo(rendered, nl=False)


if __name__ == "__main__":
    main()
