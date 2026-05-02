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


# ---------------------------------------------------------------------------
# `quicksight-gen export screenshots` (Q.2.c.exec.1)
# ---------------------------------------------------------------------------


def test_export_screenshots_help_lists_all_apps():
    """Sanity: every shipped app slug appears in --app's choices."""
    runner = CliRunner()
    result = runner.invoke(main, ["export", "screenshots", "--help"])
    assert result.exit_code == 0, result.output
    for slug in ("l1-dashboard", "l2-flow-tracing", "investigation",
                 "executives"):
        assert slug in result.output, slug


def test_export_screenshots_requires_app_or_all(tmp_path: Path):
    """Without --app or --all the command must refuse."""
    runner = CliRunner()
    result = runner.invoke(
        main, ["export", "screenshots", "-o", str(tmp_path / "shots")],
    )
    assert result.exit_code != 0
    assert "--app" in result.output or "--all" in result.output


def test_export_screenshots_rejects_app_plus_all(tmp_path: Path):
    """Passing both --app and --all is a usage error."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "export", "screenshots",
            "--app", "l1-dashboard", "--all",
            "-o", str(tmp_path / "shots"),
        ],
    )
    assert result.exit_code != 0
    assert "either --app" in result.output or "not both" in result.output


def test_export_screenshots_requires_output():
    runner = CliRunner()
    result = runner.invoke(
        main, ["export", "screenshots", "--app", "l1-dashboard"],
    )
    assert result.exit_code != 0
    assert "--output" in result.output or "Missing option" in result.output


def test_parse_viewport_defaults_and_errors():
    """The viewport parser accepts WxH integers + rejects malformed input."""
    from quicksight_gen.cli import _parse_viewport

    assert _parse_viewport("1280x900") == (1280, 900)
    # Case-insensitive 'X'.
    assert _parse_viewport("1280X900") == (1280, 900)

    import click as _click
    import pytest

    for bad in ("1280", "1280x", "x900", "abcxdef", "0x900", "1280x-1"):
        with pytest.raises(_click.BadParameter):
            _parse_viewport(bad)


def test_screenshot_apps_table_matches_apps_constant():
    """Q.2.c.exec.1: --app's choice set must stay aligned with the
    canonical APPS tuple so a new app can't slip into one but not
    the other.
    """
    from quicksight_gen.cli import APPS, _SCREENSHOT_APPS

    assert set(_SCREENSHOT_APPS.keys()) == set(APPS)
