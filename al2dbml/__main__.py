from __future__ import annotations

from pathlib import Path

import click

from . import __version__
from .generator import Generator
from .grouping import GroupingConfig, parse_rule_strings


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
    "--stats",
    "show_stats",
    is_flag=True,
    default=False,
    help="Print object counts (tables, enums, refs, groups) to stderr after building.",
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
    show_stats: bool,
) -> None:
    """Convert a compiled AL package APP into a DBML schema."""
    try:
        rules = parse_rule_strings(groups)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="-g/--group") from exc

    source = "none" if no_auto_groups else group_by.lower()
    grouping = GroupingConfig(
        enabled=not no_groups,
        rules=rules,
        source=source,  # type: ignore[arg-type]
        min_group_size=min_group_size,
    )

    try:
        generator = Generator.from_app(app, merge_extensions=merge_extensions, grouping=grouping)
        rendered = generator.dbml()
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc

    counts = generator.stats()
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
