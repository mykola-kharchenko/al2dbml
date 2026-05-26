from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from al2dbml.__main__ import main

from .fixtures.sample_symbols import sample_symbols


def _make_app(tmp_path: Path, name: str = "sample.app") -> Path:
    payload = json.dumps(sample_symbols()).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SymbolReference.json", payload)
    app = tmp_path / name
    app.write_bytes(buf.getvalue())
    return app


def test_help_mentions_group_option() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "--group" in result.output
    assert "APP" in result.output


def test_output_to_file_prints_to_stderr(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    out = tmp_path / "schema.dbml"
    runner = CliRunner()
    result = runner.invoke(main, [str(app), "-o", str(out)])
    assert result.exit_code == 0, result.stderr
    assert result.stdout == ""
    assert f"wrote {out}" in result.stderr
    body = out.read_text(encoding="utf-8")
    assert 'Table "dbo"."Customer"' in body


def test_default_output_goes_to_stdout(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, [str(app)])
    assert result.exit_code == 0, result.stderr
    assert 'Enum "Customer Type"' in result.stdout
    assert 'TableGroup "Sales"' in result.stdout
    assert not result.stdout.endswith("\n\n")


def test_explicit_group_rule(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, [str(app), "-g", "Sales=Sales*"])
    assert result.exit_code == 0
    assert 'TableGroup "Sales"' in result.stdout


def test_no_groups_flag(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, [str(app), "--no-groups"])
    assert result.exit_code == 0
    assert "TableGroup" not in result.stdout


def test_no_merge_extensions(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, [str(app), "--no-merge-extensions"])
    assert result.exit_code == 0
    assert 'Table "dbo"."Customer (Extension)"' in result.stdout


def test_invalid_group_rule_exits_nonzero(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, [str(app), "-g", "noequals"])
    assert result.exit_code != 0
    assert "group" in result.stderr.lower()


def test_missing_input_file_exits_nonzero(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, [str(tmp_path / "missing.app")])
    assert result.exit_code != 0


def test_version_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "al2dbml" in result.output


def test_min_group_size_zero_rejected(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, [str(app), "--min-group-size", "0"])
    assert result.exit_code != 0


@pytest.mark.parametrize("ext", ["badapp"])
def test_bad_archive_reports_useful_error(tmp_path: Path, ext: str) -> None:
    bad = tmp_path / f"{ext}.app"
    bad.write_bytes(b"not a real zip")
    runner = CliRunner()
    result = runner.invoke(main, [str(bad)])
    assert result.exit_code != 0
