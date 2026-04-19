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
    DS_AR_TRANSACTIONS,
    DS_AR_TRANSFER_SUMMARY,
    SHEET_AR_BALANCES,
    SHEET_AR_TRANSACTIONS,
)
from quicksight_gen.common.aging import aging_bar_visual
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
P_AR_SUBLEDGER = "pArSubledgerAccountId"
P_AR_LEDGER = "pArLedgerAccountId"
P_AR_TRANSFER = "pArTransferId"
P_AR_ACTIVITY_DATE = "pArActivityDate"
P_AR_TRANSFER_TYPE = "pArTransferType"


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
                "subledger_account_id to drill into Transactions for that "
                "sub-ledger."
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
            ],
            ConditionalFormatting={
                "ConditionalFormattingOptions": [
                    link_text_format(
                        "ar-bal-subledger-id", "subledger_account_id", link_color,
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

    return [kpi_txn_count, kpi_failed, bar_by_status, bar_by_day, table_txn]


# ---------------------------------------------------------------------------
# Exceptions tab — drift tables, non-zero, two timelines
# ---------------------------------------------------------------------------

def build_exceptions_visuals(link_color: str) -> list[Visual]:
    kpi_ledger_drift = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-exc-kpi-ledger-drift",
            Title=_title("Ledger Drift Days"),
            Subtitle=_subtitle(
                "Count of (ledger, date) combinations where stored ledger "
                "balance ≠ Σ of its sub-ledgers' stored balances"
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-exc-ledger-drift-count",
                            DS_AR_LEDGER_BALANCE_DRIFT,
                            "ledger_account_id",
                        )
                    ],
                ),
            ),
        )
    )

    kpi_subledger_drift = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-exc-kpi-subledger-drift",
            Title=_title("Sub-Ledger Drift Days"),
            Subtitle=_subtitle(
                "Count of (sub-ledger, date) combinations where stored "
                "sub-ledger balance ≠ running Σ of posted transactions"
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-exc-subledger-drift-count",
                            DS_AR_SUBLEDGER_BALANCE_DRIFT,
                            "subledger_account_id",
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

    table_ledger_drift = Visual(
        TableVisual=TableVisual(
            VisualId="ar-exc-ledger-drift-table",
            Title=_title("Ledger Balance Drift"),
            Subtitle=_subtitle(
                "Ledger-account days where stored ledger balance disagrees "
                "with the sum of its sub-ledgers' stored balances. "
                "Left-click ledger_account_id to drill into Balances with "
                "the sub-ledger table filtered to that ledger's sub-ledgers."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("ar-exc-ldrift-ledger-id",
                                         DS_AR_LEDGER_BALANCE_DRIFT,
                                         "ledger_account_id"),
                            _unagg_field("ar-exc-ldrift-ledger",
                                         DS_AR_LEDGER_BALANCE_DRIFT,
                                         "ledger_name"),
                            _unagg_field("ar-exc-ldrift-scope",
                                         DS_AR_LEDGER_BALANCE_DRIFT, "scope"),
                            _unagg_field("ar-exc-ldrift-date",
                                         DS_AR_LEDGER_BALANCE_DRIFT,
                                         "balance_date"),
                            _unagg_field("ar-exc-ldrift-stored",
                                         DS_AR_LEDGER_BALANCE_DRIFT,
                                         "stored_balance"),
                            _unagg_field("ar-exc-ldrift-computed",
                                         DS_AR_LEDGER_BALANCE_DRIFT,
                                         "computed_balance"),
                            _unagg_field("ar-exc-ldrift-amt",
                                         DS_AR_LEDGER_BALANCE_DRIFT, "drift"),
                            _unagg_field("ar-exc-ldrift-aging",
                                         DS_AR_LEDGER_BALANCE_DRIFT,
                                         "aging_bucket"),
                        ],
                    )
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "ar-exc-ldrift-date",
                                "Direction": "DESC",
                            },
                        },
                    ],
                },
            ),
            Actions=[
                _drill_down_action(
                    "action-ar-exc-ledger-to-balances",
                    "View Sub-Ledger Balances",
                    SHEET_AR_BALANCES,
                    P_AR_LEDGER,
                    "ar-exc-ldrift-ledger-id",
                ),
            ],
            ConditionalFormatting={
                "ConditionalFormattingOptions": [
                    link_text_format(
                        "ar-exc-ldrift-ledger-id",
                        "ledger_account_id",
                        link_color,
                    ),
                ],
            },
        )
    )

    table_subledger_drift = Visual(
        TableVisual=TableVisual(
            VisualId="ar-exc-subledger-drift-table",
            Title=_title("Sub-Ledger Balance Drift"),
            Subtitle=_subtitle(
                "Sub-ledger account days where stored sub-ledger balance "
                "disagrees with the running sum of posted transactions. "
                "Left-click a subledger_account_id to drill into "
                "Transactions for that sub-ledger."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("ar-exc-sdrift-subledger-id",
                                         DS_AR_SUBLEDGER_BALANCE_DRIFT,
                                         "subledger_account_id"),
                            _unagg_field("ar-exc-sdrift-subledger",
                                         DS_AR_SUBLEDGER_BALANCE_DRIFT,
                                         "subledger_name"),
                            _unagg_field("ar-exc-sdrift-ledger",
                                         DS_AR_SUBLEDGER_BALANCE_DRIFT,
                                         "ledger_name"),
                            _unagg_field("ar-exc-sdrift-scope",
                                         DS_AR_SUBLEDGER_BALANCE_DRIFT,
                                         "scope"),
                            _unagg_field("ar-exc-sdrift-date",
                                         DS_AR_SUBLEDGER_BALANCE_DRIFT,
                                         "balance_date"),
                            _unagg_field("ar-exc-sdrift-stored",
                                         DS_AR_SUBLEDGER_BALANCE_DRIFT,
                                         "stored_balance"),
                            _unagg_field("ar-exc-sdrift-computed",
                                         DS_AR_SUBLEDGER_BALANCE_DRIFT,
                                         "computed_balance"),
                            _unagg_field("ar-exc-sdrift-amt",
                                         DS_AR_SUBLEDGER_BALANCE_DRIFT,
                                         "drift"),
                            _unagg_field("ar-exc-sdrift-aging",
                                         DS_AR_SUBLEDGER_BALANCE_DRIFT,
                                         "aging_bucket"),
                        ],
                    )
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "ar-exc-sdrift-date",
                                "Direction": "DESC",
                            },
                        },
                    ],
                },
            ),
            Actions=[
                _drill_down_action(
                    "action-ar-exc-subledger-to-txn",
                    "View Transactions",
                    SHEET_AR_TRANSACTIONS,
                    P_AR_SUBLEDGER,
                    "ar-exc-sdrift-subledger-id",
                ),
            ],
            ConditionalFormatting={
                "ConditionalFormattingOptions": [
                    link_text_format(
                        "ar-exc-sdrift-subledger-id",
                        "subledger_account_id",
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
                            _unagg_field("ar-exc-nz-origin",
                                         DS_AR_NON_ZERO_TRANSFERS,
                                         "origin"),
                            _unagg_field("ar-exc-nz-aging",
                                         DS_AR_NON_ZERO_TRANSFERS,
                                         "aging_bucket"),
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

    # Two timelines — one per drift feed. Two independent feeds (ledger
    # upstream vs sub-ledger upstream) so the side-by-side plot makes which
    # feed went off the rails visually legible.
    timeline_ledger = Visual(
        BarChartVisual=BarChartVisual(
            VisualId="ar-exc-ledger-drift-timeline",
            Title=_title("Ledger Drift Timeline"),
            Subtitle=_subtitle(
                "Total ledger-drift amount per day — stored ledger balance "
                "minus Σ of its sub-ledgers' stored balances. Tall bars "
                "mark days the ledger feed was out of step with its "
                "sub-ledgers."
            ),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[_date_dim("ar-exc-ltimeline-dim",
                                            DS_AR_LEDGER_BALANCE_DRIFT,
                                            "balance_date")],
                        Values=[_measure_sum(
                            "ar-exc-ltimeline-drift",
                            DS_AR_LEDGER_BALANCE_DRIFT, "drift",
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

    timeline_subledger = Visual(
        BarChartVisual=BarChartVisual(
            VisualId="ar-exc-subledger-drift-timeline",
            Title=_title("Sub-Ledger Drift Timeline"),
            Subtitle=_subtitle(
                "Total sub-ledger drift amount per day — stored sub-ledger "
                "balance minus running Σ of posted transactions. Tall bars "
                "mark days sub-ledger balances diverged most from the "
                "ledger."
            ),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[_date_dim("ar-exc-stimeline-dim",
                                            DS_AR_SUBLEDGER_BALANCE_DRIFT,
                                            "balance_date")],
                        Values=[_measure_sum(
                            "ar-exc-stimeline-drift",
                            DS_AR_SUBLEDGER_BALANCE_DRIFT, "drift",
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

    kpi_breach = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-exc-kpi-breach",
            Title=_title("Limit Breach Days"),
            Subtitle=_subtitle(
                "Count of (sub-ledger, date, transfer_type) combinations "
                "where daily outbound exceeded the ledger's configured limit"
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-exc-breach-count",
                            DS_AR_LIMIT_BREACH,
                            "subledger_account_id",
                        )
                    ],
                ),
            ),
        )
    )

    kpi_overdraft = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-exc-kpi-overdraft",
            Title=_title("Overdraft Days"),
            Subtitle=_subtitle(
                "Count of (sub-ledger, date) cells where stored sub-ledger "
                "balance < 0"
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-exc-overdraft-count",
                            DS_AR_OVERDRAFT,
                            "subledger_account_id",
                        )
                    ],
                ),
            ),
        )
    )

    table_breach = Visual(
        TableVisual=TableVisual(
            VisualId="ar-exc-breach-table",
            Title=_title("Sub-Ledger Limit Breach"),
            Subtitle=_subtitle(
                "Days a sub-ledger account's outbound total for one "
                "transfer type exceeded the ledger's configured "
                "daily_limit. Left-click a subledger_account_id to drill "
                "into Transactions filtered by that sub-ledger, date, and "
                "transfer type."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("ar-exc-br-subledger-id",
                                         DS_AR_LIMIT_BREACH,
                                         "subledger_account_id"),
                            _unagg_field("ar-exc-br-subledger",
                                         DS_AR_LIMIT_BREACH,
                                         "subledger_name"),
                            _unagg_field("ar-exc-br-ledger",
                                         DS_AR_LIMIT_BREACH, "ledger_name"),
                            _unagg_field("ar-exc-br-date",
                                         DS_AR_LIMIT_BREACH, "activity_date"),
                            _unagg_field("ar-exc-br-date-str",
                                         DS_AR_LIMIT_BREACH,
                                         "activity_date_str"),
                            _unagg_field("ar-exc-br-type",
                                         DS_AR_LIMIT_BREACH, "transfer_type"),
                            _unagg_field("ar-exc-br-outbound",
                                         DS_AR_LIMIT_BREACH, "outbound_total"),
                            _unagg_field("ar-exc-br-limit",
                                         DS_AR_LIMIT_BREACH, "daily_limit"),
                            _unagg_field("ar-exc-br-overage",
                                         DS_AR_LIMIT_BREACH, "overage"),
                            _unagg_field("ar-exc-br-aging",
                                         DS_AR_LIMIT_BREACH, "aging_bucket"),
                        ],
                    )
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "ar-exc-br-date",
                                "Direction": "DESC",
                            },
                        },
                    ],
                },
            ),
            Actions=[
                _multi_drill_action(
                    "action-ar-exc-breach-to-txn",
                    "View Transactions",
                    SHEET_AR_TRANSACTIONS,
                    [
                        (P_AR_SUBLEDGER, "ar-exc-br-subledger-id"),
                        (P_AR_ACTIVITY_DATE, "ar-exc-br-date-str"),
                        (P_AR_TRANSFER_TYPE, "ar-exc-br-type"),
                    ],
                ),
            ],
            ConditionalFormatting={
                "ConditionalFormattingOptions": [
                    link_text_format(
                        "ar-exc-br-subledger-id", "subledger_account_id",
                        link_color,
                    ),
                ],
            },
        )
    )

    table_overdraft = Visual(
        TableVisual=TableVisual(
            VisualId="ar-exc-overdraft-table",
            Title=_title("Sub-Ledger Overdraft"),
            Subtitle=_subtitle(
                "Days a sub-ledger account's stored balance was negative. "
                "Left-click a subledger_account_id to drill into "
                "Transactions filtered by that sub-ledger and date."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("ar-exc-od-subledger-id",
                                         DS_AR_OVERDRAFT,
                                         "subledger_account_id"),
                            _unagg_field("ar-exc-od-subledger",
                                         DS_AR_OVERDRAFT, "subledger_name"),
                            _unagg_field("ar-exc-od-ledger",
                                         DS_AR_OVERDRAFT, "ledger_name"),
                            _unagg_field("ar-exc-od-date",
                                         DS_AR_OVERDRAFT, "balance_date"),
                            _unagg_field("ar-exc-od-date-str",
                                         DS_AR_OVERDRAFT, "balance_date_str"),
                            _unagg_field("ar-exc-od-stored",
                                         DS_AR_OVERDRAFT, "stored_balance"),
                            _unagg_field("ar-exc-od-aging",
                                         DS_AR_OVERDRAFT, "aging_bucket"),
                        ],
                    )
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "ar-exc-od-date",
                                "Direction": "DESC",
                            },
                        },
                    ],
                },
            ),
            Actions=[
                _multi_drill_action(
                    "action-ar-exc-overdraft-to-txn",
                    "View Transactions",
                    SHEET_AR_TRANSACTIONS,
                    [
                        (P_AR_SUBLEDGER, "ar-exc-od-subledger-id"),
                        (P_AR_ACTIVITY_DATE, "ar-exc-od-date-str"),
                    ],
                ),
            ],
            ConditionalFormatting={
                "ConditionalFormattingOptions": [
                    link_text_format(
                        "ar-exc-od-subledger-id", "subledger_account_id",
                        link_color,
                    ),
                ],
            },
        )
    )

    # Aging bar charts — one per exception check.
    aging_ledger_drift = aging_bar_visual(
        "ar-exc-aging-ledger-drift",
        "Ledger Drift by Age",
        "How long ledger drift rows have been outstanding",
        DS_AR_LEDGER_BALANCE_DRIFT,
        "ledger_account_id",
    )
    aging_subledger_drift = aging_bar_visual(
        "ar-exc-aging-subledger-drift",
        "Sub-Ledger Drift by Age",
        "How long sub-ledger drift rows have been outstanding",
        DS_AR_SUBLEDGER_BALANCE_DRIFT,
        "subledger_account_id",
    )
    aging_nonzero = aging_bar_visual(
        "ar-exc-aging-nonzero",
        "Non-Zero Transfers by Age",
        "How long non-zero transfers have been outstanding",
        DS_AR_NON_ZERO_TRANSFERS,
        "transfer_id",
    )
    aging_breach = aging_bar_visual(
        "ar-exc-aging-breach",
        "Limit Breaches by Age",
        "How long limit-breach rows have been outstanding",
        DS_AR_LIMIT_BREACH,
        "subledger_account_id",
    )
    aging_overdraft = aging_bar_visual(
        "ar-exc-aging-overdraft",
        "Overdrafts by Age",
        "How long overdraft rows have been outstanding",
        DS_AR_OVERDRAFT,
        "subledger_account_id",
    )

    # F.5.1 Sweep target non-zero EOD — operating sub-accounts under
    # Cash Concentration Master that didn't sweep to zero EOD.
    kpi_sweep_target = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-exc-kpi-sweep-target",
            Title=_title("Sweep Target Non-Zero EOD"),
            Subtitle=_subtitle(
                "Operating sub-accounts under Cash Concentration Master "
                "whose stored EOD balance is not zero — sweep failed or "
                "was skipped"
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-exc-sweep-target-count",
                            DS_AR_SWEEP_TARGET_NONZERO,
                            "subledger_account_id",
                        )
                    ],
                ),
            ),
        )
    )

    table_sweep_target = Visual(
        TableVisual=TableVisual(
            VisualId="ar-exc-sweep-target-table",
            Title=_title("Sweep Target Non-Zero EOD"),
            Subtitle=_subtitle(
                "Days an operating sub-account under Cash Concentration "
                "Master ended non-zero. Each row is a (sub-account, date) "
                "the EOD sweep didn't clear. Left-click a "
                "subledger_account_id to drill into Transactions."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("ar-exc-sw-subledger-id",
                                         DS_AR_SWEEP_TARGET_NONZERO,
                                         "subledger_account_id"),
                            _unagg_field("ar-exc-sw-subledger",
                                         DS_AR_SWEEP_TARGET_NONZERO,
                                         "subledger_name"),
                            _unagg_field("ar-exc-sw-ledger",
                                         DS_AR_SWEEP_TARGET_NONZERO,
                                         "ledger_name"),
                            _unagg_field("ar-exc-sw-date",
                                         DS_AR_SWEEP_TARGET_NONZERO,
                                         "balance_date"),
                            _unagg_field("ar-exc-sw-date-str",
                                         DS_AR_SWEEP_TARGET_NONZERO,
                                         "balance_date_str"),
                            _unagg_field("ar-exc-sw-stored",
                                         DS_AR_SWEEP_TARGET_NONZERO,
                                         "stored_balance"),
                            _unagg_field("ar-exc-sw-aging",
                                         DS_AR_SWEEP_TARGET_NONZERO,
                                         "aging_bucket"),
                        ],
                    )
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "ar-exc-sw-date",
                                "Direction": "DESC",
                            },
                        },
                    ],
                },
            ),
            Actions=[
                _multi_drill_action(
                    "action-ar-exc-sweep-target-to-txn",
                    "View Transactions",
                    SHEET_AR_TRANSACTIONS,
                    [
                        (P_AR_SUBLEDGER, "ar-exc-sw-subledger-id"),
                        (P_AR_ACTIVITY_DATE, "ar-exc-sw-date-str"),
                    ],
                ),
            ],
            ConditionalFormatting={
                "ConditionalFormattingOptions": [
                    link_text_format(
                        "ar-exc-sw-subledger-id", "subledger_account_id",
                        link_color,
                    ),
                ],
            },
        )
    )

    aging_sweep_target = aging_bar_visual(
        "ar-exc-aging-sweep-target",
        "Sweep Targets by Age",
        "How long sweep-target non-zero rows have been outstanding",
        DS_AR_SWEEP_TARGET_NONZERO,
        "subledger_account_id",
    )

    # F.5.2 Concentration master vs sub-account sweeps drift — daily
    # difference between sweep credits posted to Cash Concentration Master
    # and sweep debits drained from operating sub-accounts. KPI counts
    # drift days; timeline shows when legs went out of step.
    kpi_sweep_drift = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-exc-kpi-sweep-drift",
            Title=_title("Concentration Master Sweep Drift Days"),
            Subtitle=_subtitle(
                "Days the Cash Concentration Master credits and operating "
                "sub-account debits from clearing_sweep transfers didn't "
                "balance — sweep leg keyed off, missing, or extra"
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-exc-sweep-drift-count",
                            DS_AR_CONCENTRATION_MASTER_SWEEP_DRIFT,
                            "sweep_date",
                        )
                    ],
                ),
            ),
        )
    )

    timeline_sweep_drift = Visual(
        BarChartVisual=BarChartVisual(
            VisualId="ar-exc-sweep-drift-timeline",
            Title=_title("Concentration Master Sweep Drift Timeline"),
            Subtitle=_subtitle(
                "Per-day drift = Σ Master credits + Σ sub-account debits "
                "from clearing_sweep transfers. Healthy days = 0; non-zero "
                "bars are days the sweep legs didn't balance."
            ),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[_date_dim(
                            "ar-exc-sweep-drift-dim",
                            DS_AR_CONCENTRATION_MASTER_SWEEP_DRIFT,
                            "sweep_date",
                        )],
                        Values=[_measure_sum(
                            "ar-exc-sweep-drift-val",
                            DS_AR_CONCENTRATION_MASTER_SWEEP_DRIFT,
                            "drift",
                        )],
                    )
                ),
                Orientation="VERTICAL",
                BarsArrangement="CLUSTERED",
                CategoryLabelOptions=_axis_label("Date"),
                ValueLabelOptions=_axis_label("Drift ($)"),
            ),
        )
    )

    # F.5.3 ACH Origination Settlement non-zero EOD — days the gl-1810
    # ledger ended day non-zero because the EOD sweep to gl-1010 was
    # skipped or failed entirely.
    kpi_ach_orig_nonzero = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-exc-kpi-ach-orig-nonzero",
            Title=_title("ACH Origination Settlement Non-Zero EOD"),
            Subtitle=_subtitle(
                "Days the ACH Origination Settlement ledger (gl-1810) ended "
                "non-zero — internal EOD sweep to Cash & Due From FRB was "
                "skipped or failed"
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-exc-ach-orig-nonzero-count",
                            DS_AR_ACH_ORIG_SETTLEMENT_NONZERO,
                            "balance_date",
                        )
                    ],
                ),
            ),
        )
    )

    table_ach_orig_nonzero = Visual(
        TableVisual=TableVisual(
            VisualId="ar-exc-ach-orig-nonzero-table",
            Title=_title("ACH Origination Settlement Non-Zero EOD"),
            Subtitle=_subtitle(
                "Days the ACH Origination Settlement ledger ended non-zero. "
                "Each row is a date the day's net ACH originations weren't "
                "swept to Cash & Due From FRB. Left-click ledger_account_id "
                "to drill into Transactions for that date."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("ar-exc-ach-ledger-id",
                                         DS_AR_ACH_ORIG_SETTLEMENT_NONZERO,
                                         "ledger_account_id"),
                            _unagg_field("ar-exc-ach-ledger",
                                         DS_AR_ACH_ORIG_SETTLEMENT_NONZERO,
                                         "ledger_name"),
                            _unagg_field("ar-exc-ach-date",
                                         DS_AR_ACH_ORIG_SETTLEMENT_NONZERO,
                                         "balance_date"),
                            _unagg_field("ar-exc-ach-date-str",
                                         DS_AR_ACH_ORIG_SETTLEMENT_NONZERO,
                                         "balance_date_str"),
                            _unagg_field("ar-exc-ach-stored",
                                         DS_AR_ACH_ORIG_SETTLEMENT_NONZERO,
                                         "stored_balance"),
                            _unagg_field("ar-exc-ach-aging",
                                         DS_AR_ACH_ORIG_SETTLEMENT_NONZERO,
                                         "aging_bucket"),
                        ],
                    )
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "ar-exc-ach-date",
                                "Direction": "DESC",
                            },
                        },
                    ],
                },
            ),
            Actions=[
                _multi_drill_action(
                    "action-ar-exc-ach-orig-to-txn",
                    "View Transactions",
                    SHEET_AR_TRANSACTIONS,
                    [
                        (P_AR_ACTIVITY_DATE, "ar-exc-ach-date-str"),
                    ],
                ),
            ],
            ConditionalFormatting={
                "ConditionalFormattingOptions": [
                    link_text_format(
                        "ar-exc-ach-ledger-id", "ledger_account_id",
                        link_color,
                    ),
                ],
            },
        )
    )

    aging_ach_orig_nonzero = aging_bar_visual(
        "ar-exc-aging-ach-orig-nonzero",
        "ACH Origination Non-Zero EOD by Age",
        "How long ACH Origination Settlement non-zero days have been outstanding",
        DS_AR_ACH_ORIG_SETTLEMENT_NONZERO,
        "balance_date",
    )

    # F.5.4 Internal sweep posted but no Fed confirmation — internal EOD
    # sweep on gl-1810 succeeded but the FRB confirmation child transfer
    # never landed. Bank thinks the cash moved; Fed has no record.
    kpi_ach_sweep_no_fed = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-exc-kpi-ach-sweep-no-fed",
            Title=_title("ACH Sweep Without Fed Confirmation"),
            Subtitle=_subtitle(
                "Internal EOD sweeps on ACH Origination Settlement that "
                "posted but never received the Fed-side confirmation — "
                "bank moved the cash internally, FRB has no record"
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-exc-ach-sweep-no-fed-count",
                            DS_AR_ACH_SWEEP_NO_FED_CONFIRMATION,
                            "sweep_transfer_id",
                        )
                    ],
                ),
            ),
        )
    )

    table_ach_sweep_no_fed = Visual(
        TableVisual=TableVisual(
            VisualId="ar-exc-ach-sweep-no-fed-table",
            Title=_title("ACH Sweep Without Fed Confirmation"),
            Subtitle=_subtitle(
                "Each row is an internal sweep transfer that posted on "
                "gl-1810 but has no Fed confirmation child. Left-click "
                "sweep_transfer_id to drill into Transactions for that "
                "transfer."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("ar-exc-acsnf-tid",
                                         DS_AR_ACH_SWEEP_NO_FED_CONFIRMATION,
                                         "sweep_transfer_id"),
                            _unagg_field("ar-exc-acsnf-at",
                                         DS_AR_ACH_SWEEP_NO_FED_CONFIRMATION,
                                         "sweep_at"),
                            _unagg_field("ar-exc-acsnf-amt",
                                         DS_AR_ACH_SWEEP_NO_FED_CONFIRMATION,
                                         "sweep_amount"),
                            _unagg_field("ar-exc-acsnf-aging",
                                         DS_AR_ACH_SWEEP_NO_FED_CONFIRMATION,
                                         "aging_bucket"),
                        ],
                    )
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "ar-exc-acsnf-at",
                                "Direction": "DESC",
                            },
                        },
                    ],
                },
            ),
            Actions=[
                _multi_drill_action(
                    "action-ar-exc-ach-sweep-no-fed-to-txn",
                    "View Transactions",
                    SHEET_AR_TRANSACTIONS,
                    [
                        (P_AR_TRANSFER, "ar-exc-acsnf-tid"),
                    ],
                ),
            ],
            ConditionalFormatting={
                "ConditionalFormattingOptions": [
                    link_text_format(
                        "ar-exc-acsnf-tid", "sweep_transfer_id",
                        link_color,
                    ),
                ],
            },
        )
    )

    aging_ach_sweep_no_fed = aging_bar_visual(
        "ar-exc-aging-ach-sweep-no-fed",
        "ACH Sweep w/o Fed Confirmation by Age",
        "How long sweeps have been awaiting Fed-side confirmation",
        DS_AR_ACH_SWEEP_NO_FED_CONFIRMATION,
        "sweep_transfer_id",
    )

    # F.5.5 Fed activity with no matching internal post — Fed-side card
    # processor settlement observations with no SNB internal catch-up
    # child. Money the Fed says cleared, that SNB never recorded.
    kpi_fed_no_catchup = Visual(
        KPIVisual=KPIVisual(
            VisualId="ar-exc-kpi-fed-no-catchup",
            Title=_title("Fed Activity Without Internal Post"),
            Subtitle=_subtitle(
                "Fed-side card processor settlements that posted but have "
                "no SNB internal catch-up child — Fed says it cleared, "
                "SNB has no internal record"
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "ar-exc-fed-no-catchup-count",
                            DS_AR_FED_CARD_NO_INTERNAL_CATCHUP,
                            "fed_transfer_id",
                        )
                    ],
                ),
            ),
        )
    )

    table_fed_no_catchup = Visual(
        TableVisual=TableVisual(
            VisualId="ar-exc-fed-no-catchup-table",
            Title=_title("Fed Activity Without Internal Post"),
            Subtitle=_subtitle(
                "Each row is a Fed-observed card settlement transfer with "
                "no SNB internal catch-up child. Left-click "
                "fed_transfer_id to drill into Transactions for that "
                "transfer."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("ar-exc-fnc-tid",
                                         DS_AR_FED_CARD_NO_INTERNAL_CATCHUP,
                                         "fed_transfer_id"),
                            _unagg_field("ar-exc-fnc-at",
                                         DS_AR_FED_CARD_NO_INTERNAL_CATCHUP,
                                         "fed_at"),
                            _unagg_field("ar-exc-fnc-amt",
                                         DS_AR_FED_CARD_NO_INTERNAL_CATCHUP,
                                         "fed_amount"),
                            _unagg_field("ar-exc-fnc-aging",
                                         DS_AR_FED_CARD_NO_INTERNAL_CATCHUP,
                                         "aging_bucket"),
                        ],
                    )
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "ar-exc-fnc-at",
                                "Direction": "DESC",
                            },
                        },
                    ],
                },
            ),
            Actions=[
                _multi_drill_action(
                    "action-ar-exc-fed-no-catchup-to-txn",
                    "View Transactions",
                    SHEET_AR_TRANSACTIONS,
                    [
                        (P_AR_TRANSFER, "ar-exc-fnc-tid"),
                    ],
                ),
            ],
            ConditionalFormatting={
                "ConditionalFormattingOptions": [
                    link_text_format(
                        "ar-exc-fnc-tid", "fed_transfer_id",
                        link_color,
                    ),
                ],
            },
        )
    )

    aging_fed_no_catchup = aging_bar_visual(
        "ar-exc-aging-fed-no-catchup",
        "Fed Activity w/o Internal Post by Age",
        "How long Fed-observed settlements have been without an SNB internal record",
        DS_AR_FED_CARD_NO_INTERNAL_CATCHUP,
        "fed_transfer_id",
    )

    return [
        kpi_ledger_drift, kpi_subledger_drift, kpi_nonzero,
        kpi_breach, kpi_overdraft, kpi_sweep_target, kpi_sweep_drift,
        kpi_ach_orig_nonzero, kpi_ach_sweep_no_fed, kpi_fed_no_catchup,
        table_ledger_drift, table_subledger_drift, table_non_zero,
        table_breach, table_overdraft, table_sweep_target,
        table_ach_orig_nonzero, table_ach_sweep_no_fed, table_fed_no_catchup,
        timeline_ledger, timeline_subledger, timeline_sweep_drift,
        aging_ledger_drift, aging_subledger_drift, aging_nonzero,
        aging_breach, aging_overdraft, aging_sweep_target,
        aging_ach_orig_nonzero, aging_ach_sweep_no_fed, aging_fed_no_catchup,
    ]
