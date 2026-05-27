from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from al2dbml.validate import main

VALID_DBML = """\
Table users {
    id int [pk]
    name varchar(50)
}

Table posts {
    id int [pk]
    author_id int
}

Ref {
    posts.author_id > users.id
}
"""


INVALID_DBML = """\
Tabel users {
    id int [pk]
}
"""


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_valid_dbml_exits_zero_and_summarises(tmp_path: Path) -> None:
    file = _write(tmp_path, "schema.dbml", VALID_DBML)
    runner = CliRunner()
    result = runner.invoke(main, [str(file)])
    assert result.exit_code == 0
    # summary goes to stderr so a piped --quiet wouldn't surprise anyone
    assert "OK" in result.stderr
    assert "tables=2" in result.stderr
    assert "refs=1" in result.stderr


def test_invalid_dbml_exits_nonzero_with_line_info(tmp_path: Path) -> None:
    file = _write(tmp_path, "bad.dbml", INVALID_DBML)
    runner = CliRunner()
    result = runner.invoke(main, [str(file)])
    assert result.exit_code != 0
    assert "parse error" in result.stderr.lower()
    # error message should include line number for jump-to-line workflows
    assert "line" in result.stderr.lower()


def test_quiet_flag_suppresses_success_output(tmp_path: Path) -> None:
    file = _write(tmp_path, "schema.dbml", VALID_DBML)
    runner = CliRunner()
    result = runner.invoke(main, [str(file), "--quiet"])
    assert result.exit_code == 0
    assert result.stderr == ""
    assert result.stdout == ""


def test_missing_file_exits_nonzero(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, [str(tmp_path / "nope.dbml")])
    assert result.exit_code != 0


def test_help_mentions_pydbml(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "pydbml" in result.output.lower()


def test_round_trip_al2dbml_output_validates(tmp_path: Path) -> None:
    # The DBML al2dbml emits from the sample fixture must itself be parseable.
    # This is the cheapest possible regression net for emission bugs.
    from al2dbml.generator import Generator

    from .fixtures.sample_symbols import sample_symbols

    rendered = Generator(symbols=sample_symbols()).dbml()
    file = _write(tmp_path, "generated.dbml", rendered)
    runner = CliRunner()
    result = runner.invoke(main, [str(file)])
    assert result.exit_code == 0, result.stderr
