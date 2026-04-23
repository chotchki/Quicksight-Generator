"""Tree-based builder for the Payment Reconciliation App (L.4 port).

Replaces the constant-heavy + manually-cross-referenced builders in
``apps/payment_recon/{analysis,filters,recon_filters,visuals,recon_visuals}.py``
with the typed tree primitives from ``common/tree/``. Sheets land one
per L.4 sub-step:

- L.4.1 — Getting Started (text boxes only, app-level skeleton)
- L.4.2 — Sales Overview (KPIs + bar charts + detail table with
  cross-sheet drill into Settlements)
- L.4.3 — Settlements
- L.4.4 — Payments
- L.4.5 — Exceptions & Alerts
- L.4.6 — Payment Reconciliation tab (side-by-side mutual-filter pattern)
- L.4.7 — App-level wiring (datasets, parameters, drills, theme,
  filter controls)

**Pre-registered sheet shells.** PR's drill actions cross-reference
sheets (Sales → Settlements, Payments → Recon, etc.). Rather than
ordering substeps by dependency, ``build_payment_recon_app``
pre-registers all 6 ``Sheet`` shells (in display order) up-front so
any populator can construct a ``Drill(target_sheet=other_sheet, ...)``
referencing any other shell. Unported sheets emit as bare shells (id +
metadata only); the per-sheet byte-identity tests target their sheet
by id, so unported shells don't pollute the tested surface.
"""

from __future__ import annotations

# Importing datasets registers each PR DatasetContract via its
# module-level register_contract() side effect — required so the L.1.17
# bare-string / unvalidated-Column emit-time validator can resolve every
# ds["col"] ref in the visuals below.
from quicksight_gen.apps.payment_recon import datasets as _register_contracts  # noqa: F401
from quicksight_gen.apps.payment_recon.constants import (
    DS_PAYMENTS,
    DS_SALES,
    DS_SETTLEMENTS,
    P_PR_EXTERNAL_TXN,
    P_PR_PAYMENT,
    P_PR_SETTLEMENT,
    SHEET_EXCEPTIONS,
    SHEET_GETTING_STARTED,
    SHEET_PAYMENT_RECON,
    SHEET_PAYMENTS,
    SHEET_SALES,
    SHEET_SETTLEMENTS,
)
from quicksight_gen.apps.payment_recon.datasets import (
    OPTIONAL_SALE_METADATA,
    build_all_datasets,
)
from quicksight_gen.common import rich_text as rt
from quicksight_gen.common.config import Config
from quicksight_gen.common.models import Analysis as ModelAnalysis
from quicksight_gen.common.models import Dashboard as ModelDashboard
from quicksight_gen.common.theme import get_preset
from quicksight_gen.common.tree import (
    Analysis,
    App,
    CellAccentMenu,
    CellAccentText,
    Dataset,
    Drill,
    DrillSourceField,
    SameSheetFilter,
    Sheet,
    TextBox,
)


# ---------------------------------------------------------------------------
# Layout constants — mirror apps/payment_recon/analysis.py.
# ---------------------------------------------------------------------------
_FULL = 36
_HALF = 18
_KPI_ROW_SPAN = 6
_CHART_ROW_SPAN = 12
_TABLE_ROW_SPAN = 18


# ---------------------------------------------------------------------------
# Dataset refs. Registered on the App in build_payment_recon_app; the
# populators reference them by Python variable. Order mirrors
# `build_all_datasets` so the Analysis JSON's
# `DataSetIdentifierDeclarations` lines up with the imperative output.
# ---------------------------------------------------------------------------

def _datasets(cfg: Config) -> dict[str, Dataset]:
    """Map each PR logical dataset identifier to a typed `Dataset` ref."""
    from quicksight_gen.apps.payment_recon.constants import (
        DS_EXTERNAL_TRANSACTIONS,
        DS_MERCHANTS,
        DS_PAYMENT_RECON,
        DS_PAYMENT_RETURNS,
        DS_PAYMENTS,
        DS_SALE_SETTLEMENT_MISMATCH,
        DS_SETTLEMENT_EXCEPTIONS,
        DS_SETTLEMENT_PAYMENT_MISMATCH,
        DS_UNMATCHED_EXTERNAL_TXNS,
    )
    # Order must mirror build_all_datasets so each logical name
    # lines up with the matching DataSet's DataSetId at the same index.
    names = [
        DS_MERCHANTS,
        DS_SALES,
        DS_SETTLEMENTS,
        DS_PAYMENTS,
        DS_SETTLEMENT_EXCEPTIONS,
        DS_PAYMENT_RETURNS,
        DS_SALE_SETTLEMENT_MISMATCH,
        DS_SETTLEMENT_PAYMENT_MISMATCH,
        DS_UNMATCHED_EXTERNAL_TXNS,
        DS_EXTERNAL_TRANSACTIONS,
        DS_PAYMENT_RECON,
    ]
    built = build_all_datasets(cfg)
    return {
        name: Dataset(identifier=name, arn=cfg.dataset_arn(ds.DataSetId))
        for name, ds in zip(names, built)
    }


# ---------------------------------------------------------------------------
# Sheet descriptions — single source of truth, also surfaced in the
# Getting Started bullet blocks so each sheet's description matches the
# summary on the landing page. Lifted verbatim from analysis.py so the
# byte-identity test passes.
# ---------------------------------------------------------------------------

_SALES_DESCRIPTION = (
    "Shows total sales volume and dollar amounts. Use the filters above "
    "to narrow by date range, merchant, or location. The bar charts "
    "highlight which merchants and locations drive the most sales, and "
    "the detail table at the bottom lists individual transactions."
)

_SETTLEMENTS_DESCRIPTION = (
    "Shows how sales are bundled into settlements for each merchant. "
    "The KPIs show total settled amounts and pending counts. Use the "
    "settlement status filter to focus on specific statuses. The bar "
    "chart breaks down amounts by merchant type, and the detail table "
    "lists each settlement with its current status."
)

_PAYMENTS_DESCRIPTION = (
    "Shows payments made to merchants from settlements. The KPIs show "
    "total paid amounts and how many payments were returned. The pie "
    "chart breaks down payment statuses, and the detail table includes "
    "return reasons for any returned payments."
)

_EXCEPTIONS_DESCRIPTION = (
    "Highlights items that need attention: sales that have not been "
    "settled and payments that were returned. Use this tab to "
    "investigate overdue settlements and understand why payments "
    "were sent back. Layout is compact — half-width tables side-by-side "
    "so all exception categories are visible without scrolling."
)

_PAYMENT_RECON_DESCRIPTION = (
    "Compares internal payments against external system transactions. "
    "The top KPIs show matched and unmatched totals. External transactions "
    "and internal payments are shown side-by-side — click a row in either "
    "table to filter the other. Use the filters to narrow by date, status, "
    "or external system."
)


# Per-sheet highlights used to build bulleted summaries on the Getting
# Started tab. Each list stays scannable — three to four concrete things
# the reader will find on that sheet.
_SALES_BULLETS = [
    "KPIs: total sale count and total amount",
    "Bar charts by merchant and by location",
    "Detail table of individual transactions",
    "Filters: date range, merchant, location",
]

_SETTLEMENTS_BULLETS = [
    "KPIs: total settled amount and pending count",
    "Bar chart breaking down amounts by merchant type",
    "Detail table listing each settlement with its status",
    "Filter: settlement status",
]

_PAYMENTS_BULLETS = [
    "KPIs: total paid amount and number of returned payments",
    "Bar chart of payment statuses",
    "Detail table including return reasons",
]

_EXCEPTIONS_BULLETS = [
    "Unsettled sales and returned payments side by side",
    "Sale↔settlement and settlement↔payment amount mismatches",
    "Unmatched external-system transactions",
]

_PAYMENT_RECON_BULLETS = [
    "KPIs: matched amount, unmatched amount, and late count",
    "Click an external transaction to filter payments (and vice-versa)",
    "Filters: date, match status, external system, days outstanding",
]


# ---------------------------------------------------------------------------
# Getting Started (L.4.1)
# ---------------------------------------------------------------------------

def _section_box_content(
    title: str, body: str, bullet_items: list[str], accent: str,
) -> str:
    return rt.text_box(
        rt.heading(title, color=accent),
        rt.BR,
        rt.BR,
        rt.body(body),
        rt.BR,
        rt.bullets(bullet_items),
    )


def _populate_getting_started(cfg: Config, sheet: Sheet) -> None:
    accent = get_preset(cfg.theme_preset).accent
    is_demo = cfg.demo_database_url is not None

    sheet.layout.row(height=4).add_text_box(
        TextBox(
            text_box_id="gs-welcome",
            content=rt.text_box(
                rt.inline(
                    "Payment Reconciliation Dashboard",
                    font_size="36px",
                    color=accent,
                ),
                rt.BR,
                rt.BR,
                rt.body(
                    "Track sales, settlements, and payments through the full "
                    "reconciliation lifecycle. Use the tabs above to walk each "
                    "stage — the sections below summarise what each tab covers."
                ),
            ),
        ),
        width=_FULL,
    )
    sheet.layout.row(height=6).add_text_box(
        TextBox(
            text_box_id="gs-clickability-legend",
            content=rt.text_box(
                rt.heading("Clickable cells", color=accent),
                rt.BR,
                rt.BR,
                rt.body(
                    "Cells rendered in the theme accent color are interactive:"
                ),
                rt.bullets_raw([
                    "Plain accent-colored text — left-click drills to a related "
                    "tab or filters this view",
                    "Accent text with a pale tinted background — right-click "
                    "menu for a secondary drill, keeping the left-click action "
                    "free for the primary id",
                    rt.inline(
                        "Heads-up: drill-down filters stick after you switch "
                        "tabs. Refresh the dashboard to clear them.",
                        color=accent,
                    ),
                ]),
            ),
        ),
        width=_FULL,
    )

    if is_demo:
        sheet.layout.row(height=7).add_text_box(
            TextBox(
                text_box_id="gs-demo-flavor",
                content=rt.text_box(
                    rt.heading(
                        "Demo scenario — Sasquatch National Bank",
                        color=accent,
                    ),
                    rt.BR,
                    rt.BR,
                    rt.body(
                        "Data is seeded from six fictional Seattle coffee shops "
                        "(Bigfoot Brews, Sasquatch Sips, Yeti Espresso, Skookum "
                        "Coffee Co., Cryptid Coffee Cart, and Wildman's Roastery). "
                        "Sales flow into settlements which pay out to merchants; "
                        "some settlements are intentionally left unsettled, a "
                        "handful of payments are returned, and a few amounts are "
                        "nudged off to populate the Exceptions tab."
                    ),
                    rt.BR,
                    rt.BR,
                    rt.body(
                        "Anchor date for relative timestamps is the day the seed "
                        "was generated. Everything here was produced "
                        "deterministically from demo_data.py — explore the "
                        "filters and drill-downs freely."
                    ),
                ),
            ),
            width=_FULL,
        )

    sheet_blocks = [
        ("gs-sales", "Sales Overview", _SALES_DESCRIPTION, _SALES_BULLETS),
        (
            "gs-settlements", "Settlements",
            _SETTLEMENTS_DESCRIPTION, _SETTLEMENTS_BULLETS,
        ),
        ("gs-payments", "Payments", _PAYMENTS_DESCRIPTION, _PAYMENTS_BULLETS),
        (
            "gs-exceptions", "Exceptions & Alerts",
            _EXCEPTIONS_DESCRIPTION, _EXCEPTIONS_BULLETS,
        ),
        (
            "gs-payment-recon", "Payment Reconciliation",
            _PAYMENT_RECON_DESCRIPTION, _PAYMENT_RECON_BULLETS,
        ),
    ]
    for box_id, title, body_text, bullet_items in sheet_blocks:
        sheet.layout.row(height=7).add_text_box(
            TextBox(
                text_box_id=box_id,
                content=_section_box_content(
                    title, body_text, bullet_items, accent,
                ),
            ),
            width=_FULL,
        )


# ---------------------------------------------------------------------------
# Sales Overview (L.4.2) — 2 KPIs + 2 bar charts (each click-filters
# the detail table) + unaggregated sales detail table with cross-sheet
# right-click drill into Settlements (writes pSettlementId).
# ---------------------------------------------------------------------------

def _populate_sales_overview(
    cfg: Config,
    sheet: Sheet,
    *,
    settlements_sheet: Sheet,
    datasets: dict[str, Dataset],
) -> None:
    preset = get_preset(cfg.theme_preset)
    link_color = preset.accent
    link_tint = preset.link_tint

    ds_sales = datasets[DS_SALES]

    # Row 1: two KPIs side-by-side.
    kpi_row = sheet.layout.row(height=_KPI_ROW_SPAN)
    kpi_row.add_kpi(
        width=_HALF,
        visual_id="sales-kpi-count",  # type: ignore[arg-type]
        title="Total Sales Count",
        subtitle="Count of all sales in the selected date range",
        values=[ds_sales["sale_id"].count(field_id="sales-count")],
    )
    kpi_row.add_kpi(
        width=_HALF,
        visual_id="sales-kpi-amount",  # type: ignore[arg-type]
        title="Total Sales Amount",
        subtitle="Sum of all sale amounts in the selected date range",
        values=[ds_sales["amount"].sum(field_id="sales-amount")],
    )

    # Row 2: two horizontal bar charts (merchant + location), each with
    # a same-sheet click filter that narrows the detail table in row 3.
    # Forward-ref pattern: build SameSheetFilter actions with empty
    # target_visuals, attach to bars, then back-patch with the table
    # visual once row 3 lands.
    merchant_filter = SameSheetFilter(
        target_visuals=[],
        name="Filter by Merchant",
        action_id="action-sales-filter-by-merchant",
    )
    location_filter = SameSheetFilter(
        target_visuals=[],
        name="Filter by Location",
        action_id="action-sales-filter-by-location",
    )
    chart_row = sheet.layout.row(height=_CHART_ROW_SPAN)
    chart_row.add_bar_chart(
        width=_HALF,
        visual_id="sales-bar-by-merchant",  # type: ignore[arg-type]
        title="Sales Amount by Merchant",
        subtitle=(
            "Which merchants are generating the most sales revenue. "
            "Click a bar to filter the detail table."
        ),
        category=[ds_sales["merchant_id"].dim(field_id="merchant-dim")],
        values=[ds_sales["amount"].sum(field_id="merchant-amount")],
        orientation="HORIZONTAL",
        bars_arrangement="CLUSTERED",
        category_label="Merchant",
        value_label="Sales Amount ($)",
        actions=[merchant_filter],
    )
    chart_row.add_bar_chart(
        width=_HALF,
        visual_id="sales-bar-by-location",  # type: ignore[arg-type]
        title="Sales Amount by Location",
        subtitle=(
            "Which locations are generating the most sales revenue. "
            "Click a bar to filter the detail table."
        ),
        category=[ds_sales["location_id"].dim(field_id="location-dim")],
        values=[ds_sales["amount"].sum(field_id="location-amount")],
        orientation="HORIZONTAL",
        bars_arrangement="CLUSTERED",
        category_label="Location",
        value_label="Sales Amount ($)",
        actions=[location_filter],
    )

    # Row 3: full-width detail table. Base columns + optional metadata
    # appended after, matching the imperative SPEC 2.2 shape.
    settlement_id_col = ds_sales["settlement_id"].dim(field_id="tbl-settlement-id")
    base_columns = [
        ds_sales["sale_id"].dim(field_id="tbl-sale-id"),
        ds_sales["sale_type"].dim(field_id="tbl-sale-type"),
        settlement_id_col,
        ds_sales["merchant_id"].dim(field_id="tbl-merchant-id"),
        ds_sales["location_id"].dim(field_id="tbl-location-id"),
        ds_sales["amount"].dim(field_id="tbl-amount"),
        ds_sales["payment_method"].dim(field_id="tbl-payment-method"),
        ds_sales["sale_timestamp"].dim(field_id="tbl-timestamp"),
        ds_sales["card_brand"].dim(field_id="tbl-card-brand"),
        ds_sales["reference_id"].dim(field_id="tbl-ref-id"),
    ]
    optional_columns = [
        ds_sales[col].dim(field_id=f"tbl-sales-{col}")
        for col, _ddl, _qs, _ftype, _label in OPTIONAL_SALE_METADATA
    ]
    sheet.layout.row(height=_TABLE_ROW_SPAN).add_table(
        width=_FULL,
        visual_id="sales-detail-table",  # type: ignore[arg-type]
        title="Sales Detail",
        subtitle=(
            "Individual sale transactions — newest first. Right-click a "
            "row to open its settlement."
        ),
        columns=base_columns + optional_columns,
        sort_by=("tbl-timestamp", "DESC"),
        actions=[
            Drill(
                target_sheet=settlements_sheet,
                writes=[(P_PR_SETTLEMENT, DrillSourceField(
                    field_id="tbl-settlement-id",
                    shape=P_PR_SETTLEMENT.shape,
                ))],
                name="View Settlement",
                trigger="DATA_POINT_MENU",
                action_id="action-sale-to-settlement",
            ),
        ],
        conditional_formatting=[
            CellAccentMenu(
                on=settlement_id_col,
                text_color=link_color,
                background_color=link_tint,
            ),
        ],
    )

    # Back-patch the bar charts' click filters now that the detail
    # table exists. SameSheetFilter only resolves target_visuals'
    # visual_ids at emit time; by then the table is in the sheet.
    detail_table = sheet.visuals[-1]
    merchant_filter.target_visuals.append(detail_table)
    location_filter.target_visuals.append(detail_table)


# ---------------------------------------------------------------------------
# Settlements (L.4.3) — KPI amount + KPI pending count + full-width
# vertical bar by settlement_type (with same-sheet click filter to the
# detail table) + 8-column unaggregated detail table with two drills:
# left-click → Sales (writes pSettlementId); right-click → Payments
# (writes pPaymentId).
# ---------------------------------------------------------------------------

def _populate_settlements(
    cfg: Config,
    sheet: Sheet,
    *,
    sales_sheet: Sheet,
    payments_sheet: Sheet,
    datasets: dict[str, Dataset],
) -> None:
    preset = get_preset(cfg.theme_preset)
    link_color = preset.accent
    link_tint = preset.link_tint

    ds_stl = datasets[DS_SETTLEMENTS]

    # Row 1: two KPIs side-by-side.
    kpi_row = sheet.layout.row(height=_KPI_ROW_SPAN)
    kpi_row.add_kpi(
        width=_HALF,
        visual_id="settlements-kpi-amount",  # type: ignore[arg-type]
        title="Total Settled Amount",
        subtitle="Sum of all settlement amounts in the selected date range",
        values=[ds_stl["settlement_amount"].sum(field_id="settled-amount")],
    )
    kpi_row.add_kpi(
        width=_HALF,
        visual_id="settlements-kpi-pending",  # type: ignore[arg-type]
        title="Pending Settlements",
        subtitle="Number of settlements that have not yet completed",
        values=[ds_stl["settlement_id"].count(field_id="pending-count")],
    )

    # Row 2: full-width vertical bar by settlement_type with same-sheet
    # filter to the detail table (forward-ref + back-patch).
    type_filter = SameSheetFilter(
        target_visuals=[],
        name="Filter by Type",
        action_id="action-settlements-filter-by-type",
    )
    sheet.layout.row(height=_CHART_ROW_SPAN).add_bar_chart(
        width=_FULL,
        visual_id="settlements-bar-by-type",  # type: ignore[arg-type]
        title="Settlement Amount by Merchant Type",
        subtitle=(
            "How settlement amounts break down across merchant types. "
            "Click a bar to filter the detail table."
        ),
        category=[ds_stl["settlement_type"].dim(field_id="stype-dim")],
        values=[ds_stl["settlement_amount"].sum(field_id="stype-amount")],
        orientation="VERTICAL",
        bars_arrangement="CLUSTERED",
        category_label="Merchant Type",
        value_label="Settlement Amount ($)",
        actions=[type_filter],
    )

    # Row 3: full-width unaggregated detail table with both drills.
    settlement_id_col = ds_stl["settlement_id"].dim(field_id="tbl-stl-id")
    payment_id_col = ds_stl["payment_id"].dim(field_id="tbl-stl-payment-id")
    sheet.layout.row(height=_TABLE_ROW_SPAN).add_table(
        width=_FULL,
        visual_id="settlements-detail-table",  # type: ignore[arg-type]
        title="Settlement Detail",
        subtitle=(
            "Each settlement with its status, amount, and sale count. "
            "Click a row to view its sales."
        ),
        columns=[
            settlement_id_col,
            ds_stl["merchant_id"].dim(field_id="tbl-stl-merchant"),
            ds_stl["settlement_type"].dim(field_id="tbl-stl-type"),
            ds_stl["settlement_amount"].dim(field_id="tbl-stl-amount"),
            ds_stl["settlement_date"].dim(field_id="tbl-stl-date"),
            ds_stl["settlement_status"].dim(field_id="tbl-stl-status"),
            ds_stl["sale_count"].dim(field_id="tbl-stl-sale-count"),
            payment_id_col,
        ],
        actions=[
            Drill(
                target_sheet=sales_sheet,
                writes=[(P_PR_SETTLEMENT, DrillSourceField(
                    field_id="tbl-stl-id",
                    shape=P_PR_SETTLEMENT.shape,
                ))],
                name="View Sales",
                trigger="DATA_POINT_CLICK",
                action_id="action-settlement-to-sales",
            ),
            Drill(
                target_sheet=payments_sheet,
                writes=[(P_PR_PAYMENT, DrillSourceField(
                    field_id="tbl-stl-payment-id",
                    shape=P_PR_PAYMENT.shape,
                ))],
                name="View Payment",
                trigger="DATA_POINT_MENU",
                action_id="action-settlement-to-payment",
            ),
        ],
        conditional_formatting=[
            CellAccentText(on=settlement_id_col, color=link_color),
            CellAccentMenu(
                on=payment_id_col,
                text_color=link_color,
                background_color=link_tint,
            ),
        ],
    )

    detail_table = sheet.visuals[-1]
    type_filter.target_visuals.append(detail_table)


# ---------------------------------------------------------------------------
# Payments (L.4.4) — KPI amount + KPI returns count + full-width vertical
# bar by payment_status (with same-sheet click filter to detail table) +
# 9-column unaggregated detail table with two drills:
# left-click → Settlements (writes pSettlementId);
# right-click → Payment Recon (writes pExternalTransactionId).
# ---------------------------------------------------------------------------

def _populate_payments(
    cfg: Config,
    sheet: Sheet,
    *,
    settlements_sheet: Sheet,
    payment_recon_sheet: Sheet,
    datasets: dict[str, Dataset],
) -> None:
    preset = get_preset(cfg.theme_preset)
    link_color = preset.accent
    link_tint = preset.link_tint

    ds_pay = datasets[DS_PAYMENTS]

    # Row 1: two KPIs side-by-side.
    kpi_row = sheet.layout.row(height=_KPI_ROW_SPAN)
    kpi_row.add_kpi(
        width=_HALF,
        visual_id="payments-kpi-amount",  # type: ignore[arg-type]
        title="Total Paid Amount",
        subtitle="Sum of all payment amounts to merchants",
        values=[ds_pay["payment_amount"].sum(field_id="paid-amount")],
    )
    kpi_row.add_kpi(
        width=_HALF,
        visual_id="payments-kpi-returns",  # type: ignore[arg-type]
        title="Returned Payments",
        subtitle=(
            "Number of payments that were sent back — see detail table "
            "for reasons"
        ),
        values=[ds_pay["payment_id"].count(field_id="return-count")],
    )

    # Row 2: full-width vertical bar by payment_status (chosen over a
    # pie because QS pies don't expose keyboard navigation that the
    # browser e2e suite relies on for click-to-filter automation).
    status_filter = SameSheetFilter(
        target_visuals=[],
        name="Filter by Status",
        action_id="action-payments-filter-by-status",
    )
    sheet.layout.row(height=_CHART_ROW_SPAN).add_bar_chart(
        width=_FULL,
        visual_id="payments-bar-status",  # type: ignore[arg-type]
        title="Payment Status Breakdown",
        subtitle=(
            "Count of payments by their current status. "
            "Click a bar to filter the detail table."
        ),
        category=[ds_pay["payment_status"].dim(field_id="pstatus-dim")],
        values=[ds_pay["payment_id"].count(field_id="pstatus-count")],
        orientation="VERTICAL",
        bars_arrangement="CLUSTERED",
        category_label="Payment Status",
        value_label="Number of Payments",
        actions=[status_filter],
    )

    # Row 3: full-width 9-column detail table with two drills.
    settlement_id_col = ds_pay["settlement_id"].dim(field_id="tbl-pay-stl-id")
    ext_txn_col = ds_pay["external_transaction_id"].dim(
        field_id="tbl-pay-ext-txn",
    )
    sheet.layout.row(height=_TABLE_ROW_SPAN).add_table(
        width=_FULL,
        visual_id="payments-detail-table",  # type: ignore[arg-type]
        title="Payment Detail",
        subtitle=(
            "Each payment with its status and return reason if applicable. "
            "Click a row to view its settlement; right-click to open "
            "Payment Reconciliation for its external transaction."
        ),
        columns=[
            ds_pay["payment_id"].dim(field_id="tbl-pay-id"),
            settlement_id_col,
            ds_pay["merchant_id"].dim(field_id="tbl-pay-merchant"),
            ds_pay["payment_amount"].dim(field_id="tbl-pay-amount"),
            ds_pay["payment_date"].dim(field_id="tbl-pay-date"),
            ds_pay["payment_status"].dim(field_id="tbl-pay-status"),
            ds_pay["is_returned"].dim(field_id="tbl-pay-returned"),
            ds_pay["return_reason"].dim(field_id="tbl-pay-reason"),
            ext_txn_col,
        ],
        actions=[
            Drill(
                target_sheet=settlements_sheet,
                writes=[(P_PR_SETTLEMENT, DrillSourceField(
                    field_id="tbl-pay-stl-id",
                    shape=P_PR_SETTLEMENT.shape,
                ))],
                name="View Settlement",
                trigger="DATA_POINT_CLICK",
                action_id="action-payment-to-settlement",
            ),
            Drill(
                target_sheet=payment_recon_sheet,
                writes=[(P_PR_EXTERNAL_TXN, DrillSourceField(
                    field_id="tbl-pay-ext-txn",
                    shape=P_PR_EXTERNAL_TXN.shape,
                ))],
                name="View in Reconciliation",
                trigger="DATA_POINT_MENU",
                action_id="action-payment-to-recon",
            ),
        ],
        conditional_formatting=[
            CellAccentText(on=settlement_id_col, color=link_color),
            CellAccentMenu(
                on=ext_txn_col,
                text_color=link_color,
                background_color=link_tint,
            ),
        ],
    )

    detail_table = sheet.visuals[-1]
    status_filter.target_visuals.append(detail_table)


# ---------------------------------------------------------------------------
# App entry points
# ---------------------------------------------------------------------------

def _analysis_name(cfg: Config) -> str:
    preset = get_preset(cfg.theme_preset)
    if preset.analysis_name_prefix:
        return f"{preset.analysis_name_prefix} — Payment Reconciliation"
    return "Payment Reconciliation"


# Order matters — sheets register on the analysis in this list's order,
# which becomes the dashboard's tab order.
_PR_SHEET_SPECS: tuple[tuple[str, str, str, str], ...] = (
    (SHEET_GETTING_STARTED, "Getting Started", "Getting Started",
     "Landing page — summarises each tab in this dashboard so readers "
     "know where to look first. No filters or visuals."),
    (SHEET_SALES, "Sales Overview", "Sales Overview", _SALES_DESCRIPTION),
    (SHEET_SETTLEMENTS, "Settlements", "Settlements", _SETTLEMENTS_DESCRIPTION),
    (SHEET_PAYMENTS, "Payments", "Payments", _PAYMENTS_DESCRIPTION),
    (SHEET_EXCEPTIONS, "Exceptions & Alerts", "Exceptions & Alerts",
     _EXCEPTIONS_DESCRIPTION),
    (SHEET_PAYMENT_RECON, "Payment Reconciliation", "Payment Reconciliation",
     _PAYMENT_RECON_DESCRIPTION),
)


def build_payment_recon_app(cfg: Config) -> App:
    """Construct the Payment Reconciliation App as a tree.

    Sheets are pre-registered in display order so cross-sheet drills can
    target any sheet by ref. Populators run in any order; unported
    sheets emit as bare shells (id + metadata) until their L.4.N
    sub-step lands.
    """
    app = App(name="payment-recon", cfg=cfg)
    analysis = app.set_analysis(Analysis(
        analysis_id_suffix="payment-recon-analysis",
        name=_analysis_name(cfg),
    ))

    datasets = _datasets(cfg)
    for ds in datasets.values():
        app.add_dataset(ds)

    sheets: dict[str, Sheet] = {}
    for sheet_id, name, title, description in _PR_SHEET_SPECS:
        sheets[sheet_id] = analysis.add_sheet(Sheet(
            sheet_id=sheet_id,  # type: ignore[arg-type]
            name=name,
            title=title,
            description=description,
        ))

    _populate_getting_started(cfg, sheets[SHEET_GETTING_STARTED])
    _populate_sales_overview(
        cfg,
        sheets[SHEET_SALES],
        settlements_sheet=sheets[SHEET_SETTLEMENTS],
        datasets=datasets,
    )
    _populate_settlements(
        cfg,
        sheets[SHEET_SETTLEMENTS],
        sales_sheet=sheets[SHEET_SALES],
        payments_sheet=sheets[SHEET_PAYMENTS],
        datasets=datasets,
    )
    _populate_payments(
        cfg,
        sheets[SHEET_PAYMENTS],
        settlements_sheet=sheets[SHEET_SETTLEMENTS],
        payment_recon_sheet=sheets[SHEET_PAYMENT_RECON],
        datasets=datasets,
    )
    return app
