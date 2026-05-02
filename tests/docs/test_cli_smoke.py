"""CLI smoke for ``quicksight-gen docs`` — help + safe-emit paths.

U.9 acceptance net for the docs artifact group. Mirrors the shape
of ``tests/audit/test_cli_smoke.py``: minimal config + ``CliRunner``,
asserts ``--help`` lists every subcommand, asserts each verb's
``--help`` exits 0, and exercises the ``clean`` no-op path against
a tmp directory.

The other docs verbs are covered elsewhere or not amenable to a
fast smoke:

- ``apply`` — wraps ``mkdocs build`` (subprocess, ~10s+, scans the
  whole docs tree). Heavy; skipped — ``docs test`` runs the docs
  link sweep + persona-neutral check, which is the targeted
  emit-side regression net.
- ``serve`` — interactive blocking subprocess (mkdocs live-reload).
  Only ``--help`` smoke.
- ``test`` — shells out to pytest + pyright; only ``--help``
  (running the subprocess from inside a pytest run would recurse).
- ``export`` + ``screenshot`` — already covered in
  ``test_cli_export_screenshot.py`` in this directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from quicksight_gen.cli import main


def test_docs_help_lists_subcommands():
    runner = CliRunner()
    result = runner.invoke(main, ["docs", "--help"])
    assert result.exit_code == 0, result.output
    assert "apply" in result.output
    assert "serve" in result.output
    assert "clean" in result.output
    assert "test" in result.output
    assert "export" in result.output
    assert "screenshot" in result.output


@pytest.mark.parametrize(
    "verb", ["apply", "serve", "clean", "test", "export", "screenshot"],
)
def test_docs_verb_help_exits_zero(verb: str):
    runner = CliRunner()
    result = runner.invoke(main, ["docs", verb, "--help"])
    assert result.exit_code == 0, result.output


def test_docs_clean_missing_dir_is_noop(tmp_path: Path):
    """``docs clean -o DIR`` against a non-existent directory exits
    cleanly with a "nothing to clean" notice — no destructive ops."""
    target = tmp_path / "site"
    runner = CliRunner()
    result = runner.invoke(main, ["docs", "clean", "-o", str(target)])
    assert result.exit_code == 0, result.output
    assert "doesn't exist" in result.output
    assert not target.exists()


def test_docs_clean_removes_existing_dir(tmp_path: Path):
    """``docs clean -o DIR`` removes an existing site/ directory."""
    target = tmp_path / "site"
    target.mkdir()
    (target / "index.html").write_text("<html></html>")
    runner = CliRunner()
    result = runner.invoke(main, ["docs", "clean", "-o", str(target)])
    assert result.exit_code == 0, result.output
    assert "Removed" in result.output
    assert not target.exists()
