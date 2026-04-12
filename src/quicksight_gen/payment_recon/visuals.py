"""Visual builders for each analysis tab.

Each ``build_*_visuals()`` function returns a list of Visual objects
ready to be placed on a sheet.
"""

from __future__ import annotations

from quicksight_gen.payment_recon.constants import (
    DS_PAYMENTS,
    DS_PAYMENT_RETURNS,
    DS_SALES,
    DS_SETTLEMENTS,
    DS_SETTLEMENT_EXCEPTIONS,
    SHEET_SALES,
    SHEET_SETTLEMENTS,
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
    PieChartAggregatedFieldWells,
    PieChartConfiguration,
    PieChartFieldWells,
    PieChartVisual,
    SameSheetTargetVisualConfiguration,
    TableAggregatedFieldWells,
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
    """Build an UnaggregatedField dict for table visuals."""
    return {
        "FieldId": field_id,
        "Column": {
            "DataSetIdentifier": ds,
            "ColumnName": col_name,
        },
    }


def _drill_down_action(
    action_id: str,
    name: str,
    target_sheet: str,
    param_name: str,
    source_field_id: str,
    trigger: str = "DATA_POINT_CLICK",
) -> VisualCustomAction:
    """Build a drill-down action that sets a parameter and navigates.

    Use trigger="DATA_POINT_MENU" for a right-click menu entry when
    the visual already has a DATA_POINT_CLICK action.
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
# 7a — Sales Overview visuals
# ---------------------------------------------------------------------------

def build_sales_visuals() -> list[Visual]:
    # KPI: total sales count
    kpi_count = Visual(
        KPIVisual=KPIVisual(
            VisualId="sales-kpi-count",
            Title=_title("Total Sales Count"),
            Subtitle=_subtitle("Count of all sales in the selected date range"),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[_measure_count("sales-count", DS_SALES, "sale_id")],
                ),
            ),
        )
    )

    # KPI: total sales amount
    kpi_amount = Visual(
        KPIVisual=KPIVisual(
            VisualId="sales-kpi-amount",
            Title=_title("Total Sales Amount"),
            Subtitle=_subtitle("Sum of all sale amounts in the selected date range"),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[_measure_sum("sales-amount", DS_SALES, "amount")],
                ),
            ),
        )
    )

    # Bar chart: sales amount by merchant
    bar_merchant = Visual(
        BarChartVisual=BarChartVisual(
            VisualId="sales-bar-by-merchant",
            Title=_title("Sales Amount by Merchant"),
            Subtitle=_subtitle(
                "Which merchants are generating the most sales revenue. "
                "Click a bar to filter the detail table."
            ),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[_dim("merchant-dim", DS_SALES, "merchant_id")],
                        Values=[_measure_sum("merchant-amount", DS_SALES, "amount")],
                    )
                ),
                Orientation="HORIZONTAL",
                BarsArrangement="CLUSTERED",
                CategoryLabelOptions=_axis_label("Merchant"),
                ValueLabelOptions=_axis_label("Sales Amount ($)"),
            ),
            Actions=[
                _same_sheet_filter_action(
                    "action-sales-filter-by-merchant",
                    "Filter by Merchant",
                    ["sales-detail-table"],
                ),
            ],
        )
    )

    # Bar chart: sales amount by location
    bar_location = Visual(
        BarChartVisual=BarChartVisual(
            VisualId="sales-bar-by-location",
            Title=_title("Sales Amount by Location"),
            Subtitle=_subtitle(
                "Which locations are generating the most sales revenue. "
                "Click a bar to filter the detail table."
            ),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[_dim("location-dim", DS_SALES, "location_id")],
                        Values=[_measure_sum("location-amount", DS_SALES, "amount")],
                    )
                ),
                Orientation="HORIZONTAL",
                BarsArrangement="CLUSTERED",
                CategoryLabelOptions=_axis_label("Location"),
                ValueLabelOptions=_axis_label("Sales Amount ($)"),
            ),
            Actions=[
                _same_sheet_filter_action(
                    "action-sales-filter-by-location",
                    "Filter by Location",
                    ["sales-detail-table"],
                ),
            ],
        )
    )

    # Table: recent sales detail
    table_sales = Visual(
        TableVisual=TableVisual(
            VisualId="sales-detail-table",
            Title=_title("Sales Detail"),
            Subtitle=_subtitle("Individual sale transactions — click column headers to sort"),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("tbl-sale-id", DS_SALES, "sale_id"),
                            _unagg_field("tbl-settlement-id", DS_SALES, "settlement_id"),
                            _unagg_field("tbl-merchant-id", DS_SALES, "merchant_id"),
                            _unagg_field("tbl-location-id", DS_SALES, "location_id"),
                            _unagg_field("tbl-amount", DS_SALES, "amount"),
                            _unagg_field("tbl-timestamp", DS_SALES, "sale_timestamp"),
                            _unagg_field("tbl-card-brand", DS_SALES, "card_brand"),
                            _unagg_field("tbl-ref-id", DS_SALES, "reference_id"),
                        ]
                    )
                ),
            ),
        )
    )

    return [kpi_count, kpi_amount, bar_merchant, bar_location, table_sales]


# ---------------------------------------------------------------------------
# 7b — Settlements visuals
# ---------------------------------------------------------------------------

def build_settlements_visuals() -> list[Visual]:
    # KPI: total settled amount
    kpi_amount = Visual(
        KPIVisual=KPIVisual(
            VisualId="settlements-kpi-amount",
            Title=_title("Total Settled Amount"),
            Subtitle=_subtitle("Sum of all settlement amounts in the selected date range"),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_sum(
                            "settled-amount", DS_SETTLEMENTS, "settlement_amount"
                        )
                    ],
                ),
            ),
        )
    )

    # KPI: count of pending settlements
    kpi_pending = Visual(
        KPIVisual=KPIVisual(
            VisualId="settlements-kpi-pending",
            Title=_title("Pending Settlements"),
            Subtitle=_subtitle("Number of settlements that have not yet completed"),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "pending-count", DS_SETTLEMENTS, "settlement_id"
                        )
                    ],
                ),
            ),
        )
    )

    # Bar chart: settlement amounts by merchant type
    bar_type = Visual(
        BarChartVisual=BarChartVisual(
            VisualId="settlements-bar-by-type",
            Title=_title("Settlement Amount by Merchant Type"),
            Subtitle=_subtitle(
                "How settlement amounts break down across merchant types. "
                "Click a bar to filter the detail table."
            ),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[
                            _dim("stype-dim", DS_SETTLEMENTS, "settlement_type")
                        ],
                        Values=[
                            _measure_sum(
                                "stype-amount", DS_SETTLEMENTS, "settlement_amount"
                            )
                        ],
                    )
                ),
                Orientation="VERTICAL",
                BarsArrangement="CLUSTERED",
                CategoryLabelOptions=_axis_label("Merchant Type"),
                ValueLabelOptions=_axis_label("Settlement Amount ($)"),
            ),
            Actions=[
                _same_sheet_filter_action(
                    "action-settlements-filter-by-type",
                    "Filter by Type",
                    ["settlements-detail-table"],
                ),
            ],
        )
    )

    # Table: settlement detail — click a row to drill down to its sales
    table_settlements = Visual(
        TableVisual=TableVisual(
            VisualId="settlements-detail-table",
            Title=_title("Settlement Detail"),
            Subtitle=_subtitle(
                "Each settlement with its status, amount, and sale count. "
                "Click a row to view its sales."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field(
                                "tbl-stl-id", DS_SETTLEMENTS, "settlement_id"
                            ),
                            _unagg_field(
                                "tbl-stl-merchant", DS_SETTLEMENTS, "merchant_id"
                            ),
                            _unagg_field(
                                "tbl-stl-type", DS_SETTLEMENTS, "settlement_type"
                            ),
                            _unagg_field(
                                "tbl-stl-amount", DS_SETTLEMENTS, "settlement_amount"
                            ),
                            _unagg_field(
                                "tbl-stl-date", DS_SETTLEMENTS, "settlement_date"
                            ),
                            _unagg_field(
                                "tbl-stl-status", DS_SETTLEMENTS, "settlement_status"
                            ),
                            _unagg_field(
                                "tbl-stl-sale-count", DS_SETTLEMENTS, "sale_count"
                            ),
                        ]
                    )
                ),
            ),
            Actions=[
                _drill_down_action(
                    "action-settlement-to-sales",
                    "View Sales",
                    SHEET_SALES,
                    "pSettlementId",
                    "tbl-stl-id",
                ),
            ],
        )
    )

    return [kpi_amount, kpi_pending, bar_type, table_settlements]


# ---------------------------------------------------------------------------
# 7c — Payments visuals
# ---------------------------------------------------------------------------

def build_payments_visuals() -> list[Visual]:
    # KPI: total paid amount
    kpi_amount = Visual(
        KPIVisual=KPIVisual(
            VisualId="payments-kpi-amount",
            Title=_title("Total Paid Amount"),
            Subtitle=_subtitle("Sum of all payment amounts to merchants"),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_sum("paid-amount", DS_PAYMENTS, "payment_amount")
                    ],
                ),
            ),
        )
    )

    # KPI: count of returned payments
    kpi_returns = Visual(
        KPIVisual=KPIVisual(
            VisualId="payments-kpi-returns",
            Title=_title("Returned Payments"),
            Subtitle=_subtitle("Number of payments that were sent back — see detail table for reasons"),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count("return-count", DS_PAYMENTS, "payment_id")
                    ],
                ),
            ),
        )
    )

    # Pie chart: payment status breakdown
    pie_status = Visual(
        PieChartVisual=PieChartVisual(
            VisualId="payments-pie-status",
            Title=_title("Payment Status Breakdown"),
            Subtitle=_subtitle(
                "Proportion of payments by their current status. "
                "Click a slice to filter the detail table."
            ),
            ChartConfiguration=PieChartConfiguration(
                FieldWells=PieChartFieldWells(
                    PieChartAggregatedFieldWells=PieChartAggregatedFieldWells(
                        Category=[
                            _dim("pstatus-dim", DS_PAYMENTS, "payment_status")
                        ],
                        Values=[
                            _measure_count(
                                "pstatus-count", DS_PAYMENTS, "payment_id"
                            )
                        ],
                    )
                ),
                CategoryLabelOptions=_axis_label("Payment Status"),
                ValueLabelOptions=_axis_label("Number of Payments"),
            ),
            Actions=[
                _same_sheet_filter_action(
                    "action-payments-filter-by-status",
                    "Filter by Status",
                    ["payments-detail-table"],
                ),
            ],
        )
    )

    # Table: payment detail — click a row to drill down to its settlement
    table_payments = Visual(
        TableVisual=TableVisual(
            VisualId="payments-detail-table",
            Title=_title("Payment Detail"),
            Subtitle=_subtitle(
                "Each payment with its status and return reason if applicable. "
                "Click a row to view its settlement."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("tbl-pay-id", DS_PAYMENTS, "payment_id"),
                            _unagg_field(
                                "tbl-pay-stl-id", DS_PAYMENTS, "settlement_id"
                            ),
                            _unagg_field(
                                "tbl-pay-merchant", DS_PAYMENTS, "merchant_id"
                            ),
                            _unagg_field(
                                "tbl-pay-amount", DS_PAYMENTS, "payment_amount"
                            ),
                            _unagg_field(
                                "tbl-pay-date", DS_PAYMENTS, "payment_date"
                            ),
                            _unagg_field(
                                "tbl-pay-status", DS_PAYMENTS, "payment_status"
                            ),
                            _unagg_field(
                                "tbl-pay-returned", DS_PAYMENTS, "is_returned"
                            ),
                            _unagg_field(
                                "tbl-pay-reason", DS_PAYMENTS, "return_reason"
                            ),
                        ]
                    )
                ),
            ),
            Actions=[
                _drill_down_action(
                    "action-payment-to-settlement",
                    "View Settlement",
                    SHEET_SETTLEMENTS,
                    "pSettlementId",
                    "tbl-pay-stl-id",
                ),
            ],
        )
    )

    return [kpi_amount, kpi_returns, pie_status, table_payments]


# ---------------------------------------------------------------------------
# 7d — Exceptions & Alerts visuals
# ---------------------------------------------------------------------------

def build_exceptions_visuals() -> list[Visual]:
    # KPI: count of unsettled sales
    kpi_unsettled = Visual(
        KPIVisual=KPIVisual(
            VisualId="exceptions-kpi-unsettled",
            Title=_title("Unsettled Sales"),
            Subtitle=_subtitle("Sales that have not yet been bundled into a settlement"),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "unsettled-count",
                            DS_SETTLEMENT_EXCEPTIONS,
                            "sale_id",
                        )
                    ],
                ),
            ),
        )
    )

    # KPI: count of returned payments
    kpi_returns = Visual(
        KPIVisual=KPIVisual(
            VisualId="exceptions-kpi-returns",
            Title=_title("Returned Payments"),
            Subtitle=_subtitle("Payments that were sent back — check the table below for details"),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "exc-return-count",
                            DS_PAYMENT_RETURNS,
                            "payment_id",
                        )
                    ],
                ),
            ),
        )
    )

    # Table: unsettled sales
    table_unsettled = Visual(
        TableVisual=TableVisual(
            VisualId="exceptions-unsettled-table",
            Title=_title("Sales Missing Settlements"),
            Subtitle=_subtitle("Sales not yet bundled into a settlement — investigate if any are overdue"),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field(
                                "tbl-exc-sale-id",
                                DS_SETTLEMENT_EXCEPTIONS,
                                "sale_id",
                            ),
                            _unagg_field(
                                "tbl-exc-merchant",
                                DS_SETTLEMENT_EXCEPTIONS,
                                "merchant_id",
                            ),
                            _unagg_field(
                                "tbl-exc-merchant-name",
                                DS_SETTLEMENT_EXCEPTIONS,
                                "merchant_name",
                            ),
                            _unagg_field(
                                "tbl-exc-location",
                                DS_SETTLEMENT_EXCEPTIONS,
                                "location_id",
                            ),
                            _unagg_field(
                                "tbl-exc-amount",
                                DS_SETTLEMENT_EXCEPTIONS,
                                "amount",
                            ),
                            _unagg_field(
                                "tbl-exc-timestamp",
                                DS_SETTLEMENT_EXCEPTIONS,
                                "sale_timestamp",
                            ),
                            _unagg_field(
                                "tbl-exc-days",
                                DS_SETTLEMENT_EXCEPTIONS,
                                "days_unsettled",
                            ),
                        ]
                    )
                ),
            ),
        )
    )

    # Table: returned payments
    table_returns = Visual(
        TableVisual=TableVisual(
            VisualId="exceptions-returns-table",
            Title=_title("Returned Payments Detail"),
            Subtitle=_subtitle("Payments that were returned with the reason for each"),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field(
                                "tbl-ret-pay-id",
                                DS_PAYMENT_RETURNS,
                                "payment_id",
                            ),
                            _unagg_field(
                                "tbl-ret-stl-id",
                                DS_PAYMENT_RETURNS,
                                "settlement_id",
                            ),
                            _unagg_field(
                                "tbl-ret-merchant",
                                DS_PAYMENT_RETURNS,
                                "merchant_id",
                            ),
                            _unagg_field(
                                "tbl-ret-merchant-name",
                                DS_PAYMENT_RETURNS,
                                "merchant_name",
                            ),
                            _unagg_field(
                                "tbl-ret-amount",
                                DS_PAYMENT_RETURNS,
                                "payment_amount",
                            ),
                            _unagg_field(
                                "tbl-ret-date",
                                DS_PAYMENT_RETURNS,
                                "payment_date",
                            ),
                            _unagg_field(
                                "tbl-ret-reason",
                                DS_PAYMENT_RETURNS,
                                "return_reason",
                            ),
                        ]
                    )
                ),
            ),
        )
    )

    return [kpi_unsettled, kpi_returns, table_unsettled, table_returns]
