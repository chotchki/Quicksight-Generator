"""Visual builders for each analysis tab.

Each ``build_*_visuals()`` function returns a list of Visual objects
ready to be placed on a sheet.
"""

from __future__ import annotations

from quicksight_gen.constants import (
    DS_PAYMENTS,
    DS_PAYMENT_RETURNS,
    DS_SALES,
    DS_SETTLEMENTS,
    DS_SETTLEMENT_EXCEPTIONS,
)
from quicksight_gen.models import (
    BarChartAggregatedFieldWells,
    BarChartConfiguration,
    BarChartFieldWells,
    BarChartVisual,
    CategoricalDimensionField,
    CategoricalMeasureField,
    ColumnIdentifier,
    DimensionField,
    KPIConfiguration,
    KPIFieldWells,
    KPIVisual,
    MeasureField,
    NumericalAggregationFunction,
    NumericalMeasureField,
    PieChartAggregatedFieldWells,
    PieChartConfiguration,
    PieChartFieldWells,
    PieChartVisual,
    TableAggregatedFieldWells,
    TableConfiguration,
    TableFieldWells,
    TableUnaggregatedFieldWells,
    TableVisual,
    Visual,
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


def _unagg_field(field_id: str, ds: str, col_name: str) -> dict:
    """Build an UnaggregatedField dict for table visuals."""
    return {
        "FieldId": field_id,
        "Column": {
            "DataSetIdentifier": ds,
            "ColumnName": col_name,
        },
    }


# ---------------------------------------------------------------------------
# 7a — Sales Overview visuals
# ---------------------------------------------------------------------------

def build_sales_visuals() -> list[Visual]:
    # KPI: total sales count
    kpi_count = Visual(
        KPIVisual=KPIVisual(
            VisualId="sales-kpi-count",
            Title=_title("Total Sales Count"),
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
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[_dim("merchant-dim", DS_SALES, "merchant_id")],
                        Values=[_measure_sum("merchant-amount", DS_SALES, "amount")],
                    )
                ),
                Orientation="HORIZONTAL",
                BarsArrangement="CLUSTERED",
            ),
        )
    )

    # Bar chart: sales amount by location
    bar_location = Visual(
        BarChartVisual=BarChartVisual(
            VisualId="sales-bar-by-location",
            Title=_title("Sales Amount by Location"),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[_dim("location-dim", DS_SALES, "location_id")],
                        Values=[_measure_sum("location-amount", DS_SALES, "amount")],
                    )
                ),
                Orientation="HORIZONTAL",
                BarsArrangement="CLUSTERED",
            ),
        )
    )

    # Table: recent sales detail
    table_sales = Visual(
        TableVisual=TableVisual(
            VisualId="sales-detail-table",
            Title=_title("Sales Detail"),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field("tbl-sale-id", DS_SALES, "sale_id"),
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
            ),
        )
    )

    # Table: settlement detail
    table_settlements = Visual(
        TableVisual=TableVisual(
            VisualId="settlements-detail-table",
            Title=_title("Settlement Detail"),
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
            ),
        )
    )

    # Table: payment detail
    table_payments = Visual(
        TableVisual=TableVisual(
            VisualId="payments-detail-table",
            Title=_title("Payment Detail"),
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
