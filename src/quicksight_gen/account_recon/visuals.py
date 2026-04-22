"""Visual builders for Account Recon.

Phase 4 expands the skeleton from Phase 3:

Drill-downs (pattern mirrors payment_recon):
  * Balances ledger row (right-click) → filters sub-ledger table on same
    sheet to that ledger's sub-ledgers via ``pArLedgerAccountId``.
  * Balances sub-ledger row (left-click) → Transactions filtered by
    sub-ledger account.
  * Transfers row (left-click) → Transactions filtered by transfer_id.
  * Exceptions ledger-drift (left-click) → Balances, sub-ledger table
    filtered by ledger.
  * Exceptions sub-ledger-drift (left-click) → Transactions filtered by
    sub-ledger account.
  * Exceptions non-zero-transfer (left-click) → Transactions filtered by
    transfer_id.

Same-sheet chart-filter actions on every new chart so clicking a bar
filters the detail table on the same sheet (matches payment_recon).

Visual additions:
  * Ledger Drift Timeline on Exceptions (alongside the existing sub-ledger
    timeline — two feeds, two lines).
  * Transfer Status bar chart on Transfers.
  * Transactions-by-day grouped bar chart on Transactions.
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
    DateMeasureField,
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


def _measure_date_count(
    field_id: str, ds: str, col_name: str,
) -> MeasureField:
    """COUNT aggregation over a DATETIME column.

    QuickSight rejects ``CategoricalMeasureField`` on DATETIME columns
    (those require ``DateMeasureField`` with the same COUNT/DISTINCT_COUNT
    aggregations).
    """
    return MeasureField(
        DateMeasureField=DateMeasureField(
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
P_AR_SUBLEDGER = "pArSubledgerAccountId"
P_AR_LEDGER = "pArLedgerAccountId"
P_AR_TRANSFER = "pArTransferId"
P_AR_ACTIVITY_DATE = "pArActivityDate"
P_AR_TRANSFER_TYPE = "pArTransferType"
P_AR_ACCOUNT = "pArAccountId"


def _multi_drill_action(
    action_id: str,
    name: str,
    target_sheet: str,
    param_sources: list[tuple[str, str]],
    trigger: str = "DATA_POINT_CLICK",
) -> VisualCustomAction:
    """Navigate to another sheet and set several drill-down parameters.

    Each entry in ``param_sources`` is ``(destination_parameter, source_field_id)``
    and emits one ParameterValueConfiguration.
    """
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
                        }
                        for param_name, source_field_id in param_sources
                    ],
                ),
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Balances tab — ledger + sub-ledger drift tables with drill-downs
# ---------------------------------------------------------------------------

def build_balances_visuals(link_color: str, link_tint: str) -> list[Visual]:
    kpi_ledgers = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-balances-kpi-ledgers",
            Title=_title("Ledger Accounts"),
            Subtitle=_subtitle("Count of ledger accounts (internal + external)"),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-balances-ledger-count",
                            DS_AR_LEDGER_ACCOUNTS,
                            "ledger_account_id",
                        )
                    ],
                ),
            ),
        )
    )

    kpi_subledgers = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-balances-kpi-subledgers",
            Title=_title("Sub-Ledger Accounts"),
            Subtitle=_subtitle(
                "Count of individual sub-ledger accounts under all ledgers"
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-balances-subledger-count",
                            DS_AR_SUBLEDGER_ACCOUNTS,
                            "subledger_account_id",
                        )
                    ],
                ),
            ),
        )
    )

    table_ledgers = Visual(
        TableVisual=TableVisual(
            VisualId="ar-balances-ledger-table",
            Title=_title("Ledger Account Balances"),
            Subtitle=_subtitle(
                "Each ledger account's stored vs computed daily balance. "
                "Computed = Σ of its sub-ledgers' stored balances. "
                "Right-click a ledger_account_id to filter the sub-ledger "
                "table below to that ledger's sub-ledgers."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("ar-bal-ledger-id",
                                         DS_AR_LEDGER_BALANCE_DRIFT,
                                         "ledger_account_id"),
                            _unagg_field("ar-bal-ledger-name",
                                         DS_AR_LEDGER_BALANCE_DRIFT,
                                         "ledger_name"),
                            _unagg_field("ar-bal-scope",
                                         DS_AR_LEDGER_BALANCE_DRIFT, "scope"),
                            _unagg_field("ar-bal-date",
                                         DS_AR_LEDGER_BALANCE_DRIFT,
                                         "balance_date"),
                            _unagg_field("ar-bal-stored",
                                         DS_AR_LEDGER_BALANCE_DRIFT,
                                         "stored_balance"),
                            _unagg_field("ar-bal-computed",
                                         DS_AR_LEDGER_BALANCE_DRIFT,
                                         "computed_balance"),
                            _unagg_field("ar-bal-drift",
                                         DS_AR_LEDGER_BALANCE_DRIFT, "drift"),
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
                # filter group ``fg-ar-drill-ledger-on-balances-subledger`` is
                # scoped to the sub-ledger table only via SELECTED_VISUALS, so
                # setting the parameter filters just that visual.
                _drill_down_action(
                    "action-ar-balances-filter-subledgers",
                    "Filter Sub-Ledger Accounts Below",
                    SHEET_AR_BALANCES,
                    P_AR_LEDGER,
                    "ar-bal-ledger-id",
                    trigger="DATA_POINT_MENU",
                ),
            ],
            ConditionalFormatting={
                "ConditionalFormattingOptions": [
                    menu_link_text_format(
                        "ar-bal-ledger-id",
                        "ledger_account_id",
                        link_color,
                        link_tint,
                    ),
                ],
            },
        )
    )

    table_subledgers = Visual(
        TableVisual=TableVisual(
            VisualId="ar-balances-subledger-table",
            Title=_title("Sub-Ledger Account Balances"),
            Subtitle=_subtitle(
                "Each sub-ledger account's stored vs computed daily balance. "
                "Computed = running Σ of posted transactions. Left-click a "
                "subledger_account_id to drill left into Transactions for "
                "that sub-ledger; right-click to drill right into the Daily "
                "Statement for that account-day."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("ar-bal-subledger-id",
                                         DS_AR_SUBLEDGER_BALANCE_DRIFT,
                                         "subledger_account_id"),
                            _unagg_field("ar-bal-subledger-name",
                                         DS_AR_SUBLEDGER_BALANCE_DRIFT,
                                         "subledger_name"),
                            _unagg_field("ar-bal-subledger-ledger",
                                         DS_AR_SUBLEDGER_BALANCE_DRIFT,
                                         "ledger_name"),
                            _unagg_field("ar-bal-subledger-scope",
                                         DS_AR_SUBLEDGER_BALANCE_DRIFT, "scope"),
                            _unagg_field("ar-bal-subledger-date",
                                         DS_AR_SUBLEDGER_BALANCE_DRIFT,
                                         "balance_date"),
                            _unagg_field("ar-bal-subledger-stored",
                                         DS_AR_SUBLEDGER_BALANCE_DRIFT,
                                         "stored_balance"),
                            _unagg_field("ar-bal-subledger-computed",
                                         DS_AR_SUBLEDGER_BALANCE_DRIFT,
                                         "computed_balance"),
                            _unagg_field("ar-bal-subledger-drift",
                                         DS_AR_SUBLEDGER_BALANCE_DRIFT,
                                         "drift"),
                        ],
                    )
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "ar-bal-subledger-date",
                                "Direction": "DESC",
                            },
                        },
                    ],
                },
            ),
            Actions=[
                _drill_down_action(
                    "action-ar-balances-subledger-to-txn",
                    "View Transactions",
                    SHEET_AR_TRANSACTIONS,
                    P_AR_SUBLEDGER,
                    "ar-bal-subledger-id",
                ),
                _multi_drill_action(
                    "action-ar-balances-subledger-to-daily-statement",
                    "View Daily Statement",
                    SHEET_AR_DAILY_STATEMENT,
                    [
                        ("pArDsAccountId", "ar-bal-subledger-id"),
                        ("pArDsBalanceDate", "ar-bal-subledger-date"),
                    ],
                    trigger="DATA_POINT_MENU",
                ),
            ],
            ConditionalFormatting={
                "ConditionalFormattingOptions": [
                    menu_link_text_format(
                        "ar-bal-subledger-id",
                        "subledger_account_id",
                        link_color,
                        link_tint,
                    ),
                ],
            },
        )
    )

    return [kpi_ledgers, kpi_subledgers, table_ledgers, table_subledgers]


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
                            _unagg_field("ar-txn-ledger",
                                         DS_AR_TRANSACTIONS,
                                         "ledger_name"),
                            _unagg_field("ar-txn-subledger",
                                         DS_AR_TRANSACTIONS,
                                         "subledger_name"),
                            _unagg_field("ar-txn-scope",
                                         DS_AR_TRANSACTIONS, "scope"),
                            _unagg_field("ar-txn-posting-level",
                                         DS_AR_TRANSACTIONS,
                                         "posting_level"),
                            _unagg_field("ar-txn-origin",
                                         DS_AR_TRANSACTIONS, "origin"),
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

    return [
        kpi_txn_count, kpi_failed, bar_by_status, bar_by_day, table_txn,
    ]


# ---------------------------------------------------------------------------
# Daily Statement tab — per-(account, day) feed-validation artifact
# ---------------------------------------------------------------------------

def build_daily_statement_visuals() -> list[Visual]:
    """Per-account daily statement sheet.

    Users pick one account and one day via sheet-level filter controls;
    the five KPIs + transaction table narrow to that slice. Summary
    columns are per-row constants after the filter resolves, so SUM is
    just "read the single row's value" — cheapest aggregation that
    QuickSight renders on a KPI visual.
    """

    kpi_opening = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-ds-kpi-opening",
            Title=_title("Opening Balance"),
            Subtitle=_subtitle(
                "Stored end-of-day balance on the prior business day — "
                "the starting point the day's posting activity walks from"
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_sum(
                            "ar-ds-opening-val",
                            DS_AR_DAILY_STATEMENT_SUMMARY,
                            "opening_balance",
                        )
                    ],
                ),
            ),
        )
    )

    kpi_debits = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-ds-kpi-debits",
            Title=_title("Total Debits"),
            Subtitle=_subtitle(
                "Sum of positive signed_amount legs posted on the day "
                "(non-failed). Matches the Dr column on a statement."
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_sum(
                            "ar-ds-debits-val",
                            DS_AR_DAILY_STATEMENT_SUMMARY,
                            "total_debits",
                        )
                    ],
                ),
            ),
        )
    )

    kpi_credits = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-ds-kpi-credits",
            Title=_title("Total Credits"),
            Subtitle=_subtitle(
                "Sum of negative signed_amount legs posted on the day "
                "(absolute value, non-failed). Matches the Cr column."
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_sum(
                            "ar-ds-credits-val",
                            DS_AR_DAILY_STATEMENT_SUMMARY,
                            "total_credits",
                        )
                    ],
                ),
            ),
        )
    )

    kpi_closing = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-ds-kpi-closing",
            Title=_title("Closing Balance (Stored)"),
            Subtitle=_subtitle(
                "Stored end-of-day balance from daily_balances — what "
                "the feed asserts the account ended the day at"
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_sum(
                            "ar-ds-closing-val",
                            DS_AR_DAILY_STATEMENT_SUMMARY,
                            "closing_balance_stored",
                        )
                    ],
                ),
            ),
        )
    )

    kpi_drift = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-ds-kpi-drift",
            Title=_title("Drift"),
            Subtitle=_subtitle(
                "Stored closing − (opening + Σ signed legs). Zero on a "
                "clean feed; any non-zero value means the feed's balance "
                "doesn't match its own posting activity."
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_sum(
                            "ar-ds-drift-val",
                            DS_AR_DAILY_STATEMENT_SUMMARY,
                            "drift",
                        )
                    ],
                ),
            ),
        )
    )

    transactions_table = Visual(
        TableVisual=TableVisual(
            VisualId="ar-ds-transactions-table",
            Title=_title("Transaction Detail"),
            Subtitle=_subtitle(
                "Every leg posted to the selected account on the selected "
                "day. counter_account_name shows the other side(s) of each "
                "transfer — the offsetting legs keyed against this account."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("ar-ds-txn-posted-at",
                                         DS_AR_DAILY_STATEMENT_TRANSACTIONS,
                                         "posted_at"),
                            _unagg_field("ar-ds-txn-type",
                                         DS_AR_DAILY_STATEMENT_TRANSACTIONS,
                                         "transfer_type"),
                            _unagg_field("ar-ds-txn-origin",
                                         DS_AR_DAILY_STATEMENT_TRANSACTIONS,
                                         "origin"),
                            _unagg_field("ar-ds-txn-direction",
                                         DS_AR_DAILY_STATEMENT_TRANSACTIONS,
                                         "direction"),
                            _unagg_field("ar-ds-txn-signed-amount",
                                         DS_AR_DAILY_STATEMENT_TRANSACTIONS,
                                         "signed_amount"),
                            _unagg_field("ar-ds-txn-counter",
                                         DS_AR_DAILY_STATEMENT_TRANSACTIONS,
                                         "counter_account_name"),
                            _unagg_field("ar-ds-txn-transfer-id",
                                         DS_AR_DAILY_STATEMENT_TRANSACTIONS,
                                         "transfer_id"),
                            _unagg_field("ar-ds-txn-status",
                                         DS_AR_DAILY_STATEMENT_TRANSACTIONS,
                                         "status"),
                            _unagg_field("ar-ds-txn-memo",
                                         DS_AR_DAILY_STATEMENT_TRANSACTIONS,
                                         "memo"),
                        ],
                    )
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "ar-ds-txn-posted-at",
                                "Direction": "ASC",
                            },
                        },
                    ],
                },
            ),
        )
    )

    return [
        kpi_opening,
        kpi_debits,
        kpi_credits,
        kpi_closing,
        kpi_drift,
        transactions_table,
    ]


# ---------------------------------------------------------------------------
# Today's Exceptions tab (Phase K.1.2) — unified exceptions table
# ---------------------------------------------------------------------------

def build_todays_exceptions_visuals(
    link_color: str, link_tint: str,
) -> list[Visual]:
    """KPI + breakdown bar + unified exceptions table.

    The legacy Exceptions sheet bundles 14 separate per-check blocks; this
    sheet replaces them with one harmonized view fed by the
    ``ar_unified_exceptions`` dataset (UNION ALL across the 14 underlying
    exception views). The bar chart on top shows count per check_type
    coloured by severity, providing the "14 count tiles" affordance from
    K.1.2 in a single visual that QuickSight's grid actually renders well.
    Click a bar to filter the table to that check_type; click a row in the
    table to drill into Transactions for that transfer_id (left-click) or
    that account-day slice (right-click). The two system-level drift checks
    (``concentration_master_sweep_drift``, ``gl_vs_fed_master_drift``)
    don't carry either, so they remain visible but un-drillable.
    """
    kpi_total = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-todays-exc-kpi-total",
            Title=_title("Total Exceptions"),
            Subtitle=_subtitle(
                "Count of open exception rows across all 14 reconciliation "
                "checks. Use the breakdown below to triage by check type "
                "and severity."
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-todays-exc-total-count",
                            DS_AR_UNIFIED_EXCEPTIONS,
                            "check_type",
                        )
                    ],
                ),
            ),
        )
    )

    breakdown_bar = Visual(
        BarChartVisual=BarChartVisual(
            VisualId="ar-todays-exc-breakdown",
            Title=_title("Exceptions by Check"),
            Subtitle=_subtitle(
                "Count of open exceptions per check type, coloured by "
                "severity (red = drift / overdraft, orange = expected-zero, "
                "amber = limit-breach, yellow = other). Click a bar to "
                "filter the table below to that check type."
            ),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[_dim("ar-todays-exc-check-dim",
                                       DS_AR_UNIFIED_EXCEPTIONS,
                                       "check_type")],
                        Values=[_measure_count(
                            "ar-todays-exc-check-count",
                            DS_AR_UNIFIED_EXCEPTIONS,
                            "check_type",
                        )],
                        Colors=[_dim("ar-todays-exc-severity-color",
                                     DS_AR_UNIFIED_EXCEPTIONS,
                                     "severity")],
                    )
                ),
                Orientation="HORIZONTAL",
                BarsArrangement="STACKED",
                CategoryLabelOptions=_axis_label("Check"),
                ValueLabelOptions=_axis_label("Exceptions"),
                ColorLabelOptions=_axis_label("Severity"),
            ),
            Actions=[
                _same_sheet_filter_action(
                    "action-ar-todays-exc-bar-filter",
                    "Filter Exceptions Table",
                    ["ar-todays-exc-table"],
                ),
            ],
        )
    )

    unified_table = Visual(
        TableVisual=TableVisual(
            VisualId="ar-todays-exc-table",
            Title=_title("Open Exceptions"),
            Subtitle=_subtitle(
                "Every open exception row across all 14 checks, sorted by "
                "severity then aging. Left-click a transfer_id to drill into "
                "Transactions for that transfer; right-click an account_id "
                "to drill into Transactions for that account-day. The two "
                "system-level drift rollups (concentration master sweep, GL "
                "vs Fed master) carry neither value — investigate them on "
                "the Trends sheet."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("ar-todays-exc-check",
                                         DS_AR_UNIFIED_EXCEPTIONS,
                                         "check_type"),
                            _unagg_field("ar-todays-exc-severity",
                                         DS_AR_UNIFIED_EXCEPTIONS,
                                         "severity"),
                            # K.2: bind the FieldId to the YYYY-MM-DD
                            # string projection (not the DATETIME
                            # exception_date) so the drill SourceField
                            # writes pArActivityDate in a format the
                            # destination's posted_date filter can match.
                            _unagg_field("ar-todays-exc-date",
                                         DS_AR_UNIFIED_EXCEPTIONS,
                                         "exception_date_str"),
                            _unagg_field("ar-todays-exc-age",
                                         DS_AR_UNIFIED_EXCEPTIONS,
                                         "aging_bucket"),
                            _unagg_field("ar-todays-exc-days",
                                         DS_AR_UNIFIED_EXCEPTIONS,
                                         "days_outstanding"),
                            _unagg_field("ar-todays-exc-account",
                                         DS_AR_UNIFIED_EXCEPTIONS,
                                         "account_id"),
                            _unagg_field("ar-todays-exc-account-name",
                                         DS_AR_UNIFIED_EXCEPTIONS,
                                         "account_name"),
                            _unagg_field("ar-todays-exc-account-level",
                                         DS_AR_UNIFIED_EXCEPTIONS,
                                         "account_level"),
                            _unagg_field("ar-todays-exc-ledger",
                                         DS_AR_UNIFIED_EXCEPTIONS,
                                         "ledger_name"),
                            _unagg_field("ar-todays-exc-transfer-id",
                                         DS_AR_UNIFIED_EXCEPTIONS,
                                         "transfer_id"),
                            _unagg_field("ar-todays-exc-transfer-type",
                                         DS_AR_UNIFIED_EXCEPTIONS,
                                         "transfer_type"),
                            _unagg_field("ar-todays-exc-primary",
                                         DS_AR_UNIFIED_EXCEPTIONS,
                                         "primary_amount"),
                            _unagg_field("ar-todays-exc-secondary",
                                         DS_AR_UNIFIED_EXCEPTIONS,
                                         "secondary_amount"),
                        ],
                    )
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "ar-todays-exc-severity",
                                "Direction": "ASC",
                            },
                        },
                        {
                            "FieldSort": {
                                "FieldId": "ar-todays-exc-days",
                                "Direction": "DESC",
                            },
                        },
                    ],
                },
            ),
            Actions=[
                _drill_down_action(
                    "action-ar-todays-exc-to-txn",
                    "View Transactions",
                    SHEET_AR_TRANSACTIONS,
                    P_AR_TRANSFER,
                    "ar-todays-exc-transfer-id",
                ),
                # K.2 spike validation (a): focused test of the
                # SetParametersOperation code path with the calc-field
                # destination filter. This drill writes:
                #   - account, date via SourceField (required for drill
                #     semantics — these stay parameter-bound on the
                #     destination for now)
                #   - pArTransferId via IncludeNullValue+empty (the only
                #     destination filter that has been rewired to the
                #     calc-field PASS shape; we test that an empty write
                #     here propagates as ALL on Transactions).
                # If validation passes, extend the calc-field shape to
                # the other destination filters and add their empty
                # writes here too.
                VisualCustomAction(
                    CustomActionId="action-ar-todays-exc-to-txn-by-account",
                    Name="View Transactions for Account-Day",
                    Trigger="DATA_POINT_MENU",
                    ActionOperations=[
                        VisualCustomActionOperation(
                            NavigationOperation=CustomActionNavigationOperation(
                                LocalNavigationConfiguration=LocalNavigationConfiguration(
                                    TargetSheetId=SHEET_AR_TRANSACTIONS,
                                ),
                            ),
                        ),
                        VisualCustomActionOperation(
                            SetParametersOperation=CustomActionSetParametersOperation(
                                ParameterValueConfigurations=[
                                    {
                                        "DestinationParameterName": P_AR_ACCOUNT,
                                        "Value": {"SourceField": "ar-todays-exc-account"},
                                    },
                                    {
                                        "DestinationParameterName": P_AR_ACTIVITY_DATE,
                                        "Value": {"SourceField": "ar-todays-exc-date"},
                                    },
                                    {
                                        # K.2 sentinel reset — write
                                        # "__ALL__" to clear any
                                        # prior pArTransferId value.
                                        # The destination calc-field
                                        # filter recognizes the
                                        # sentinel and lets every row
                                        # pass. Both empty-string and
                                        # IncludeNullValue:True+empty
                                        # were tried first via this
                                        # same drill and produced 0
                                        # rows on Transactions (drill-
                                        # action code path delivers
                                        # them as something the calc
                                        # field can't simplify to "no
                                        # filter").
                                        "DestinationParameterName": P_AR_TRANSFER,
                                        "Value": {
                                            "CustomValuesConfiguration": {
                                                "CustomValues": {
                                                    "StringValues": ["__ALL__"],
                                                },
                                            },
                                        },
                                    },
                                ],
                            ),
                        ),
                    ],
                ),
            ],
            ConditionalFormatting={
                "ConditionalFormattingOptions": [
                    link_text_format(
                        "ar-todays-exc-transfer-id",
                        "transfer_id",
                        link_color,
                    ),
                    menu_link_text_format(
                        "ar-todays-exc-account",
                        "account_id",
                        link_color,
                        link_tint,
                    ),
                ],
            },
        )
    )

    return [kpi_total, breakdown_bar, unified_table]


# ---------------------------------------------------------------------------
# Exceptions Trends tab (Phase K.1.3) — cross-check rollups + aging matrix
# + per-check daily trend lines, all derived from the unified-exceptions
# dataset where applicable, with the rollup datasets feeding the same-shape
# aggregations they always did.
# ---------------------------------------------------------------------------

def build_exceptions_trends_visuals() -> list[Visual]:
    """Trend / rollup view paired with Today's Exceptions.

    Layout (top → bottom):
      * Drift Timelines rollup (overlay of CMS + GL/Fed drift series).
      * Two-Sided Post Mismatch rollup (KPI + table).
      * Accounts Expected Zero at EOD rollup (KPI + table).
      * Aging matrix — count of unified exceptions per (aging bucket,
        check type), so the eye picks up which checks accumulate stale
        rows.
      * Per-check daily trend — count of unified exceptions per day,
        coloured by check type, so spikes line up across checks.
    """
    timeline_drift_rollup = Visual(
        BarChartVisual=BarChartVisual(
            VisualId="ar-exc-drift-timelines-rollup",
            Title=_title("Balance Drift Timelines"),
            Subtitle=_subtitle(
                "Per-day drift from Concentration Master sweep and GL vs "
                "Fed Master on one shared axis. Healthy days = 0; "
                "clustered bars = days a feed diverged."
            ),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[_date_dim(
                            "ar-exc-drift-rollup-dim",
                            DS_AR_BALANCE_DRIFT_TIMELINES_ROLLUP,
                            "drift_date",
                        )],
                        Values=[_measure_sum(
                            "ar-exc-drift-rollup-val",
                            DS_AR_BALANCE_DRIFT_TIMELINES_ROLLUP,
                            "drift",
                        )],
                        Colors=[_dim(
                            "ar-exc-drift-rollup-color",
                            DS_AR_BALANCE_DRIFT_TIMELINES_ROLLUP,
                            "source_check",
                        )],
                    )
                ),
                Orientation="VERTICAL",
                BarsArrangement="CLUSTERED",
                CategoryLabelOptions=_axis_label("Date"),
                ValueLabelOptions=_axis_label("Drift ($)"),
                ColorLabelOptions=_axis_label("Source"),
            ),
        )
    )

    kpi_two_sided_rollup = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-exc-kpi-two-sided-rollup",
            Title=_title("Two-Sided Post Mismatch"),
            Subtitle=_subtitle(
                "Total findings where one side of an expected SNB/Fed "
                "post pair landed but the other side never did"
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-exc-two-sided-rollup-count",
                            DS_AR_TWO_SIDED_POST_MISMATCH_ROLLUP,
                            "transfer_id",
                        )
                    ],
                ),
            ),
        )
    )

    table_two_sided_rollup = Visual(
        TableVisual=TableVisual(
            VisualId="ar-exc-two-sided-rollup-table",
            Title=_title("Two-Sided Post Mismatch"),
            Subtitle=_subtitle(
                "Each row is a transfer where the side_present leg posted "
                "but side_missing never did. source_check identifies the "
                "detection rule; ordered oldest-first by aging."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("ar-exc-tsr-xfer-id",
                                         DS_AR_TWO_SIDED_POST_MISMATCH_ROLLUP,
                                         "transfer_id"),
                            _unagg_field("ar-exc-tsr-observed-at",
                                         DS_AR_TWO_SIDED_POST_MISMATCH_ROLLUP,
                                         "observed_at"),
                            _unagg_field("ar-exc-tsr-amount",
                                         DS_AR_TWO_SIDED_POST_MISMATCH_ROLLUP,
                                         "amount"),
                            _unagg_field("ar-exc-tsr-side-present",
                                         DS_AR_TWO_SIDED_POST_MISMATCH_ROLLUP,
                                         "side_present"),
                            _unagg_field("ar-exc-tsr-side-missing",
                                         DS_AR_TWO_SIDED_POST_MISMATCH_ROLLUP,
                                         "side_missing"),
                            _unagg_field("ar-exc-tsr-aging",
                                         DS_AR_TWO_SIDED_POST_MISMATCH_ROLLUP,
                                         "aging_bucket"),
                            _unagg_field("ar-exc-tsr-source",
                                         DS_AR_TWO_SIDED_POST_MISMATCH_ROLLUP,
                                         "source_check"),
                        ],
                    )
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "ar-exc-tsr-aging",
                                "Direction": "DESC",
                            },
                        },
                    ],
                },
            ),
        )
    )

    kpi_expected_zero_rollup = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-exc-kpi-expected-zero-rollup",
            Title=_title("Accounts Expected Zero at EOD"),
            Subtitle=_subtitle(
                "Total non-zero EOD findings across Sweep targets, ACH "
                "Origination Settlement, and Internal Transfer Suspense — "
                "same SHAPE: a control account that should be zero, isn't"
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-exc-expected-zero-rollup-count",
                            DS_AR_EXPECTED_ZERO_EOD_ROLLUP,
                            "account_id",
                        )
                    ],
                ),
            ),
        )
    )

    table_expected_zero_rollup = Visual(
        TableVisual=TableVisual(
            VisualId="ar-exc-expected-zero-rollup-table",
            Title=_title("Accounts Expected Zero at EOD"),
            Subtitle=_subtitle(
                "Every (account, date) where a control account ended day "
                "non-zero. source_check identifies which detection rule "
                "fired; ordered oldest-first by aging."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("ar-exc-ezr-acct-id",
                                         DS_AR_EXPECTED_ZERO_EOD_ROLLUP,
                                         "account_id"),
                            _unagg_field("ar-exc-ezr-acct-name",
                                         DS_AR_EXPECTED_ZERO_EOD_ROLLUP,
                                         "account_name"),
                            _unagg_field("ar-exc-ezr-level",
                                         DS_AR_EXPECTED_ZERO_EOD_ROLLUP,
                                         "account_level"),
                            _unagg_field("ar-exc-ezr-date",
                                         DS_AR_EXPECTED_ZERO_EOD_ROLLUP,
                                         "balance_date"),
                            _unagg_field("ar-exc-ezr-balance",
                                         DS_AR_EXPECTED_ZERO_EOD_ROLLUP,
                                         "stored_balance"),
                            _unagg_field("ar-exc-ezr-aging",
                                         DS_AR_EXPECTED_ZERO_EOD_ROLLUP,
                                         "aging_bucket"),
                            _unagg_field("ar-exc-ezr-source",
                                         DS_AR_EXPECTED_ZERO_EOD_ROLLUP,
                                         "source_check"),
                        ],
                    )
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "ar-exc-ezr-aging",
                                "Direction": "DESC",
                            },
                        },
                    ],
                },
            ),
        )
    )

    aging_matrix = Visual(
        BarChartVisual=BarChartVisual(
            VisualId="ar-exc-trends-aging-matrix",
            Title=_title("Aging by Check"),
            Subtitle=_subtitle(
                "Count of open exceptions per aging bucket, stacked by "
                "check type — concentration of stale (8-30, >30) bars "
                "marks checks that are falling behind."
            ),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[_dim("ar-exc-trends-aging-dim",
                                       DS_AR_UNIFIED_EXCEPTIONS,
                                       "aging_bucket")],
                        Values=[_measure_count(
                            "ar-exc-trends-aging-count",
                            DS_AR_UNIFIED_EXCEPTIONS,
                            "check_type",
                        )],
                        Colors=[_dim("ar-exc-trends-aging-color",
                                     DS_AR_UNIFIED_EXCEPTIONS,
                                     "check_type")],
                    )
                ),
                Orientation="HORIZONTAL",
                BarsArrangement="STACKED",
                CategoryLabelOptions=_axis_label("Aging Bucket"),
                ValueLabelOptions=_axis_label("Exceptions"),
                ColorLabelOptions=_axis_label("Check"),
            ),
        )
    )

    per_check_trend = Visual(
        BarChartVisual=BarChartVisual(
            VisualId="ar-exc-trends-per-check",
            Title=_title("Exceptions per Check, by Day"),
            Subtitle=_subtitle(
                "Daily count of open exception rows, stacked by check "
                "type. Use the date-range filter to widen or narrow the "
                "window; spikes that line up across checks usually point "
                "to a single upstream feed event."
            ),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[_date_dim("ar-exc-trends-perchk-dim",
                                            DS_AR_UNIFIED_EXCEPTIONS,
                                            "exception_date")],
                        Values=[_measure_count(
                            "ar-exc-trends-perchk-count",
                            DS_AR_UNIFIED_EXCEPTIONS,
                            "check_type",
                        )],
                        Colors=[_dim("ar-exc-trends-perchk-color",
                                     DS_AR_UNIFIED_EXCEPTIONS,
                                     "check_type")],
                    )
                ),
                Orientation="VERTICAL",
                BarsArrangement="STACKED",
                CategoryLabelOptions=_axis_label("Date"),
                ValueLabelOptions=_axis_label("Exceptions"),
                ColorLabelOptions=_axis_label("Check"),
            ),
        )
    )

    return [
        timeline_drift_rollup,
        kpi_two_sided_rollup,
        table_two_sided_rollup,
        kpi_expected_zero_rollup,
        table_expected_zero_rollup,
        aging_matrix,
        per_check_trend,
    ]
