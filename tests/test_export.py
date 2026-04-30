"""Tests for `quicksight-gen export docs`.

The legacy ``export training`` command + the whitelabel substitution
machinery were dropped in O.1.l. Docs render now happens via
mkdocs-macros against the L2-fed ``HandbookVocabulary`` — there's no
post-render string-replace step to test.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from click.testing import CliRunner

from quicksight_gen.cli import main


def test_bundled_docs_directory_exists():
    docs = files("quicksight_gen") / "docs"
    assert docs.is_dir()
    assert (docs / "index.md").is_file()
    assert (docs / "Schema_v6.md").is_file()
    assert (docs / "handbook" / "customization.md").is_file()


def test_export_docs_writes_tree(tmp_path: Path):
    runner = CliRunner()
    out = tmp_path / "exported-docs"
    result = runner.invoke(main, ["export", "docs", "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert (out / "index.md").is_file()
    assert (out / "Schema_v6.md").is_file()
    assert (out / "handbook" / "customization.md").is_file()
    assert (out / "walkthroughs" / "customization" /
            "how-do-i-test-my-customization.md").is_file()


def test_export_docs_requires_output(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(main, ["export", "docs"])
    assert result.exit_code != 0
    assert "--output" in result.output or "Missing option" in result.output
