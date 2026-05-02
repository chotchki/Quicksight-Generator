"""``quicksight-gen audit`` — PDF reconciliation report.

Three operations:

  apply  — emit Markdown source for the report (default), or
           ``--execute`` to write a PDF via reportlab.
  clean  — list the report file that would be removed (default), or
           ``--execute`` to delete it.
  test   — pytest the audit module + pyright.

The report is a regulator-ready PDF generated **directly from the
database**, querying the per-prefix L1 invariant matviews + base
tables. Same emit-vs-execute pattern as the other artifact groups —
no ``--execute`` means the integrator can review the rendered
Markdown / page outline before committing to a real PDF write.

Phase U.1 ships the **cover page**: institution heading + period
band + generation timestamp, plus a provenance-fingerprint placeholder
rendered into the page footer (real fingerprint lands in U.7). Body
sections (executive summary, per-invariant tables, per-account-day
Daily Statement walk, sign-off block) land in U.2+.

Period default: ``yesterday + last 7 days`` (a 7-day window ending
yesterday). Override with ``--from YYYY-MM-DD`` / ``--to YYYY-MM-DD``.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import click

from quicksight_gen.cli._helpers import (
    config_option,
    execute_option,
    l2_instance_option,
    resolve_l2_for_demo,
)


@click.group()
def audit() -> None:
    """Per-instance PDF reconciliation report (cover, summary, exceptions)."""


def _period_option_from():  # type: ignore[no-untyped-def]
    return click.option(
        "--from", "period_from",
        type=click.DateTime(formats=["%Y-%m-%d"]), default=None,
        help=(
            "Period start (YYYY-MM-DD, inclusive). Default: today − 7 days "
            "(start of the 7-day window ending yesterday)."
        ),
    )


def _period_option_to():  # type: ignore[no-untyped-def]
    return click.option(
        "--to", "period_to",
        type=click.DateTime(formats=["%Y-%m-%d"]), default=None,
        help=(
            "Period end (YYYY-MM-DD, inclusive). Default: yesterday "
            "(today − 1)."
        ),
    )


def _resolve_period(
    period_from: datetime | None, period_to: datetime | None,
    *, today: date | None = None,
) -> tuple[date, date]:
    """Resolve the report period.

    Default: a 7-day window ending yesterday — i.e. ``[today − 7,
    today − 1]`` inclusive. Both endpoints are inclusive dates.
    Override either endpoint via ``--from`` / ``--to``.
    """
    anchor = today or date.today()
    end = period_to.date() if period_to is not None else anchor - timedelta(days=1)
    start = period_from.date() if period_from is not None else anchor - timedelta(days=7)
    if start > end:
        raise click.UsageError(
            f"--from ({start.isoformat()}) must not be after --to "
            f"({end.isoformat()})."
        )
    return start, end


def _institution_name(instance) -> str:  # type: ignore[no-untyped-def]
    """Pull the institution display name from the L2 persona block.

    Falls back to the L2 instance identifier when no persona block is
    declared — the report still renders cleanly against any L2 YAML.
    """
    persona = getattr(instance, "persona", None)
    if persona is not None and persona.institution:
        return str(persona.institution[0])
    return str(instance.instance)


@audit.command("apply")
@l2_instance_option()
@config_option(required_for_dialect_only=True)
@_period_option_from()
@_period_option_to()
@click.option(
    "-o", "--output", "output",
    type=click.Path(), default=None,
    help=(
        "Output path. Without --execute: Markdown source destination "
        "(default: stdout). With --execute: PDF destination "
        "(default: report.pdf)."
    ),
)
@execute_option()
def audit_apply(
    l2_instance_path: str | None,
    config: str,
    period_from: datetime | None,
    period_to: datetime | None,
    output: str | None,
    execute: bool,
) -> None:
    """Emit the audit report's Markdown source (or ``--execute`` to write a PDF).

    Default: print the Markdown rendering of the report (cover +
    section outline) to stdout. Pass ``-o FILE`` to write to a file.
    Useful for review before committing to a PDF.

    Pass ``--execute`` to render the report as a PDF via reportlab.
    Default destination is ``report.pdf`` in the current working
    directory; override with ``-o FILE``.

    Phase U.1 ships the cover page; body sections (executive summary,
    per-invariant tables, Daily Statement walk, sign-off block) land
    in U.2+ as the page-by-page review gates close.
    """
    _cfg, instance = resolve_l2_for_demo(config, l2_instance_path)
    start, end = _resolve_period(period_from, period_to)
    institution = _institution_name(instance)
    generated_at = datetime.now()

    if execute:
        out_path = Path(output) if output is not None else Path("report.pdf")
        _write_audit_pdf(
            out_path,
            institution=institution,
            period=(start, end),
            generated_at=generated_at,
        )
        click.echo(
            f"Wrote audit report to {out_path} "
            f"(institution={institution}, period={start}–{end})."
        )
        return

    markdown = _render_audit_markdown(
        institution=institution,
        period=(start, end),
        generated_at=generated_at,
    )
    if output is None:
        click.echo(markdown, nl=False)
        return
    Path(output).write_text(markdown, encoding="utf-8")
    click.echo(
        f"Wrote audit Markdown source to {output} "
        f"({len(markdown)} bytes).",
        err=True,
    )


@audit.command("clean")
@click.option(
    "-o", "--output", "output",
    type=click.Path(), default="report.pdf",
    help="PDF path to remove (default: report.pdf).",
)
@execute_option()
def audit_clean(output: str, execute: bool) -> None:
    """Print or remove the generated report file.

    Default: print the path that would be deleted (no side effect).
    Pass ``--execute`` to actually unlink it.
    """
    target = Path(output)
    if not target.exists():
        click.echo(f"{target} doesn't exist; nothing to clean.")
        return
    if not execute:
        click.echo(f"Would delete: {target}")
        return
    target.unlink()
    click.echo(f"Removed {target}")


@audit.command("test")
@click.option(
    "--pytest-args", default="",
    help="Extra args passed verbatim to pytest (e.g. '-k smoke').",
)
def audit_test(pytest_args: str) -> None:
    """Run the audit test suite (pytest + pyright on cli/audit.py)."""
    pytest_argv = (
        [sys.executable, "-m", "pytest", "tests/audit/", "-q"]
        + (pytest_args.split() if pytest_args else [])
    )
    pyright_argv = [
        sys.executable, "-m", "pyright",
        "src/quicksight_gen/cli/audit.py",
    ]
    failed = []
    click.echo(f"$ {' '.join(pytest_argv)}")
    if subprocess.call(pytest_argv) != 0:
        failed.append("pytest")
    click.echo(f"$ {' '.join(pyright_argv)}")
    if subprocess.call(pyright_argv) != 0:
        failed.append("pyright")
    if failed:
        raise click.ClickException(f"audit test failed: {', '.join(failed)}")
    click.echo("audit test: OK")


# -- Renderers (cover page — U.2+ appends body sections) ----------------------


def _l2_fingerprint_placeholder() -> str:
    """Provenance-fingerprint placeholder.

    U.7 replaces this with ``sha256(L2_instance_fingerprint ||
    sorted_matview_row_hashes || period_anchor)`` and adds an
    ``audit verify`` subcommand. The placeholder text is distinctive
    enough that grep'ing the rendered report for it catches a "we
    shipped without wiring U.7" regression before the auditor does.
    """
    return "<pending — see Phase U.7>"


def _render_audit_markdown(
    *,
    institution: str,
    period: tuple[date, date],
    generated_at: datetime,
) -> str:
    """Markdown rendering of the audit report.

    Mirrors the PDF cover-page shape so an integrator can review the
    report's content before committing to a real PDF write. U.2+
    appends body sections (executive summary, per-invariant tables,
    Daily Statement walk, sign-off block).
    """
    start, end = period
    fingerprint = _l2_fingerprint_placeholder()
    return (
        "# QuickSight Generator audit report\n"
        "\n"
        f"## {institution}\n"
        "\n"
        f"**Reporting period:** {start.isoformat()} – {end.isoformat()} "
        "(inclusive)\n"
        "\n"
        f"**Generated:** {generated_at.isoformat(timespec='seconds')}\n"
        "\n"
        "This report covers the L1 reconciliation invariants — drift, "
        "overdraft, limit breach, stuck pending, stuck unbundled, "
        "supersession audit — for the period above. Sourced directly "
        "from the operator's database matviews; see the provenance "
        "fingerprint at the bottom of every page for reproducibility.\n"
        "\n"
        "---\n"
        "\n"
        f"_Provenance fingerprint:_ `{fingerprint}`\n"
        "\n"
        "_Body sections (executive summary, per-invariant violation "
        "tables, per-account-day Daily Statement walk, sign-off block) "
        "land in Phase U.2+._\n"
    )


def _write_audit_pdf(
    path: Path,
    *,
    institution: str,
    period: tuple[date, date],
    generated_at: datetime,
) -> None:
    """Render the audit report as a PDF.

    U.1 lays out the cover page: title, institution heading, period
    band, generation timestamp, scope prose, and a provenance footer
    on every page (placeholder fingerprint until U.7). U.2+ appends
    body pages by extending the platypus story.
    """
    # Imported lazily so the audit CLI loads even when the [audit]
    # extra isn't installed — only --execute paths need reportlab.
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.85 * inch,  # extra room for the page footer
        title=f"QuickSight Generator audit report — {institution}",
    )
    styles = getSampleStyleSheet()
    institution_style = ParagraphStyle(
        "InstitutionName",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        spaceBefore=0,
        spaceAfter=12,
    )
    period_band_style = ParagraphStyle(
        "PeriodBand",
        parent=styles["BodyText"],
        fontSize=13,
        leading=18,
        spaceBefore=6,
        spaceAfter=6,
        textColor=HexColor("#1a1a1a"),
        backColor=HexColor("#eef3f7"),
        borderColor=HexColor("#c7d6e3"),
        borderWidth=0.5,
        borderPadding=10,
    )
    start, end = period
    story = [
        Paragraph(
            "QuickSight Generator audit report",
            styles["Title"],
        ),
        Spacer(1, 0.2 * inch),
        Paragraph(institution, institution_style),
        Spacer(1, 0.1 * inch),
        Paragraph(
            f"<b>Reporting period:</b> {start.isoformat()} &ndash; "
            f"{end.isoformat()} (inclusive)",
            period_band_style,
        ),
        Spacer(1, 0.25 * inch),
        Paragraph(
            f"<b>Generated:</b> {generated_at.isoformat(timespec='seconds')}",
            styles["BodyText"],
        ),
        Spacer(1, 0.4 * inch),
        Paragraph(
            "This report covers the L1 reconciliation invariants &mdash; "
            "drift, overdraft, limit breach, stuck pending, stuck "
            "unbundled, supersession audit &mdash; for the period above. "
            "Sourced directly from the operator's database matviews; see "
            "the provenance fingerprint at the bottom of every page for "
            "reproducibility.",
            styles["BodyText"],
        ),
        Spacer(1, 0.4 * inch),
        Paragraph(
            "<i>Body sections (executive summary, per-invariant violation "
            "tables, per-account-day Daily Statement walk, sign-off block) "
            "land in Phase U.2+.</i>",
            styles["BodyText"],
        ),
    ]
    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)


def _draw_footer(canvas, doc) -> None:  # type: ignore[no-untyped-def]
    """Page footer drawn on every page.

    Per Phase U.6 the footer carries the report-version sentinel,
    page number, and the source-data fingerprint. U.1 wires the slot
    with a placeholder fingerprint so the layout is correct when U.7
    swaps the real hash in.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch

    canvas.saveState()
    width, _ = letter
    canvas.setFont("Helvetica", 8)
    canvas.setFillGray(0.4)
    left = 0.75 * inch
    right = width - 0.75 * inch
    baseline = 0.5 * inch
    canvas.drawString(
        left, baseline,
        f"QuickSight Generator audit report  ·  Page {doc.page}",
    )
    canvas.drawRightString(
        right, baseline,
        f"Provenance: {_l2_fingerprint_placeholder()}",
    )
    canvas.restoreState()
