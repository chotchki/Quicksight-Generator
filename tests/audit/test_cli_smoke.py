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
    assert "verify" in result.output


def test_audit_verify_errors_on_pdf_without_provenance(
    min_config: Path, tmp_path: Path,
):
    """``audit verify`` against a PDF generated without a DB has no
    embedded provenance — must error out cleanly, not crash."""
    out = tmp_path / "report.pdf"
    runner = CliRunner()
    # Generate without DB → no embedded provenance.
    apply_result = runner.invoke(
        main,
        [
            "audit", "apply",
            "-c", str(min_config),
            "--l2", str(_SPEC_EXAMPLE),
            "-o", str(out),
            "--execute",
        ],
    )
    assert apply_result.exit_code == 0, apply_result.output

    verify_result = runner.invoke(
        main,
        [
            "audit", "verify", str(out),
            "-c", str(min_config),
            "--l2", str(_SPEC_EXAMPLE),
        ],
    )
    assert verify_result.exit_code != 0
    assert "no embedded provenance" in verify_result.output


def test_audit_verify_errors_on_missing_pdf(
    min_config: Path, tmp_path: Path,
):
    """``audit verify`` requires the PDF to exist."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "audit", "verify", str(tmp_path / "nope.pdf"),
            "-c", str(min_config),
        ],
    )
    assert result.exit_code != 0


def test_provenance_fingerprint_round_trips_through_dict():
    """to_dict / from_dict round trip preserves every field +
    composite_sha so the embedded JSON in a PDF can be rehydrated
    by ``audit verify`` without information loss.
    """
    from quicksight_gen.cli.audit import ProvenanceFingerprint
    fp = ProvenanceFingerprint(
        transactions_hwm=42,
        transactions_sha="a" * 64,
        balances_hwm=7,
        balances_sha="b" * 64,
        l2_yaml_sha="c" * 64,
        code_identity="v8.1.0+gabc1234567890",
    )
    payload = fp.to_dict()
    rehydrated = ProvenanceFingerprint.from_dict(payload)
    assert rehydrated == fp
    assert rehydrated.composite_sha == fp.composite_sha
    assert rehydrated.short == fp.composite_sha[:8]


def test_provenance_fingerprint_rejects_unknown_schema():
    """from_dict guards against rehydrating a future schema version
    that the running code doesn't understand — better to fail loud
    than silently misverify.
    """
    from quicksight_gen.cli.audit import ProvenanceFingerprint
    with pytest.raises(ValueError, match="Unrecognized provenance schema"):
        ProvenanceFingerprint.from_dict({"schema": "qsg-audit-provenance-v999"})


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
    assert "# QuickSight Generator Audit Report" in result.output
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
    # U.3.d Stuck pending transactions section.
    assert "## Stuck pending transactions" in result.output
    # U.3.e Stuck unbundled transactions section.
    assert "## Stuck unbundled transactions" in result.output
    # U.3.f Supersession audit section.
    assert "## Supersession audit" in result.output
    # U.5 Sign-off block.
    assert "## Sign-off" in result.output
    assert "### System attestation" in result.output
    assert "### Auditor attestation" in result.output
    assert "Generated by" in result.output
    assert "quicksight-gen v" in result.output
    assert "L2 instance" in result.output
    assert "Auditor name" in result.output
    assert "Notes / exceptions" in result.output


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
    assert "# QuickSight Generator Audit Report" in content


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
    # U.6 cover-page source-data provenance block.
    assert "Source-data provenance" in text
    assert "Transactions table" in text
    assert "Daily balances table" in text
    assert "L2 instance YAML" in text
    assert "quicksight-gen code" in text
    # U.6 per-page footer chrome (NumberedCanvas).
    assert "Page 1 of " in text
    assert "Provenance: pending" in text
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
    # U.3.d Stuck pending transactions page.
    assert "Stuck pending transactions" in text
    # U.3.e Stuck unbundled transactions page.
    assert "Stuck unbundled transactions" in text
    # U.3.f Supersession audit page.
    assert "Supersession audit" in text
    # U.5 Sign-off page.
    assert "Sign-off" in text
    assert "System attestation" in text
    assert "Auditor attestation" in text
    assert "quicksight-gen v" in text  # version stamped
    assert "Auditor name" in text  # printable form field
    assert "Notes / exceptions" in text


def test_audit_pdf_bookmarks_resolve_to_real_pages(
    min_config: Path, tmp_path: Path,
):
    """Bookmarks must land on the right page (regression net).

    Catches two failure modes seen in development:
    1. NumberedCanvas snapshot/restore pattern collapses every
       bookmark target to page 1 because ``dict(self.__dict__)``
       captured page-ref state and restoring overwrote the
       accumulated bookmark→page refs. Easy to miss because the
       PDF still renders fine and the TOC text looks normal — only
       the sidebar nav is broken.
    2. multiBuild stopping too early so TOC/bookmarks disagree
       (off-by-one on a section heading after a TOC overflow shift).

    Asserts:
    - Bookmarks span ≥3 distinct pages (would catch the all-page-1
      collapse outright).
    - Bookmarks are monotonically non-decreasing in PDF order
      (parents come before children top-of-doc to bottom).
    - No two top-level (H1) bookmarks point to the same page (every
      section header is its own ``PageBreak``-separated page; if two
      collapse it means a section emitted nothing or PageBreak
      handling broke).
    - The TOC page text contains every H1 title (sanity that the
      TOC flowable rendered the entries it collected).
    """
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

    from pypdf import PdfReader
    reader = PdfReader(str(out))

    # Walk the outline: collect (depth, title, 1-indexed page).
    entries: list[tuple[int, str, int]] = []

    def walk(items, depth=0):  # type: ignore[no-untyped-def]
        for item in items:
            if isinstance(item, list):
                walk(item, depth + 1)
            else:
                page_idx = reader.get_destination_page_number(item)
                entries.append((depth, item.title, page_idx + 1))

    walk(reader.outline)
    assert entries, "PDF outline is empty — bookmarks didn't emit"

    pages = [page for _, _, page in entries]
    distinct_pages = set(pages)
    assert len(distinct_pages) >= 3, (
        f"Bookmarks collapsed onto {len(distinct_pages)} distinct "
        f"pages ({sorted(distinct_pages)}) — likely the canvas "
        f"snapshot/restore bug that overwrites destinations dict. "
        f"Outline: {entries[:5]}"
    )

    # Monotonicity in PDF order.
    for prev, curr in zip(entries, entries[1:]):
        assert prev[2] <= curr[2], (
            f"Bookmarks out of order: {prev} comes before {curr} but "
            f"its page is later. multiBuild may not have converged."
        )

    # No two H1s on same page.
    h1_entries = [e for e in entries if e[0] == 0]
    h1_pages: dict[int, str] = {}
    for _, title, page in h1_entries:
        if page in h1_pages:
            raise AssertionError(
                f"Two top-level sections collapsed to page {page}: "
                f"'{h1_pages[page]}' and '{title}'. Either a section "
                f"emitted no content or a PageBreak got dropped."
            )
        h1_pages[page] = title

    # TOC contains every H1 title.
    toc_text = ""
    for page in reader.pages[:5]:
        text = page.extract_text(extraction_mode="layout") or ""
        if "Table of contents" in text or toc_text:
            toc_text += text + "\n"
    missing_toc = [
        title for _, title, _ in h1_entries if title not in toc_text
    ]
    assert not missing_toc, (
        f"TOC text is missing H1 entries: {missing_toc}. "
        f"TOC flowable may have rendered before all entries were "
        f"collected (multiBuild convergence)."
    )


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
