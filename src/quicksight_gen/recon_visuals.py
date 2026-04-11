"""Visual builders for the Reconciliation analysis tabs.

Each ``build_*_visuals()`` function returns a list of Visual objects
for one sheet of the reconciliation analysis.
"""

from __future__ import annotations

from quicksight_gen.constants import (
    DS_EXTERNAL_TRANSACTIONS,
    DS_PAYMENT_RECON,
    DS_RECON_EXCEPTIONS,
    DS_SALES_RECON,
    DS_SETTLEMENT_RECON,
)
from quicksight_gen.models import (
    AxisLabelOptions,
    BarChartAggregatedFieldWells,
    BarChartConfiguration,
    BarChartFieldWells,
    BarChartVisual,
    CategoricalDimensionField,
    CategoricalMeasureField,
    ChartAxisLabelOptions,
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
    TableConfiguration,
    TableFieldWells,
    TableUnaggregatedFieldWells,
    TableVisual,
    Visual,
    VisualSubtitleLabelOptions,
    VisualTitleLabelOptions,
)


# ---------------------------------------------------------------------------
# Shorthand helpers (same pattern as visuals.py)
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


def _unagg_field(field_id: str, ds: str, col_name: str) -> dict:
    return {
        "FieldId": field_id,
        "Column": {
            "DataSetIdentifier": ds,
            "ColumnName": col_name,
        },
    }


def _axis_label(label: str) -> ChartAxisLabelOptions:
    return ChartAxisLabelOptions(
        AxisLabelOptions=[AxisLabelOptions(CustomLabel=label)],
    )


# ---------------------------------------------------------------------------
# 3a — Reconciliation Overview visuals
# ---------------------------------------------------------------------------

def build_recon_overview_visuals() -> list[Visual]:
    # KPI: total matched count
    kpi_matched = Visual(
        KPIVisual=KPIVisual(
            VisualId="recon-kpi-matched",
            Title=_title("Matched"),
            Subtitle=_subtitle("Transactions where internal and external totals are equal"),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "recon-matched-count",
                            DS_RECON_EXCEPTIONS,
                            "transaction_id",
                        )
                    ],
                ),
            ),
        )
    )

    # KPI: total not-yet-matched count
    kpi_pending = Visual(
        KPIVisual=KPIVisual(
            VisualId="recon-kpi-pending",
            Title=_title("Not Yet Matched"),
            Subtitle=_subtitle("Transactions still waiting for internal records to match"),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "recon-pending-count",
                            DS_RECON_EXCEPTIONS,
                            "transaction_id",
                        )
                    ],
                ),
            ),
        )
    )

    # KPI: total late count
    kpi_late = Visual(
        KPIVisual=KPIVisual(
            VisualId="recon-kpi-late",
            Title=_title("Late"),
            Subtitle=_subtitle("Unmatched transactions that have exceeded their late threshold"),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            "recon-late-count",
                            DS_RECON_EXCEPTIONS,
                            "transaction_id",
                        )
                    ],
                ),
            ),
        )
    )

    # Pie chart: match status breakdown
    pie_status = Visual(
        PieChartVisual=PieChartVisual(
            VisualId="recon-pie-status",
            Title=_title("Match Status Breakdown"),
            Subtitle=_subtitle("Proportion of all transactions by match status"),
            ChartConfiguration=PieChartConfiguration(
                FieldWells=PieChartFieldWells(
                    PieChartAggregatedFieldWells=PieChartAggregatedFieldWells(
                        Category=[
                            _dim(
                                "recon-status-dim",
                                DS_RECON_EXCEPTIONS,
                                "match_status",
                            )
                        ],
                        Values=[
                            _measure_count(
                                "recon-status-count",
                                DS_RECON_EXCEPTIONS,
                                "transaction_id",
                            )
                        ],
                    )
                ),
                CategoryLabelOptions=_axis_label("Match Status"),
                ValueLabelOptions=_axis_label("Transaction Count"),
            ),
        )
    )

    # Bar chart: match status by type
    bar_by_type = Visual(
        BarChartVisual=BarChartVisual(
            VisualId="recon-bar-by-type",
            Title=_title("Match Status by Type"),
            Subtitle=_subtitle("Compares how many sales, settlements, and payments are matched, pending, or late"),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[
                            _dim(
                                "recon-type-dim",
                                DS_RECON_EXCEPTIONS,
                                "transaction_type",
                            )
                        ],
                        Values=[
                            _measure_count(
                                "recon-type-count",
                                DS_RECON_EXCEPTIONS,
                                "transaction_id",
                            )
                        ],
                        Colors=[
                            _dim(
                                "recon-type-status",
                                DS_RECON_EXCEPTIONS,
                                "match_status",
                            )
                        ],
                    )
                ),
                Orientation="VERTICAL",
                BarsArrangement="STACKED",
                CategoryLabelOptions=_axis_label("Transaction Type"),
                ValueLabelOptions=_axis_label("Transaction Count"),
                ColorLabelOptions=_axis_label("Match Status"),
            ),
        )
    )

    # Bar chart: match status by external system
    bar_by_system = Visual(
        BarChartVisual=BarChartVisual(
            VisualId="recon-bar-by-system",
            Title=_title("Match Status by External System"),
            Subtitle=_subtitle("Which external systems have the most mismatches"),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[
                            _dim(
                                "recon-system-dim",
                                DS_RECON_EXCEPTIONS,
                                "external_system",
                            )
                        ],
                        Values=[
                            _measure_count(
                                "recon-system-count",
                                DS_RECON_EXCEPTIONS,
                                "transaction_id",
                            )
                        ],
                        Colors=[
                            _dim(
                                "recon-system-status",
                                DS_RECON_EXCEPTIONS,
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
        )
    )

    return [kpi_matched, kpi_pending, kpi_late, pie_status, bar_by_type, bar_by_system]


# ---------------------------------------------------------------------------
# Helpers for per-type recon sheets (3b, 3c, 3d share the same structure)
# ---------------------------------------------------------------------------

def _build_recon_type_visuals(
    prefix: str,
    ds: str,
    type_label: str,
    count_col: str,
) -> list[Visual]:
    """Build the standard set of visuals for a per-type reconciliation sheet.

    Args:
        prefix: unique prefix for visual/field IDs (e.g. "sales-recon")
        ds: dataset identifier constant
        type_label: human-readable type name (e.g. "Sales")
        count_col: column name for the record count (e.g. "sale_count")
    """
    # KPI: matched count
    kpi_matched = Visual(
        KPIVisual=KPIVisual(
            VisualId=f"{prefix}-kpi-matched",
            Title=_title(f"{type_label} Matched"),
            Subtitle=_subtitle(f"Number of {type_label.lower()} transactions fully reconciled"),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(f"{prefix}-matched-count", ds, "transaction_id")
                    ],
                ),
            ),
        )
    )

    # KPI: unmatched/late count
    kpi_unmatched = Visual(
        KPIVisual=KPIVisual(
            VisualId=f"{prefix}-kpi-unmatched",
            Title=_title(f"{type_label} Unmatched / Late"),
            Subtitle=_subtitle(f"Number of {type_label.lower()} transactions not yet matched or overdue"),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            f"{prefix}-unmatched-count", ds, "transaction_id"
                        )
                    ],
                ),
            ),
        )
    )

    # Bar chart: match status by merchant
    bar_merchant = Visual(
        BarChartVisual=BarChartVisual(
            VisualId=f"{prefix}-bar-merchant",
            Title=_title(f"{type_label} Match Status by Merchant"),
            Subtitle=_subtitle(f"Which merchants have {type_label.lower()} reconciliation issues"),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[_dim(f"{prefix}-merchant-dim", ds, "merchant_id")],
                        Values=[
                            _measure_count(
                                f"{prefix}-merchant-count", ds, "transaction_id"
                            )
                        ],
                        Colors=[
                            _dim(f"{prefix}-merchant-status", ds, "match_status")
                        ],
                    )
                ),
                Orientation="HORIZONTAL",
                BarsArrangement="STACKED",
                CategoryLabelOptions=_axis_label("Merchant"),
                ValueLabelOptions=_axis_label("Transaction Count"),
                ColorLabelOptions=_axis_label("Match Status"),
            ),
        )
    )

    # Table: reconciliation detail
    table_detail = Visual(
        TableVisual=TableVisual(
            VisualId=f"{prefix}-detail-table",
            Title=_title(f"{type_label} Reconciliation Detail"),
            Subtitle=_subtitle(
                f"Each {type_label.lower()} transaction with its match status and difference. "
                "The 'Late Threshold' column shows the definition of 'late' for this type "
                "— this is set by the system and cannot be changed here."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                        Values=[
                            _unagg_field(f"{prefix}-tbl-txn-id", ds, "transaction_id"),
                            _unagg_field(
                                f"{prefix}-tbl-ext-sys", ds, "external_system"
                            ),
                            _unagg_field(
                                f"{prefix}-tbl-ext-amt", ds, "external_amount"
                            ),
                            _unagg_field(
                                f"{prefix}-tbl-int-total", ds, "internal_total"
                            ),
                            _unagg_field(f"{prefix}-tbl-diff", ds, "difference"),
                            _unagg_field(
                                f"{prefix}-tbl-status", ds, "match_status"
                            ),
                            _unagg_field(
                                f"{prefix}-tbl-days", ds, "days_outstanding"
                            ),
                            _unagg_field(
                                f"{prefix}-tbl-late-desc",
                                ds,
                                "late_threshold_description",
                            ),
                        ]
                    )
                ),
            ),
        )
    )

    return [kpi_matched, kpi_unmatched, bar_merchant, table_detail]


# ---------------------------------------------------------------------------
# 3b — Sales Reconciliation visuals
# ---------------------------------------------------------------------------

def build_sales_recon_visuals() -> list[Visual]:
    return _build_recon_type_visuals(
        prefix="sales-recon",
        ds=DS_SALES_RECON,
        type_label="Sales",
        count_col="sale_count",
    )


# ---------------------------------------------------------------------------
# 3c — Settlement Reconciliation visuals
# ---------------------------------------------------------------------------

def build_settlement_recon_visuals() -> list[Visual]:
    return _build_recon_type_visuals(
        prefix="settlement-recon",
        ds=DS_SETTLEMENT_RECON,
        type_label="Settlement",
        count_col="settlement_count",
    )


# ---------------------------------------------------------------------------
# 3d — Payment Reconciliation visuals
# ---------------------------------------------------------------------------

def build_payment_recon_visuals() -> list[Visual]:
    return _build_recon_type_visuals(
        prefix="payment-recon",
        ds=DS_PAYMENT_RECON,
        type_label="Payment",
        count_col="payment_count",
    )
