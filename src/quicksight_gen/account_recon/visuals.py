"""Visual builders for Account Recon.

Phase 3 keeps the layout rough: KPIs + tables + a bar chart timeline
on the Exceptions tab. Drill-downs and chart-filter actions are
intentionally deferred to Phase 4.
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
    DateDimensionField,
    DimensionField,
    KPIConfiguration,
    KPIFieldWells,
    KPIVisual,
    MeasureField,
    NumericalAggregationFunction,
    NumericalMeasureField,
    TableConfiguration,
    TableFieldWells,
    TableUnaggregatedFieldWells,
    TableVisual,
    Visual,
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
# Balances tab — parent account drift + child account directory
# ---------------------------------------------------------------------------

def build_balances_visuals() -> list[Visual]:
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
                "Computed = Σ of its children's stored balances. Drift is "
                "non-zero when the parent feed disagrees with its children."
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
        )
    )

    table_children = Visual(
        TableVisual=TableVisual(
            VisualId="ar-balances-child-table",
            Title=_title("Child Account Balances"),
            Subtitle=_subtitle(
                "Each child account's stored vs computed daily balance. "
                "Computed = running Σ of posted transactions. Drift is "
                "non-zero when the child feed disagrees with the underlying "
                "transactions."
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
        )
    )

    return [kpi_parents, kpi_accounts, table_parents, table_children]


# ---------------------------------------------------------------------------
# Transfers tab — transfer list with net-zero flag
# ---------------------------------------------------------------------------

def build_transfers_visuals() -> list[Visual]:
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

    table_transfers = Visual(
        TableVisual=TableVisual(
            VisualId="ar-transfers-summary-table",
            Title=_title("Transfer Summary"),
            Subtitle=_subtitle(
                "Every transfer with its net amount, debit/credit totals, "
                "leg count, and net-zero status. Healthy transfers have net = 0."
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
        )
    )

    return [kpi_transfers, kpi_unhealthy, table_transfers]


# ---------------------------------------------------------------------------
# Transactions tab — raw ledger with failed-call-out
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
                "Failed slices should be rare."
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

    return [kpi_txn_count, kpi_failed, bar_by_status, table_txn]


# ---------------------------------------------------------------------------
# Exceptions tab — drift + non-zero + timeline
# ---------------------------------------------------------------------------

def build_exceptions_visuals() -> list[Visual]:
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
                "with the sum of its children's stored balances. Points at "
                "the parent-balance upstream feed. Drift > 0 means stored "
                "is higher than the children's sum."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
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
        )
    )

    table_child_drift = Visual(
        TableVisual=TableVisual(
            VisualId="ar-exc-child-drift-table",
            Title=_title("Child Balance Drift"),
            Subtitle=_subtitle(
                "Child-account days where stored child balance disagrees "
                "with the running sum of posted transactions. Points at "
                "the child-balance upstream feed or a missed transaction. "
                "Drift > 0 means stored is higher than the ledger."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
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
        )
    )

    table_non_zero = Visual(
        TableVisual=TableVisual(
            VisualId="ar-exc-nonzero-table",
            Title=_title("Non-Zero Transfers"),
            Subtitle=_subtitle(
                "Transfers where the sum of non-failed legs is not zero. "
                "Either a counter-leg failed, or the amounts were keyed off."
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
        )
    )

    # Timeline: sum of child-level drift per day. Child drift is closer
    # to the ledger (and typically finer-grained than parent drift), so
    # it's the more informative trace to plot. Phase 4 can add a second
    # series for parent drift if needed.
    timeline = Visual(
        BarChartVisual=BarChartVisual(
            VisualId="ar-exc-drift-timeline",
            Title=_title("Child Drift Timeline"),
            Subtitle=_subtitle(
                "Total child-drift amount per day. Tall bars mark days "
                "where stored child balances diverged most from the "
                "posted-transaction ledger."
            ),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[_date_dim("ar-exc-timeline-dim",
                                            DS_AR_ACCOUNT_BALANCE_DRIFT,
                                            "balance_date")],
                        Values=[_measure_sum(
                            "ar-exc-timeline-drift",
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
        timeline,
    ]
