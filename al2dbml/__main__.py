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
    "--no-auto-groups",
    is_flag=True,
    default=False,
    help="Disable the first-word auto-grouping fallback.",
)
@click.option(
    "--min-group-size",
    type=click.IntRange(min=1),
    default=2,
    show_default=True,
    help="Drop groups containing fewer than this many tables.",
)
@click.version_option(__version__, prog_name="al2dbml")
def main(
    app: Path,
    output: Path | None,
    merge_extensions: bool,
    groups: tuple[str, ...],
    no_groups: bool,
    no_auto_groups: bool,
    min_group_size: int,
) -> None:
    """Convert a compiled AL package APP into a DBML schema."""
    try:
        rules = parse_rule_strings(groups)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="-g/--group") from exc

    grouping = GroupingConfig(
        enabled=not no_groups,
        rules=rules,
        auto_fallback=not no_auto_groups,
        min_group_size=min_group_size,
    )

    try:
        generator = Generator.from_app(app, merge_extensions=merge_extensions, grouping=grouping)
        rendered = generator.dbml()
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc

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
