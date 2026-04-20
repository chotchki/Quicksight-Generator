"""Visual builders for the Payment Reconciliation sheet.

Provides KPIs, an external transactions table, and an internal payments
table with mutual filtering via the pExternalTransactionId parameter.
"""

from __future__ import annotations

from quicksight_gen.payment_recon.constants import (
    DS_EXTERNAL_TRANSACTIONS,
    DS_PAYMENT_RECON,
    DS_PAYMENTS,
    SHEET_PAYMENT_RECON,
)
from quicksight_gen.common.aging import aging_bar_visual
from quicksight_gen.common.clickability import link_text_format
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
# Shorthand helpers
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


def _set_param_action(
    action_id: str,
    name: str,
    param_name: str,
    source_field_id: str,
) -> VisualCustomAction:
    """Build a DATA_POINT_CLICK action that navigates to the recon sheet
    and sets a parameter. QuickSight requires NavigationOperation before
    SetParametersOperation, even for same-sheet interactions."""
    return VisualCustomAction(
        CustomActionId=action_id,
        Name=name,
        Trigger="DATA_POINT_CLICK",
        ActionOperations=[
            VisualCustomActionOperation(
                NavigationOperation=CustomActionNavigationOperation(
                    LocalNavigationConfiguration=LocalNavigationConfiguration(
                        TargetSheetId=SHEET_PAYMENT_RECON,
                    ),
                ),
            ),
            VisualCustomActionOperation(
                SetParametersOperation=CustomActionSetParametersOperation(
                    ParameterValueConfigurations=[
                        {
                            "DestinationParameterName": param_name,
                            "Value": {
                                "SourceField": source_field_id,
                            },
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
) -> VisualCustomAction:
    """Build a DATA_POINT_CLICK action that filters target visuals on the same sheet."""
    return VisualCustomAction(
        CustomActionId=action_id,
        Name=name,
        Trigger="DATA_POINT_CLICK",
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


# ---------------------------------------------------------------------------
# Payment Reconciliation visuals
# ---------------------------------------------------------------------------

def build_payment_recon_visuals(link_color: str) -> list[Visual]:
    """Build visuals for the Payment Reconciliation sheet.

    ``link_color`` is the theme accent color applied to the two
    mutual-filter source cells (external transaction id and the
    payments table's external_transaction_id column), so users see
    them as clickable.
    """

    # KPI: total matched amount
    kpi_matched = Visual(
        KPIVisual=KPIVisual(
            VisualId="recon-kpi-matched-amount",
            Title=_title("Matched Amount"),
            Subtitle=_subtitle(
                "Total external transaction amount that matches internal payments"
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_sum(
                            "recon-matched-amt",
                            DS_PAYMENT_RECON,
                            "external_amount",
                        )
                    ],
                ),
            ),
        )
    )

    # KPI: total unmatched amount
    kpi_unmatched = Visual(
        KPIVisual=KPIVisual(
            VisualId="recon-kpi-unmatched-amount",
            Title=_title("Unmatched Amount"),
            Subtitle=_subtitle(
                "Total external transaction amount not yet matched to internal payments"
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_sum(
                            "recon-unmatched-amt",
                            DS_PAYMENT_RECON,
                            "external_amount",
                        )
                    ],
                ),
            ),
        )
    )

    # KPI: late count
    kpi_late = Visual(
        KPIVisual=KPIVisual(
            VisualId="recon-kpi-late-count",
            Title=_title("Late Transactions"),
            Subtitle=_subtitle(
                "Transactions that have exceeded the late threshold without matching"
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "recon-late-count",
                            DS_PAYMENT_RECON,
                            "transaction_id",
                        )
                    ],
                ),
            ),
        )
    )

    # Bar chart: match status by external system
    bar_by_system = Visual(
        BarChartVisual=BarChartVisual(
            VisualId="recon-bar-by-system",
            Title=_title("Match Status by External System"),
            Subtitle=_subtitle(
                "Which external systems have the most mismatches. "
                "Click a bar to filter the tables below."
            ),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[
                            _dim(
                                "recon-system-dim",
                                DS_PAYMENT_RECON,
                                "external_system",
                            )
                        ],
                        Values=[
                            _measure_count(
                                "recon-system-count",
                                DS_PAYMENT_RECON,
                                "transaction_id",
                            )
                        ],
                        Colors=[
                            _dim(
                                "recon-system-status",
                                DS_PAYMENT_RECON,
                                "match_status",
                            )
                        ],
                    )
                ),
                Orientation="VERTICAL",
                BarsArrangement="STACKED",
                CategoryLabelOptions=_axis_label("External System"),
                ValueLabelOptions=_axis_label("Transaction Count"),
                ColorLabelOptions=_axis_label("Match Status"),
            ),
            Actions=[
                _same_sheet_filter_action(
                    "action-recon-filter-by-system",
                    "Filter by System",
                    ["recon-ext-txn-table", "recon-payments-table"],
                ),
            ],
        )
    )

    # Table: external transactions (payment recon aggregated view)
    table_ext_txns = Visual(
        TableVisual=TableVisual(
            VisualId="recon-ext-txn-table",
            Title=_title("External Transactions"),
            Subtitle=_subtitle(
                "Each external transaction with its match status and difference. "
                "Click a row to filter the Internal Payments table."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field(
                                "recon-tbl-txn-id",
                                DS_PAYMENT_RECON,
                                "transaction_id",
                            ),
                            _unagg_field(
                                "recon-tbl-ext-sys",
                                DS_PAYMENT_RECON,
                                "external_system",
                            ),
                            _unagg_field(
                                "recon-tbl-ext-amt",
                                DS_PAYMENT_RECON,
                                "external_amount",
                            ),
                            _unagg_field(
                                "recon-tbl-int-total",
                                DS_PAYMENT_RECON,
                                "internal_total",
                            ),
                            _unagg_field(
                                "recon-tbl-diff",
                                DS_PAYMENT_RECON,
                                "difference",
                            ),
                            _unagg_field(
                                "recon-tbl-status",
                                DS_PAYMENT_RECON,
                                "match_status",
                            ),
                            _unagg_field(
                                "recon-tbl-pay-count",
                                DS_PAYMENT_RECON,
                                "payment_count",
                            ),
                            _unagg_field(
                                "recon-tbl-merchant",
                                DS_PAYMENT_RECON,
                                "merchant_id",
                            ),
                            _unagg_field(
                                "recon-tbl-days",
                                DS_PAYMENT_RECON,
                                "days_outstanding",
                            ),
                        ]
                    )
                ),
            ),
            Actions=[
                _set_param_action(
                    "action-recon-ext-txn-click",
                    "Show Payments",
                    "pExternalTransactionId",
                    "recon-tbl-txn-id",
                ),
            ],
            ConditionalFormatting={
                "ConditionalFormattingOptions": [
                    link_text_format(
                        "recon-tbl-txn-id", "transaction_id", link_color
                    ),
                ],
            },
        )
    )

    # Table: internal payments linked to external transactions
    table_payments = Visual(
        TableVisual=TableVisual(
            VisualId="recon-payments-table",
            Title=_title("Internal Payments"),
            Subtitle=_subtitle(
                "Payments linked to external transactions. "
                "Click a row to filter the External Transactions table."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field(
                                "recon-pay-id",
                                DS_PAYMENTS,
                                "payment_id",
                            ),
                            _unagg_field(
                                "recon-pay-merchant",
                                DS_PAYMENTS,
                                "merchant_id",
                            ),
                            _unagg_field(
                                "recon-pay-amount",
                                DS_PAYMENTS,
                                "payment_amount",
                            ),
                            _unagg_field(
                                "recon-pay-date",
                                DS_PAYMENTS,
                                "payment_date",
                            ),
                            _unagg_field(
                                "recon-pay-status",
                                DS_PAYMENTS,
                                "payment_status",
                            ),
                            _unagg_field(
                                "recon-pay-ext-txn",
                                DS_PAYMENTS,
                                "external_transaction_id",
                            ),
                        ]
                    )
                ),
            ),
            Actions=[
                _set_param_action(
                    "action-recon-pay-click",
                    "Show Transaction",
                    "pExternalTransactionId",
                    "recon-pay-ext-txn",
                ),
            ],
            ConditionalFormatting={
                "ConditionalFormattingOptions": [
                    link_text_format(
                        "recon-pay-ext-txn",
                        "external_transaction_id",
                        link_color,
                    ),
                ],
            },
        )
    )

    aging_recon = aging_bar_visual(
        "recon-aging-bar",
        "Reconciliation by Age",
        "How long external transactions have been outstanding "
        "— older items are more likely to need investigation",
        DS_PAYMENT_RECON,
        "transaction_id",
    )

    return [
        kpi_matched,
        kpi_unmatched,
        kpi_late,
        bar_by_system,
        aging_recon,
        table_ext_txns,
        table_payments,
    ]
