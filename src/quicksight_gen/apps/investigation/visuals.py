"""Investigation visuals.

K.4.3 ships the Recipient Fanout sheet's visuals — three KPIs (distinct
qualifying recipients, total distinct senders behind them, total dollars
flowing in) plus a recipient-grain ranked table sorted by distinct
sender count desc. All four read the recipient-fanout dataset (one row
per (recipient leg, sender leg) pair) and are gated by the threshold
filter group on the analysis-level ``recipient_distinct_sender_count``
calc field — so they show only recipients whose fanout meets the
slider's current value.

K.4.4 / K.4.5 add visuals for the Volume Anomalies and Money Trail
sheets.
"""

from __future__ import annotations

from quicksight_gen.apps.investigation.constants import (
    CF_INV_FANOUT_DISTINCT_SENDERS,
    DS_INV_RECIPIENT_FANOUT,
    V_INV_FANOUT_KPI_AMOUNT,
    V_INV_FANOUT_KPI_RECIPIENTS,
    V_INV_FANOUT_KPI_SENDERS,
    V_INV_FANOUT_TABLE,
)
from quicksight_gen.common.models import (
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
    TableAggregatedFieldWells,
    TableConfiguration,
    TableFieldWells,
    TableVisual,
    Visual,
    VisualSubtitleLabelOptions,
    VisualTitleLabelOptions,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _col(name: str) -> ColumnIdentifier:
    return ColumnIdentifier(
        DataSetIdentifier=DS_INV_RECIPIENT_FANOUT, ColumnName=name,
    )


def _dim(field_id: str, col_name: str) -> DimensionField:
    return DimensionField(
        CategoricalDimensionField=CategoricalDimensionField(
            FieldId=field_id, Column=_col(col_name),
        ),
    )


def _measure_distinct(field_id: str, col_name: str) -> MeasureField:
    return MeasureField(
        CategoricalMeasureField=CategoricalMeasureField(
            FieldId=field_id,
            Column=_col(col_name),
            AggregationFunction="DISTINCT_COUNT",
        ),
    )


def _measure_sum(field_id: str, col_name: str) -> MeasureField:
    return MeasureField(
        NumericalMeasureField=NumericalMeasureField(
            FieldId=field_id,
            Column=_col(col_name),
            AggregationFunction=NumericalAggregationFunction(
                SimpleNumericalAggregation="SUM",
            ),
        ),
    )


def _measure_max(field_id: str, col_name: str) -> MeasureField:
    """MAX of an analysis-level windowed-aggregate calc field.

    The fanout calc field returns the same value on every row of a
    recipient (it's a partitioned distinct count), so MAX per recipient
    surfaces that row-constant value once in the aggregated table.
    """
    return MeasureField(
        NumericalMeasureField=NumericalMeasureField(
            FieldId=field_id,
            Column=_col(col_name),
            AggregationFunction=NumericalAggregationFunction(
                SimpleNumericalAggregation="MAX",
            ),
        ),
    )


def _title(text: str) -> VisualTitleLabelOptions:
    return VisualTitleLabelOptions(
        Visibility="VISIBLE", FormatText={"PlainText": text},
    )


def _subtitle(text: str) -> VisualSubtitleLabelOptions:
    return VisualSubtitleLabelOptions(
        Visibility="VISIBLE", FormatText={"PlainText": text},
    )


# ---------------------------------------------------------------------------
# Recipient Fanout visuals
# ---------------------------------------------------------------------------

def _kpi_recipients() -> Visual:
    return Visual(
        KPIVisual=KPIVisual(
            VisualId=V_INV_FANOUT_KPI_RECIPIENTS,
            Title=_title("Qualifying Recipients"),
            Subtitle=_subtitle(
                "Distinct recipients meeting the fanout threshold."
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_distinct(
                            "inv-fanout-kpi-recipients-val",
                            "recipient_account_id",
                        ),
                    ],
                ),
            ),
        ),
    )


def _kpi_senders() -> Visual:
    return Visual(
        KPIVisual=KPIVisual(
            VisualId=V_INV_FANOUT_KPI_SENDERS,
            Title=_title("Distinct Senders"),
            Subtitle=_subtitle(
                "Distinct sender accounts feeding the qualifying recipients."
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_distinct(
                            "inv-fanout-kpi-senders-val",
                            "sender_account_id",
                        ),
                    ],
                ),
            ),
        ),
    )


def _kpi_amount() -> Visual:
    return Visual(
        KPIVisual=KPIVisual(
            VisualId=V_INV_FANOUT_KPI_AMOUNT,
            Title=_title("Total Inbound"),
            Subtitle=_subtitle(
                "Sum of inbound amounts across qualifying recipient legs."
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_sum(
                            "inv-fanout-kpi-amount-val", "amount",
                        ),
                    ],
                ),
            ),
        ),
    )


def _recipient_table() -> Visual:
    """One row per qualifying recipient, sorted by distinct sender count.

    Aggregated to recipient grain via GroupBy on the recipient identity
    columns. The threshold filter narrows the underlying rows to those
    whose recipient meets the slider's current value, so every recipient
    in the table is "interesting" by definition.

    K.4.7 wires a per-row drill into AR Transactions filtered to the
    recipient's account_id — that's why the dataset stays at the legs
    grain underneath.
    """
    return Visual(
        TableVisual=TableVisual(
            VisualId=V_INV_FANOUT_TABLE,
            Title=_title("Recipient Fanout — Ranked"),
            Subtitle=_subtitle(
                "One row per recipient. Ranked by distinct sender count "
                "(highest = widest funnel)."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableAggregatedFieldWells=TableAggregatedFieldWells(
                        GroupBy=[
                            _dim("inv-fanout-tbl-recipient-id",
                                 "recipient_account_id"),
                            _dim("inv-fanout-tbl-recipient-name",
                                 "recipient_account_name"),
                            _dim("inv-fanout-tbl-recipient-type",
                                 "recipient_account_type"),
                        ],
                        Values=[
                            _measure_max(
                                "inv-fanout-tbl-distinct-senders",
                                CF_INV_FANOUT_DISTINCT_SENDERS,
                            ),
                            _measure_distinct(
                                "inv-fanout-tbl-transfer-count",
                                "transfer_id",
                            ),
                            _measure_sum(
                                "inv-fanout-tbl-amount-total", "amount",
                            ),
                        ],
                    ),
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "inv-fanout-tbl-distinct-senders",
                                "Direction": "DESC",
                            },
                        },
                    ],
                },
            ),
        ),
    )


def build_fanout_visuals() -> list[Visual]:
    return [
        _kpi_recipients(),
        _kpi_senders(),
        _kpi_amount(),
        _recipient_table(),
    ]
