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

Phase U.2 ships the **executive summary page** on top of the U.1
cover: per-period totals (transaction count, transfer count, dollar
volume gross/net) + L1 invariant exception counts (drift, ledger
drift, overdraft, limit breach, stuck pending, stuck unbundled,
supersession). Real numbers when ``demo_database_url`` is configured;
graceful "—" placeholders + a notice when it isn't, so the layout
stays previewable without a live DB.

Page footer carries a provenance-fingerprint placeholder (real
fingerprint lands in U.7). Per-invariant violation tables, the
per-account-day Daily Statement walk, and the sign-off block land
in U.3+.

Period default: ``yesterday + last 7 days`` (a 7-day window ending
yesterday). Override with ``--from YYYY-MM-DD`` / ``--to YYYY-MM-DD``.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
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


# -- Executive summary (U.2) --------------------------------------------------


@dataclass(frozen=True)
class ExecSummary:
    """Totals rendered on the executive summary page.

    All counts are inclusive of both period endpoints. Dollar volume
    follows the dashboards' per-transfer aggregation convention
    (``MAX(ABS(amount_money))`` for gross, ``SUM(amount_money)`` for
    net) so a multi-leg transfer counts once, not once per leg.
    """
    transactions_count: int
    transfers_count: int
    dollar_volume_gross: Decimal
    dollar_volume_net: Decimal
    # Ordered (label, count) pairs — preserves render order.
    exception_counts: list[tuple[str, int]]


# (display label, matview suffix, date column on that matview)
_EXCEPTION_INVARIANTS: list[tuple[str, str, str]] = [
    ("Drift", "drift", "business_day_start"),
    ("Ledger drift", "ledger_drift", "business_day_start"),
    ("Overdraft", "overdraft", "business_day_start"),
    ("Limit breach", "limit_breach", "business_day"),
    ("Stuck pending", "stuck_pending", "posting"),
    ("Stuck unbundled", "stuck_unbundled", "posting"),
]


def _query_executive_summary(
    cfg, instance, period: tuple[date, date],  # type: ignore[no-untyped-def]
) -> ExecSummary | None:
    """Aggregate the executive-summary totals against the demo DB.

    Returns None when ``cfg.demo_database_url`` is unset — the
    renderers fall back to "—" placeholders so the layout stays
    previewable without a live connection.

    Date literals use ``DATE 'YYYY-MM-DD'`` which both Postgres and
    Oracle accept; the inclusive end is enforced via ``< end + 1
    day`` so end-of-period TIMESTAMPs are caught.
    """
    if cfg.demo_database_url is None:
        return None

    from quicksight_gen.common.db import connect_demo_db

    prefix = instance.instance
    start, end = period
    start_lit = f"DATE '{start.isoformat()}'"
    end_excl_lit = f"DATE '{(end + timedelta(days=1)).isoformat()}'"

    conn = connect_demo_db(cfg)
    try:
        cur = conn.cursor()

        cur.execute(
            f"SELECT COUNT(*),"
            f" COUNT(DISTINCT transfer_id)"
            f" FROM {prefix}_transactions"
            f" WHERE status = 'Posted'"
            f"   AND posting >= {start_lit}"
            f"   AND posting < {end_excl_lit}"
        )
        leg_count, transfer_count = cur.fetchone()

        cur.execute(
            f"SELECT COALESCE(SUM(transfer_gross), 0),"
            f" COALESCE(SUM(transfer_net), 0)"
            f" FROM ("
            f"   SELECT MAX(ABS(amount_money)) AS transfer_gross,"
            f"          SUM(amount_money) AS transfer_net"
            f"   FROM {prefix}_transactions"
            f"   WHERE status = 'Posted'"
            f"     AND posting >= {start_lit}"
            f"     AND posting < {end_excl_lit}"
            f"   GROUP BY transfer_id"
            f" ) per_transfer"
        )
        gross, net = cur.fetchone()

        exception_counts: list[tuple[str, int]] = []
        for label, suffix, date_col in _EXCEPTION_INVARIANTS:
            cur.execute(
                f"SELECT COUNT(*) FROM {prefix}_{suffix}"
                f" WHERE {date_col} >= {start_lit}"
                f"   AND {date_col} < {end_excl_lit}"
            )
            (count,) = cur.fetchone()
            exception_counts.append((label, int(count or 0)))

        # Supersession: count distinct logical transactions whose any
        # entry posts in the period AND have >1 entries (i.e. were
        # superseded). Mirrors the L1 dashboard's
        # build_supersession_transactions_dataset window-function read.
        cur.execute(
            f"SELECT COUNT(*) FROM ("
            f"   SELECT id FROM {prefix}_transactions"
            f"   WHERE posting >= {start_lit}"
            f"     AND posting < {end_excl_lit}"
            f"   GROUP BY id"
            f"   HAVING COUNT(*) > 1"
            f" ) superseded"
        )
        (superseded_count,) = cur.fetchone()
        exception_counts.append(("Supersession", int(superseded_count or 0)))

        return ExecSummary(
            transactions_count=int(leg_count or 0),
            transfers_count=int(transfer_count or 0),
            dollar_volume_gross=Decimal(gross or 0),
            dollar_volume_net=Decimal(net or 0),
            exception_counts=exception_counts,
        )
    finally:
        conn.close()


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
    exec_summary = _query_executive_summary(_cfg, instance, (start, end))

    if execute:
        out_path = Path(output) if output is not None else Path("report.pdf")
        _write_audit_pdf(
            out_path,
            institution=institution,
            period=(start, end),
            generated_at=generated_at,
            exec_summary=exec_summary,
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
        exec_summary=exec_summary,
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
    exec_summary: ExecSummary | None,
) -> str:
    """Markdown rendering of the audit report.

    Mirrors the PDF page sequence — cover, then executive summary —
    so an integrator can review the report's content before
    committing to a real PDF write. U.3+ appends per-invariant
    tables, the Daily Statement walk, and the sign-off block.
    """
    start, end = period
    fingerprint = _l2_fingerprint_placeholder()
    cover = (
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
    )
    body = _render_executive_summary_markdown(exec_summary)
    trailer = (
        "\n"
        "_Per-invariant violation tables, the per-account-day Daily "
        "Statement walk, and the sign-off block land in Phase U.3+._\n"
    )
    return cover + body + trailer


def _render_executive_summary_markdown(
    summary: ExecSummary | None,
) -> str:
    """Executive summary section in Markdown form.

    Renders the same Volume + Exception-counts tables as the PDF.
    When ``summary`` is None (no DB), shows "—" cells with a notice
    so the layout stays previewable.
    """
    if summary is None:
        volume_rows = (
            "| Transactions (legs) | — |\n"
            "| Transfers (logical events) | — |\n"
            "| Dollar volume — gross | — |\n"
            "| Dollar volume — net | — |\n"
        )
        exc_labels = [label for label, _, _ in _EXCEPTION_INVARIANTS] + [
            "Supersession",
        ]
        exc_rows = "".join(f"| {label} | — |\n" for label in exc_labels)
        notice = (
            "\n_Database not configured — totals shown as placeholders. "
            "Set `demo_database_url` in your config to populate._\n"
        )
    else:
        volume_rows = (
            f"| Transactions (legs) | {summary.transactions_count:,} |\n"
            f"| Transfers (logical events) | {summary.transfers_count:,} |\n"
            f"| Dollar volume — gross | "
            f"${summary.dollar_volume_gross:,.2f} |\n"
            f"| Dollar volume — net | "
            f"${summary.dollar_volume_net:,.2f} |\n"
        )
        exc_rows = "".join(
            f"| {label} | {count:,} |\n"
            for label, count in summary.exception_counts
        )
        notice = ""
    return (
        "\n"
        "---\n"
        "\n"
        "## Executive summary\n"
        f"{notice}"
        "\n"
        "### Volume\n"
        "\n"
        "| Metric | Value |\n"
        "|---|---:|\n"
        f"{volume_rows}"
        "\n"
        "### Exception counts\n"
        "\n"
        "| Invariant | Count |\n"
        "|---|---:|\n"
        f"{exc_rows}"
    )


def _write_audit_pdf(
    path: Path,
    *,
    institution: str,
    period: tuple[date, date],
    generated_at: datetime,
    exec_summary: ExecSummary | None,
) -> None:
    """Render the audit report as a PDF.

    Page 1 is the cover (title, institution, period band, generation
    timestamp, scope prose). Page 2 is the U.2 executive summary
    (Volume + Exception-counts tables). Every page carries a footer
    with the provenance fingerprint placeholder (real hash lands in
    U.7). U.3+ extends the platypus story with per-invariant tables.
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
    ]
    story.extend(_executive_summary_story(exec_summary, styles, period))
    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)


def _executive_summary_story(
    summary: ExecSummary | None,
    styles,  # type: ignore[no-untyped-def]
    period: tuple[date, date],
) -> list:  # type: ignore[type-arg]
    """Platypus elements for the U.2 executive summary page.

    Caller appends to the doc story after the cover page. Renders a
    page break, heading, period context, and two tables (Volume +
    Exception counts). When summary is None, renders "—" cells and a
    notice — keeps the layout reviewable without a live DB.
    """
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    start, end = period
    elements: list = [
        PageBreak(),
        Paragraph("Executive summary", styles["Heading1"]),
        Paragraph(
            f"Reporting period: {start.isoformat()} &ndash; "
            f"{end.isoformat()} (inclusive)",
            styles["BodyText"],
        ),
        Spacer(1, 0.15 * inch),
    ]

    if summary is None:
        elements.append(
            Paragraph(
                "<i>Database not configured &mdash; totals shown as "
                "placeholders. Set <b>demo_database_url</b> in your "
                "config to populate.</i>",
                styles["BodyText"],
            ),
        )
        volume_data = [
            ["Metric", "Value"],
            ["Transactions (legs)", "—"],
            ["Transfers (logical events)", "—"],
            ["Dollar volume — gross", "—"],
            ["Dollar volume — net", "—"],
        ]
        exc_rows = [[label, "—"] for label, _, _ in _EXCEPTION_INVARIANTS]
        exc_rows.append(["Supersession", "—"])
        exception_data = [["Invariant", "Count"]] + exc_rows
    else:
        volume_data = [
            ["Metric", "Value"],
            ["Transactions (legs)", f"{summary.transactions_count:,}"],
            ["Transfers (logical events)", f"{summary.transfers_count:,}"],
            ["Dollar volume — gross", f"${summary.dollar_volume_gross:,.2f}"],
            ["Dollar volume — net", f"${summary.dollar_volume_net:,.2f}"],
        ]
        exception_data = [["Invariant", "Count"]] + [
            [label, f"{count:,}"]
            for label, count in summary.exception_counts
        ]

    table_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a1a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c7d6e3")),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ])
    col_widths = [3.5 * inch, 2.5 * inch]

    elements.extend([
        Spacer(1, 0.15 * inch),
        Paragraph("Volume", styles["Heading3"]),
        Spacer(1, 0.05 * inch),
        Table(volume_data, colWidths=col_widths, style=table_style),
        Spacer(1, 0.3 * inch),
        Paragraph("Exception counts", styles["Heading3"]),
        Spacer(1, 0.05 * inch),
        Table(exception_data, colWidths=col_widths, style=table_style),
    ])
    return elements


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
