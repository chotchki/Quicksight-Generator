"""Investigation visuals.

K.4.3 ships the Recipient Fanout sheet's visuals — three KPIs (distinct
qualifying recipients, total distinct senders behind them, total dollars
flowing in) plus a recipient-grain ranked table sorted by distinct
sender count desc. All four read the recipient-fanout dataset (one row
per (recipient leg, sender leg) pair) and are gated by the threshold
filter group on the analysis-level ``recipient_distinct_sender_count``
calc field — so they show only recipients whose fanout meets the
slider's current value.

K.4.4 ships the Volume Anomalies sheet — KPI flagged count, σ-bucket
distribution bar chart, and ranked table of flagged pair-windows. The
distribution chart is intentionally NOT gated by the σ filter (it shows
the full population so the slider's cutoff is meaningful).

K.4.5 ships the Money Trail sheet — Sankey diagram (chain root →
intermediate accounts → terminal accounts, weighted by SUM(hop_amount))
beside a hop-by-hop detail table sorted by depth ascending. Both
visuals read the matview-backed money-trail dataset, scoped to one
chain via the chain-root parameter.
"""

from __future__ import annotations

from quicksight_gen.apps.investigation.constants import (
    CF_INV_FANOUT_DISTINCT_SENDERS,
    DS_INV_MONEY_TRAIL,
    DS_INV_RECIPIENT_FANOUT,
    DS_INV_VOLUME_ANOMALIES,
    V_INV_ANOMALIES_DISTRIBUTION,
    V_INV_ANOMALIES_KPI_FLAGGED,
    V_INV_ANOMALIES_TABLE,
    V_INV_FANOUT_KPI_AMOUNT,
    V_INV_FANOUT_KPI_RECIPIENTS,
    V_INV_FANOUT_KPI_SENDERS,
    V_INV_FANOUT_TABLE,
    V_INV_MONEY_TRAIL_SANKEY,
    V_INV_MONEY_TRAIL_TABLE,
)
from quicksight_gen.common.models import (
    BarChartAggregatedFieldWells,
    BarChartConfiguration,
    BarChartFieldWells,
    BarChartSortConfiguration,
    BarChartVisual,
    CategoricalDimensionField,
    CategoricalMeasureField,
    ColumnIdentifier,
    DateDimensionField,
    DimensionField,
    KPIConfiguration,
    KPIFieldWells,
    KPIVisual,
    MeasureField,
    NumericalAggregationFunction,
    NumericalDimensionField,
    NumericalMeasureField,
    SankeyDiagramAggregatedFieldWells,
    SankeyDiagramChartConfiguration,
    SankeyDiagramFieldWells,
    SankeyDiagramSortConfiguration,
    SankeyDiagramVisual,
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

def _col(ds: str, name: str) -> ColumnIdentifier:
    return ColumnIdentifier(DataSetIdentifier=ds, ColumnName=name)


def _dim(ds: str, field_id: str, col_name: str) -> DimensionField:
    return DimensionField(
        CategoricalDimensionField=CategoricalDimensionField(
            FieldId=field_id, Column=_col(ds, col_name),
        ),
    )


def _date_dim(ds: str, field_id: str, col_name: str) -> DimensionField:
    return DimensionField(
        DateDimensionField=DateDimensionField(
            FieldId=field_id, Column=_col(ds, col_name),
        ),
    )


def _num_dim(ds: str, field_id: str, col_name: str) -> DimensionField:
    return DimensionField(
        NumericalDimensionField=NumericalDimensionField(
            FieldId=field_id, Column=_col(ds, col_name),
        ),
    )


def _measure_distinct(ds: str, field_id: str, col_name: str) -> MeasureField:
    return MeasureField(
        CategoricalMeasureField=CategoricalMeasureField(
            FieldId=field_id,
            Column=_col(ds, col_name),
            AggregationFunction="DISTINCT_COUNT",
        ),
    )


def _measure_count(ds: str, field_id: str, col_name: str) -> MeasureField:
    return MeasureField(
        CategoricalMeasureField=CategoricalMeasureField(
            FieldId=field_id,
            Column=_col(ds, col_name),
            AggregationFunction="COUNT",
        ),
    )


def _measure_sum(ds: str, field_id: str, col_name: str) -> MeasureField:
    return MeasureField(
        NumericalMeasureField=NumericalMeasureField(
            FieldId=field_id,
            Column=_col(ds, col_name),
            AggregationFunction=NumericalAggregationFunction(
                SimpleNumericalAggregation="SUM",
            ),
        ),
    )


def _measure_max(ds: str, field_id: str, col_name: str) -> MeasureField:
    """MAX aggregation over a numeric column.

    For the fanout calc field this surfaces the row-constant
    distinct-sender value once per recipient. For z_score it surfaces
    the worst-case σ in a window-pair group (when the table aggregates
    multiple rows for one pair, MAX picks the most-anomalous window).
    """
    return MeasureField(
        NumericalMeasureField=NumericalMeasureField(
            FieldId=field_id,
            Column=_col(ds, col_name),
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

_DS_FANOUT = DS_INV_RECIPIENT_FANOUT
_DS_ANOMALIES = DS_INV_VOLUME_ANOMALIES
_DS_MONEY_TRAIL = DS_INV_MONEY_TRAIL


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
                            _DS_FANOUT,
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
                            _DS_FANOUT,
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
                            _DS_FANOUT,
                            "inv-fanout-kpi-amount-val",
                            "amount",
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
                            _dim(_DS_FANOUT,
                                 "inv-fanout-tbl-recipient-id",
                                 "recipient_account_id"),
                            _dim(_DS_FANOUT,
                                 "inv-fanout-tbl-recipient-name",
                                 "recipient_account_name"),
                            _dim(_DS_FANOUT,
                                 "inv-fanout-tbl-recipient-type",
                                 "recipient_account_type"),
                        ],
                        Values=[
                            _measure_max(
                                _DS_FANOUT,
                                "inv-fanout-tbl-distinct-senders",
                                CF_INV_FANOUT_DISTINCT_SENDERS,
                            ),
                            _measure_distinct(
                                _DS_FANOUT,
                                "inv-fanout-tbl-transfer-count",
                                "transfer_id",
                            ),
                            _measure_sum(
                                _DS_FANOUT,
                                "inv-fanout-tbl-amount-total",
                                "amount",
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


# ---------------------------------------------------------------------------
# Volume Anomalies visuals (K.4.4)
# ---------------------------------------------------------------------------

def _kpi_anomalies_flagged() -> Visual:
    """Count of pair-windows surviving the σ filter.

    Sigma threshold filter is scoped to KPI + table only (not the
    distribution chart), so this KPI updates as the analyst drags the
    slider while the chart stays anchored.
    """
    return Visual(
        KPIVisual=KPIVisual(
            VisualId=V_INV_ANOMALIES_KPI_FLAGGED,
            Title=_title("Flagged Pair-Windows"),
            Subtitle=_subtitle(
                "Pair-windows whose 2-day rolling SUM clears the σ threshold."
            ),
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(
                    Values=[
                        _measure_count(
                            _DS_ANOMALIES,
                            "inv-anomalies-kpi-flagged-val",
                            "recipient_account_id",
                        ),
                    ],
                ),
            ),
        ),
    )


def _distribution_chart() -> Visual:
    """σ-bucket distribution across the full population.

    Intentionally not gated by the σ filter (see filters.py — the filter
    group is scoped SELECTED_VISUALS to exclude this visual). The chart
    is the analyst's reference frame: see where 2σ vs. 4σ falls in the
    overall shape before deciding where to set the slider.
    """
    return Visual(
        BarChartVisual=BarChartVisual(
            VisualId=V_INV_ANOMALIES_DISTRIBUTION,
            Title=_title("Pair-Window σ Distribution"),
            Subtitle=_subtitle(
                "Pair-windows bucketed by |z-score| against the population "
                "mean. Chart is intentionally NOT filtered by the σ slider."
            ),
            ChartConfiguration=BarChartConfiguration(
                FieldWells=BarChartFieldWells(
                    BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                        Category=[
                            _dim(_DS_ANOMALIES,
                                 "inv-anomalies-dist-bucket",
                                 "z_bucket"),
                        ],
                        Values=[
                            _measure_count(
                                _DS_ANOMALIES,
                                "inv-anomalies-dist-count",
                                "recipient_account_id",
                            ),
                        ],
                    ),
                ),
                Orientation="VERTICAL",
                BarsArrangement="CLUSTERED",
                SortConfiguration=BarChartSortConfiguration(
                    CategorySort=[
                        {
                            "FieldSort": {
                                "FieldId": "inv-anomalies-dist-bucket",
                                "Direction": "ASC",
                            },
                        },
                    ],
                ),
            ),
        ),
    )


def _anomalies_table() -> Visual:
    """Flagged windows ranked by σ desc.

    Table aggregates to (sender, recipient, window_end) grain — one row
    per flagged window. The σ filter is wired to this visual via the
    SELECTED_VISUALS scope, so dragging the slider narrows the rows.
    """
    return Visual(
        TableVisual=TableVisual(
            VisualId=V_INV_ANOMALIES_TABLE,
            Title=_title("Flagged Pair-Windows — Ranked"),
            Subtitle=_subtitle(
                "One row per flagged 2-day window. Ranked by z-score "
                "(highest = furthest from the population mean)."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableAggregatedFieldWells=TableAggregatedFieldWells(
                        GroupBy=[
                            _dim(_DS_ANOMALIES,
                                 "inv-anomalies-tbl-recipient-id",
                                 "recipient_account_id"),
                            _dim(_DS_ANOMALIES,
                                 "inv-anomalies-tbl-recipient-name",
                                 "recipient_account_name"),
                            _dim(_DS_ANOMALIES,
                                 "inv-anomalies-tbl-sender-id",
                                 "sender_account_id"),
                            _dim(_DS_ANOMALIES,
                                 "inv-anomalies-tbl-sender-name",
                                 "sender_account_name"),
                            _date_dim(_DS_ANOMALIES,
                                      "inv-anomalies-tbl-window-end",
                                      "window_end"),
                        ],
                        Values=[
                            _measure_max(
                                _DS_ANOMALIES,
                                "inv-anomalies-tbl-z-score",
                                "z_score",
                            ),
                            _measure_max(
                                _DS_ANOMALIES,
                                "inv-anomalies-tbl-window-sum",
                                "window_sum",
                            ),
                            _measure_max(
                                _DS_ANOMALIES,
                                "inv-anomalies-tbl-transfer-count",
                                "transfer_count",
                            ),
                        ],
                    ),
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "inv-anomalies-tbl-z-score",
                                "Direction": "DESC",
                            },
                        },
                    ],
                },
            ),
        ),
    )


def build_anomalies_visuals() -> list[Visual]:
    return [
        _kpi_anomalies_flagged(),
        _distribution_chart(),
        _anomalies_table(),
    ]


# ---------------------------------------------------------------------------
# Money Trail visuals (K.4.5)
# ---------------------------------------------------------------------------

# Sankey items-limit shape: cap distinct source / destination nodes the
# diagram renders. Set generously here — the chain root filter narrows
# to one chain, so the realistic cap is "chain depth" not "every account
# in the system". 50 covers the deepest chain we expect (PR's 4-hop
# `external_txn → payment → settlement → sale` × any synthetic chain
# extensions in the demo seed) with comfortable headroom.
_SANKEY_NODE_CAP = 50


def _money_trail_sankey() -> Visual:
    """Chain-walking Sankey: source_account → target_account, weight = SUM(hop_amount).

    Filters narrow to a single chain via the chain-root parameter, so
    the diagram renders one connected provenance flow. Each edge in the
    matview becomes a Sankey ribbon weighted by the leg's hop amount.

    Multi-leg-only semantics flow through from the matview: single-leg
    transfers (sales, raw external arrivals) appear as chain members
    (visible in the depth column on the table) but don't contribute
    visible Sankey ribbons. To inspect them, drill from the table row
    into AR Transactions filtered to the transfer_id.
    """
    return Visual(
        SankeyDiagramVisual=SankeyDiagramVisual(
            VisualId=V_INV_MONEY_TRAIL_SANKEY,
            Title=_title("Money Trail — Chain Sankey"),
            Subtitle=_subtitle(
                "Source account → target account ribbons for the selected "
                "chain. Ribbon thickness = SUM(hop_amount). Single-leg "
                "transfers don't render here — see the detail table for "
                "every chain member."
            ),
            ChartConfiguration=SankeyDiagramChartConfiguration(
                FieldWells=SankeyDiagramFieldWells(
                    SankeyDiagramAggregatedFieldWells=SankeyDiagramAggregatedFieldWells(
                        Source=[
                            _dim(_DS_MONEY_TRAIL,
                                 "inv-money-trail-sankey-source",
                                 "source_account_name"),
                        ],
                        Destination=[
                            _dim(_DS_MONEY_TRAIL,
                                 "inv-money-trail-sankey-target",
                                 "target_account_name"),
                        ],
                        Weight=[
                            _measure_sum(
                                _DS_MONEY_TRAIL,
                                "inv-money-trail-sankey-weight",
                                "hop_amount",
                            ),
                        ],
                    ),
                ),
                SortConfiguration=SankeyDiagramSortConfiguration(
                    WeightSort=[
                        {
                            "FieldSort": {
                                "FieldId": "inv-money-trail-sankey-weight",
                                "Direction": "DESC",
                            },
                        },
                    ],
                    SourceItemsLimit={
                        "ItemsLimit": _SANKEY_NODE_CAP,
                        "OtherCategories": "INCLUDE",
                    },
                    DestinationItemsLimit={
                        "ItemsLimit": _SANKEY_NODE_CAP,
                        "OtherCategories": "INCLUDE",
                    },
                ),
            ),
        ),
    )


def _money_trail_table() -> Visual:
    """Hop-by-hop detail table for the selected chain.

    Beside the Sankey for legibility — surfaces depth, transfer_id,
    transfer_type, posted_at, and amount per hop. Sorted by depth ASC so
    the chain reads top-to-bottom from root → leaf. Aggregates to
    (depth, transfer_id, source, target) grain to collapse leg pairs
    that share the same source/target into one row.
    """
    return Visual(
        TableVisual=TableVisual(
            VisualId=V_INV_MONEY_TRAIL_TABLE,
            Title=_title("Money Trail — Hop-by-Hop"),
            Subtitle=_subtitle(
                "Every edge in the selected chain, ordered root → leaf "
                "by depth. Drill a row into AR Transactions for the "
                "underlying transaction legs."
            ),
            ChartConfiguration=TableConfiguration(
                FieldWells=TableFieldWells(
                    TableAggregatedFieldWells=TableAggregatedFieldWells(
                        GroupBy=[
                            _num_dim(_DS_MONEY_TRAIL,
                                     "inv-money-trail-tbl-depth",
                                     "depth"),
                            _dim(_DS_MONEY_TRAIL,
                                 "inv-money-trail-tbl-transfer-id",
                                 "transfer_id"),
                            _dim(_DS_MONEY_TRAIL,
                                 "inv-money-trail-tbl-transfer-type",
                                 "transfer_type"),
                            _dim(_DS_MONEY_TRAIL,
                                 "inv-money-trail-tbl-source-name",
                                 "source_account_name"),
                            _dim(_DS_MONEY_TRAIL,
                                 "inv-money-trail-tbl-target-name",
                                 "target_account_name"),
                            _date_dim(_DS_MONEY_TRAIL,
                                      "inv-money-trail-tbl-posted-at",
                                      "posted_at"),
                        ],
                        Values=[
                            _measure_sum(
                                _DS_MONEY_TRAIL,
                                "inv-money-trail-tbl-amount",
                                "hop_amount",
                            ),
                        ],
                    ),
                ),
                SortConfiguration={
                    "RowSort": [
                        {
                            "FieldSort": {
                                "FieldId": "inv-money-trail-tbl-depth",
                                "Direction": "ASC",
                            },
                        },
                    ],
                },
            ),
        ),
    )


def build_money_trail_visuals() -> list[Visual]:
    return [
        _money_trail_sankey(),
        _money_trail_table(),
    ]
