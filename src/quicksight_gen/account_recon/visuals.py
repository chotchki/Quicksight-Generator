"""Visual builders for Account Recon.

Phase 4 expands the skeleton from Phase 3:

Drill-downs (pattern mirrors payment_recon):
  * Balances parent row (right-click) → filters child table on same sheet
    to that parent's children via ``pArParentAccountId``.
  * Balances child row (left-click) → Transactions filtered by account.
  * Transfers row (left-click) → Transactions filtered by transfer_id.
  * Exceptions parent-drift (left-click) → Balances, child table filtered
    by parent.
  * Exceptions child-drift (left-click) → Transactions filtered by account.
  * Exceptions non-zero-transfer (left-click) → Transactions filtered by
    transfer_id.

Same-sheet chart-filter actions on every new chart so clicking a bar
filters the detail table on the same sheet (matches payment_recon).

Visual additions:
  * Parent Drift Timeline on Exceptions (alongside the existing child
    timeline — two feeds, two lines).
  * Transfer Status bar chart on Transfers.
  * Transactions-by-day grouped bar chart on Transactions.
"""

from __future__ import annotations

from quicksight_gen.account_recon.constants import (
    DS_AR_ACCOUNT_BALANCE_DRIFT,
    DS_AR_ACCOUNTS,
    DS_AR_NON_ZERO_TRANSFERS,
    DS_AR_PARENT_ACCOUNTS,
    DS_AR_PARENT_BALANCE_DRIFT,
    DS_AR_TRANSACTIONS,
    DS_AR_TRANSFER_SUMMARY,
    SHEET_AR_BALANCES,
    SHEET_AR_TRANSACTIONS,
)
from quicksight_gen.common.clickability import (
    link_text_format,
    menu_link_text_format,
)
from quicksight_gen.common.models import (
    AxisLabelOptions,
    BarChartAggregatedFieldWells,
    BarChartConfiguration,
    BarChartFieldWells,
    BarChartVisual,
    CategoricalDimensionField,
    CategoricalMeasureField,
    ChartAxisLabelOptions,
    ColumnIdentifier,
    CustomActionFilterOperation,
    CustomActionNavigationOperation,
    CustomActionSetParametersOperation,
    DateDimensionField,
    DimensionField,
    FilterOperationSelectedFieldsConfiguration,
    FilterOperationTargetVisualsConfiguration,
    KPIConfiguration,
    KPIFieldWells,
    KPIVisual,
    LocalNavigationConfiguration,
    MeasureField,
    NumericalAggregationFunction,
    NumericalMeasureField,
    SameSheetTargetVisualConfiguration,
    TableConfiguration,
    TableFieldWells,
    TableUnaggregatedFieldWells,
    TableVisual,
    Visual,
    VisualCustomAction,
    VisualCustomActionOperation,
    VisualSubtitleLabelOptions,
    VisualTitleLabelOptions,
)


# ---------------------------------------------------------------------------
# Shorthand helpers (mirror payment_recon/visuals.py conventions)
# ---------------------------------------------------------------------------

def _col(ds: str, name: str) -> ColumnIdentifier:
    return ColumnIdentifier(DataSetIdentifier=ds, ColumnName=name)


def _dim(field_id: str, ds: str, col_name: str) -> DimensionField:
    return DimensionField(
        CategoricalDimensionField=CategoricalDimensionField(
            FieldId=field_id,
            Column=_col(ds, col_name),
        )
    )


def _date_dim(
    field_id: str, ds: str, col_name: str, granularity: str = "DAY",
) -> DimensionField:
    return DimensionField(
        DateDimensionField=DateDimensionField(
            FieldId=field_id,
            Column=_col(ds, col_name),
            DateGranularity=granularity,
        )
    )


def _measure_sum(field_id: str, ds: str, col_name: str) -> MeasureField:
    return MeasureField(
        NumericalMeasureField=NumericalMeasureField(
            FieldId=field_id,
            Column=_col(ds, col_name),
            AggregationFunction=NumericalAggregationFunction(
                SimpleNumericalAggregation="SUM"
            ),
        )
    )


def _measure_count(field_id: str, ds: str, col_name: str) -> MeasureField:
    return MeasureField(
        CategoricalMeasureField=CategoricalMeasureField(
            FieldId=field_id,
            Column=_col(ds, col_name),
            AggregationFunction="COUNT",
        )
    )


def _title(text: str) -> VisualTitleLabelOptions:
    return VisualTitleLabelOptions(
        Visibility="VISIBLE",
        FormatText={"PlainText": text},
    )


def _subtitle(text: str) -> VisualSubtitleLabelOptions:
    return VisualSubtitleLabelOptions(
        Visibility="VISIBLE",
        FormatText={"PlainText": text},
    )


def _axis_label(label: str) -> ChartAxisLabelOptions:
    return ChartAxisLabelOptions(
        AxisLabelOptions=[AxisLabelOptions(CustomLabel=label)],
    )


def _unagg_field(field_id: str, ds: str, col_name: str) -> dict:
    return {
        "FieldId": field_id,
        "Column": {
            "DataSetIdentifier": ds,
            "ColumnName": col_name,
        },
    }


# ---------------------------------------------------------------------------
# Action helpers (mirror payment_recon/visuals.py)
# ---------------------------------------------------------------------------

def _drill_down_action(
    action_id: str,
    name: str,
    target_sheet: str,
    param_name: str,
    source_field_id: str,
    trigger: str = "DATA_POINT_CLICK",
) -> VisualCustomAction:
    """Navigate to another sheet and set a drill-down parameter."""
    return VisualCustomAction(
        CustomActionId=action_id,
        Name=name,
        Trigger=trigger,
        ActionOperations=[
            VisualCustomActionOperation(
                NavigationOperation=CustomActionNavigationOperation(
                    LocalNavigationConfiguration=LocalNavigationConfiguration(
                        TargetSheetId=target_sheet,
                    ),
                ),
            ),
            VisualCustomActionOperation(
                SetParametersOperation=CustomActionSetParametersOperation(
                    ParameterValueConfigurations=[
                        {
                            "DestinationParameterName": param_name,
                            "Value": {"SourceField": source_field_id},
                        },
                    ],
                ),
            ),
        ],
    )


def _same_sheet_filter_action(
    action_id: str,
    name: str,
    target_visual_ids: list[str],
    trigger: str = "DATA_POINT_CLICK",
) -> VisualCustomAction:
    """Click filters target visuals on the same sheet via ALL_FIELDS."""
    return VisualCustomAction(
        CustomActionId=action_id,
        Name=name,
        Trigger=trigger,
        ActionOperations=[
            VisualCustomActionOperation(
                FilterOperation=CustomActionFilterOperation(
                    SelectedFieldsConfiguration=FilterOperationSelectedFieldsConfiguration(
                        SelectedFieldOptions="ALL_FIELDS",
                    ),
                    TargetVisualsConfiguration=FilterOperationTargetVisualsConfiguration(
                        SameSheetTargetVisualConfiguration=SameSheetTargetVisualConfiguration(
                            TargetVisuals=target_visual_ids,
                        ),
                    ),
                ),
            ),
        ],
    )


# Drill-down parameter names
P_AR_ACCOUNT = "pArAccountId"
P_AR_PARENT = "pArParentAccountId"
P_AR_TRANSFER = "pArTransferId"


# ---------------------------------------------------------------------------
# Balances tab — parent + child drift tables with drill-downs
# ---------------------------------------------------------------------------

def build_balances_visuals(link_color: str, link_tint: str) -> list[Visual]:
    kpi_parents = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-balances-kpi-parents",
            Title=_title("Parent Accounts"),
            Subtitle=_subtitle("Count of parent accounts (internal + external)"),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-balances-parent-count",
                            DS_AR_PARENT_ACCOUNTS,
                            "parent_account_id",
                        )
                    ],
                ),
            ),
        )
    )

    kpi_accounts = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-balances-kpi-accounts",
            Title=_title("Child Accounts"),
            Subtitle=_subtitle("Count of individual accounts under all parents"),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-balances-account-count",
                            DS_AR_ACCOUNTS,
                            "account_id",
                        )
                    ],
                ),
            ),
        )
    )

    table_parents = Visual(
        TableVisual=TableVisual(
            VisualId="ar-balances-parent-table",
            Title=_title("Parent Account Balances"),
            Subtitle=_subtitle(
                "Each parent account's stored vs computed daily balance. "
                "Computed = Σ of its children's stored balances. Right-click "
                "a parent_account_id to filter the child table below to "
                "that parent's children."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("ar-bal-parent-id",
                                         DS_AR_PARENT_BALANCE_DRIFT,
                                         "parent_account_id"),
                            _unagg_field("ar-bal-parent-name",
                                         DS_AR_PARENT_BALANCE_DRIFT,
                                         "parent_name"),
                            _unagg_field("ar-bal-scope",
                                         DS_AR_PARENT_BALANCE_DRIFT, "scope"),
                            _unagg_field("ar-bal-date",
                                         DS_AR_PARENT_BALANCE_DRIFT,
                                         "balance_date"),
                            _unagg_field("ar-bal-stored",
                                         DS_AR_PARENT_BALANCE_DRIFT,
                                         "stored_balance"),
                            _unagg_field("ar-bal-computed",
                                         DS_AR_PARENT_BALANCE_DRIFT,
                                         "computed_balance"),
                            _unagg_field("ar-bal-drift",
                                         DS_AR_PARENT_BALANCE_DRIFT, "drift"),
                        ],
                    )
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "ar-bal-date",
                                "Direction": "DESC",
                            },
                        },
                    ],
                },
            ),
            Actions=[
                # Navigation is a no-op (target is the current sheet) — AWS
                # rejects a SetParametersOperation that isn't preceded by a
                # NavigationOperation, so we include one. The drill-down
                # filter group ``fg-ar-drill-parent-on-balances-child`` is
                # scoped to the child table only via SELECTED_VISUALS, so
                # setting the parameter filters just that visual.
                _drill_down_action(
                    "action-ar-balances-filter-children",
                    "Filter Child Accounts Below",
                    SHEET_AR_BALANCES,
                    P_AR_PARENT,
                    "ar-bal-parent-id",
                    trigger="DATA_POINT_MENU",
                ),
            ],
            ConditionalFormatting={
                "ConditionalFormattingOptions": [
                    menu_link_text_format(
                        "ar-bal-parent-id",
                        "parent_account_id",
                        link_color,
                        link_tint,
                    ),
                ],
            },
        )
    )

    table_children = Visual(
        TableVisual=TableVisual(
            VisualId="ar-balances-child-table",
            Title=_title("Child Account Balances"),
            Subtitle=_subtitle(
                "Each child account's stored vs computed daily balance. "
                "Computed = running Σ of posted transactions. Left-click an "
                "account_id to drill into Transactions for that account."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("ar-bal-child-id",
                                         DS_AR_ACCOUNT_BALANCE_DRIFT,
                                         "account_id"),
                            _unagg_field("ar-bal-child-name",
                                         DS_AR_ACCOUNT_BALANCE_DRIFT,
                                         "account_name"),
                            _unagg_field("ar-bal-child-parent",
                                         DS_AR_ACCOUNT_BALANCE_DRIFT,
                                         "parent_name"),
                            _unagg_field("ar-bal-child-scope",
                                         DS_AR_ACCOUNT_BALANCE_DRIFT, "scope"),
                            _unagg_field("ar-bal-child-date",
                                         DS_AR_ACCOUNT_BALANCE_DRIFT,
                                         "balance_date"),
                            _unagg_field("ar-bal-child-stored",
                                         DS_AR_ACCOUNT_BALANCE_DRIFT,
                                         "stored_balance"),
                            _unagg_field("ar-bal-child-computed",
                                         DS_AR_ACCOUNT_BALANCE_DRIFT,
                                         "computed_balance"),
                            _unagg_field("ar-bal-child-drift",
                                         DS_AR_ACCOUNT_BALANCE_DRIFT,
                                         "drift"),
                        ],
                    )
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "ar-bal-child-date",
                                "Direction": "DESC",
                            },
                        },
                    ],
                },
            ),
            Actions=[
                _drill_down_action(
                    "action-ar-balances-child-to-txn",
                    "View Transactions",
                    SHEET_AR_TRANSACTIONS,
                    P_AR_ACCOUNT,
                    "ar-bal-child-id",
                ),
            ],
            ConditionalFormatting={
                "ConditionalFormattingOptions": [
                    link_text_format(
                        "ar-bal-child-id", "account_id", link_color,
                    ),
                ],
            },
        )
    )

    return [kpi_parents, kpi_accounts, table_parents, table_children]


# ---------------------------------------------------------------------------
# Transfers tab — KPIs, status bar chart, transfer summary with drill-down
# ---------------------------------------------------------------------------

def build_transfers_visuals(link_color: str) -> list[Visual]:
    kpi_transfers = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-transfers-kpi-count",
            Title=_title("Total Transfers"),
            Subtitle=_subtitle("Count of transfers across all statuses"),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-transfers-count",
                            DS_AR_TRANSFER_SUMMARY,
                            "transfer_id",
                        )
                    ],
                ),
            ),
        )
    )

    kpi_unhealthy = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-transfers-kpi-unhealthy",
            Title=_title("Non-Zero Transfers"),
            Subtitle=_subtitle(
                "Transfers whose non-failed legs don't sum to zero — the "
                "ledger is out of balance for these"
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-transfers-unhealthy",
                            DS_AR_NON_ZERO_TRANSFERS,
                            "transfer_id",
                        )
                    ],
                ),
            ),
        )
    )

    bar_status = Visual(
        BarChartVisual=BarChartVisual(
            VisualId="ar-transfers-bar-status",
            Title=_title("Transfer Status"),
            Subtitle=_subtitle(
                "Count of transfers by net-zero status. Click a bar to "
                "filter the summary table below."
            ),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[_dim("ar-xfr-status-dim",
                                       DS_AR_TRANSFER_SUMMARY,
                                       "net_zero_status")],
                        Values=[_measure_count(
                            "ar-xfr-status-count",
                            DS_AR_TRANSFER_SUMMARY,
                            "transfer_id",
                        )],
                    )
                ),
                Orientation="HORIZONTAL",
                BarsArrangement="CLUSTERED",
                CategoryLabelOptions=_axis_label("Status"),
                ValueLabelOptions=_axis_label("Transfers"),
            ),
            Actions=[
                _same_sheet_filter_action(
                    "action-ar-transfers-bar-filter",
                    "Filter Transfer Summary",
                    ["ar-transfers-summary-table"],
                ),
            ],
        )
    )

    table_transfers = Visual(
        TableVisual=TableVisual(
            VisualId="ar-transfers-summary-table",
            Title=_title("Transfer Summary"),
            Subtitle=_subtitle(
                "Every transfer with its net amount, debit/credit totals, "
                "leg count, and net-zero status. Left-click a transfer_id "
                "to drill into Transactions for that transfer."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("ar-xfr-id",
                                         DS_AR_TRANSFER_SUMMARY,
                                         "transfer_id"),
                            _unagg_field("ar-xfr-posted",
                                         DS_AR_TRANSFER_SUMMARY,
                                         "first_posted_at"),
                            _unagg_field("ar-xfr-debit",
                                         DS_AR_TRANSFER_SUMMARY,
                                         "total_debit"),
                            _unagg_field("ar-xfr-credit",
                                         DS_AR_TRANSFER_SUMMARY,
                                         "total_credit"),
                            _unagg_field("ar-xfr-net",
                                         DS_AR_TRANSFER_SUMMARY,
                                         "net_amount"),
                            _unagg_field("ar-xfr-status",
                                         DS_AR_TRANSFER_SUMMARY,
                                         "net_zero_status"),
                            _unagg_field("ar-xfr-scope",
                                         DS_AR_TRANSFER_SUMMARY,
                                         "scope_type"),
                            _unagg_field("ar-xfr-failed-legs",
                                         DS_AR_TRANSFER_SUMMARY,
                                         "failed_leg_count"),
                            _unagg_field("ar-xfr-memo",
                                         DS_AR_TRANSFER_SUMMARY, "memo"),
                        ],
                    )
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "ar-xfr-posted",
                                "Direction": "DESC",
                            },
                        },
                    ],
                },
            ),
            Actions=[
                _drill_down_action(
                    "action-ar-transfers-to-txn",
                    "View Transactions",
                    SHEET_AR_TRANSACTIONS,
                    P_AR_TRANSFER,
                    "ar-xfr-id",
                ),
            ],
            ConditionalFormatting={
                "ConditionalFormattingOptions": [
                    link_text_format(
                        "ar-xfr-id", "transfer_id", link_color,
                    ),
                ],
            },
        )
    )

    return [kpi_transfers, kpi_unhealthy, bar_status, table_transfers]


# ---------------------------------------------------------------------------
# Transactions tab — KPIs, two charts, detail table
# ---------------------------------------------------------------------------

def build_transactions_visuals() -> list[Visual]:
    kpi_txn_count = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-txn-kpi-count",
            Title=_title("Total Transactions"),
            Subtitle=_subtitle("Count of all transactions (all statuses)"),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-txn-count",
                            DS_AR_TRANSACTIONS,
                            "transaction_id",
                        )
                    ],
                ),
            ),
        )
    )

    kpi_failed = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-txn-kpi-failed",
            Title=_title("Failed Transactions"),
            Subtitle=_subtitle(
                "Transactions that did not post — money never moved. "
                "Contributes to non-zero transfers upstream."
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-txn-failed-count",
                            DS_AR_TRANSACTIONS,
                            "transaction_id",
                        )
                    ],
                ),
            ),
        )
    )

    bar_by_status = Visual(
        BarChartVisual=BarChartVisual(
            VisualId="ar-txn-bar-by-status",
            Title=_title("Transactions by Status"),
            Subtitle=_subtitle(
                "Breakdown of posted / pending / failed transactions. "
                "Click a bar to filter the detail table below."
            ),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[_dim("ar-txn-status-dim",
                                       DS_AR_TRANSACTIONS, "status")],
                        Values=[_measure_count(
                            "ar-txn-status-count",
                            DS_AR_TRANSACTIONS, "transaction_id",
                        )],
                    )
                ),
                Orientation="HORIZONTAL",
                BarsArrangement="CLUSTERED",
                CategoryLabelOptions=_axis_label("Status"),
                ValueLabelOptions=_axis_label("Transactions"),
            ),
            Actions=[
                _same_sheet_filter_action(
                    "action-ar-txn-bar-filter",
                    "Filter Transaction Detail",
                    ["ar-txn-detail-table"],
                ),
            ],
        )
    )

    # Transactions-by-day: vertical bar chart grouped (clustered) by status.
    # Rendered as a time series — one cluster per day, coloured by status —
    # so posted / failed trends are visible alongside the bar-by-status
    # aggregate totals above.
    bar_by_day = Visual(
        BarChartVisual=BarChartVisual(
            VisualId="ar-txn-bar-by-day",
            Title=_title("Transactions by Day"),
            Subtitle=_subtitle(
                "Daily transaction volume split by status. Click a bar to "
                "filter the detail table below."
            ),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[_date_dim("ar-txn-day-dim",
                                            DS_AR_TRANSACTIONS, "posted_at")],
                        Values=[_measure_count(
                            "ar-txn-day-count",
                            DS_AR_TRANSACTIONS, "transaction_id",
                        )],
                        Colors=[_dim("ar-txn-day-color",
                                     DS_AR_TRANSACTIONS, "status")],
                    )
                ),
                Orientation="VERTICAL",
                BarsArrangement="STACKED",
                CategoryLabelOptions=_axis_label("Date"),
                ValueLabelOptions=_axis_label("Transactions"),
                ColorLabelOptions=_axis_label("Status"),
            ),
            Actions=[
                _same_sheet_filter_action(
                    "action-ar-txn-day-filter",
                    "Filter Transaction Detail",
                    ["ar-txn-detail-table"],
                ),
            ],
        )
    )

    table_txn = Visual(
        TableVisual=TableVisual(
            VisualId="ar-txn-detail-table",
            Title=_title("Transaction Detail"),
            Subtitle=_subtitle(
                "Every leg of every transfer — newest first. Failed rows "
                "indicate legs that did not post."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("ar-txn-id",
                                         DS_AR_TRANSACTIONS,
                                         "transaction_id"),
                            _unagg_field("ar-txn-transfer",
                                         DS_AR_TRANSACTIONS,
                                         "transfer_id"),
                            _unagg_field("ar-txn-parent",
                                         DS_AR_TRANSACTIONS,
                                         "parent_name"),
                            _unagg_field("ar-txn-account",
                                         DS_AR_TRANSACTIONS,
                                         "account_name"),
                            _unagg_field("ar-txn-scope",
                                         DS_AR_TRANSACTIONS, "scope"),
                            _unagg_field("ar-txn-amount",
                                         DS_AR_TRANSACTIONS, "amount"),
                            _unagg_field("ar-txn-status",
                                         DS_AR_TRANSACTIONS, "status"),
                            _unagg_field("ar-txn-posted",
                                         DS_AR_TRANSACTIONS, "posted_at"),
                            _unagg_field("ar-txn-memo",
                                         DS_AR_TRANSACTIONS, "memo"),
                        ],
                    )
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "ar-txn-posted",
                                "Direction": "DESC",
                            },
                        },
                    ],
                },
            ),
        )
    )

    return [kpi_txn_count, kpi_failed, bar_by_status, bar_by_day, table_txn]


# ---------------------------------------------------------------------------
# Exceptions tab — drift tables, non-zero, two timelines
# ---------------------------------------------------------------------------

def build_exceptions_visuals(link_color: str) -> list[Visual]:
    kpi_parent_drift = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-exc-kpi-parent-drift",
            Title=_title("Parent Drift Days"),
            Subtitle=_subtitle(
                "Count of (parent, date) combinations where stored parent "
                "balance ≠ Σ of its children's stored balances"
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-exc-parent-drift-count",
                            DS_AR_PARENT_BALANCE_DRIFT,
                            "parent_account_id",
                        )
                    ],
                ),
            ),
        )
    )

    kpi_child_drift = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-exc-kpi-child-drift",
            Title=_title("Child Drift Days"),
            Subtitle=_subtitle(
                "Count of (child, date) combinations where stored child "
                "balance ≠ running Σ of posted transactions"
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-exc-child-drift-count",
                            DS_AR_ACCOUNT_BALANCE_DRIFT,
                            "account_id",
                        )
                    ],
                ),
            ),
        )
    )

    kpi_nonzero = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-exc-kpi-nonzero",
            Title=_title("Non-Zero Transfers"),
            Subtitle=_subtitle(
                "Transfers whose non-failed legs don't balance out"
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-exc-nonzero-count",
                            DS_AR_NON_ZERO_TRANSFERS,
                            "transfer_id",
                        )
                    ],
                ),
            ),
        )
    )

    table_parent_drift = Visual(
        TableVisual=TableVisual(
            VisualId="ar-exc-parent-drift-table",
            Title=_title("Parent Balance Drift"),
            Subtitle=_subtitle(
                "Parent-account days where stored parent balance disagrees "
                "with the sum of its children's stored balances. Left-click "
                "parent_account_id to drill into Balances with the child "
                "table filtered to that parent's children."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("ar-exc-pdrift-parent-id",
                                         DS_AR_PARENT_BALANCE_DRIFT,
                                         "parent_account_id"),
                            _unagg_field("ar-exc-pdrift-parent",
                                         DS_AR_PARENT_BALANCE_DRIFT,
                                         "parent_name"),
                            _unagg_field("ar-exc-pdrift-scope",
                                         DS_AR_PARENT_BALANCE_DRIFT, "scope"),
                            _unagg_field("ar-exc-pdrift-date",
                                         DS_AR_PARENT_BALANCE_DRIFT,
                                         "balance_date"),
                            _unagg_field("ar-exc-pdrift-stored",
                                         DS_AR_PARENT_BALANCE_DRIFT,
                                         "stored_balance"),
                            _unagg_field("ar-exc-pdrift-computed",
                                         DS_AR_PARENT_BALANCE_DRIFT,
                                         "computed_balance"),
                            _unagg_field("ar-exc-pdrift-amt",
                                         DS_AR_PARENT_BALANCE_DRIFT, "drift"),
                        ],
                    )
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "ar-exc-pdrift-date",
                                "Direction": "DESC",
                            },
                        },
                    ],
                },
            ),
            Actions=[
                _drill_down_action(
                    "action-ar-exc-parent-to-balances",
                    "View Child Balances",
                    SHEET_AR_BALANCES,
                    P_AR_PARENT,
                    "ar-exc-pdrift-parent-id",
                ),
            ],
            ConditionalFormatting={
                "ConditionalFormattingOptions": [
                    link_text_format(
                        "ar-exc-pdrift-parent-id",
                        "parent_account_id",
                        link_color,
                    ),
                ],
            },
        )
    )

    table_child_drift = Visual(
        TableVisual=TableVisual(
            VisualId="ar-exc-child-drift-table",
            Title=_title("Child Balance Drift"),
            Subtitle=_subtitle(
                "Child-account days where stored child balance disagrees "
                "with the running sum of posted transactions. Left-click an "
                "account_id to drill into Transactions for that account."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("ar-exc-cdrift-account-id",
                                         DS_AR_ACCOUNT_BALANCE_DRIFT,
                                         "account_id"),
                            _unagg_field("ar-exc-cdrift-account",
                                         DS_AR_ACCOUNT_BALANCE_DRIFT,
                                         "account_name"),
                            _unagg_field("ar-exc-cdrift-parent",
                                         DS_AR_ACCOUNT_BALANCE_DRIFT,
                                         "parent_name"),
                            _unagg_field("ar-exc-cdrift-scope",
                                         DS_AR_ACCOUNT_BALANCE_DRIFT,
                                         "scope"),
                            _unagg_field("ar-exc-cdrift-date",
                                         DS_AR_ACCOUNT_BALANCE_DRIFT,
                                         "balance_date"),
                            _unagg_field("ar-exc-cdrift-stored",
                                         DS_AR_ACCOUNT_BALANCE_DRIFT,
                                         "stored_balance"),
                            _unagg_field("ar-exc-cdrift-computed",
                                         DS_AR_ACCOUNT_BALANCE_DRIFT,
                                         "computed_balance"),
                            _unagg_field("ar-exc-cdrift-amt",
                                         DS_AR_ACCOUNT_BALANCE_DRIFT,
                                         "drift"),
                        ],
                    )
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "ar-exc-cdrift-date",
                                "Direction": "DESC",
                            },
                        },
                    ],
                },
            ),
            Actions=[
                _drill_down_action(
                    "action-ar-exc-child-to-txn",
                    "View Transactions",
                    SHEET_AR_TRANSACTIONS,
                    P_AR_ACCOUNT,
                    "ar-exc-cdrift-account-id",
                ),
            ],
            ConditionalFormatting={
                "ConditionalFormattingOptions": [
                    link_text_format(
                        "ar-exc-cdrift-account-id",
                        "account_id",
                        link_color,
                    ),
                ],
            },
        )
    )

    table_non_zero = Visual(
        TableVisual=TableVisual(
            VisualId="ar-exc-nonzero-table",
            Title=_title("Non-Zero Transfers"),
            Subtitle=_subtitle(
                "Transfers where the sum of non-failed legs is not zero. "
                "Left-click a transfer_id to drill into Transactions for "
                "that transfer."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("ar-exc-nz-id",
                                         DS_AR_NON_ZERO_TRANSFERS,
                                         "transfer_id"),
                            _unagg_field("ar-exc-nz-posted",
                                         DS_AR_NON_ZERO_TRANSFERS,
                                         "first_posted_at"),
                            _unagg_field("ar-exc-nz-debit",
                                         DS_AR_NON_ZERO_TRANSFERS,
                                         "total_debit"),
                            _unagg_field("ar-exc-nz-credit",
                                         DS_AR_NON_ZERO_TRANSFERS,
                                         "total_credit"),
                            _unagg_field("ar-exc-nz-net",
                                         DS_AR_NON_ZERO_TRANSFERS,
                                         "net_amount"),
                            _unagg_field("ar-exc-nz-failed",
                                         DS_AR_NON_ZERO_TRANSFERS,
                                         "failed_leg_count"),
                            _unagg_field("ar-exc-nz-memo",
                                         DS_AR_NON_ZERO_TRANSFERS, "memo"),
                        ],
                    )
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "ar-exc-nz-posted",
                                "Direction": "DESC",
                            },
                        },
                    ],
                },
            ),
            Actions=[
                _drill_down_action(
                    "action-ar-exc-nonzero-to-txn",
                    "View Transactions",
                    SHEET_AR_TRANSACTIONS,
                    P_AR_TRANSFER,
                    "ar-exc-nz-id",
                ),
            ],
            ConditionalFormatting={
                "ConditionalFormattingOptions": [
                    link_text_format(
                        "ar-exc-nz-id", "transfer_id", link_color,
                    ),
                ],
            },
        )
    )

    # Two timelines — one per drift feed. Two independent feeds (parent
    # upstream vs child upstream) so the side-by-side plot makes which
    # feed went off the rails visually legible.
    timeline_parent = Visual(
        BarChartVisual=BarChartVisual(
            VisualId="ar-exc-parent-drift-timeline",
            Title=_title("Parent Drift Timeline"),
            Subtitle=_subtitle(
                "Total parent-drift amount per day — stored parent balance "
                "minus Σ of its children's stored balances. Tall bars mark "
                "days the parent feed was out of step with its children."
            ),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[_date_dim("ar-exc-ptimeline-dim",
                                            DS_AR_PARENT_BALANCE_DRIFT,
                                            "balance_date")],
                        Values=[_measure_sum(
                            "ar-exc-ptimeline-drift",
                            DS_AR_PARENT_BALANCE_DRIFT, "drift",
                        )],
                    )
                ),
                Orientation="VERTICAL",
                BarsArrangement="CLUSTERED",
                CategoryLabelOptions=_axis_label("Date"),
                ValueLabelOptions=_axis_label("Total Drift ($)"),
            ),
        )
    )

    timeline_child = Visual(
        BarChartVisual=BarChartVisual(
            VisualId="ar-exc-child-drift-timeline",
            Title=_title("Child Drift Timeline"),
            Subtitle=_subtitle(
                "Total child-drift amount per day — stored child balance "
                "minus running Σ of posted transactions. Tall bars mark "
                "days child balances diverged most from the ledger."
            ),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[_date_dim("ar-exc-ctimeline-dim",
                                            DS_AR_ACCOUNT_BALANCE_DRIFT,
                                            "balance_date")],
                        Values=[_measure_sum(
                            "ar-exc-ctimeline-drift",
                            DS_AR_ACCOUNT_BALANCE_DRIFT, "drift",
                        )],
                    )
                ),
                Orientation="VERTICAL",
                BarsArrangement="CLUSTERED",
                CategoryLabelOptions=_axis_label("Date"),
                ValueLabelOptions=_axis_label("Total Drift ($)"),
            ),
        )
    )

    return [
        kpi_parent_drift, kpi_child_drift, kpi_nonzero,
        table_parent_drift, table_child_drift, table_non_zero,
        timeline_parent, timeline_child,
    ]
