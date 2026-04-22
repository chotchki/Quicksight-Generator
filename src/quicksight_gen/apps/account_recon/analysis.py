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

from dataclasses import dataclass

from quicksight_gen.apps.account_recon.constants import (
    DS_AR_BALANCE_DRIFT_TIMELINES_ROLLUP,
    DS_AR_DAILY_STATEMENT_SUMMARY,
    DS_AR_DAILY_STATEMENT_TRANSACTIONS,
    DS_AR_EXPECTED_ZERO_EOD_ROLLUP,
    DS_AR_LEDGER_ACCOUNTS,
    DS_AR_LEDGER_BALANCE_DRIFT,
    DS_AR_NON_ZERO_TRANSFERS,
    DS_AR_SUBLEDGER_ACCOUNTS,
    DS_AR_SUBLEDGER_BALANCE_DRIFT,
    DS_AR_TRANSACTIONS,
    DS_AR_TRANSFER_SUMMARY,
    DS_AR_TWO_SIDED_POST_MISMATCH_ROLLUP,
    DS_AR_UNIFIED_EXCEPTIONS,
    FG_AR_DRILL_ACCOUNT_ON_TXN,
    FG_AR_DRILL_ACTIVITY_DATE_ON_TXN,
    FG_AR_DRILL_LEDGER_ON_BALANCES_SUBLEDGER,
    FG_AR_DRILL_SUBLEDGER_ON_TXN,
    FG_AR_DRILL_TRANSFER_ON_TXN,
    FG_AR_DRILL_TRANSFER_TYPE_ON_TXN,
    P_AR_ACCOUNT,
    P_AR_ACTIVITY_DATE,
    P_AR_DS_ACCOUNT,
    P_AR_DS_BALANCE_DATE,
    P_AR_LEDGER,
    P_AR_SUBLEDGER,
    P_AR_TRANSFER,
    P_AR_TRANSFER_TYPE,
    SHEET_AR_BALANCES,
    SHEET_AR_DAILY_STATEMENT,
    SHEET_AR_EXCEPTIONS_TRENDS,
    SHEET_AR_GETTING_STARTED,
    SHEET_AR_TODAYS_EXCEPTIONS,
    SHEET_AR_TRANSACTIONS,
    SHEET_AR_TRANSFERS,
    V_AR_BALANCES_KPI_LEDGERS,
    V_AR_BALANCES_KPI_SUBLEDGERS,
    V_AR_BALANCES_LEDGER_TABLE,
    V_AR_BALANCES_SUBLEDGER_TABLE,
    V_AR_DS_KPI_CLOSING,
    V_AR_DS_KPI_CREDITS,
    V_AR_DS_KPI_DEBITS,
    V_AR_DS_KPI_DRIFT,
    V_AR_DS_KPI_OPENING,
    V_AR_DS_TRANSACTIONS_TABLE,
    V_AR_EXC_DRIFT_TIMELINES_ROLLUP,
    V_AR_EXC_EXPECTED_ZERO_ROLLUP_TABLE,
    V_AR_EXC_KPI_EXPECTED_ZERO_ROLLUP,
    V_AR_EXC_KPI_TWO_SIDED_ROLLUP,
    V_AR_EXC_TRENDS_AGING_MATRIX,
    V_AR_EXC_TRENDS_PER_CHECK,
    V_AR_EXC_TWO_SIDED_ROLLUP_TABLE,
    V_AR_TODAYS_EXC_BREAKDOWN,
    V_AR_TODAYS_EXC_KPI_TOTAL,
    V_AR_TODAYS_EXC_TABLE,
    V_AR_TRANSFERS_BAR_STATUS,
    V_AR_TRANSFERS_KPI_COUNT,
    V_AR_TRANSFERS_KPI_UNHEALTHY,
    V_AR_TRANSFERS_SUMMARY_TABLE,
    V_AR_TXN_BAR_BY_DAY,
    V_AR_TXN_BAR_BY_STATUS,
    V_AR_TXN_DETAIL_TABLE,
    V_AR_TXN_KPI_COUNT,
    V_AR_TXN_KPI_FAILED,
)
from quicksight_gen.apps.account_recon.datasets import build_all_datasets
from quicksight_gen.apps.account_recon.filters import (
    build_balances_controls,
    build_daily_statement_parameter_controls,
    build_exceptions_trends_controls,
    build_filter_groups,
    build_todays_exceptions_controls,
    build_transactions_controls,
    build_transfers_controls,
)
from quicksight_gen.apps.account_recon.visuals import (
    build_balances_visuals,
    build_daily_statement_visuals,
    build_exceptions_trends_visuals,
    build_todays_exceptions_visuals,
    build_transactions_visuals,
    build_transfers_visuals,
)
from quicksight_gen.common.drill import DrillParam
from quicksight_gen.common.ids import FilterGroupId, SheetId, VisualId
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
    DateTimeDefaultValues,
    DateTimeParameterDeclaration,
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


def _kpi_pair(id_left: VisualId, id_right: VisualId) -> list[GridLayoutElement]:
    return [
        GridLayoutElement(
            ElementId=id_left, ElementType=GridLayoutElement.VISUAL,
            ColumnSpan=_HALF, RowSpan=_KPI_ROW_SPAN,
            ColumnIndex=0,
        ),
        GridLayoutElement(
            ElementId=id_right, ElementType=GridLayoutElement.VISUAL,
            ColumnSpan=_HALF, RowSpan=_KPI_ROW_SPAN,
            ColumnIndex=_HALF,
        ),
    ]


def _chart_pair(id_left: VisualId, id_right: VisualId) -> list[GridLayoutElement]:
    return [
        GridLayoutElement(
            ElementId=id_left, ElementType=GridLayoutElement.VISUAL,
            ColumnSpan=_HALF, RowSpan=_CHART_ROW_SPAN,
            ColumnIndex=0,
        ),
        GridLayoutElement(
            ElementId=id_right, ElementType=GridLayoutElement.VISUAL,
            ColumnSpan=_HALF, RowSpan=_CHART_ROW_SPAN,
            ColumnIndex=_HALF,
        ),
    ]


def _full_width_visual(element_id: VisualId, row_span: int) -> GridLayoutElement:
    return GridLayoutElement(
        ElementId=element_id, ElementType=GridLayoutElement.VISUAL,
        ColumnSpan=_FULL, RowSpan=row_span,
        ColumnIndex=0,
    )


def _full_width_text(element_id: str, row_span: int) -> GridLayoutElement:
    return GridLayoutElement(
        ElementId=element_id, ElementType=GridLayoutElement.TEXT_BOX,
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

_TODAYS_EXCEPTIONS_DESCRIPTION = (
    "The 9am scan — every open exception across all 14 reconciliation "
    "checks in one unified table, sorted by severity then aging. Top KPI "
    "tracks total open count; the breakdown bar shows distribution by "
    "check type, coloured by severity. Filter by check, account, or age "
    "bucket; left-click a transfer_id to drill into Transactions."
)

_EXCEPTIONS_TRENDS_DESCRIPTION = (
    "The trend / rollup view paired with Today's Exceptions. Cross-check "
    "rollups at the top teach the SHAPE of recurring error classes — "
    "balance drift over time, two-sided posts where one side landed and "
    "the other didn't, control accounts that should be zero at EOD but "
    "aren't. Below: an aging-by-check matrix and a daily per-check trend "
    "so spikes line up across checks. Filters carry over from Today's "
    "Exceptions."
)

_DAILY_STATEMENT_DESCRIPTION = (
    "Per-account daily statement — pick one account and one day, and "
    "the sheet walks opening balance, debits, credits, stored closing, "
    "and drift, plus every posted leg. Drift = stored closing − "
    "(opening + Σ signed legs); on a clean feed it's zero, so a non-zero "
    "value is the single visual cue that the feed doesn't reconcile."
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

_TODAYS_EXCEPTIONS_BULLETS = [
    "Total open count + breakdown by check (coloured by severity)",
    "Unified table — every open exception, sorted severity then aging",
    "Filter by check, account, or aging bucket",
    "Left-click a transfer_id to drill into Transactions",
]

_EXCEPTIONS_TRENDS_BULLETS = [
    "Drift Timelines rollup (CMS sweep + GL/Fed Master on one axis)",
    "Two-Sided Post Mismatch + Accounts Expected Zero rollups (KPI + table)",
    "Aging-by-Check matrix and per-check daily trend",
    "Filters propagate to/from Today's Exceptions",
]

_DAILY_STATEMENT_BULLETS = [
    "Pick one account + one day via the sheet's filter controls",
    "Five KPIs: Opening, Debits, Credits, Closing (stored), Drift",
    "Drift = stored closing − (opening + Σ signed legs); zero on a clean feed",
    "Detail table: every leg with direction, counter-account, memo, and transfer_id",
    "Intended as the feed-validation artifact the Data Integration Team can screenshot",
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
                    "Demo scenario — Sasquatch National Bank",
                    color=accent,
                ),
                rt.BR,
                rt.BR,
                rt.body(
                    "Sasquatch National Bank (SNB), a Pacific Northwest "
                    "community bank, recently absorbed Farmers Exchange "
                    "Bank's commercial book. SNB's general ledger has "
                    "eight internal control accounts (Cash & Due From "
                    "FRB, ACH Origination Settlement, Card Acquiring "
                    "Settlement, Wire Settlement Suspense, Internal "
                    "Transfer Suspense, Cash Concentration Master, "
                    "Internal Suspense / Reconciliation, and Customer "
                    "Deposits — DDA Control) plus per-customer DDAs for "
                    "three coffee retailers (Bigfoot Brews, Sasquatch "
                    "Sips, Yeti Espresso) and four commercial customers "
                    "(Cascade Timber Mill, Pinecrest Vineyards, Big "
                    "Meadow Dairy, Harvest Moon Bakery)."
                ),
                rt.BR,
                rt.BR,
                rt.body(
                    "SNB's Cash Management Suite drives four telling "
                    "transfer flows: ZBA / Cash Concentration sweeps "
                    "(operating sub-accounts sweep to the master at "
                    "EOD), daily ACH origination sweeps to the FRB "
                    "Master Account, external force-posted card "
                    "settlements that internal books must catch up to, "
                    "and on-us internal transfers routed through the "
                    "Internal Transfer Suspense account. Each flow is "
                    "planted with both success cycles and characteristic "
                    "failure modes — sweep target non-zero, missing Fed "
                    "confirmation, force-post without internal catch-up, "
                    "stuck-in-suspense, reversed-but-not-credited."
                ),
                rt.BR,
                rt.BR,
                rt.body(
                    "Ledger and sub-ledger stored balances also carry "
                    "disjoint planted drift, plus a handful of off-amount "
                    "transfers, failed legs, limit breaches, and "
                    "overdrafts — so every Exceptions check surfaces "
                    "distinct rows. The Exceptions tab leads with "
                    "cross-check rollups so you learn to spot the same "
                    "SHAPE of error across multiple accounts."
                ),
                rt.BR,
                rt.BR,
                rt.body(
                    "AR is the unified view of SNB's shared ledger — "
                    "Payment Reconciliation's merchant DDAs (the same "
                    "coffee retailers' acquiring side) and external-rail "
                    "settlement account surface here too, alongside the "
                    "CMS accounts above. Use the Ledger and Sub-Ledger "
                    "pickers to scope your view if you want CMS-only."
                ),
                rt.BR,
                rt.BR,
                rt.body(
                    "Data is deterministic — anchor date is the day the "
                    "seed was generated. Explore the date-range, "
                    "transfer-type, posting-level, origin, and "
                    "show-only toggles to see how each tab responds."
                ),
            ),
        ))
        layout.append(_full_width_text("ar-gs-demo-flavor", 14))

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
            "ar-gs-todays-exceptions", "Today's Exceptions",
            _TODAYS_EXCEPTIONS_DESCRIPTION, _TODAYS_EXCEPTIONS_BULLETS,
        ),
        (
            "ar-gs-exceptions-trends", "Exceptions Trends",
            _EXCEPTIONS_TRENDS_DESCRIPTION, _EXCEPTIONS_TRENDS_BULLETS,
        ),
        (
            "ar-gs-daily-statement", "Daily Statement",
            _DAILY_STATEMENT_DESCRIPTION, _DAILY_STATEMENT_BULLETS,
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
            _kpi_pair(V_AR_BALANCES_KPI_LEDGERS, V_AR_BALANCES_KPI_SUBLEDGERS)
            + [_full_width_visual(V_AR_BALANCES_LEDGER_TABLE, _TABLE_ROW_SPAN)]
            + [_full_width_visual(V_AR_BALANCES_SUBLEDGER_TABLE, _TABLE_ROW_SPAN)]
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
            _kpi_pair(V_AR_TRANSFERS_KPI_COUNT, V_AR_TRANSFERS_KPI_UNHEALTHY)
            + [_full_width_visual(V_AR_TRANSFERS_BAR_STATUS, _CHART_ROW_SPAN)]
            + [_full_width_visual(V_AR_TRANSFERS_SUMMARY_TABLE, _TABLE_ROW_SPAN)]
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
            _kpi_pair(V_AR_TXN_KPI_COUNT, V_AR_TXN_KPI_FAILED)
            + _chart_pair(V_AR_TXN_BAR_BY_STATUS, V_AR_TXN_BAR_BY_DAY)
            + [_full_width_visual(V_AR_TXN_DETAIL_TABLE, _TABLE_ROW_SPAN)]
        ),
    )


def _build_daily_statement_sheet(cfg: Config) -> SheetDefinition:
    """Per-(account, day) feed-validation sheet.

    Layout: five KPIs across the top (three 12-wide on row A, two
    18-wide on row B — matches the Exceptions 3+2 KPI grid), then a
    full-width transaction table.
    """
    third = _FULL // 3

    kpi_row_a = [
        GridLayoutElement(
            ElementId=V_AR_DS_KPI_OPENING, ElementType=GridLayoutElement.VISUAL,
            ColumnSpan=third, RowSpan=_KPI_ROW_SPAN, ColumnIndex=0,
        ),
        GridLayoutElement(
            ElementId=V_AR_DS_KPI_DEBITS, ElementType=GridLayoutElement.VISUAL,
            ColumnSpan=third, RowSpan=_KPI_ROW_SPAN, ColumnIndex=third,
        ),
        GridLayoutElement(
            ElementId=V_AR_DS_KPI_CREDITS, ElementType=GridLayoutElement.VISUAL,
            ColumnSpan=third, RowSpan=_KPI_ROW_SPAN, ColumnIndex=third * 2,
        ),
    ]
    kpi_row_b = _kpi_pair(V_AR_DS_KPI_CLOSING, V_AR_DS_KPI_DRIFT)
    table_row = [_full_width_visual(V_AR_DS_TRANSACTIONS_TABLE, _TABLE_ROW_SPAN)]

    return SheetDefinition(
        SheetId=SHEET_AR_DAILY_STATEMENT,
        Name="Daily Statement",
        Title="Daily Statement",
        Description=_DAILY_STATEMENT_DESCRIPTION,
        ContentType="INTERACTIVE",
        Visuals=build_daily_statement_visuals(),
        ParameterControls=build_daily_statement_parameter_controls(cfg),
        Layouts=_grid_layout(kpi_row_a + kpi_row_b + table_row),
    )


def _build_todays_exceptions_sheet(
    cfg: Config, link_color: str, link_tint: str,
) -> SheetDefinition:
    """Phase K.1.2 — unified exception triage surface.

    Layout: total-count KPI (full width), severity-coloured breakdown
    bar (full width), unified detail table (full width). The legacy
    Exceptions sheet stays in place until K.1.4 drops the per-check
    blocks.
    """
    return SheetDefinition(
        SheetId=SHEET_AR_TODAYS_EXCEPTIONS,
        Name="Today's Exceptions",
        Title="Today's Exceptions",
        Description=_TODAYS_EXCEPTIONS_DESCRIPTION,
        ContentType="INTERACTIVE",
        Visuals=build_todays_exceptions_visuals(link_color, link_tint),
        FilterControls=build_todays_exceptions_controls(cfg),
        Layouts=_grid_layout(
            [_full_width_visual(V_AR_TODAYS_EXC_KPI_TOTAL, _KPI_ROW_SPAN)]
            + [_full_width_visual(V_AR_TODAYS_EXC_BREAKDOWN, _CHART_ROW_SPAN)]
            + [_full_width_visual(V_AR_TODAYS_EXC_TABLE, _TABLE_ROW_SPAN)]
        ),
    )


def _build_exceptions_trends_sheet(cfg: Config) -> SheetDefinition:
    """Phase K.1.3 — trend / rollup view paired with Today's Exceptions.

    Layout (top → bottom, all full width):
      * Drift Timelines rollup (clustered bar)
      * Two-Sided Post Mismatch — KPI then table
      * Accounts Expected Zero at EOD — KPI then table
      * Aging-by-Check matrix (stacked bar)
      * Per-check daily trend (stacked bar)
    """
    return SheetDefinition(
        SheetId=SHEET_AR_EXCEPTIONS_TRENDS,
        Name="Exceptions Trends",
        Title="Exceptions Trends",
        Description=_EXCEPTIONS_TRENDS_DESCRIPTION,
        ContentType="INTERACTIVE",
        Visuals=build_exceptions_trends_visuals(),
        FilterControls=build_exceptions_trends_controls(cfg),
        Layouts=_grid_layout(
            [_full_width_visual(V_AR_EXC_DRIFT_TIMELINES_ROLLUP, _CHART_ROW_SPAN)]
            + [_full_width_visual(V_AR_EXC_KPI_TWO_SIDED_ROLLUP, _KPI_ROW_SPAN)]
            + [_full_width_visual(V_AR_EXC_TWO_SIDED_ROLLUP_TABLE, _TABLE_ROW_SPAN)]
            + [_full_width_visual(V_AR_EXC_KPI_EXPECTED_ZERO_ROLLUP, _KPI_ROW_SPAN)]
            + [_full_width_visual(V_AR_EXC_EXPECTED_ZERO_ROLLUP_TABLE, _TABLE_ROW_SPAN)]
            + [_full_width_visual(V_AR_EXC_TRENDS_AGING_MATRIX, _CHART_ROW_SPAN)]
            + [_full_width_visual(V_AR_EXC_TRENDS_PER_CHECK, _CHART_ROW_SPAN)]
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
        DS_AR_EXPECTED_ZERO_EOD_ROLLUP,
        DS_AR_TWO_SIDED_POST_MISMATCH_ROLLUP,
        DS_AR_BALANCE_DRIFT_TIMELINES_ROLLUP,
        DS_AR_DAILY_STATEMENT_SUMMARY,
        DS_AR_DAILY_STATEMENT_TRANSACTIONS,
        DS_AR_UNIFIED_EXCEPTIONS,
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

# Phase K.2 sentinel — see _build_drill_helper_calculated_fields below
# for usage. Picked to be obviously synthetic and unable to collide with
# any real account/transfer/date string in the data.
_DRILL_RESET_SENTINEL = "__ALL__"


def _ar_string_parameter(
    name: str, default_value: str | None = None,
) -> ParameterDeclaration:
    """Declare a SINGLE_VALUED string param.

    ``default_value`` lets a parameter declare the K.2 reset sentinel
    as its untouched-state default — needed for any param whose
    destination filter uses the calc-field PASS shape, since both the
    "never-touched" state and the "drill reset" path must produce the
    sentinel value the calc field recognizes.
    """
    static_values = [default_value] if default_value is not None else []
    return ParameterDeclaration(
        StringParameterDeclaration=StringParameterDeclaration(
            ParameterValueType="SINGLE_VALUED",
            Name=name,
            DefaultValues={"StaticValues": static_values},
        ),
    )


def _drill_param_declaration(name: str) -> ParameterDeclaration:
    """Declare a drill-down string param that defaults to the sentinel.

    Raises if ``name`` is not a drill parameter — the sentinel default
    is only meaningful for params consumed by calc-field PASS filters,
    so declaring a non-drill parameter through this helper would be a
    programming error.
    """
    if name not in _DRILL_PARAMS_WITH_SENTINEL_DEFAULT:
        raise ValueError(
            f"{name!r} is not a drill parameter (known: "
            f"{sorted(_DRILL_PARAMS_WITH_SENTINEL_DEFAULT)}). Declare it "
            f"via _ar_string_parameter if it's a plain string param."
        )
    return _ar_string_parameter(name, default_value=_DRILL_RESET_SENTINEL)


def _ar_balance_date_parameter() -> ParameterDeclaration:
    """Daily Statement balance-date parameter — defaults to today.

    Bound to ``filter-ar-ds-balance-date`` so the date picker writes
    through, and to the right-click drill from the Balances sub-ledger
    table so a row click jumps the sheet to that account-day.
    """
    return ParameterDeclaration(
        DateTimeParameterDeclaration=DateTimeParameterDeclaration(
            Name=P_AR_DS_BALANCE_DATE.name,
            TimeGranularity="DAY",
            DefaultValues=DateTimeDefaultValues(
                RollingDate={"Expression": "truncDate('DD', now())"},
            ),
        ),
    )


# Phase K.2 — calc-field-based "pass" filter for every cross-sheet drill.
#
# Background: parameter-bound CategoryFilters (CustomFilterConfiguration
# { MatchOperator: EQUALS, ParameterName, NullOption: ALL_VALUES }) do
# NOT actually treat an empty SINGLE_VALUED string param as "match all"
# at runtime. They match the literal empty string instead, suppressing
# every row. Because of that, a drill that wrote only some params would
# leave the others at empty/stale, and the destination would silently
# narrow to nothing. The K.2 spike confirmed this against pArTransferId.
#
# The fix: move the parameter test into a calculated-field expression
# that returns 'PASS' when the param equals a sentinel value (or the
# column matches the param). The filter group statically requires the
# calc field equal 'PASS' — no parameter binding on the filter shape
# itself. The parameter declares the sentinel as its default so a
# never-touched fresh-load state passes through too. A drill action
# that wants to clear the param writes the sentinel explicitly.
#
# Why a sentinel ("__ALL__") instead of testing for empty/null in the
# calc field: the spike's empty/null path worked via URL fragment but
# failed via SetParametersOperation with every value-shape variant
# tried (IncludeNullValue:True+StringValues:[], StringValues:[""],
# coalesce(${p},'')=''). The drill-action code path apparently
# doesn't deliver the parameter value to the calc field in a form
# that simplifies to NULL/'' the way URL-fragment does. A real-string
# sentinel sidesteps the question entirely — every code path can
# write the literal "__ALL__" with confidence.


@dataclass(frozen=True)
class _DrillFilterSpec:
    """Single source of truth for one cross-sheet drill parameter.

    Used to derive both the calc-field declaration (which encodes the
    pass logic) and the FilterGroup that scopes the calc field to a
    sheet (and optionally specific visuals). Keeping all three pieces
    here in one record makes it impossible to forget the filter when
    adding a calc field, or vice versa. K.2 cleanup wired the
    ``parameter`` field to the typed ``DrillParam`` defined in
    ``visuals.py`` so the parameter name + shape come from one place.
    """
    fg_id: FilterGroupId
    filter_id: str
    parameter: DrillParam
    dataset_id: str
    column_name: str
    sheet_id: SheetId
    visual_ids: tuple[VisualId, ...] | None = None

    @property
    def parameter_name(self) -> str:
        return self.parameter.name

    @property
    def calc_field_name(self) -> str:
        # ``_drill_pass_<paramName>_on_<dataset_short>``. The dataset
        # short is the part of fg_id after "on-" so a sheet-restricted
        # variant (e.g. "balances-subledger") gets a distinct name.
        on_suffix = self.fg_id.split("on-", 1)[-1].replace("-", "_")
        return f"_drill_pass_{self.parameter_name}_on_{on_suffix}"


_DRILL_SPECS: list[_DrillFilterSpec] = [
    _DrillFilterSpec(
        fg_id=FG_AR_DRILL_SUBLEDGER_ON_TXN,
        filter_id="filter-ar-drill-subledger-on-txn",
        parameter=P_AR_SUBLEDGER,
        dataset_id=DS_AR_TRANSACTIONS,
        column_name="subledger_account_id",
        sheet_id=SHEET_AR_TRANSACTIONS,
    ),
    _DrillFilterSpec(
        fg_id=FG_AR_DRILL_TRANSFER_ON_TXN,
        filter_id="filter-ar-drill-transfer-on-txn",
        parameter=P_AR_TRANSFER,
        dataset_id=DS_AR_TRANSACTIONS,
        column_name="transfer_id",
        sheet_id=SHEET_AR_TRANSACTIONS,
    ),
    _DrillFilterSpec(
        fg_id=FG_AR_DRILL_ACTIVITY_DATE_ON_TXN,
        filter_id="filter-ar-drill-activity-date-on-txn",
        parameter=P_AR_ACTIVITY_DATE,
        dataset_id=DS_AR_TRANSACTIONS,
        column_name="posted_date",
        sheet_id=SHEET_AR_TRANSACTIONS,
    ),
    _DrillFilterSpec(
        fg_id=FG_AR_DRILL_TRANSFER_TYPE_ON_TXN,
        filter_id="filter-ar-drill-transfer-type-on-txn",
        parameter=P_AR_TRANSFER_TYPE,
        dataset_id=DS_AR_TRANSACTIONS,
        column_name="transfer_type",
        sheet_id=SHEET_AR_TRANSACTIONS,
    ),
    _DrillFilterSpec(
        fg_id=FG_AR_DRILL_ACCOUNT_ON_TXN,
        filter_id="filter-ar-drill-account-on-txn",
        parameter=P_AR_ACCOUNT,
        dataset_id=DS_AR_TRANSACTIONS,
        column_name="account_id",
        sheet_id=SHEET_AR_TRANSACTIONS,
    ),
    _DrillFilterSpec(
        fg_id=FG_AR_DRILL_LEDGER_ON_BALANCES_SUBLEDGER,
        filter_id="filter-ar-drill-ledger-on-balances-subledger",
        parameter=P_AR_LEDGER,
        dataset_id=DS_AR_SUBLEDGER_BALANCE_DRIFT,
        column_name="ledger_account_id",
        sheet_id=SHEET_AR_BALANCES,
        visual_ids=(V_AR_BALANCES_SUBLEDGER_TABLE,),
    ),
]

# Set of parameter names whose declarations need to default to the
# sentinel — derived from the spec list so a new drill doesn't get
# silently left out of the parameter declarations.
_DRILL_PARAMS_WITH_SENTINEL_DEFAULT = frozenset(
    spec.parameter_name for spec in _DRILL_SPECS
)


def _build_drill_helper_calculated_fields() -> list[dict]:
    """Calc fields backing every drill filter.

    Each spec produces ``ifelse(${param} = '__ALL__', 'PASS',
    ifelse({column} = ${param}, 'PASS', 'FAIL'))``. The destination
    filter group requires the calc field equal 'PASS', so the sentinel
    short-circuits to a no-op and any other value narrows to matches.
    """
    return [
        {
            "Name": spec.calc_field_name,
            "DataSetIdentifier": spec.dataset_id,
            "Expression": (
                f"ifelse("
                f"${{{spec.parameter_name}}} = '{_DRILL_RESET_SENTINEL}', "
                f"'PASS', "
                f"ifelse({{{spec.column_name}}} = ${{{spec.parameter_name}}}, "
                f"'PASS', 'FAIL')"
                f")"
            ),
        }
        for spec in _DRILL_SPECS
    ]


def _calc_field_pass_filter_group(spec: _DrillFilterSpec) -> FilterGroup:
    """FilterGroup that statically requires ``calc_field == 'PASS'``.

    The parameter test lives entirely in the calc field expression.
    The filter shape itself is purely static — a literal CategoryValue
    of "PASS" — so it never trips the empty-string-narrows-to-nothing
    behavior of parameter-bound CustomFilterConfiguration.

    Why ``CustomFilterConfiguration`` with a literal value rather than
    ``FilterListConfiguration`` / ``CustomFilterListConfiguration``:
    both list shapes reject EQUALS at the API (only CONTAINS /
    DOES_NOT_CONTAIN). The single-value Custom variant is the only
    shape that supports exact equality on a string column.
    """
    scoping = SheetVisualScopingConfiguration(
        SheetId=spec.sheet_id,
        Scope=(
            SheetVisualScopingConfiguration.SELECTED_VISUALS
            if spec.visual_ids
            else SheetVisualScopingConfiguration.ALL_VISUALS
        ),
        VisualIds=list(spec.visual_ids) if spec.visual_ids else None,
    )
    return FilterGroup(
        FilterGroupId=spec.fg_id,
        CrossDataset=FilterGroup.SINGLE_DATASET,
        ScopeConfiguration=FilterScopeConfiguration(
            SelectedSheets=SelectedSheetsFilterScopeConfiguration(
                SheetVisualScopingConfigurations=[scoping],
            ),
        ),
        Status=FilterGroup.ENABLED,
        Filters=[
            Filter(
                CategoryFilter=CategoryFilter(
                    FilterId=spec.filter_id,
                    Column=ColumnIdentifier(
                        DataSetIdentifier=spec.dataset_id,
                        ColumnName=spec.calc_field_name,
                    ),
                    Configuration=CategoryFilterConfiguration(
                        CustomFilterConfiguration={
                            "MatchOperator": "EQUALS",
                            "CategoryValue": "PASS",
                            "NullOption": "NON_NULLS_ONLY",
                        },
                    ),
                ),
            ),
        ],
    )


def _build_drill_down_filter_groups() -> list[FilterGroup]:
    """Six calc-field-pass filter groups, one per drill parameter."""
    return [_calc_field_pass_filter_group(spec) for spec in _DRILL_SPECS]


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
            _build_todays_exceptions_sheet(cfg, link_color, link_tint),
            _build_exceptions_trends_sheet(cfg),
            _build_daily_statement_sheet(cfg),
        ],
        FilterGroups=build_filter_groups(cfg) + _build_drill_down_filter_groups(),
        CalculatedFields=_build_drill_helper_calculated_fields(),
        # Every drill parameter defaults to the sentinel so a
        # fresh-load (untouched) state passes through the calc-field
        # PASS filter as a no-op. Membership in
        # _DRILL_PARAMS_WITH_SENTINEL_DEFAULT is derived from
        # _DRILL_SPECS so adding a drill spec automatically wires the
        # default — no chance of declaring a calc field whose param
        # has a missing/empty default.
        ParameterDeclarations=[
            _drill_param_declaration(P_AR_SUBLEDGER.name),
            _drill_param_declaration(P_AR_LEDGER.name),
            _drill_param_declaration(P_AR_TRANSFER.name),
            _drill_param_declaration(P_AR_ACTIVITY_DATE.name),
            _drill_param_declaration(P_AR_TRANSFER_TYPE.name),
            _drill_param_declaration(P_AR_ACCOUNT.name),
            _ar_string_parameter(P_AR_DS_ACCOUNT.name),
            _ar_balance_date_parameter(),
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
