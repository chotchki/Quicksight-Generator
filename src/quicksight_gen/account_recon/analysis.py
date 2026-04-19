"""QuickSight Analysis + Dashboard for Account Recon.

Phase 5 extends the Exceptions tab with two more independent checks —
per-type daily transfer limit breaches and sub-ledger overdrafts — plus
the filters and drill-downs that feed them. Five string parameters
(``pArSubledgerAccountId``, ``pArLedgerAccountId``, ``pArTransferId``,
``pArActivityDate``, ``pArTransferType``) thread the drill-downs; each
has a matching filter group scoped to its target sheet (or the ledger's
same-sheet sub-ledger table).
"""

from __future__ import annotations

from quicksight_gen.account_recon.constants import (
    DS_AR_LEDGER_ACCOUNTS,
    DS_AR_LEDGER_BALANCE_DRIFT,
    DS_AR_LIMIT_BREACH,
    DS_AR_NON_ZERO_TRANSFERS,
    DS_AR_OVERDRAFT,
    DS_AR_SUBLEDGER_ACCOUNTS,
    DS_AR_SUBLEDGER_BALANCE_DRIFT,
    DS_AR_SWEEP_TARGET_NONZERO,
    DS_AR_CONCENTRATION_MASTER_SWEEP_DRIFT,
    DS_AR_ACH_ORIG_SETTLEMENT_NONZERO,
    DS_AR_ACH_SWEEP_NO_FED_CONFIRMATION,
    DS_AR_FED_CARD_NO_INTERNAL_CATCHUP,
    DS_AR_GL_VS_FED_MASTER_DRIFT,
    DS_AR_INTERNAL_REVERSAL_UNCREDITED,
    DS_AR_INTERNAL_TRANSFER_STUCK,
    DS_AR_INTERNAL_TRANSFER_SUSPENSE_NONZERO,
    DS_AR_EXPECTED_ZERO_EOD_ROLLUP,
    DS_AR_TWO_SIDED_POST_MISMATCH_ROLLUP,
    DS_AR_BALANCE_DRIFT_TIMELINES_ROLLUP,
    DS_AR_TRANSACTIONS,
    DS_AR_TRANSFER_SUMMARY,
    SHEET_AR_BALANCES,
    SHEET_AR_EXCEPTIONS,
    SHEET_AR_GETTING_STARTED,
    SHEET_AR_TRANSACTIONS,
    SHEET_AR_TRANSFERS,
)
from quicksight_gen.account_recon.datasets import build_all_datasets
from quicksight_gen.account_recon.filters import (
    build_balances_controls,
    build_exceptions_controls,
    build_filter_groups,
    build_transactions_controls,
    build_transfers_controls,
)
from quicksight_gen.account_recon.visuals import (
    build_balances_visuals,
    build_exceptions_visuals,
    build_transactions_visuals,
    build_transfers_visuals,
)
from quicksight_gen.common import rich_text as rt
from quicksight_gen.common.config import Config
from quicksight_gen.common.models import (
    Analysis,
    AnalysisDefinition,
    CategoryFilter,
    CategoryFilterConfiguration,
    ColumnIdentifier,
    Dashboard,
    DashboardPublishOptions,
    DataSetIdentifierDeclaration,
    Filter,
    FilterGroup,
    FilterScopeConfiguration,
    GridLayoutConfiguration,
    GridLayoutElement,
    Layout,
    LayoutConfiguration,
    ParameterDeclaration,
    ResourcePermission,
    SelectedSheetsFilterScopeConfiguration,
    SheetDefinition,
    SheetTextBox,
    SheetVisualScopingConfiguration,
    StringParameterDeclaration,
)
from quicksight_gen.common.theme import get_preset


_ANALYSIS_ACTIONS = [
    "quicksight:DescribeAnalysis",
    "quicksight:DescribeAnalysisPermissions",
    "quicksight:UpdateAnalysis",
    "quicksight:UpdateAnalysisPermissions",
    "quicksight:DeleteAnalysis",
    "quicksight:QueryAnalysis",
    "quicksight:RestoreAnalysis",
]

_DASHBOARD_ACTIONS = [
    "quicksight:DescribeDashboard",
    "quicksight:ListDashboardVersions",
    "quicksight:UpdateDashboardPermissions",
    "quicksight:QueryDashboard",
    "quicksight:UpdateDashboard",
    "quicksight:DeleteDashboard",
    "quicksight:DescribeDashboardPermissions",
    "quicksight:UpdateDashboardPublishedVersion",
    "quicksight:UpdateDashboardLinks",
]


# ---------------------------------------------------------------------------
# Layout helpers — QuickSight grid is 36 columns wide
# ---------------------------------------------------------------------------

_KPI_ROW_SPAN = 6
_CHART_ROW_SPAN = 12
_TABLE_ROW_SPAN = 18
_HALF = 18
_FULL = 36


def _grid_layout(elements: list[GridLayoutElement]) -> list[Layout]:
    return [Layout(Configuration=LayoutConfiguration(
        GridLayout=GridLayoutConfiguration(Elements=elements),
    ))]


def _kpi_pair(id_left: str, id_right: str) -> list[GridLayoutElement]:
    return [
        GridLayoutElement(
            ElementId=id_left, ElementType="VISUAL",
            ColumnSpan=_HALF, RowSpan=_KPI_ROW_SPAN,
            ColumnIndex=0,
        ),
        GridLayoutElement(
            ElementId=id_right, ElementType="VISUAL",
            ColumnSpan=_HALF, RowSpan=_KPI_ROW_SPAN,
            ColumnIndex=_HALF,
        ),
    ]


def _chart_pair(id_left: str, id_right: str) -> list[GridLayoutElement]:
    return [
        GridLayoutElement(
            ElementId=id_left, ElementType="VISUAL",
            ColumnSpan=_HALF, RowSpan=_CHART_ROW_SPAN,
            ColumnIndex=0,
        ),
        GridLayoutElement(
            ElementId=id_right, ElementType="VISUAL",
            ColumnSpan=_HALF, RowSpan=_CHART_ROW_SPAN,
            ColumnIndex=_HALF,
        ),
    ]


def _full_width_visual(element_id: str, row_span: int) -> GridLayoutElement:
    return GridLayoutElement(
        ElementId=element_id, ElementType="VISUAL",
        ColumnSpan=_FULL, RowSpan=row_span,
        ColumnIndex=0,
    )


def _full_width_text(element_id: str, row_span: int) -> GridLayoutElement:
    return GridLayoutElement(
        ElementId=element_id, ElementType="TEXT_BOX",
        ColumnSpan=_FULL, RowSpan=row_span,
        ColumnIndex=0,
    )


# ---------------------------------------------------------------------------
# Sheet descriptions (shared with the Getting Started sheet)
# ---------------------------------------------------------------------------

_BALANCES_DESCRIPTION = (
    "Stored daily balances at both levels. Ledger table compares stored "
    "ledger balance to the sum of its sub-ledgers' stored balances; "
    "sub-ledger table compares each sub-ledger's stored balance to the "
    "running sum of posted transactions. Drift rows bubble up on the "
    "Exceptions tab."
)

_TRANSFERS_DESCRIPTION = (
    "Every transfer represented as a group of transactions sharing a "
    "transfer_id. Healthy transfers net to zero across non-failed legs; "
    "non-zero transfers indicate a keying error or a failed counter-leg."
)

_TRANSACTIONS_DESCRIPTION = (
    "Raw posting ledger — one row per leg. Includes both sub-ledger "
    "postings and direct ledger postings (funding batches, fees, sweeps). "
    "Filter by Posting Level to isolate ledger-level activity. Failed "
    "rows feed the non-zero transfer cases on Exceptions."
)

_EXCEPTIONS_DESCRIPTION = (
    "Five independent reconciliation problems side by side. Ledger drift "
    "is stored ledger vs Σ sub-ledgers' stored balances — fingers the "
    "ledger-balance upstream feed. Sub-ledger drift is stored sub-ledger "
    "vs Σ posted transactions — fingers the sub-ledger balance feed or "
    "the ledger. Non-zero transfers are per-transfer imbalances. Limit "
    "breaches are (sub-ledger, day, type) triples where outbound volume "
    "exceeded the ledger-defined daily transfer limit for that type. "
    "Overdrafts are sub-ledger days where the stored balance went "
    "negative. The timelines show when each drift feed spiked."
)


# Per-sheet highlights used to build bulleted summaries on the Getting
# Started tab.
_BALANCES_BULLETS = [
    "Ledger balances: stored ledger vs Σ sub-ledgers' stored balances",
    "Sub-ledger balances: stored sub-ledger vs Σ posted transactions",
    "Click an account to drill into its transactions",
]

_TRANSFERS_BULLETS = [
    "Transfer summary: one row per transfer_id",
    "Unhealthy transfers (non-zero net or failed legs) surface on Exceptions",
    "Click a transfer to drill into its underlying transactions",
]

_TRANSACTIONS_BULLETS = [
    "Raw ledger — one row per posting (sub-ledger and ledger-level)",
    "Filters: date range, transfer type, posting level, Show Only Failed",
    "Ledger-level postings: funding batches, fee assessments, clearing sweeps",
    "Failed rows feed the non-zero transfer cases on Exceptions",
]

_EXCEPTIONS_BULLETS = [
    "Ledger and sub-ledger balance drift (separate upstream feeds)",
    "Non-zero transfers, daily limit breaches, and sub-ledger overdrafts",
    "Timelines show when each drift feed spiked",
    "Click any row to drill into the underlying transactions",
]


# ---------------------------------------------------------------------------
# Text boxes
# ---------------------------------------------------------------------------

def _section_box(
    box_id: str, title: str, body: str, bullet_items: list[str], accent: str,
) -> SheetTextBox:
    """Per-sheet Getting Started block: heading + body paragraph + bullets."""
    return SheetTextBox(
        SheetTextBoxId=box_id,
        Content=rt.text_box(
            rt.heading(title, color=accent),
            rt.BR,
            rt.BR,
            rt.body(body),
            rt.BR,
            rt.bullets(bullet_items),
        ),
    )


# ---------------------------------------------------------------------------
# Getting Started sheet
# ---------------------------------------------------------------------------

def _build_getting_started_sheet(cfg: Config) -> SheetDefinition:
    is_demo = cfg.demo_database_url is not None
    accent = get_preset(cfg.theme_preset).accent

    welcome_box = SheetTextBox(
        SheetTextBoxId="ar-gs-welcome",
        Content=rt.text_box(
            rt.inline(
                "Account Reconciliation Dashboard",
                font_size="36px",
                color=accent,
            ),
            rt.BR,
            rt.BR,
            rt.body(
                "Reconcile stored daily balances at the ledger- and "
                "sub-ledger account levels against their computed "
                "counterparts, plus transfer-level transactions for a "
                "bank's double-entry ledger. Walk from aggregate balances "
                "down to individual transactions — the Exceptions tab "
                "pulls the problems together in one place."
            ),
        ),
    )

    tip_box = SheetTextBox(
        SheetTextBoxId="ar-gs-nav-tip",
        Content=rt.text_box(
            rt.heading("Navigation tip", color=accent),
            rt.BR,
            rt.BR,
            rt.bullets_raw([
                rt.inline(
                    "Heads-up: drill-down filters stick after you switch "
                    "tabs. Refresh the dashboard to clear them.",
                    color=accent,
                ),
            ]),
        ),
    )

    text_boxes: list[SheetTextBox] = [welcome_box, tip_box]
    layout: list[GridLayoutElement] = [
        _full_width_text("ar-gs-welcome", 5),
        _full_width_text("ar-gs-nav-tip", 4),
    ]

    if is_demo:
        text_boxes.append(SheetTextBox(
            SheetTextBoxId="ar-gs-demo-flavor",
            Content=rt.text_box(
                rt.heading(
                    "Demo scenario — Farmers Exchange Bank",
                    color=accent,
                ),
                rt.BR,
                rt.BR,
                rt.body(
                    "Five ledger accounts (Big Meadow Checking, Harvest "
                    "Moon Savings, Orchard Lending Pool, Valley Grain "
                    "Co-op, and Harvest Credit Exchange) move money "
                    "between ten sub-ledger accounts over a ~40 day "
                    "window using four transfer types (ach, wire, "
                    "internal, cash). Ledger accounts define per-type "
                    "daily outbound limits; a handful of "
                    "sub-ledger-day-type cells intentionally breach those "
                    "limits."
                ),
                rt.BR,
                rt.BR,
                rt.body(
                    "A handful of transfers have a failed leg, another "
                    "handful are keyed off by a few dollars, three "
                    "sub-ledger days land in overdraft, and "
                    "ledger/sub-ledger stored balances carry disjoint "
                    "planted drift — so each of the five Exceptions "
                    "tables surfaces its own distinct rows."
                ),
                rt.BR,
                rt.BR,
                rt.body(
                    "Data is deterministic — anchor date is the day the "
                    "seed was generated. Explore the date-range, "
                    "transfer-type, and show-only toggles to see how each "
                    "tab responds."
                ),
            ),
        ))
        layout.append(_full_width_text("ar-gs-demo-flavor", 9))

    sheet_blocks = [
        (
            "ar-gs-balances", "Balances",
            _BALANCES_DESCRIPTION, _BALANCES_BULLETS,
        ),
        (
            "ar-gs-transfers", "Transfers",
            _TRANSFERS_DESCRIPTION, _TRANSFERS_BULLETS,
        ),
        (
            "ar-gs-transactions", "Transactions",
            _TRANSACTIONS_DESCRIPTION, _TRANSACTIONS_BULLETS,
        ),
        (
            "ar-gs-exceptions", "Exceptions",
            _EXCEPTIONS_DESCRIPTION, _EXCEPTIONS_BULLETS,
        ),
    ]
    for box_id, title, body_text, bullet_items in sheet_blocks:
        text_boxes.append(
            _section_box(box_id, title, body_text, bullet_items, accent)
        )
        layout.append(_full_width_text(box_id, row_span=7))

    return SheetDefinition(
        SheetId=SHEET_AR_GETTING_STARTED,
        Name="Getting Started",
        Title="Getting Started",
        Description=(
            "Landing page — summarises each tab in this dashboard so readers "
            "know where to look first. No filters or visuals."
        ),
        ContentType="INTERACTIVE",
        TextBoxes=text_boxes,
        Layouts=_grid_layout(layout),
    )


# ---------------------------------------------------------------------------
# Tab sheets
# ---------------------------------------------------------------------------

def _build_balances_sheet(cfg: Config, link_color: str, link_tint: str) -> SheetDefinition:
    return SheetDefinition(
        SheetId=SHEET_AR_BALANCES,
        Name="Balances",
        Title="Balances",
        Description=_BALANCES_DESCRIPTION,
        ContentType="INTERACTIVE",
        Visuals=build_balances_visuals(link_color, link_tint),
        FilterControls=build_balances_controls(cfg),
        Layouts=_grid_layout(
            _kpi_pair("ar-balances-kpi-ledgers", "ar-balances-kpi-subledgers")
            + [_full_width_visual("ar-balances-ledger-table", _TABLE_ROW_SPAN)]
            + [_full_width_visual("ar-balances-subledger-table", _TABLE_ROW_SPAN)]
        ),
    )


def _build_transfers_sheet(cfg: Config, link_color: str) -> SheetDefinition:
    return SheetDefinition(
        SheetId=SHEET_AR_TRANSFERS,
        Name="Transfers",
        Title="Transfers",
        Description=_TRANSFERS_DESCRIPTION,
        ContentType="INTERACTIVE",
        Visuals=build_transfers_visuals(link_color),
        FilterControls=build_transfers_controls(cfg),
        Layouts=_grid_layout(
            _kpi_pair("ar-transfers-kpi-count", "ar-transfers-kpi-unhealthy")
            + [_full_width_visual("ar-transfers-bar-status", _CHART_ROW_SPAN)]
            + [_full_width_visual("ar-transfers-summary-table", _TABLE_ROW_SPAN)]
        ),
    )


def _build_transactions_sheet(cfg: Config) -> SheetDefinition:
    return SheetDefinition(
        SheetId=SHEET_AR_TRANSACTIONS,
        Name="Transactions",
        Title="Transactions",
        Description=_TRANSACTIONS_DESCRIPTION,
        ContentType="INTERACTIVE",
        Visuals=build_transactions_visuals(),
        FilterControls=build_transactions_controls(cfg),
        Layouts=_grid_layout(
            _kpi_pair("ar-txn-kpi-count", "ar-txn-kpi-failed")
            + _chart_pair("ar-txn-bar-by-status", "ar-txn-bar-by-day")
            + [_full_width_visual("ar-txn-detail-table", _TABLE_ROW_SPAN)]
        ),
    )


def _build_exceptions_sheet(cfg: Config, link_color: str) -> SheetDefinition:
    """Four independent reconciliation checks + two timelines.

    Layout choices:
      * 5 KPIs wrap into a 3+2 grid (three 12-wide on top, two 18-wide
        on the second half-row) — keeps every KPI wide enough to read.
      * Tables are paired half-width (18 cols each) rather than single-
        column to cram four tables into two rows without each shrinking
        its internals. Timelines stay in the third row.
    """
    third = _FULL // 3  # 12-wide for the three-across KPI row

    kpi_row_a = [
        GridLayoutElement(
            ElementId="ar-exc-kpi-ledger-drift", ElementType="VISUAL",
            ColumnSpan=third, RowSpan=_KPI_ROW_SPAN, ColumnIndex=0,
        ),
        GridLayoutElement(
            ElementId="ar-exc-kpi-subledger-drift", ElementType="VISUAL",
            ColumnSpan=third, RowSpan=_KPI_ROW_SPAN, ColumnIndex=third,
        ),
        GridLayoutElement(
            ElementId="ar-exc-kpi-nonzero", ElementType="VISUAL",
            ColumnSpan=third, RowSpan=_KPI_ROW_SPAN, ColumnIndex=third * 2,
        ),
    ]
    kpi_row_b = _kpi_pair("ar-exc-kpi-breach", "ar-exc-kpi-overdraft")

    # Four exception tables paired half-width for density. Timelines stay
    # on a later row.
    table_row_a = [
        GridLayoutElement(
            ElementId="ar-exc-ledger-drift-table", ElementType="VISUAL",
            ColumnSpan=_HALF, RowSpan=_TABLE_ROW_SPAN, ColumnIndex=0,
        ),
        GridLayoutElement(
            ElementId="ar-exc-subledger-drift-table", ElementType="VISUAL",
            ColumnSpan=_HALF, RowSpan=_TABLE_ROW_SPAN, ColumnIndex=_HALF,
        ),
    ]
    table_row_b = [
        GridLayoutElement(
            ElementId="ar-exc-nonzero-table", ElementType="VISUAL",
            ColumnSpan=_HALF, RowSpan=_TABLE_ROW_SPAN, ColumnIndex=0,
        ),
        GridLayoutElement(
            ElementId="ar-exc-breach-table", ElementType="VISUAL",
            ColumnSpan=_HALF, RowSpan=_TABLE_ROW_SPAN, ColumnIndex=_HALF,
        ),
    ]
    table_row_c = [
        _full_width_visual("ar-exc-overdraft-table", _TABLE_ROW_SPAN),
    ]

    # F.5.1: Sweep target non-zero EOD — KPI on its own row, then full-width
    # detail table, then full-width aging bar. New checks append to the
    # bottom of the sheet; F.5.10 will reorganize once all rollups are in.
    sweep_target_row_kpi = [
        GridLayoutElement(
            ElementId="ar-exc-kpi-sweep-target", ElementType="VISUAL",
            ColumnSpan=_FULL, RowSpan=_KPI_ROW_SPAN, ColumnIndex=0,
        ),
    ]
    sweep_target_table = [
        _full_width_visual("ar-exc-sweep-target-table", _TABLE_ROW_SPAN),
    ]
    sweep_target_aging = [
        _full_width_visual("ar-exc-aging-sweep-target", _CHART_ROW_SPAN),
    ]

    # F.5.2: Concentration Master sweep drift — KPI half-width, timeline
    # half-width on the same row. Mirrors the existing (ledger-drift,
    # sub-ledger-drift) timeline pair shape.
    sweep_drift_row = [
        GridLayoutElement(
            ElementId="ar-exc-kpi-sweep-drift", ElementType="VISUAL",
            ColumnSpan=_HALF, RowSpan=_KPI_ROW_SPAN, ColumnIndex=0,
        ),
        GridLayoutElement(
            ElementId="ar-exc-sweep-drift-timeline", ElementType="VISUAL",
            ColumnSpan=_HALF, RowSpan=_KPI_ROW_SPAN, ColumnIndex=_HALF,
        ),
    ]

    # F.5.3: ACH Origination Settlement non-zero EOD — same shape as
    # F.5.1 (KPI / table / aging bar stacked full width).
    ach_orig_row_kpi = [
        GridLayoutElement(
            ElementId="ar-exc-kpi-ach-orig-nonzero", ElementType="VISUAL",
            ColumnSpan=_FULL, RowSpan=_KPI_ROW_SPAN, ColumnIndex=0,
        ),
    ]
    ach_orig_table = [
        _full_width_visual("ar-exc-ach-orig-nonzero-table", _TABLE_ROW_SPAN),
    ]
    ach_orig_aging = [
        _full_width_visual("ar-exc-aging-ach-orig-nonzero", _CHART_ROW_SPAN),
    ]

    # F.5.4: ACH internal sweep posted but no Fed confirmation — KPI /
    # table / aging bar stacked full width.
    ach_sweep_no_fed_row_kpi = [
        GridLayoutElement(
            ElementId="ar-exc-kpi-ach-sweep-no-fed", ElementType="VISUAL",
            ColumnSpan=_FULL, RowSpan=_KPI_ROW_SPAN, ColumnIndex=0,
        ),
    ]
    ach_sweep_no_fed_table = [
        _full_width_visual("ar-exc-ach-sweep-no-fed-table", _TABLE_ROW_SPAN),
    ]
    ach_sweep_no_fed_aging = [
        _full_width_visual("ar-exc-aging-ach-sweep-no-fed", _CHART_ROW_SPAN),
    ]

    # F.5.5: Fed activity with no matching internal post — KPI / table /
    # aging bar stacked full width.
    fed_no_catchup_row_kpi = [
        GridLayoutElement(
            ElementId="ar-exc-kpi-fed-no-catchup", ElementType="VISUAL",
            ColumnSpan=_FULL, RowSpan=_KPI_ROW_SPAN, ColumnIndex=0,
        ),
    ]
    fed_no_catchup_table = [
        _full_width_visual("ar-exc-fed-no-catchup-table", _TABLE_ROW_SPAN),
    ]
    fed_no_catchup_aging = [
        _full_width_visual("ar-exc-aging-fed-no-catchup", _CHART_ROW_SPAN),
    ]

    # F.5.6: GL-vs-Fed Master drift — KPI half-width, timeline
    # half-width on the same row. Mirrors F.5.2 sweep_drift_row shape.
    gl_fed_drift_row = [
        GridLayoutElement(
            ElementId="ar-exc-kpi-gl-fed-drift", ElementType="VISUAL",
            ColumnSpan=_HALF, RowSpan=_KPI_ROW_SPAN, ColumnIndex=0,
        ),
        GridLayoutElement(
            ElementId="ar-exc-gl-fed-drift-timeline", ElementType="VISUAL",
            ColumnSpan=_HALF, RowSpan=_KPI_ROW_SPAN, ColumnIndex=_HALF,
        ),
    ]

    # F.5.7: Stuck in Internal Transfer Suspense — KPI / table / aging
    # bar stacked full width.
    internal_stuck_row_kpi = [
        GridLayoutElement(
            ElementId="ar-exc-kpi-internal-stuck", ElementType="VISUAL",
            ColumnSpan=_FULL, RowSpan=_KPI_ROW_SPAN, ColumnIndex=0,
        ),
    ]
    internal_stuck_table = [
        _full_width_visual("ar-exc-internal-stuck-table", _TABLE_ROW_SPAN),
    ]
    internal_stuck_aging = [
        _full_width_visual("ar-exc-aging-internal-stuck", _CHART_ROW_SPAN),
    ]

    # F.5.8: Internal Transfer Suspense non-zero EOD — KPI / table /
    # aging bar stacked full width. Mirrors F.5.3 ach-orig shape.
    internal_suspense_nonzero_row_kpi = [
        GridLayoutElement(
            ElementId="ar-exc-kpi-internal-suspense-nonzero",
            ElementType="VISUAL",
            ColumnSpan=_FULL, RowSpan=_KPI_ROW_SPAN, ColumnIndex=0,
        ),
    ]
    internal_suspense_nonzero_table = [
        _full_width_visual(
            "ar-exc-internal-suspense-nonzero-table", _TABLE_ROW_SPAN,
        ),
    ]
    internal_suspense_nonzero_aging = [
        _full_width_visual(
            "ar-exc-aging-internal-suspense-nonzero", _CHART_ROW_SPAN,
        ),
    ]

    # F.5.9: Internal Transfer Reversal Uncredited / "double spend" —
    # KPI / table / aging bar stacked full width.
    internal_reversal_uncredited_row_kpi = [
        GridLayoutElement(
            ElementId="ar-exc-kpi-internal-reversal-uncredited",
            ElementType="VISUAL",
            ColumnSpan=_FULL, RowSpan=_KPI_ROW_SPAN, ColumnIndex=0,
        ),
    ]
    internal_reversal_uncredited_table = [
        _full_width_visual(
            "ar-exc-internal-reversal-uncredited-table", _TABLE_ROW_SPAN,
        ),
    ]
    internal_reversal_uncredited_aging = [
        _full_width_visual(
            "ar-exc-aging-internal-reversal-uncredited", _CHART_ROW_SPAN,
        ),
    ]

    # F.5.10.a: Accounts Expected Zero at EOD rollup — placed at the TOP of
    # the Exceptions sheet so the same-SHAPE pattern across F.5.1, F.5.3,
    # F.5.8 hits the eye first; per-check tables remain below for drill-in.
    expected_zero_rollup_row_kpi = [
        GridLayoutElement(
            ElementId="ar-exc-kpi-expected-zero-rollup",
            ElementType="VISUAL",
            ColumnSpan=_FULL, RowSpan=_KPI_ROW_SPAN, ColumnIndex=0,
        ),
    ]
    expected_zero_rollup_table = [
        _full_width_visual(
            "ar-exc-expected-zero-rollup-table", _TABLE_ROW_SPAN,
        ),
    ]

    # F.5.10.b: Two-Sided Post Mismatch rollup — sits above F.5.10.a so
    # the same-SHAPE pattern across F.5.4 + F.5.5 (one side of an expected
    # SNB/Fed post pair landed, the other never did) hits the eye first.
    two_sided_rollup_row_kpi = [
        GridLayoutElement(
            ElementId="ar-exc-kpi-two-sided-rollup",
            ElementType="VISUAL",
            ColumnSpan=_FULL, RowSpan=_KPI_ROW_SPAN, ColumnIndex=0,
        ),
    ]
    two_sided_rollup_table = [
        _full_width_visual(
            "ar-exc-two-sided-rollup-table", _TABLE_ROW_SPAN,
        ),
    ]

    # F.5.10.c: Balance Drift Timelines rollup — sits at the very top of
    # the Exceptions sheet so the overlay of F.5.2 + F.5.6 drift series
    # is the first thing the eye lands on; per-check timelines stay below.
    drift_timelines_rollup = [
        _full_width_visual(
            "ar-exc-drift-timelines-rollup", _CHART_ROW_SPAN,
        ),
    ]

    return SheetDefinition(
        SheetId=SHEET_AR_EXCEPTIONS,
        Name="Exceptions",
        Title="Exceptions",
        Description=_EXCEPTIONS_DESCRIPTION,
        ContentType="INTERACTIVE",
        Visuals=build_exceptions_visuals(link_color),
        FilterControls=build_exceptions_controls(cfg),
        Layouts=_grid_layout(
            drift_timelines_rollup
            + two_sided_rollup_row_kpi
            + two_sided_rollup_table
            + expected_zero_rollup_row_kpi
            + expected_zero_rollup_table
            + kpi_row_a
            + kpi_row_b
            + table_row_a
            + table_row_b
            + table_row_c
            + _chart_pair(
                "ar-exc-ledger-drift-timeline",
                "ar-exc-subledger-drift-timeline",
            )
            + sweep_target_row_kpi
            + sweep_target_table
            + sweep_target_aging
            + sweep_drift_row
            + ach_orig_row_kpi
            + ach_orig_table
            + ach_orig_aging
            + ach_sweep_no_fed_row_kpi
            + ach_sweep_no_fed_table
            + ach_sweep_no_fed_aging
            + fed_no_catchup_row_kpi
            + fed_no_catchup_table
            + fed_no_catchup_aging
            + gl_fed_drift_row
            + internal_stuck_row_kpi
            + internal_stuck_table
            + internal_stuck_aging
            + internal_suspense_nonzero_row_kpi
            + internal_suspense_nonzero_table
            + internal_suspense_nonzero_aging
            + internal_reversal_uncredited_row_kpi
            + internal_reversal_uncredited_table
            + internal_reversal_uncredited_aging
        ),
    )


# ---------------------------------------------------------------------------
# Dataset identifier declarations
# ---------------------------------------------------------------------------

def _build_dataset_declarations(cfg: Config) -> list[DataSetIdentifierDeclaration]:
    """Map logical AR dataset identifiers to their ARNs.

    Order must match ``build_all_datasets`` so each ARN lines up with
    the intended logical identifier.
    """
    datasets = build_all_datasets(cfg)
    names = [
        DS_AR_LEDGER_ACCOUNTS,
        DS_AR_SUBLEDGER_ACCOUNTS,
        DS_AR_TRANSACTIONS,
        DS_AR_LEDGER_BALANCE_DRIFT,
        DS_AR_SUBLEDGER_BALANCE_DRIFT,
        DS_AR_TRANSFER_SUMMARY,
        DS_AR_NON_ZERO_TRANSFERS,
        DS_AR_LIMIT_BREACH,
        DS_AR_OVERDRAFT,
        DS_AR_SWEEP_TARGET_NONZERO,
        DS_AR_CONCENTRATION_MASTER_SWEEP_DRIFT,
        DS_AR_ACH_ORIG_SETTLEMENT_NONZERO,
        DS_AR_ACH_SWEEP_NO_FED_CONFIRMATION,
        DS_AR_FED_CARD_NO_INTERNAL_CATCHUP,
        DS_AR_GL_VS_FED_MASTER_DRIFT,
        DS_AR_INTERNAL_TRANSFER_STUCK,
        DS_AR_INTERNAL_TRANSFER_SUSPENSE_NONZERO,
        DS_AR_INTERNAL_REVERSAL_UNCREDITED,
        DS_AR_EXPECTED_ZERO_EOD_ROLLUP,
        DS_AR_TWO_SIDED_POST_MISMATCH_ROLLUP,
        DS_AR_BALANCE_DRIFT_TIMELINES_ROLLUP,
    ]
    return [
        DataSetIdentifierDeclaration(
            Identifier=name,
            DataSetArn=cfg.dataset_arn(ds.DataSetId),
        )
        for name, ds in zip(names, datasets)
    ]


# ---------------------------------------------------------------------------
# Drill-down parameters + filter groups
# ---------------------------------------------------------------------------

def _ar_string_parameter(name: str) -> ParameterDeclaration:
    return ParameterDeclaration(
        StringParameterDeclaration=StringParameterDeclaration(
            ParameterValueType="SINGLE_VALUED",
            Name=name,
            DefaultValues={"StaticValues": []},
        ),
    )


def _parameter_filter_group(
    fg_id: str,
    filter_id: str,
    dataset_id: str,
    column_name: str,
    parameter_name: str,
    sheet_id: str,
    visual_ids: list[str] | None = None,
) -> FilterGroup:
    """CategoryFilter that binds ``column_name`` to a drill-down parameter.

    When ``visual_ids`` is provided the filter is scoped to just those
    visuals on the sheet (used for the Balances same-sheet sub-ledger
    table drill). Otherwise it applies to every visual on the sheet.
    """
    scoping = SheetVisualScopingConfiguration(
        SheetId=sheet_id,
        Scope="SELECTED_VISUALS" if visual_ids else "ALL_VISUALS",
        VisualIds=visual_ids,
    )
    return FilterGroup(
        FilterGroupId=fg_id,
        CrossDataset="SINGLE_DATASET",
        ScopeConfiguration=FilterScopeConfiguration(
            SelectedSheets=SelectedSheetsFilterScopeConfiguration(
                SheetVisualScopingConfigurations=[scoping],
            ),
        ),
        Status="ENABLED",
        Filters=[
            Filter(
                CategoryFilter=CategoryFilter(
                    FilterId=filter_id,
                    Column=ColumnIdentifier(
                        DataSetIdentifier=dataset_id,
                        ColumnName=column_name,
                    ),
                    Configuration=CategoryFilterConfiguration(
                        CustomFilterConfiguration={
                            "MatchOperator": "EQUALS",
                            "ParameterName": parameter_name,
                            "NullOption": "ALL_VALUES",
                        },
                    ),
                ),
            ),
        ],
    )


def _build_drill_down_filter_groups() -> list[FilterGroup]:
    """Five parameter-bound filter groups that implement the drills.

    Phase 4 contributed the sub-ledger/transfer/ledger-on-balances trio;
    Phase 5 adds activity-date and transfer-type bindings on the
    Transactions sheet so breach/overdraft rows drill to a precise
    (sub-ledger, date[, type]) slice.
    """
    return [
        _parameter_filter_group(
            fg_id="fg-ar-drill-subledger-on-txn",
            filter_id="filter-ar-drill-subledger-on-txn",
            dataset_id=DS_AR_TRANSACTIONS,
            column_name="subledger_account_id",
            parameter_name="pArSubledgerAccountId",
            sheet_id=SHEET_AR_TRANSACTIONS,
        ),
        _parameter_filter_group(
            fg_id="fg-ar-drill-transfer-on-txn",
            filter_id="filter-ar-drill-transfer-on-txn",
            dataset_id=DS_AR_TRANSACTIONS,
            column_name="transfer_id",
            parameter_name="pArTransferId",
            sheet_id=SHEET_AR_TRANSACTIONS,
        ),
        _parameter_filter_group(
            fg_id="fg-ar-drill-activity-date-on-txn",
            filter_id="filter-ar-drill-activity-date-on-txn",
            dataset_id=DS_AR_TRANSACTIONS,
            column_name="posted_date",
            parameter_name="pArActivityDate",
            sheet_id=SHEET_AR_TRANSACTIONS,
        ),
        _parameter_filter_group(
            fg_id="fg-ar-drill-transfer-type-on-txn",
            filter_id="filter-ar-drill-transfer-type-on-txn",
            dataset_id=DS_AR_TRANSACTIONS,
            column_name="transfer_type",
            parameter_name="pArTransferType",
            sheet_id=SHEET_AR_TRANSACTIONS,
        ),
        _parameter_filter_group(
            fg_id="fg-ar-drill-ledger-on-balances-subledger",
            filter_id="filter-ar-drill-ledger-on-balances-subledger",
            dataset_id=DS_AR_SUBLEDGER_BALANCE_DRIFT,
            column_name="ledger_account_id",
            parameter_name="pArLedgerAccountId",
            sheet_id=SHEET_AR_BALANCES,
            visual_ids=["ar-balances-subledger-table"],
        ),
    ]


# ---------------------------------------------------------------------------
# Top-level definition / Analysis / Dashboard
# ---------------------------------------------------------------------------

def _build_definition(cfg: Config) -> AnalysisDefinition:
    preset = get_preset(cfg.theme_preset)
    link_color = preset.accent
    link_tint = preset.link_tint

    return AnalysisDefinition(
        DataSetIdentifierDeclarations=_build_dataset_declarations(cfg),
        Sheets=[
            _build_getting_started_sheet(cfg),
            _build_balances_sheet(cfg, link_color, link_tint),
            _build_transfers_sheet(cfg, link_color),
            _build_transactions_sheet(cfg),
            _build_exceptions_sheet(cfg, link_color),
        ],
        FilterGroups=build_filter_groups(cfg) + _build_drill_down_filter_groups(),
        ParameterDeclarations=[
            _ar_string_parameter("pArSubledgerAccountId"),
            _ar_string_parameter("pArLedgerAccountId"),
            _ar_string_parameter("pArTransferId"),
            _ar_string_parameter("pArActivityDate"),
            _ar_string_parameter("pArTransferType"),
        ],
    )


def _analysis_name(cfg: Config) -> str:
    preset = get_preset(cfg.theme_preset)
    if preset.analysis_name_prefix:
        return f"{preset.analysis_name_prefix} — Account Reconciliation"
    return "Account Reconciliation"


def build_analysis(cfg: Config) -> Analysis:
    """Build the complete Account Recon Analysis resource."""
    analysis_id = cfg.prefixed("account-recon-analysis")
    theme_id = cfg.prefixed("theme")

    permissions = None
    if cfg.principal_arns:
        permissions = [
            ResourcePermission(Principal=arn, Actions=_ANALYSIS_ACTIONS)
            for arn in cfg.principal_arns
        ]

    return Analysis(
        AwsAccountId=cfg.aws_account_id,
        AnalysisId=analysis_id,
        Name=_analysis_name(cfg),
        ThemeArn=cfg.theme_arn(theme_id),
        Definition=_build_definition(cfg),
        Permissions=permissions,
        Tags=cfg.tags(),
    )


def build_account_recon_dashboard(cfg: Config) -> Dashboard:
    """Build the Account Recon published Dashboard."""
    dashboard_id = cfg.prefixed("account-recon-dashboard")
    theme_id = cfg.prefixed("theme")

    permissions = None
    if cfg.principal_arns:
        permissions = [
            ResourcePermission(Principal=arn, Actions=_DASHBOARD_ACTIONS)
            for arn in cfg.principal_arns
        ]

    return Dashboard(
        AwsAccountId=cfg.aws_account_id,
        DashboardId=dashboard_id,
        Name=_analysis_name(cfg),
        ThemeArn=cfg.theme_arn(theme_id),
        Definition=_build_definition(cfg),
        Permissions=permissions,
        Tags=cfg.tags(),
        VersionDescription="Generated by quicksight-gen",
        DashboardPublishOptions=DashboardPublishOptions(
            AdHocFilteringOption={"AvailabilityStatus": "ENABLED"},
            ExportToCSVOption={"AvailabilityStatus": "ENABLED"},
            SheetControlsOption={"VisibilityState": "EXPANDED"},
        ),
    )
