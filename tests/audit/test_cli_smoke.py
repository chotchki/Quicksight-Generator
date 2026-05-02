"""CLI smoke for ``quicksight-gen audit`` — shape + cover-page render.

Verifies:
- ``audit --help`` lists the expected subcommands.
- ``audit apply`` (no --execute) emits Markdown carrying the L2
  institution heading + the resolved period + a generation timestamp
  + a provenance-fingerprint placeholder.
- ``audit apply --execute -o FILE`` writes a non-trivial PDF whose
  text payload mentions the institution + reporting period + footer
  provenance (proves reportlab is wired up + the L2 binding +
  cover-page layout threaded through).
- ``audit clean`` is a no-op without ``--execute`` and unlinks
  with it.

Real coverage of the underlying SQL + per-section template-input
dicts lands in U.8 (``test_sql.py`` + ``test_template_input.py``).
This file is the U.0 + U.1 acceptance net.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner

from quicksight_gen.cli import main
from quicksight_gen.cli.audit import _resolve_period


_FIXTURES = Path(__file__).parent.parent / "l2"
_SPEC_EXAMPLE = _FIXTURES / "spec_example.yaml"


@pytest.fixture
def min_config(tmp_path: Path) -> Path:
    """Minimal config.yaml — no demo_database_url; audit U.0 doesn't
    need a live DB connection (skeleton mode is metadata-only)."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "aws_account_id: '111122223333'\n"
        "aws_region: us-west-2\n"
        "datasource_arn: arn:aws:quicksight:us-west-2:111122223333"
        ":datasource/ds\n"
    )
    return cfg


def test_audit_help_lists_subcommands():
    runner = CliRunner()
    result = runner.invoke(main, ["audit", "--help"])
    assert result.exit_code == 0, result.output
    assert "apply" in result.output
    assert "clean" in result.output
    assert "test" in result.output


def test_audit_apply_emits_markdown_to_stdout(min_config: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "audit", "apply",
            "-c", str(min_config),
            "--l2", str(_SPEC_EXAMPLE),
        ],
    )
    assert result.exit_code == 0, result.output
    # Cover-page markdown shape sanity.
    assert "# QuickSight Generator audit report" in result.output
    assert "## spec_example" in result.output  # institution as H2
    assert "**Reporting period:**" in result.output
    assert "**Generated:**" in result.output
    assert "Provenance fingerprint:" in result.output
    assert "U.7" in result.output  # placeholder cites where real hash lands
    # Executive summary section sanity (U.2).
    assert "## Executive summary" in result.output
    assert "### Volume" in result.output
    assert "### Exception counts" in result.output
    assert "Transactions (legs)" in result.output
    assert "Drift" in result.output
    assert "Supersession" in result.output
    # No DB configured → placeholder notice rendered.
    assert "Database not configured" in result.output
    # U.3.a Drift violations section.
    assert "## Drift violations" in result.output
    # U.3.b Overdraft violations section.
    assert "## Overdraft violations" in result.output
    # U.3.c Limit breach violations section.
    assert "## Limit breach violations" in result.output


def test_audit_apply_emits_markdown_to_file(min_config: Path, tmp_path: Path):
    out = tmp_path / "report.md"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "audit", "apply",
            "-c", str(min_config),
            "--l2", str(_SPEC_EXAMPLE),
            "-o", str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.is_file()
    content = out.read_text()
    assert "# QuickSight Generator audit report" in content


def test_audit_apply_period_overrides(min_config: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "audit", "apply",
            "-c", str(min_config),
            "--l2", str(_SPEC_EXAMPLE),
            "--from", "2026-01-01",
            "--to", "2026-01-07",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "2026-01-01" in result.output
    assert "2026-01-07" in result.output


def test_audit_apply_period_from_after_to_errors(min_config: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "audit", "apply",
            "-c", str(min_config),
            "--l2", str(_SPEC_EXAMPLE),
            "--from", "2026-01-08",
            "--to", "2026-01-01",
        ],
    )
    assert result.exit_code != 0
    assert "must not be after" in result.output


def test_audit_apply_execute_writes_pdf(min_config: Path, tmp_path: Path):
    out = tmp_path / "report.pdf"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "audit", "apply",
            "-c", str(min_config),
            "--l2", str(_SPEC_EXAMPLE),
            "-o", str(out),
            "--execute",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.is_file()
    # PDFs start with %PDF- magic bytes.
    assert out.read_bytes().startswith(b"%PDF-")
    # End-to-end sanity (per Phase U test plan): extract text via
    # pypdf and confirm the institution + period + skeleton sentinel
    # actually rendered onto the page.
    from pypdf import PdfReader
    reader = PdfReader(str(out))
    # U.1 cover + U.2 executive summary = at least 2 pages.
    assert len(reader.pages) >= 2
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "audit report" in text.lower()
    assert "spec_example" in text  # institution heading rendered
    assert "Reporting period" in text  # period band rendered
    assert "Provenance" in text  # page footer rendered
    assert "U.7" in text  # fingerprint placeholder cites where it lands
    # U.2 executive summary content.
    assert "Executive summary" in text
    assert "Volume" in text
    assert "Exception counts" in text
    assert "Transactions (legs)" in text
    assert "Drift" in text
    assert "Supersession" in text
    # No DB → placeholder notice on the exec summary page.
    assert "Database not configured" in text
    # U.3.a Drift violations page.
    assert "Drift violations" in text
    # U.3.b Overdraft violations page.
    assert "Overdraft violations" in text
    # U.3.c Limit breach violations page.
    assert "Limit breach violations" in text


def test_audit_clean_default_is_dry_run(tmp_path: Path):
    target = tmp_path / "report.pdf"
    target.write_bytes(b"%PDF-stub")
    runner = CliRunner()
    result = runner.invoke(main, ["audit", "clean", "-o", str(target)])
    assert result.exit_code == 0, result.output
    assert "Would delete" in result.output
    assert target.exists(), "default clean should not actually delete"


def test_audit_clean_execute_deletes(tmp_path: Path):
    target = tmp_path / "report.pdf"
    target.write_bytes(b"%PDF-stub")
    runner = CliRunner()
    result = runner.invoke(
        main, ["audit", "clean", "-o", str(target), "--execute"],
    )
    assert result.exit_code == 0, result.output
    assert not target.exists()


def test_audit_clean_missing_file_is_noop(tmp_path: Path):
    target = tmp_path / "does-not-exist.pdf"
    runner = CliRunner()
    result = runner.invoke(main, ["audit", "clean", "-o", str(target)])
    assert result.exit_code == 0, result.output
    assert "doesn't exist" in result.output


def test_resolve_period_default_is_seven_day_window():
    """Default = today − 7 ... today − 1 (inclusive). 7 days, ending yesterday."""
    today = date(2026, 5, 15)
    start, end = _resolve_period(None, None, today=today)
    assert start == date(2026, 5, 8)
    assert end == date(2026, 5, 14)
    assert (end - start).days == 6  # inclusive 7-day window
