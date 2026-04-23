"""Tree-based builder for the Investigation App (L.2 port).

Replaces the constant-heavy + manually-cross-referenced builders in
``apps/investigation/{analysis,filters,visuals}.py`` with the typed
tree primitives from ``common/tree/``. Sheets land one per L.2 sub-step:

- L.2.1 — Getting Started (text boxes only, app-level skeleton)
- L.2.2 — Recipient Fanout (3 KPIs + ranked table + threshold slider +
  date range filter)
- L.2.3 — Volume Anomalies
- L.2.4 — Money Trail
- L.2.5 — Account Network (already validated through L.0 + L.1.15)
- L.2.6 — App-level wiring: dashboard + dataset declarations
- L.2.7 — Drop ALL_FG_INV_IDS / ALL_P_INV from constants.py

Per-sub-step contract: byte-identical SheetDefinition output compared
to the imperative builder's per-sheet output. The byte-identity tests
live in ``tests/test_l2_investigation_port.py``.
"""

from __future__ import annotations

from quicksight_gen.apps.investigation.constants import (
    CF_INV_FANOUT_DISTINCT_SENDERS,
    DS_INV_RECIPIENT_FANOUT,
    DS_INV_VOLUME_ANOMALIES,
    FG_INV_ANOMALIES_SIGMA,
    FG_INV_ANOMALIES_WINDOW,
    FG_INV_FANOUT_THRESHOLD,
    FG_INV_FANOUT_WINDOW,
    P_INV_ANOMALIES_SIGMA,
    P_INV_FANOUT_THRESHOLD,
    SHEET_INV_ANOMALIES,
    SHEET_INV_FANOUT,
    SHEET_INV_GETTING_STARTED,
    V_INV_ANOMALIES_DISTRIBUTION,
    V_INV_ANOMALIES_KPI_FLAGGED,
    V_INV_ANOMALIES_TABLE,
    V_INV_FANOUT_KPI_AMOUNT,
    V_INV_FANOUT_KPI_RECIPIENTS,
    V_INV_FANOUT_KPI_SENDERS,
    V_INV_FANOUT_TABLE,
)
from quicksight_gen.common import rich_text as rt
from quicksight_gen.common.config import Config
from quicksight_gen.common.theme import get_preset
from quicksight_gen.common.tree import (
    KPI,
    Analysis,
    App,
    BarChart,
    CalcField,
    CategoryFilter,  # noqa: F401 — used by future sheets
    Dataset,
    Dim,
    FilterDateTimePicker,
    FilterGroup,
    IntegerParam,
    Measure,
    NumericRangeFilter,
    ParameterSlider,
    Sheet,
    Table,
    TextBox,
    TimeRangeFilter,
)


# Layout constants mirror apps/investigation/analysis.py.
_FULL = 36
_THIRD = 12
_KPI_ROW_SPAN = 6
_TABLE_ROW_SPAN = 18


# Fanout-specific defaults (imperative builder mirrors these in filters.py).
_DEFAULT_FANOUT_THRESHOLD = 5
_FANOUT_SLIDER_MIN = 1
_FANOUT_SLIDER_MAX = 20

# Anomalies-specific defaults.
_DEFAULT_ANOMALIES_SIGMA = 2
_SIGMA_SLIDER_MIN = 1
_SIGMA_SLIDER_MAX = 4


# ---------------------------------------------------------------------------
# Sheet descriptions (shared with imperative side — byte-identity only
# cares about the string content, not where it's constructed).
# ---------------------------------------------------------------------------

_FANOUT_DESCRIPTION = (
    "Who is receiving money from an unusual number of distinct senders? "
    "Drag the slider to set the minimum sender count; the table ranks "
    "qualifying recipients by funnel width."
)

_ANOMALY_DESCRIPTION = (
    "Which sender → recipient pair just spiked above its baseline? "
    "Rolling 2-day SUM per pair vs. the population mean + standard "
    "deviation. Drag the σ slider to flag the tail. The distribution "
    "chart shows the full population — your slider cutoff against that "
    "shape — while the KPI + table show only flagged windows."
)


# ---------------------------------------------------------------------------
# Getting Started (L.2.1)
# ---------------------------------------------------------------------------

def _build_getting_started_sheet(cfg: Config, analysis: Analysis) -> Sheet:
    """Getting Started — landing page with welcome + roadmap text boxes.

    Two full-width text boxes stacked top-to-bottom. No visuals,
    no controls, no filters. The simplest sheet on Investigation —
    its job in L.2.1 is to land the app-level skeleton (App + Analysis +
    text-box layout slot support) so subsequent sheet ports snap in.
    """
    accent = get_preset(cfg.theme_preset).accent

    sheet = analysis.add_sheet(Sheet(
        sheet_id=SHEET_INV_GETTING_STARTED,
        name="Getting Started",
        title="Getting Started",
        description=(
            "Landing page — summarises each tab in this dashboard. "
            "No filters or visuals."
        ),
    ))

    welcome = sheet.add_text_box(TextBox(
        text_box_id="inv-gs-welcome",
        content=rt.text_box(
            rt.inline(
                "Investigation Dashboard",
                font_size="36px",
                color=accent,
            ),
            rt.BR,
            rt.BR,
            rt.body(
                "Compliance / AML triage surface for the Sasquatch "
                "National Bank shared base ledger. Three question-shaped "
                "sheets — recipient fanout, volume anomalies, and money "
                "trail — each one drilling back into Account "
                "Reconciliation or Payment Reconciliation for the row "
                "evidence."
            ),
        ),
    ))
    roadmap = sheet.add_text_box(TextBox(
        text_box_id="inv-gs-roadmap",
        content=rt.text_box(
            rt.heading("Sheets in this dashboard", color=accent),
            rt.BR,
            rt.BR,
            rt.bullets([
                "Recipient Fanout — who is receiving money from too many "
                "distinct senders? (live)",
                "Volume Anomalies — which sender → recipient pair just "
                "spiked above the rolling baseline? (live)",
                "Money Trail — where did this transfer originate and "
                "where does it go? (live)",
                "Account Network — who does this account exchange money "
                "with, on either side? (live)",
            ]),
        ),
    ))

    sheet.place(welcome, col_span=_FULL, row_span=5, col_index=0)
    sheet.place(roadmap, col_span=_FULL, row_span=6, col_index=0)

    return sheet


# ---------------------------------------------------------------------------
# Recipient Fanout (L.2.2)
# ---------------------------------------------------------------------------

def _build_recipient_fanout_sheet(
    cfg: Config, app: App, analysis: Analysis,
) -> Sheet:
    """Recipient Fanout — 3 KPIs + ranked table.

    Registers the fanout dataset + integer parameter + analysis-level
    calc field that backs the threshold filter. Builds 3 KPIs
    (qualifying recipients / distinct senders / total inbound) plus a
    recipient-grain ranked table. Wires the threshold slider (parameter
    control) + date range picker (filter control). Scopes both filter
    groups to this sheet.

    Layout: 3 KPIs across Row 1 (each ⅓ width), table full-width on
    Row 2.
    """
    del cfg  # reserved for theme-driven styling in later sub-steps

    ds_fanout = app.add_dataset(Dataset(
        identifier=DS_INV_RECIPIENT_FANOUT,
        arn=app.cfg.dataset_arn(app.cfg.prefixed("inv-recipient-fanout-dataset")),
    ))

    threshold_param = analysis.add_parameter(IntegerParam(
        name=P_INV_FANOUT_THRESHOLD,
        default=[_DEFAULT_FANOUT_THRESHOLD],
    ))

    distinct_senders_calc = analysis.add_calc_field(CalcField(
        name=CF_INV_FANOUT_DISTINCT_SENDERS,
        dataset=ds_fanout,
        expression=(
            "distinct_count({sender_account_id}, "
            "[{recipient_account_id}])"
        ),
    ))

    sheet = analysis.add_sheet(Sheet(
        sheet_id=SHEET_INV_FANOUT,
        name="Recipient Fanout",
        title="Recipient Fanout",
        description=_FANOUT_DESCRIPTION,
    ))

    kpi_recipients = sheet.add_visual(KPI(
        visual_id=V_INV_FANOUT_KPI_RECIPIENTS,
        title="Qualifying Recipients",
        subtitle="Distinct recipients meeting the fanout threshold.",
        values=[Measure.distinct_count(
            ds_fanout, "inv-fanout-kpi-recipients-val", "recipient_account_id",
        )],
    ))
    kpi_senders = sheet.add_visual(KPI(
        visual_id=V_INV_FANOUT_KPI_SENDERS,
        title="Distinct Senders",
        subtitle=(
            "Distinct sender accounts feeding the qualifying recipients."
        ),
        values=[Measure.distinct_count(
            ds_fanout, "inv-fanout-kpi-senders-val", "sender_account_id",
        )],
    ))
    kpi_amount = sheet.add_visual(KPI(
        visual_id=V_INV_FANOUT_KPI_AMOUNT,
        title="Total Inbound",
        subtitle=(
            "Sum of inbound amounts across qualifying recipient legs."
        ),
        values=[Measure.sum(
            ds_fanout, "inv-fanout-kpi-amount-val", "amount",
        )],
    ))
    table = sheet.add_visual(Table(
        visual_id=V_INV_FANOUT_TABLE,
        title="Recipient Fanout — Ranked",
        subtitle=(
            "One row per recipient. Ranked by distinct sender count "
            "(highest = widest funnel)."
        ),
        group_by=[
            Dim(ds_fanout, "inv-fanout-tbl-recipient-id",
                "recipient_account_id"),
            Dim(ds_fanout, "inv-fanout-tbl-recipient-name",
                "recipient_account_name"),
            Dim(ds_fanout, "inv-fanout-tbl-recipient-type",
                "recipient_account_type"),
        ],
        values=[
            Measure.max(
                ds_fanout, "inv-fanout-tbl-distinct-senders",
                distinct_senders_calc,
            ),
            Measure.distinct_count(
                ds_fanout, "inv-fanout-tbl-transfer-count", "transfer_id",
            ),
            Measure.sum(
                ds_fanout, "inv-fanout-tbl-amount-total", "amount",
            ),
        ],
        sort_by=("inv-fanout-tbl-distinct-senders", "DESC"),
    ))

    # Row 1: 3 KPIs each ⅓ width.
    sheet.place(kpi_recipients,
                col_span=_THIRD, row_span=_KPI_ROW_SPAN, col_index=0)
    sheet.place(kpi_senders,
                col_span=_THIRD, row_span=_KPI_ROW_SPAN, col_index=_THIRD)
    sheet.place(kpi_amount,
                col_span=_THIRD, row_span=_KPI_ROW_SPAN, col_index=_THIRD * 2)
    # Row 2: table full-width.
    sheet.place(table,
                col_span=_FULL, row_span=_TABLE_ROW_SPAN, col_index=0)

    # Date-range window on posted_at — ALL visuals on this sheet. Narrow
    # scope: fanout sheet only, not cross-sheet.
    window_fg = analysis.add_filter_group(FilterGroup(
        filter_group_id=FG_INV_FANOUT_WINDOW,
        filters=[TimeRangeFilter(
            filter_id="filter-inv-fanout-window",
            dataset=ds_fanout,
            column="posted_at",
            null_option="NON_NULLS_ONLY",
            time_granularity="DAY",
        )],
    ))
    window_fg.scope_sheet(sheet)

    # Threshold on the distinct-senders calc field, min-only, parameter-bound.
    # IncludeMinimum=True matches "slider value = visible cutoff".
    threshold_fg = analysis.add_filter_group(FilterGroup(
        filter_group_id=FG_INV_FANOUT_THRESHOLD,
        filters=[NumericRangeFilter(
            filter_id="filter-inv-fanout-threshold",
            dataset=ds_fanout,
            column=distinct_senders_calc,
            minimum_parameter=threshold_param,
            null_option="NON_NULLS_ONLY",
            include_minimum=True,
        )],
    ))
    threshold_fg.scope_sheet(sheet)

    # Sheet controls: date range picker + threshold slider.
    sheet.add_filter_control(FilterDateTimePicker(
        filter=window_fg.filters[0],
        title="Date Range",
        type="DATE_RANGE",
        control_id="ctrl-inv-fanout-window",
    ))
    sheet.add_parameter_control(ParameterSlider(
        parameter=threshold_param,
        title="Min distinct senders",
        minimum_value=_FANOUT_SLIDER_MIN,
        maximum_value=_FANOUT_SLIDER_MAX,
        step_size=1,
        control_id="ctrl-inv-fanout-threshold",
    ))

    return sheet


# ---------------------------------------------------------------------------
# Volume Anomalies (L.2.3)
# ---------------------------------------------------------------------------

def _build_volume_anomalies_sheet(
    cfg: Config, app: App, analysis: Analysis,
) -> Sheet:
    """Volume Anomalies — KPI flagged-count + σ distribution + ranked table.

    Load-bearing case for the tree's scope API: the σ filter scopes
    SELECTED_VISUALS (KPI + table only) so the distribution bar chart
    keeps rendering the full population. The chart's job is the
    reference frame — see where 2σ vs. 4σ falls in the overall shape
    before deciding where to set the slider.

    Layout:
      * Row 1: KPI flagged count (⅓ width) + distribution bar chart
        (⅔ width, 2× row span so it has room for the buckets).
      * Row 2: full-width flagged table sorted by z_score desc.
    """
    del cfg

    ds_anomalies = app.add_dataset(Dataset(
        identifier=DS_INV_VOLUME_ANOMALIES,
        arn=app.cfg.dataset_arn(app.cfg.prefixed("inv-volume-anomalies-dataset")),
    ))

    sigma_param = analysis.add_parameter(IntegerParam(
        name=P_INV_ANOMALIES_SIGMA,
        default=[_DEFAULT_ANOMALIES_SIGMA],
    ))

    sheet = analysis.add_sheet(Sheet(
        sheet_id=SHEET_INV_ANOMALIES,
        name="Volume Anomalies",
        title="Volume Anomalies",
        description=_ANOMALY_DESCRIPTION,
    ))

    kpi_flagged = sheet.add_visual(KPI(
        visual_id=V_INV_ANOMALIES_KPI_FLAGGED,
        title="Flagged Pair-Windows",
        subtitle=(
            "Pair-windows whose 2-day rolling SUM clears the σ threshold."
        ),
        values=[Measure.count(
            ds_anomalies, "inv-anomalies-kpi-flagged-val",
            "recipient_account_id",
        )],
    ))
    distribution = sheet.add_visual(BarChart(
        visual_id=V_INV_ANOMALIES_DISTRIBUTION,
        title="Pair-Window σ Distribution",
        subtitle=(
            "Pair-windows bucketed by |z-score| against the population "
            "mean. Chart is intentionally NOT filtered by the σ slider."
        ),
        category=[Dim(
            ds_anomalies, "inv-anomalies-dist-bucket", "z_bucket",
        )],
        values=[Measure.count(
            ds_anomalies, "inv-anomalies-dist-count",
            "recipient_account_id",
        )],
        orientation="VERTICAL",
        bars_arrangement="CLUSTERED",
        sort_by=("inv-anomalies-dist-bucket", "ASC"),
    ))
    table = sheet.add_visual(Table(
        visual_id=V_INV_ANOMALIES_TABLE,
        title="Flagged Pair-Windows — Ranked",
        subtitle=(
            "One row per flagged 2-day window. Ranked by z-score "
            "(highest = furthest from the population mean)."
        ),
        group_by=[
            Dim(ds_anomalies, "inv-anomalies-tbl-recipient-id",
                "recipient_account_id"),
            Dim(ds_anomalies, "inv-anomalies-tbl-recipient-name",
                "recipient_account_name"),
            Dim(ds_anomalies, "inv-anomalies-tbl-sender-id",
                "sender_account_id"),
            Dim(ds_anomalies, "inv-anomalies-tbl-sender-name",
                "sender_account_name"),
            Dim.date(ds_anomalies, "inv-anomalies-tbl-window-end",
                     "window_end"),
        ],
        values=[
            Measure.max(ds_anomalies, "inv-anomalies-tbl-z-score",
                        "z_score"),
            Measure.max(ds_anomalies, "inv-anomalies-tbl-window-sum",
                        "window_sum"),
            Measure.max(ds_anomalies, "inv-anomalies-tbl-transfer-count",
                        "transfer_count"),
        ],
        sort_by=("inv-anomalies-tbl-z-score", "DESC"),
    ))

    # Layout: KPI ⅓ + Distribution ⅔ × 2 row span; Table full-width.
    sheet.place(kpi_flagged,
                col_span=_THIRD, row_span=_KPI_ROW_SPAN, col_index=0)
    sheet.place(distribution,
                col_span=_THIRD * 2, row_span=_KPI_ROW_SPAN * 2,
                col_index=_THIRD)
    sheet.place(table,
                col_span=_FULL, row_span=_TABLE_ROW_SPAN, col_index=0)

    # Window date-range filter: ALL visuals on this sheet (chart + KPI +
    # table all narrow with the date range so the chart's shape stays
    # tied to what the analyst is investigating).
    window_fg = analysis.add_filter_group(FilterGroup(
        filter_group_id=FG_INV_ANOMALIES_WINDOW,
        filters=[TimeRangeFilter(
            filter_id="filter-inv-anomalies-window",
            dataset=ds_anomalies,
            column="window_end",
            null_option="NON_NULLS_ONLY",
            time_granularity="DAY",
        )],
    ))
    window_fg.scope_sheet(sheet)

    # σ threshold: SELECTED_VISUALS — KPI + table only. The distribution
    # chart stays unfiltered so it can show the full population shape.
    # This is the load-bearing scope-by-visuals case for L.2.3.
    sigma_fg = analysis.add_filter_group(FilterGroup(
        filter_group_id=FG_INV_ANOMALIES_SIGMA,
        filters=[NumericRangeFilter(
            filter_id="filter-inv-anomalies-sigma",
            dataset=ds_anomalies,
            column="z_score",
            minimum_parameter=sigma_param,
            null_option="NON_NULLS_ONLY",
            include_minimum=True,
        )],
    ))
    sigma_fg.scope_visuals(sheet, [kpi_flagged, table])

    sheet.add_filter_control(FilterDateTimePicker(
        filter=window_fg.filters[0],
        title="Window End Date",
        type="DATE_RANGE",
        control_id="ctrl-inv-anomalies-window",
    ))
    sheet.add_parameter_control(ParameterSlider(
        parameter=sigma_param,
        title="Min sigma",
        minimum_value=_SIGMA_SLIDER_MIN,
        maximum_value=_SIGMA_SLIDER_MAX,
        step_size=1,
        control_id="ctrl-inv-anomalies-sigma",
    ))

    return sheet


# ---------------------------------------------------------------------------
# App builder
# ---------------------------------------------------------------------------

def build_investigation_app(cfg: Config) -> App:
    """Build the Investigation App tree.

    Grows one sheet per L.2.x sub-step; L.2.6 attaches the Dashboard
    and swaps the CLI's analysis/dashboard build path to this function.
    """
    app = App(name="investigation", cfg=cfg)
    analysis = app.set_analysis(Analysis(
        analysis_id_suffix="investigation-analysis",
        name="Investigation",
    ))
    _build_getting_started_sheet(cfg, analysis)
    _build_recipient_fanout_sheet(cfg, app, analysis)
    _build_volume_anomalies_sheet(cfg, app, analysis)
    return app
