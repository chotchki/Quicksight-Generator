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
    SHEET_AR_BALANCES,
    SHEET_AR_DAILY_STATEMENT,
    SHEET_AR_EXCEPTIONS_TRENDS,
    SHEET_AR_GETTING_STARTED,
    SHEET_AR_TODAYS_EXCEPTIONS,
    SHEET_AR_TRANSACTIONS,
    SHEET_AR_TRANSFERS,
)
from quicksight_gen.account_recon.datasets import build_all_datasets
from quicksight_gen.account_recon.filters import (
    build_balances_controls,
    build_daily_statement_parameter_controls,
    build_exceptions_trends_controls,
    build_filter_groups,
    build_todays_exceptions_controls,
    build_transactions_controls,
    build_transfers_controls,
)
from quicksight_gen.account_recon.visuals import (
    build_balances_visuals,
    build_daily_statement_visuals,
    build_exceptions_trends_visuals,
    build_todays_exceptions_visuals,
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


def _build_daily_statement_sheet(cfg: Config) -> SheetDefinition:
    """Per-(account, day) feed-validation sheet.

    Layout: five KPIs across the top (three 12-wide on row A, two
    18-wide on row B — matches the Exceptions 3+2 KPI grid), then a
    full-width transaction table.
    """
    third = _FULL // 3

    kpi_row_a = [
        GridLayoutElement(
            ElementId="ar-ds-kpi-opening", ElementType="VISUAL",
            ColumnSpan=third, RowSpan=_KPI_ROW_SPAN, ColumnIndex=0,
        ),
        GridLayoutElement(
            ElementId="ar-ds-kpi-debits", ElementType="VISUAL",
            ColumnSpan=third, RowSpan=_KPI_ROW_SPAN, ColumnIndex=third,
        ),
        GridLayoutElement(
            ElementId="ar-ds-kpi-credits", ElementType="VISUAL",
            ColumnSpan=third, RowSpan=_KPI_ROW_SPAN, ColumnIndex=third * 2,
        ),
    ]
    kpi_row_b = _kpi_pair("ar-ds-kpi-closing", "ar-ds-kpi-drift")
    table_row = [_full_width_visual("ar-ds-transactions-table", _TABLE_ROW_SPAN)]

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
            [_full_width_visual("ar-todays-exc-kpi-total", _KPI_ROW_SPAN)]
            + [_full_width_visual("ar-todays-exc-breakdown", _CHART_ROW_SPAN)]
            + [_full_width_visual("ar-todays-exc-table", _TABLE_ROW_SPAN)]
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
            [_full_width_visual("ar-exc-drift-timelines-rollup", _CHART_ROW_SPAN)]
            + [_full_width_visual("ar-exc-kpi-two-sided-rollup", _KPI_ROW_SPAN)]
            + [_full_width_visual("ar-exc-two-sided-rollup-table", _TABLE_ROW_SPAN)]
            + [_full_width_visual("ar-exc-kpi-expected-zero-rollup", _KPI_ROW_SPAN)]
            + [_full_width_visual("ar-exc-expected-zero-rollup-table", _TABLE_ROW_SPAN)]
            + [_full_width_visual("ar-exc-trends-aging-matrix", _CHART_ROW_SPAN)]
            + [_full_width_visual("ar-exc-trends-per-check", _CHART_ROW_SPAN)]
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

def _ar_string_parameter(name: str) -> ParameterDeclaration:
    return ParameterDeclaration(
        StringParameterDeclaration=StringParameterDeclaration(
            ParameterValueType="SINGLE_VALUED",
            Name=name,
            DefaultValues={"StaticValues": []},
        ),
    )


def _ar_balance_date_parameter() -> ParameterDeclaration:
    """Daily Statement balance-date parameter — defaults to today.

    Bound to ``filter-ar-ds-balance-date`` so the date picker writes
    through, and to the right-click drill from the Balances sub-ledger
    table so a row click jumps the sheet to that account-day.
    """
    return ParameterDeclaration(
        DateTimeParameterDeclaration=DateTimeParameterDeclaration(
            Name="pArDsBalanceDate",
            TimeGranularity="DAY",
            DefaultValues=DateTimeDefaultValues(
                RollingDate={"Expression": "truncDate('DD', now())"},
            ),
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
            fg_id="fg-ar-drill-account-on-txn",
            filter_id="filter-ar-drill-account-on-txn",
            dataset_id=DS_AR_TRANSACTIONS,
            column_name="account_id",
            parameter_name="pArAccountId",
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
            _build_todays_exceptions_sheet(cfg, link_color, link_tint),
            _build_exceptions_trends_sheet(cfg),
            _build_daily_statement_sheet(cfg),
        ],
        FilterGroups=build_filter_groups(cfg) + _build_drill_down_filter_groups(),
        ParameterDeclarations=[
            _ar_string_parameter("pArSubledgerAccountId"),
            _ar_string_parameter("pArLedgerAccountId"),
            _ar_string_parameter("pArTransferId"),
            _ar_string_parameter("pArActivityDate"),
            _ar_string_parameter("pArTransferType"),
            _ar_string_parameter("pArAccountId"),
            _ar_string_parameter("pArDsAccountId"),
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
