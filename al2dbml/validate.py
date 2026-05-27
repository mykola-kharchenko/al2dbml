from __future__ import annotations

from pathlib import Path

import click

from . import __version__


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument(
    "file",
    type=click.Path(exists=True, dir_okay=False, file_okay=True, path_type=Path),
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    default=False,
    help="Suppress the success summary; only report errors.",
)
@click.version_option(__version__, prog_name="al2dbml-validate")
def main(file: Path, quiet: bool) -> None:
    """Parse a DBML FILE through pydbml and report syntax errors.

    Exit code is 0 on a clean parse, non-zero on a syntax error. On success a
    short summary is printed to stderr; pass ``--quiet`` to suppress it.

    The parser used is pydbml; it is not byte-for-byte identical to the official
    @dbml/cli used by dbdiagram.io, but in practice catches the same syntax
    mistakes. For the authoritative check, run ``dbml2sql FILE --postgres`` from
    @dbml/cli once you have Node installed.
    """
    # Local import keeps the al2dbml convert path free of the parser cost at startup.
    import pydbml
    from pyparsing.exceptions import ParseBaseException

    source = file.read_text(encoding="utf-8")
    try:
        db = pydbml.PyDBML(source)
    except ParseBaseException as exc:
        raise click.ClickException(
            f"{file}: parse error at line {exc.lineno}, column {exc.column}: {exc.msg}"
        ) from exc

    if not quiet:
        summary = (
            f"{file}: OK — "
            f"tables={len(db.tables)}, "
            f"refs={len(db.refs)}, "
            f"enums={len(db.enums)}, "
            f"groups={len(db.table_groups)}"
        )
        click.echo(summary, err=True)


if __name__ == "__main__":
    main()
