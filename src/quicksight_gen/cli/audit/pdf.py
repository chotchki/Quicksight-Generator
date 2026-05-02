"""PDF renderers for the audit report.

reportlab story builders that take pre-queried dataclass instances
(``cli/audit/__init__.py`` populates them) + the resolved
``ThemePreset`` and assemble the page sequence: cover (with optional
logo + provenance block) → TOC → exec summary → per-invariant
sections → Daily Statement walks → sign-off.

Generic reportlab plumbing (``BookmarkedDocTemplate``,
``bookmarked_h1``/``h3``, ``make_footer_drawer``) lives in
``common/pdf/audit_chrome.py`` so this module stays focused on
audit-specific story content.
"""

from __future__ import annotations

import json as _json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import click

from quicksight_gen.common.pdf.audit_chrome import (
    BookmarkedDocTemplate,
    bookmarked_h1,
    bookmarked_h3,
    make_footer_drawer,
)
from quicksight_gen.common.provenance import (
    ProvenanceFingerprint,
    l2_fingerprint_placeholder,
)


from quicksight_gen.cli.audit import (
    DailyStatementWalk,
    DriftViolation,
    ExecSummary,
    LimitBreachViolation,
    OverdraftViolation,
    StuckPendingViolation,
    StuckUnbundledViolation,
    SupersessionAuditData,
    _EXCEPTION_INVARIANTS,
    _format_age,
    _split_limit_breach_by_account_class,
    _split_overdraft_by_account_class,
    _split_stuck_pending_by_account_class,
    _split_stuck_unbundled_by_account_class,
)


def _write_audit_pdf(
    path: Path,
    *,
    institution: str,
    period: tuple[date, date],
    generated_at: datetime,
    exec_summary: ExecSummary | None,
    drift_rows: list[DriftViolation] | None,
    overdraft_rows: list[OverdraftViolation] | None,
    limit_breach_rows: list[LimitBreachViolation] | None,
    stuck_pending_rows: list[StuckPendingViolation] | None,
    stuck_unbundled_rows: list[StuckUnbundledViolation] | None,
    supersession_data: SupersessionAuditData | None,
    daily_statement_walks: list[DailyStatementWalk] | None,
    singleton_ids: set[str],
    theme,  # type: ignore[no-untyped-def] # ThemePreset
    version: str,
    l2_label: str,
    provenance: ProvenanceFingerprint | None,
) -> None:
    """Render the audit report as a PDF.

    Page sequence: cover → table of contents → executive summary →
    per-invariant tables (Drift, Overdraft, Limit breach, Stuck
    pending, Stuck unbundled, Supersession audit) → per-account Daily
    Statement walks. Each per-invariant page paginates via LongTable;
    every page carries a footer with the provenance fingerprint
    placeholder (real hash lands in U.7).

    Uses ``BookmarkedDocTemplate.multiBuild`` (two-pass) so the
    ``TableOfContents`` flowable can pick up correct page numbers,
    and section headings emit both PDF outline entries (left-sidebar
    nav) and TOC entries via the ``afterFlowable`` hook.
    """
    # Imported lazily so the audit CLI loads even when the [audit]
    # extra isn't installed — only --execute paths need reportlab.
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Frame,
        PageBreak,
        PageTemplate,
        Paragraph,
        Spacer,
    )
    from reportlab.platypus.tableofcontents import TableOfContents

    path.parent.mkdir(parents=True, exist_ok=True)
    # Mutable holder bridges multiBuild's two-pass rendering: pass 1's
    # _allSatisfied stamps the just-stabilized page count here; pass 2's
    # footer drawer reads it back as "Page X of N".
    total_pages_holder: list[int] = [0]
    # Provenance fingerprint embedded in PDF metadata (Subject) as a
    # JSON blob so ``audit verify`` can extract it from the PDF
    # without re-running the audit. When provenance is None
    # (skeleton mode, no DB), Subject stays empty.
    import json as _json
    subject_meta = (
        _json.dumps(provenance.to_dict(), separators=(",", ":"))
        if provenance is not None
        else ""
    )
    doc = BookmarkedDocTemplate(
        str(path),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.85 * inch,  # extra room for the page footer
        title=f"QuickSight Generator Audit Report — {institution}",
        subject=subject_meta,
        author=f"quicksight-gen v{version}",
        total_pages_holder=total_pages_holder,
    )
    footer_drawer = make_footer_drawer(
        theme,
        version=version,
        generated_at=generated_at,
        total_pages_holder=total_pages_holder,
        provenance=provenance,
    )
    main_frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height, id="normal",
    )
    doc.addPageTemplates([
        PageTemplate(id="main", frames=[main_frame], onPage=footer_drawer),
    ])
    styles = getSampleStyleSheet()
    institution_style = ParagraphStyle(
        "InstitutionName",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        spaceBefore=0,
        spaceAfter=12,
        textColor=HexColor(theme.primary_fg),
    )
    period_band_style = ParagraphStyle(
        "PeriodBand",
        parent=styles["BodyText"],
        fontSize=13,
        leading=18,
        spaceBefore=6,
        spaceAfter=6,
        textColor=HexColor(theme.primary_fg),
        backColor=HexColor(theme.link_tint),
        borderColor=HexColor(theme.accent),
        borderWidth=0.5,
        borderPadding=10,
    )
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            "TOCHeading1", parent=styles["BodyText"],
            fontSize=12, leading=16, fontName="Helvetica-Bold",
            leftIndent=0, spaceAfter=4,
            textColor=HexColor(theme.primary_fg),
        ),
        ParagraphStyle(
            "TOCHeading2", parent=styles["BodyText"],
            fontSize=10, leading=14,
            leftIndent=18, spaceAfter=2,
            textColor=HexColor(theme.secondary_fg),
        ),
    ]
    start, end = period
    # Cover-page Title: bookmark at level 0 so the auditor can jump
    # back to the cover from anywhere via the sidebar nav, and so it
    # appears at the top of the rendered TOC. We attach
    # _bookmark_level directly rather than wrapping in
    # bookmarked_h1 because we want to preserve the Title style.
    cover_title = Paragraph(
        "QuickSight Generator Audit Report",
        styles["Title"],
    )
    cover_title._bookmark_level = 0  # type: ignore[attr-defined]
    toc_heading = Paragraph("Table of Contents", styles["Heading1"])
    toc_heading._bookmark_level = 0  # type: ignore[attr-defined]
    # Optional: institutional logo above the title when theme.logo
    # is a loadable absolute file path.
    logo_flowable = _cover_logo_flowable(theme)
    story: list = []
    if logo_flowable is not None:
        story.extend([logo_flowable, Spacer(1, 0.25 * inch)])
    story.extend([
        cover_title,
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
            "Sourced directly from the operator's database matviews; the "
            "per-source breakdown below + the page-footer fingerprint "
            "bind this report's contents to its inputs for "
            "reproducibility.",
            styles["BodyText"],
        ),
    ])
    story.extend(_provenance_block_story(
        styles, theme,
        version=version, l2_label=l2_label,
        provenance=provenance,
    ))
    story.extend([
        # Table of contents (own page, bookmarked at level 0 above so
        # the auditor can jump to it from the sidebar nav and so it
        # shows up in its own rendered list).
        PageBreak(),
        toc_heading,
        Spacer(1, 0.15 * inch),
        toc,
    ])
    story.extend(_executive_summary_story(
        exec_summary, styles, period, theme,
    ))
    story.extend(_drift_story(drift_rows, styles, period, theme))
    story.extend(_overdraft_story(
        overdraft_rows, styles, period, singleton_ids, theme,
    ))
    story.extend(_limit_breach_story(
        limit_breach_rows, styles, period, singleton_ids, theme,
    ))
    story.extend(_stuck_pending_story(
        stuck_pending_rows, styles, singleton_ids, theme,
    ))
    story.extend(_stuck_unbundled_story(
        stuck_unbundled_rows, styles, singleton_ids, theme,
    ))
    story.extend(_supersession_story(
        supersession_data, styles, period, theme,
    ))
    story.extend(_daily_statement_walks_story(
        daily_statement_walks, styles, theme,
    ))
    story.extend(_signoff_story(
        styles, theme,
        institution=institution,
        period=period,
        generated_at=generated_at,
        version=version,
        l2_label=l2_label,
        provenance=provenance,
    ))
    # multiBuild = two-pass render so TableOfContents picks up the
    # final page numbers (pass 1 collects via the afterFlowable hook,
    # pass 2 renders the resolved TOC). The doc template's
    # _allSatisfied override stamps the final page count into
    # total_pages_holder between passes so pass 2's footer drawer
    # can render "Page X of N" (U.6).
    doc.multiBuild(story)


def _executive_summary_story(
    summary: ExecSummary | None,
    styles,  # type: ignore[no-untyped-def]
    period: tuple[date, date],
    theme,  # type: ignore[no-untyped-def] # ThemePreset
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
        bookmarked_h1("Executive Summary", styles),
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
        exc_rows = [
            [f"{label}*" if date_col is None else label, "—"]
            for label, _, date_col in _EXCEPTION_INVARIANTS
        ]
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
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(theme.primary_fg)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(theme.accent_fg)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(theme.link_tint)),
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
        bookmarked_h3("Volume", styles),
        Spacer(1, 0.05 * inch),
        Table(volume_data, colWidths=col_widths, style=table_style),
        Spacer(1, 0.3 * inch),
        bookmarked_h3("Exception Counts", styles),
        Spacer(1, 0.05 * inch),
        Table(exception_data, colWidths=col_widths, style=table_style),
        Spacer(1, 0.1 * inch),
        Paragraph(
            "<i>* Current state &mdash; open as of report generation, "
            "regardless of when posted (matches the L1 dashboard "
            "convention for stuck-aging matviews).</i>",
            styles["BodyText"],
        ),
    ])
    return elements


def _drift_story(
    rows: list[DriftViolation] | None,
    styles,  # type: ignore[no-untyped-def]
    period: tuple[date, date],
    theme,  # type: ignore[no-untyped-def] # ThemePreset
) -> list:  # type: ignore[type-arg]
    """Platypus elements for the U.3.a Drift violations page.

    LongTable auto-paginates with the header row repeated. None = no
    DB → placeholder notice. Empty list = DB healthy with zero
    drifts in period → good-news render. Non-empty = full table.
    """
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        LongTable,
        PageBreak,
        Paragraph,
        Spacer,
        TableStyle,
    )

    start, end = period
    elements: list = [
        PageBreak(),
        bookmarked_h1("Drift Violations", styles),
        Paragraph(
            f"Reporting period: {start.isoformat()} &ndash; "
            f"{end.isoformat()} (inclusive).",
            styles["BodyText"],
        ),
        Paragraph(
            "<i>Per-account-day discrepancies between stored "
            "end-of-day balance and the balance computed from "
            "posted transactions.</i>",
            styles["BodyText"],
        ),
        Spacer(1, 0.15 * inch),
    ]

    if rows is None:
        elements.append(
            Paragraph(
                "<i>Database not configured &mdash; table not "
                "populated. Set <b>demo_database_url</b> in your "
                "config to query.</i>",
                styles["BodyText"],
            ),
        )
        return elements
    if not rows:
        elements.append(
            Paragraph(
                "<i>No drift detected for the period &mdash; "
                "books reconcile.</i>",
                styles["BodyText"],
            ),
        )
        return elements

    cell_style = ParagraphStyle(
        "DriftCell",
        parent=styles["BodyText"],
        fontSize=8,
        leading=10,
        spaceBefore=0,
        spaceAfter=0,
    )
    header = [
        "Account ID",
        "Account name",
        "Role",
        "Day",
        "Stored",
        "Computed",
        "Drift",
    ]
    data: list[list] = [header]
    for r in rows:
        data.append([
            Paragraph(r.account_id, cell_style),
            Paragraph(r.account_name, cell_style),
            Paragraph(r.account_role, cell_style),
            r.business_day.isoformat(),
            f"${r.stored_balance:,.2f}",
            f"${r.computed_balance:,.2f}",
            f"${r.drift:,.2f}",
        ])

    table_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(theme.primary_fg)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(theme.accent_fg)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(theme.link_tint)),
        # Right-align numeric columns (Day, Stored, Computed, Drift).
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor(theme.secondary_bg),
        ]),
    ])
    col_widths = [
        1.15 * inch,  # Account ID
        1.15 * inch,  # Account name
        1.05 * inch,  # Role  (fits "CustomerDDA" / "ConcentrationMaster")
        0.8 * inch,   # Day
        0.95 * inch,  # Stored
        0.95 * inch,  # Computed
        0.9 * inch,   # Drift
    ]
    elements.append(
        LongTable(
            data, colWidths=col_widths, style=table_style, repeatRows=1,
        ),
    )
    return elements


def _overdraft_story(
    rows: list[OverdraftViolation] | None,
    styles,  # type: ignore[no-untyped-def]
    period: tuple[date, date],
    singleton_ids: set[str],
    theme,  # type: ignore[no-untyped-def] # ThemePreset
) -> list:  # type: ignore[type-arg]
    """Platypus elements for the U.3.b Overdraft violations page.

    Renders up to TWO sub-tables:
      - Parent accounts (L2 ``Account`` singletons): per-row detail
        — each occurrence of a parent itself going negative is a
        systemic event worth surfacing individually.
      - Child accounts (template-materialized): grouped by parent
        role; one row per parent role with distinct-children-negative
        + summed-peak-negative.
    Empty sub-tables are omitted; the section header still renders.
    """
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        LongTable,
        PageBreak,
        Paragraph,
        Spacer,
        TableStyle,
    )

    start, end = period
    elements: list = [
        PageBreak(),
        bookmarked_h1("Overdraft Violations", styles),
        Paragraph(
            f"Reporting period: {start.isoformat()} &ndash; "
            f"{end.isoformat()} (inclusive).",
            styles["BodyText"],
        ),
        Paragraph(
            "<i>Account-days where the stored end-of-day balance "
            "went negative. Parent accounts (L2 singletons &mdash; "
            "GL clearing, concentration, ZBA master) shown per-row "
            "because a parent itself going negative is systemic. "
            "Child accounts (templated, e.g. customer DDAs, ZBA "
            "sub-accounts) roll up by parent role.</i>",
            styles["BodyText"],
        ),
        Spacer(1, 0.15 * inch),
    ]

    if rows is None:
        elements.append(
            Paragraph(
                "<i>Database not configured &mdash; table not "
                "populated. Set <b>demo_database_url</b> in your "
                "config to query.</i>",
                styles["BodyText"],
            ),
        )
        return elements
    if not rows:
        elements.append(
            Paragraph(
                "<i>No overdrafts detected for the period.</i>",
                styles["BodyText"],
            ),
        )
        return elements

    parent_rows, child_groups = _split_overdraft_by_account_class(
        rows, singleton_ids,
    )
    cell_style = ParagraphStyle(
        "OverdraftCell",
        parent=styles["BodyText"],
        fontSize=8,
        leading=10,
        spaceBefore=0,
        spaceAfter=0,
    )
    base_table_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(theme.primary_fg)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(theme.accent_fg)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(theme.link_tint)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor(theme.secondary_bg),
        ]),
    ])

    if parent_rows:
        elements.extend([
            bookmarked_h3("Parent Accounts (Per-Row Detail)", styles),
            Spacer(1, 0.05 * inch),
        ])
        detail_data: list[list] = [
            ["Account ID", "Account name", "Role", "Day", "Stored balance"],
        ]
        for r in parent_rows:
            detail_data.append([
                Paragraph(r.account_id, cell_style),
                Paragraph(r.account_name, cell_style),
                Paragraph(r.account_role, cell_style),
                r.business_day.isoformat(),
                f"${r.stored_balance:,.2f}",
            ])
        detail_style = TableStyle(
            base_table_style.getCommands() + [
                ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
            ],
        )
        elements.append(LongTable(
            detail_data,
            colWidths=[1.6 * inch, 1.5 * inch, 1.5 * inch,
                       0.8 * inch, 1.5 * inch],
            style=detail_style, repeatRows=1,
        ))
        elements.append(Spacer(1, 0.25 * inch))

    if child_groups:
        elements.extend([
            bookmarked_h3(
                "Child Accounts Grouped by Parent Role", styles,
            ),
            Spacer(1, 0.05 * inch),
        ])
        group_data: list[list] = [
            ["Parent role", "Children negative", "Total peak negative"],
        ]
        for s in child_groups:
            group_data.append([
                Paragraph(s.parent_role, cell_style),
                f"{s.distinct_children_negative}",
                f"${s.total_peak_negative:,.2f}",
            ])
        group_style = TableStyle(
            base_table_style.getCommands() + [
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ],
        )
        elements.append(LongTable(
            group_data,
            colWidths=[3.0 * inch, 1.6 * inch, 2.3 * inch],
            style=group_style, repeatRows=1,
        ))
    return elements


def _limit_breach_story(
    rows: list[LimitBreachViolation] | None,
    styles,  # type: ignore[no-untyped-def]
    period: tuple[date, date],
    singleton_ids: set[str],
    theme,  # type: ignore[no-untyped-def] # ThemePreset
) -> list:  # type: ignore[type-arg]
    """Platypus elements for the U.3.c Limit breach violations page.

    Same parent-vs-child split as Overdraft. Children grouped by
    (parent_role, transfer_type) since the LimitSchedule cap is
    keyed on that pair. Parent table carries 8 columns (account,
    role, day, transfer_type, outbound, cap, overshoot); child
    summary 4 columns (parent_role, transfer_type, count, total
    overshoot).
    """
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        LongTable,
        PageBreak,
        Paragraph,
        Spacer,
        TableStyle,
    )

    start, end = period
    elements: list = [
        PageBreak(),
        bookmarked_h1("Limit Breach Violations", styles),
        Paragraph(
            f"Reporting period: {start.isoformat()} &ndash; "
            f"{end.isoformat()} (inclusive).",
            styles["BodyText"],
        ),
        Paragraph(
            "<i>Account-day-transfer_type cells where cumulative "
            "outbound exceeded the L2-configured cap. Parent accounts "
            "shown per-row; child accounts grouped by (parent role, "
            "transfer type) &mdash; the LimitSchedule key shape.</i>",
            styles["BodyText"],
        ),
        Spacer(1, 0.15 * inch),
    ]

    if rows is None:
        elements.append(
            Paragraph(
                "<i>Database not configured &mdash; table not "
                "populated. Set <b>demo_database_url</b> in your "
                "config to query.</i>",
                styles["BodyText"],
            ),
        )
        return elements
    if not rows:
        elements.append(
            Paragraph(
                "<i>No limit breaches detected for the period.</i>",
                styles["BodyText"],
            ),
        )
        return elements

    parent_rows, child_groups = _split_limit_breach_by_account_class(
        rows, singleton_ids,
    )
    cell_style = ParagraphStyle(
        "LimitBreachCell",
        parent=styles["BodyText"],
        fontSize=8,
        leading=10,
        spaceBefore=0,
        spaceAfter=0,
    )
    base_table_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(theme.primary_fg)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(theme.accent_fg)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(theme.link_tint)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor(theme.secondary_bg),
        ]),
    ])

    if parent_rows:
        elements.extend([
            bookmarked_h3("Parent Accounts (Per-Row Detail)", styles),
            Spacer(1, 0.05 * inch),
        ])
        detail_data: list[list] = [
            ["Account ID", "Account name", "Role", "Day",
             "Transfer type", "Outbound", "Cap", "Overshoot"],
        ]
        for r in parent_rows:
            detail_data.append([
                Paragraph(r.account_id, cell_style),
                Paragraph(r.account_name, cell_style),
                Paragraph(r.account_role, cell_style),
                r.business_day.isoformat(),
                Paragraph(r.transfer_type, cell_style),
                f"${r.outbound_total:,.2f}",
                f"${r.cap:,.2f}",
                f"${r.overshoot:,.2f}",
            ])
        detail_style = TableStyle(
            base_table_style.getCommands() + [
                # Right-align Day + Transfer type + 3 numerics.
                ("ALIGN", (5, 1), (-1, -1), "RIGHT"),
            ],
        )
        elements.append(LongTable(
            detail_data,
            colWidths=[1.05 * inch, 1.05 * inch, 0.85 * inch,
                       0.75 * inch, 0.95 * inch, 0.85 * inch,
                       0.7 * inch, 0.8 * inch],
            style=detail_style, repeatRows=1,
        ))
        elements.append(Spacer(1, 0.25 * inch))

    if child_groups:
        elements.extend([
            bookmarked_h3(
                "Child Accounts Grouped by Parent Role + Transfer Type",
                styles,
            ),
            Spacer(1, 0.05 * inch),
        ])
        group_data: list[list] = [
            ["Parent role", "Transfer type",
             "Children breaching", "Total overshoot"],
        ]
        for s in child_groups:
            group_data.append([
                Paragraph(s.parent_role, cell_style),
                Paragraph(s.transfer_type, cell_style),
                f"{s.distinct_children_breaching}",
                f"${s.total_overshoot:,.2f}",
            ])
        group_style = TableStyle(
            base_table_style.getCommands() + [
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
            ],
        )
        elements.append(LongTable(
            group_data,
            colWidths=[2.0 * inch, 2.0 * inch,
                       1.4 * inch, 1.5 * inch],
            style=group_style, repeatRows=1,
        ))
    return elements


def _stuck_pending_story(
    rows: list[StuckPendingViolation] | None,
    styles,  # type: ignore[no-untyped-def]
    singleton_ids: set[str],
    theme,  # type: ignore[no-untyped-def] # ThemePreset
) -> list:  # type: ignore[type-arg]
    """Platypus elements for the U.3.d Stuck pending transactions page.

    Current-state matview: NO date filter (mirrors L1 dashboard).
    Same parent/child split as Overdraft + Limit breach. Child
    summary 5 cols (parent role, transfer type, distinct children,
    stuck transaction count, total amount) — transaction count drives
    operational workload, child count drives spread.
    """
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        LongTable,
        PageBreak,
        Paragraph,
        Spacer,
        TableStyle,
    )

    elements: list = [
        PageBreak(),
        bookmarked_h1("Stuck Pending Transactions", styles),
        Paragraph(
            "<i>Transactions currently in Pending status whose age "
            "exceeds the L2-configured aging cap. <b>Current-state</b> "
            "&mdash; shown regardless of posting date; the report "
            "period band on the cover does not scope this section.</i>",
            styles["BodyText"],
        ),
        Spacer(1, 0.15 * inch),
    ]

    if rows is None:
        elements.append(
            Paragraph(
                "<i>Database not configured &mdash; table not "
                "populated. Set <b>demo_database_url</b> in your "
                "config to query.</i>",
                styles["BodyText"],
            ),
        )
        return elements
    if not rows:
        elements.append(
            Paragraph(
                "<i>No stuck pending transactions &mdash; backlog "
                "clear.</i>",
                styles["BodyText"],
            ),
        )
        return elements

    parent_rows, child_groups = _split_stuck_pending_by_account_class(
        rows, singleton_ids,
    )
    cell_style = ParagraphStyle(
        "StuckPendingCell",
        parent=styles["BodyText"],
        fontSize=8,
        leading=10,
        spaceBefore=0,
        spaceAfter=0,
    )
    base_table_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(theme.primary_fg)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(theme.accent_fg)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(theme.link_tint)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor(theme.secondary_bg),
        ]),
    ])

    if parent_rows:
        elements.extend([
            bookmarked_h3("Parent Accounts (Per-Row Detail)", styles),
            Spacer(1, 0.05 * inch),
        ])
        detail_data: list[list] = [
            ["Account ID", "Account name", "Transfer type",
             "Posted", "Amount", "Age", "Cap"],
        ]
        for r in parent_rows:
            detail_data.append([
                Paragraph(r.account_id, cell_style),
                Paragraph(r.account_name, cell_style),
                Paragraph(r.transfer_type, cell_style),
                r.posting.strftime("%Y-%m-%d %H:%M"),
                f"${r.amount_money:,.2f}",
                _format_age(r.age_seconds),
                _format_age(r.max_pending_age_seconds),
            ])
        detail_style = TableStyle(
            base_table_style.getCommands() + [
                ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
            ],
        )
        elements.append(LongTable(
            detail_data,
            colWidths=[1.15 * inch, 1.15 * inch, 1.1 * inch,
                       1.05 * inch, 0.95 * inch,
                       0.7 * inch, 0.7 * inch],
            style=detail_style, repeatRows=1,
        ))
        elements.append(Spacer(1, 0.25 * inch))

    if child_groups:
        elements.extend([
            bookmarked_h3(
                "Child Accounts Grouped by Parent Role + Transfer Type",
                styles,
            ),
            Spacer(1, 0.05 * inch),
        ])
        group_data: list[list] = [
            ["Parent role", "Transfer type", "Children affected",
             "Stuck transactions", "Total amount"],
        ]
        for s in child_groups:
            group_data.append([
                Paragraph(s.parent_role, cell_style),
                Paragraph(s.transfer_type, cell_style),
                f"{s.distinct_children_affected}",
                f"{s.stuck_transaction_count}",
                f"${s.total_stuck_amount:,.2f}",
            ])
        group_style = TableStyle(
            base_table_style.getCommands() + [
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
            ],
        )
        elements.append(LongTable(
            group_data,
            colWidths=[1.6 * inch, 1.6 * inch, 1.2 * inch,
                       1.2 * inch, 1.3 * inch],
            style=group_style, repeatRows=1,
        ))
    return elements


def _stuck_unbundled_story(
    rows: list[StuckUnbundledViolation] | None,
    styles,  # type: ignore[no-untyped-def]
    singleton_ids: set[str],
    theme,  # type: ignore[no-untyped-def] # ThemePreset
) -> list:  # type: ignore[type-arg]
    """Platypus elements for the U.3.e Stuck unbundled transactions page.

    Same shape as Stuck pending; cap is ``max_unbundled_age_seconds``.
    Current-state, no date filter.
    """
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        LongTable,
        PageBreak,
        Paragraph,
        Spacer,
        TableStyle,
    )

    elements: list = [
        PageBreak(),
        bookmarked_h1("Stuck Unbundled Transactions", styles),
        Paragraph(
            "<i>Posted transactions awaiting bundle assignment whose "
            "age exceeds the L2-configured bundling cap. "
            "<b>Current-state</b> &mdash; shown regardless of posting "
            "date; the report period band on the cover does not scope "
            "this section.</i>",
            styles["BodyText"],
        ),
        Spacer(1, 0.15 * inch),
    ]

    if rows is None:
        elements.append(
            Paragraph(
                "<i>Database not configured &mdash; table not "
                "populated. Set <b>demo_database_url</b> in your "
                "config to query.</i>",
                styles["BodyText"],
            ),
        )
        return elements
    if not rows:
        elements.append(
            Paragraph(
                "<i>No stuck unbundled transactions &mdash; bundling "
                "caught up.</i>",
                styles["BodyText"],
            ),
        )
        return elements

    parent_rows, child_groups = _split_stuck_unbundled_by_account_class(
        rows, singleton_ids,
    )
    cell_style = ParagraphStyle(
        "StuckUnbundledCell",
        parent=styles["BodyText"],
        fontSize=8,
        leading=10,
        spaceBefore=0,
        spaceAfter=0,
    )
    base_table_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(theme.primary_fg)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(theme.accent_fg)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(theme.link_tint)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor(theme.secondary_bg),
        ]),
    ])

    if parent_rows:
        elements.extend([
            bookmarked_h3("Parent Accounts (Per-Row Detail)", styles),
            Spacer(1, 0.05 * inch),
        ])
        detail_data: list[list] = [
            ["Account ID", "Account name", "Transfer type",
             "Posted", "Amount", "Age", "Cap"],
        ]
        for r in parent_rows:
            detail_data.append([
                Paragraph(r.account_id, cell_style),
                Paragraph(r.account_name, cell_style),
                Paragraph(r.transfer_type, cell_style),
                r.posting.strftime("%Y-%m-%d %H:%M"),
                f"${r.amount_money:,.2f}",
                _format_age(r.age_seconds),
                _format_age(r.max_unbundled_age_seconds),
            ])
        detail_style = TableStyle(
            base_table_style.getCommands() + [
                ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
            ],
        )
        elements.append(LongTable(
            detail_data,
            colWidths=[1.15 * inch, 1.15 * inch, 1.1 * inch,
                       1.05 * inch, 0.95 * inch,
                       0.7 * inch, 0.7 * inch],
            style=detail_style, repeatRows=1,
        ))
        elements.append(Spacer(1, 0.25 * inch))

    if child_groups:
        elements.extend([
            bookmarked_h3(
                "Child Accounts Grouped by Parent Role + Transfer Type",
                styles,
            ),
            Spacer(1, 0.05 * inch),
        ])
        group_data: list[list] = [
            ["Parent role", "Transfer type", "Children affected",
             "Stuck transactions", "Total amount"],
        ]
        for s in child_groups:
            group_data.append([
                Paragraph(s.parent_role, cell_style),
                Paragraph(s.transfer_type, cell_style),
                f"{s.distinct_children_affected}",
                f"{s.stuck_transaction_count}",
                f"${s.total_stuck_amount:,.2f}",
            ])
        group_style = TableStyle(
            base_table_style.getCommands() + [
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
            ],
        )
        elements.append(LongTable(
            group_data,
            colWidths=[1.6 * inch, 1.6 * inch, 1.2 * inch,
                       1.2 * inch, 1.3 * inch],
            style=group_style, repeatRows=1,
        ))
    return elements


def _supersession_story(
    data: SupersessionAuditData | None,
    styles,  # type: ignore[no-untyped-def]
    period: tuple[date, date],
    theme,  # type: ignore[no-untyped-def] # ThemePreset
) -> list:  # type: ignore[type-arg]
    """Platypus elements for the U.3.f Supersession audit page.

    Aggregate table covers entire dataset; detail tables limited to
    the report window (one per base table, omitted if empty).
    """
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        LongTable,
        PageBreak,
        Paragraph,
        Spacer,
        TableStyle,
    )

    start, end = period
    elements: list = [
        PageBreak(),
        bookmarked_h1("Supersession Audit", styles),
        Paragraph(
            "<i>Aggregate counts cover the <b>entire dataset</b> "
            "(current-state); detail tables are limited to "
            f"{start.isoformat()} &ndash; {end.isoformat()} "
            "(inclusive) so the page stays bounded as supersession "
            "history accumulates over time.</i>",
            styles["BodyText"],
        ),
        Spacer(1, 0.15 * inch),
    ]

    if data is None:
        elements.append(
            Paragraph(
                "<i>Database not configured &mdash; table not "
                "populated. Set <b>demo_database_url</b> in your "
                "config to query.</i>",
                styles["BodyText"],
            ),
        )
        return elements
    if not data.aggregates:
        elements.append(
            Paragraph(
                "<i>No supersessions recorded &mdash; entries have "
                "not been corrected.</i>",
                styles["BodyText"],
            ),
        )
        return elements

    cell_style = ParagraphStyle(
        "SupersessionCell",
        parent=styles["BodyText"],
        fontSize=8,
        leading=10,
        spaceBefore=0,
        spaceAfter=0,
    )
    base_table_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(theme.primary_fg)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(theme.accent_fg)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(theme.link_tint)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor(theme.secondary_bg),
        ]),
    ])

    elements.extend([
        bookmarked_h3("Aggregate (Entire Dataset)", styles),
        Spacer(1, 0.05 * inch),
    ])
    aggregate_data: list[list] = [
        ["Base table", "Reason category", "Total", "New in period"],
    ]
    for r in data.aggregates:
        aggregate_data.append([
            Paragraph(r.base_table, cell_style),
            Paragraph(r.supersedes_category, cell_style),
            f"{r.total_count:,}",
            f"{r.new_in_period_count:,}",
        ])
    aggregate_style = TableStyle(
        base_table_style.getCommands() + [
            ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ],
    )
    elements.append(LongTable(
        aggregate_data,
        colWidths=[1.6 * inch, 2.4 * inch, 1.4 * inch, 1.5 * inch],
        style=aggregate_style, repeatRows=1,
    ))

    if data.transaction_details:
        elements.extend([
            Spacer(1, 0.25 * inch),
            bookmarked_h3(
                "Transactions — Correcting Entries in Period", styles,
            ),
            Spacer(1, 0.05 * inch),
        ])
        txn_data: list[list] = [
            ["Transaction ID", "Reason", "Account ID", "Account name",
             "Posted", "Amount"],
        ]
        for d in data.transaction_details:
            txn_data.append([
                Paragraph(d.transaction_id, cell_style),
                Paragraph(d.supersedes_category, cell_style),
                Paragraph(d.account_id, cell_style),
                Paragraph(d.account_name, cell_style),
                d.posting.strftime("%Y-%m-%d %H:%M"),
                f"${d.amount_money:,.2f}",
            ])
        txn_style = TableStyle(
            base_table_style.getCommands() + [
                ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
            ],
        )
        elements.append(LongTable(
            txn_data,
            colWidths=[1.3 * inch, 1.1 * inch, 1.0 * inch,
                       1.2 * inch, 1.2 * inch, 1.0 * inch],
            style=txn_style, repeatRows=1,
        ))

    if data.daily_balance_details:
        elements.extend([
            Spacer(1, 0.25 * inch),
            bookmarked_h3(
                "Daily Balances — Correcting Entries in Period", styles,
            ),
            Spacer(1, 0.05 * inch),
        ])
        bal_data: list[list] = [
            ["Account ID", "Account name", "Day", "Reason", "Balance"],
        ]
        for d in data.daily_balance_details:
            bal_data.append([
                Paragraph(d.account_id, cell_style),
                Paragraph(d.account_name, cell_style),
                d.business_day.isoformat(),
                Paragraph(d.supersedes_category, cell_style),
                f"${d.money:,.2f}",
            ])
        bal_style = TableStyle(
            base_table_style.getCommands() + [
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
            ],
        )
        elements.append(LongTable(
            bal_data,
            colWidths=[1.5 * inch, 1.5 * inch, 1.0 * inch,
                       1.5 * inch, 1.3 * inch],
            style=bal_style, repeatRows=1,
        ))

    if not data.transaction_details and not data.daily_balance_details:
        elements.extend([
            Spacer(1, 0.2 * inch),
            Paragraph(
                "<i>No new correcting entries posted in the report "
                "window &mdash; aggregate counts above are all from "
                "prior periods.</i>",
                styles["BodyText"],
            ),
        ])
    return elements


def _daily_statement_walks_story(
    walks: list[DailyStatementWalk] | None,
    styles,  # type: ignore[no-untyped-def]
    theme,  # type: ignore[no-untyped-def] # ThemePreset
) -> list:  # type: ignore[type-arg]
    """Platypus elements for the U.4 per-account Daily Statement walk pages.

    Section header at level-0 outline; one sub-section per walk at
    level-1 outline (so the auditor can jump to a specific account-day
    from the sidebar / TOC). Each walk renders a 5-KPI summary table
    + a transactions detail table mirroring the dashboard's Daily
    Statement sheet.
    """
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        LongTable,
        PageBreak,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    elements: list = [
        PageBreak(),
        bookmarked_h1("Per-Account Daily Statement Walk", styles),
        Paragraph(
            "One walk per (account, day) pair from U.3.a's drift table, "
            "plus every internal parent-account day in the report window. "
            "Internal parents (L2 singletons &mdash; GL clearing, "
            "concentration, ZBA master) render even when drift is zero "
            "because their day-by-day walk is itself auditor-relevant; a "
            "clean walk is evidence of correctness. External counterparty "
            "singletons are out of scope for reconciliation and do not "
            "get walks.",
            styles["BodyText"],
        ),
        Paragraph(
            "<i>The <b>Drift</b> KPI here is the per-day drift "
            "(closing stored &minus; closing recomputed-from-day's-flow). "
            "U.3.a's table shows cumulative drift "
            "(stored &minus; sum of all transactions ever); the two can "
            "diverge when daily_balances are sparse.</i>",
            styles["BodyText"],
        ),
        Spacer(1, 0.15 * inch),
    ]

    if walks is None:
        elements.append(
            Paragraph(
                "<i>Database not configured &mdash; walks not "
                "populated. Set <b>demo_database_url</b> in your "
                "config to query.</i>",
                styles["BodyText"],
            ),
        )
        return elements
    if not walks:
        elements.append(
            Paragraph(
                "<i>No drift in the report window &mdash; no walks "
                "needed.</i>",
                styles["BodyText"],
            ),
        )
        return elements

    cell_style = ParagraphStyle(
        "DailyStatementCell",
        parent=styles["BodyText"],
        fontSize=8,
        leading=10,
        spaceBefore=0,
        spaceAfter=0,
    )
    base_table_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(theme.primary_fg)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(theme.accent_fg)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(theme.link_tint)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor(theme.secondary_bg),
        ]),
    ])

    for w in walks:
        # Sub-section heading + bookmark (one per walk so auditor can
        # jump to a specific account-day from the sidebar / TOC).
        elements.append(PageBreak())
        elements.append(bookmarked_h3(
            f"{w.account_id} — {w.business_day_end.isoformat()}", styles,
        ))
        elements.append(Paragraph(
            f"<b>{w.account_name}</b> ({w.account_role})",
            styles["BodyText"],
        ))
        elements.append(Spacer(1, 0.1 * inch))

        # 5-KPI summary table (one row, currency-formatted).
        kpi_data: list[list] = [
            ["Opening", "Debits", "Credits", "Closing stored", "Drift"],
            [
                f"${w.opening_balance:,.2f}",
                f"${w.total_debits:,.2f}",
                f"${w.total_credits:,.2f}",
                f"${w.closing_balance_stored:,.2f}",
                f"${w.drift:,.2f}",
            ],
        ]
        kpi_style = TableStyle(
            base_table_style.getCommands() + [
                ("ALIGN", (0, 1), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 0), (-1, 0), "RIGHT"),
            ],
        )
        elements.append(Table(
            kpi_data,
            colWidths=[1.4 * inch] * 5,
            style=kpi_style,
        ))
        elements.append(Spacer(1, 0.2 * inch))

        # Day's transactions detail. Heading NOT bookmarked — adding
        # a "Posted Money records" entry per walk would clutter the
        # sidebar with 50 identical-titled entries; the per-walk
        # account-day bookmark already covers nav.
        if w.transactions:
            elements.append(Paragraph(
                "Posted Money records", styles["Heading3"],
            ))
            txn_data: list[list] = [
                ["Posted", "Transaction ID", "Transfer type",
                 "Direction", "Amount", "Status"],
            ]
            for t in w.transactions:
                txn_data.append([
                    t.posting.strftime("%H:%M"),
                    Paragraph(t.transaction_id, cell_style),
                    Paragraph(t.transfer_type, cell_style),
                    t.amount_direction,
                    f"${t.amount_money:,.2f}",
                    t.status,
                ])
            txn_style = TableStyle(
                base_table_style.getCommands() + [
                    ("ALIGN", (4, 1), (4, -1), "RIGHT"),
                ],
            )
            elements.append(LongTable(
                txn_data,
                colWidths=[0.7 * inch, 1.5 * inch, 1.4 * inch,
                           0.85 * inch, 1.0 * inch, 0.8 * inch],
                style=txn_style, repeatRows=1,
            ))
        else:
            elements.append(Paragraph(
                "<i>No Posted Money records on this day.</i>",
                styles["BodyText"],
            ))
    return elements


def _signoff_story(
    styles,  # type: ignore[no-untyped-def]
    theme,  # type: ignore[no-untyped-def] # ThemePreset
    *,
    institution: str,
    period: tuple[date, date],
    generated_at: datetime,
    version: str,
    l2_label: str,
    provenance: ProvenanceFingerprint | None,
) -> list:
    """Final-page sign-off block with system + auditor attestation (U.5).

    System block carries machine-attestable provenance (code version,
    L2 instance, period, generation timestamp, fingerprint
    placeholder) — what U.7's cryptographic seal will cover. Auditor
    block is a printable form (signature line + notes box) for human
    sign-off; intentionally separate so an unattended pipeline can
    publish the system block without forging a human signature.
    """
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    start, end = period
    cell_style = ParagraphStyle(
        "SignoffCell",
        parent=styles["BodyText"],
        fontSize=10,
        leading=13,
    )
    label_style = ParagraphStyle(
        "SignoffLabel",
        parent=cell_style,
        fontName="Helvetica-Bold",
    )
    signature_line_color = HexColor(theme.primary_fg)
    panel_bg = HexColor(theme.link_tint)

    system_data = [
        [Paragraph("Institution", label_style),
         Paragraph(institution, cell_style)],
        [Paragraph("Reporting period", label_style),
         Paragraph(
             f"{start.isoformat()} &ndash; {end.isoformat()} (inclusive)",
             cell_style,
         )],
        [Paragraph("Generated by", label_style),
         Paragraph(f"quicksight-gen v{version}", cell_style)],
        [Paragraph("Generated at", label_style),
         Paragraph(
             generated_at.isoformat(timespec="seconds"), cell_style,
         )],
        [Paragraph("L2 instance", label_style),
         Paragraph(l2_label, cell_style)],
        [Paragraph("Provenance fingerprint", label_style),
         Paragraph(
             "<font face='Courier'>"
             + (
                 provenance.composite_sha
                 if provenance is not None
                 else l2_fingerprint_placeholder()
                     .replace("<", "&lt;").replace(">", "&gt;")
             )
             + "</font>",
             cell_style,
         )],
    ]
    system_table = Table(
        system_data,
        colWidths=[1.9 * inch, 4.6 * inch],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, -1), panel_bg),
            ("BOX", (0, 0), (-1, -1), 0.5,
             HexColor(theme.secondary_fg)),
            ("INNERGRID", (0, 0), (-1, -1), 0.25,
             HexColor(theme.secondary_fg)),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]),
    )

    # Auditor form — labels left, blank rule on the right via an
    # underline-padded empty cell. reportlab can't easily draw a real
    # baseline-only rule per cell, so use a bottom border on the
    # right column to read as a printable signature line.
    auditor_fields = [
        "Auditor name",
        "Title",
        "Organization",
        "Date reviewed",
        "Signature",
    ]
    auditor_data = [
        [Paragraph(f, label_style), Paragraph("", cell_style)]
        for f in auditor_fields
    ]
    auditor_style_cmds = [
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    # Bottom rule on the right (signature) column for every row.
    for r in range(len(auditor_fields)):
        auditor_style_cmds.append(
            ("LINEBELOW", (1, r), (1, r), 0.5, signature_line_color),
        )
    auditor_table = Table(
        auditor_data,
        colWidths=[1.6 * inch, 4.9 * inch],
        style=TableStyle(auditor_style_cmds),
    )

    # Notes / exceptions box — single tall cell with a bordered frame.
    notes_table = Table(
        [[Paragraph("", cell_style)]],
        colWidths=[6.5 * inch],
        rowHeights=[1.6 * inch],
        style=TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5,
             HexColor(theme.secondary_fg)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]),
    )

    return [
        PageBreak(),
        bookmarked_h1("Sign-Off", styles),
        Paragraph(
            "<b>System Attestation</b>",
            styles["Heading3"],
        ),
        Paragraph(
            "<i>Machine-generated. Binds this report to the code "
            "version, L2 spec, source data, and generation time. The "
            "external cryptographic seal over this block lands in "
            "Phase U.7.</i>",
            styles["BodyText"],
        ),
        Spacer(1, 0.1 * inch),
        system_table,
        Spacer(1, 0.4 * inch),
        Paragraph(
            "<b>Auditor Attestation</b>",
            styles["Heading3"],
        ),
        Paragraph(
            "<i>I have reviewed the contents of this report and "
            "attest to the findings above as of the report period. "
            "May be left blank if the report was generated unattended "
            "(e.g. an automated pipeline) &mdash; the system block "
            "above stands on its own.</i>",
            styles["BodyText"],
        ),
        Spacer(1, 0.1 * inch),
        auditor_table,
        Spacer(1, 0.25 * inch),
        Paragraph(
            "<b>Notes / Exceptions</b>",
            styles["BodyText"],
        ),
        Spacer(1, 0.05 * inch),
        notes_table,
    ]




def _cover_logo_flowable(theme):  # type: ignore[no-untyped-def]
    """Cover-page logo Image flowable (or None if no logo / can't load).

    Reads ``theme.logo`` (string accepting either a URL or absolute
    file path). For audit-PDF generation we deliberately do NOT
    fetch URLs — making the audit network-dependent at gen time is
    a fragility we don't want for a regulator-facing deliverable
    (and a URL fetch failure mid-generation would either break the
    audit outright or silently swap in a stale cached version
    depending on caching). URLs and unloadable paths log a warning
    and skip the logo; the cover renders without it rather than
    failing the audit.

    Sized to fit within a 4"x1" bounding box, scaled proportionally
    so the natural aspect ratio is preserved. Centered horizontally
    by reportlab's default ``hAlign``.
    """
    from reportlab.lib.units import inch
    from reportlab.platypus import Image

    logo = getattr(theme, "logo", None)
    if not logo:
        return None
    if logo.startswith(("http://", "https://", "//")):
        click.echo(
            f"audit: skipping URL logo {logo!r} on cover page — URL "
            f"fetching disabled for audit reproducibility. Use an "
            f"absolute file path in theme.logo to render.",
            err=True,
        )
        return None
    path = Path(logo)
    if not path.is_absolute() or not path.is_file():
        click.echo(
            f"audit: theme.logo {logo!r} not found at absolute file "
            f"path — cover page will render without it.",
            err=True,
        )
        return None
    try:
        return Image(
            str(path),
            width=4.0 * inch,
            height=1.0 * inch,
            kind="proportional",
        )
    except Exception as e:  # reportlab raises various
        click.echo(
            f"audit: failed to load theme.logo {logo!r}: {e}; "
            f"cover page will render without it.",
            err=True,
        )
        return None


def _provenance_block_story(
    styles,  # type: ignore[no-untyped-def]
    theme,  # type: ignore[no-untyped-def] # ThemePreset
    *,
    version: str,
    l2_label: str,
    provenance: ProvenanceFingerprint | None,
) -> list:
    """Cover-page long-form source-data provenance block (U.6).

    Lists the source artifacts that, together, fully determine this
    report's content: the operator's two base tables (transactions +
    daily_balances), the L2 instance YAML, and the quicksight-gen
    code version. U.7 fills in the per-source SHA256 + high-water
    entry-id columns; until then they show the long-form
    ``<pending>`` placeholder so a grep for it catches a "we shipped
    without wiring U.7" regression before the auditor does.

    Distinct from the per-page footer (which carries a SHORT hash);
    this is the per-source breakdown that the footer's hash
    summarizes.
    """
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    cell_style = ParagraphStyle(
        "ProvenanceCell",
        parent=styles["BodyText"],
        fontSize=9,
        leading=12,
    )
    header_style = ParagraphStyle(
        "ProvenanceHeader",
        parent=cell_style,
        fontName="Helvetica-Bold",
        textColor=HexColor(theme.primary_fg),
    )
    code_style = ParagraphStyle(
        "ProvenanceCode",
        parent=cell_style,
        fontName="Courier",
    )

    placeholder = l2_fingerprint_placeholder().replace(
        "<", "&lt;",
    ).replace(">", "&gt;")

    def _row(source: str, hwm: str, hash_text: str) -> list:
        return [
            Paragraph(source, cell_style),
            Paragraph(hwm, code_style),
            Paragraph(hash_text, code_style),
        ]

    if provenance is not None:
        tx_hwm = str(provenance.transactions_hwm)
        tx_sha = provenance.transactions_sha
        bal_hwm = str(provenance.balances_hwm)
        bal_sha = provenance.balances_sha
        l2_sha = provenance.l2_yaml_sha
        code_id = provenance.code_identity
        code_sha = provenance.composite_sha
    else:
        tx_hwm = tx_sha = bal_hwm = bal_sha = l2_sha = placeholder
        code_id = f"v{version}"
        code_sha = placeholder

    rows = [
        [
            Paragraph("Source", header_style),
            Paragraph("Last entry / version", header_style),
            Paragraph("SHA256", header_style),
        ],
        _row("Transactions table", tx_hwm, tx_sha),
        _row("Daily balances table", bal_hwm, bal_sha),
        _row("L2 instance YAML", l2_label, l2_sha),
        _row("quicksight-gen code", code_id, code_sha),
    ]
    table = Table(
        rows,
        colWidths=[2.0 * inch, 2.2 * inch, 2.8 * inch],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, 0),
             HexColor(theme.link_tint)),
            ("BOX", (0, 0), (-1, -1), 0.5,
             HexColor(theme.secondary_fg)),
            ("INNERGRID", (0, 0), (-1, -1), 0.25,
             HexColor(theme.secondary_fg)),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]),
    )
    return [
        Spacer(1, 0.3 * inch),
        Paragraph(
            "<b>Source-Data Provenance</b>", styles["Heading3"],
        ),
        Paragraph(
            "<i>Reproducibility binding. The contents of this report "
            "derive entirely from the four sources below. The full "
            "fingerprint (the SHA256 of these inputs concatenated) "
            "is summarized in every page footer; the cryptographic "
            "seal over the system attestation block on the sign-off "
            "page covers the same inputs.</i>",
            styles["BodyText"],
        ),
        Spacer(1, 0.1 * inch),
        table,
    ]
