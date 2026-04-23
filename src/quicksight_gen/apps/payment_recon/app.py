"""Tree-based builder for the Payment Reconciliation App (L.4 port).

Replaces the constant-heavy + manually-cross-referenced builders in
``apps/payment_recon/{analysis,filters,recon_filters,visuals,recon_visuals}.py``
with the typed tree primitives from ``common/tree/``. Sheets land one
per L.4 sub-step:

- L.4.1 — Getting Started (text boxes only, app-level skeleton)
- L.4.2 — Sales Overview
- L.4.3 — Settlements
- L.4.4 — Payments
- L.4.5 — Exceptions & Alerts
- L.4.6 — Payment Reconciliation tab (side-by-side mutual-filter pattern)
- L.4.7 — App-level wiring (datasets, parameters, drills, theme)

The minimal L.4.1 shape mirrors L.3.1 / L.2.1 — only Getting Started is
registered. Subsequent substeps add sheets and (when cross-sheet drills
land) switch to the pre-register-all-shells pattern AR adopted at L.3.2.
"""

from __future__ import annotations

# Importing datasets registers each PR DatasetContract via its
# module-level register_contract() side effect — required so the L.1.17
# bare-string / unvalidated-Column emit-time validator can resolve every
# ds["col"] ref in the visuals below.
from quicksight_gen.apps.payment_recon import datasets as _register_contracts  # noqa: F401
from quicksight_gen.apps.payment_recon.constants import (
    SHEET_GETTING_STARTED,
)
from quicksight_gen.common import rich_text as rt
from quicksight_gen.common.config import Config
from quicksight_gen.common.models import Analysis as ModelAnalysis
from quicksight_gen.common.models import Dashboard as ModelDashboard
from quicksight_gen.common.theme import get_preset
from quicksight_gen.common.tree import (
    Analysis,
    App,
    Sheet,
    TextBox,
)


# Layout constants mirror apps/payment_recon/analysis.py.
_FULL = 36


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
    accent_for_blocks = accent
    for box_id, title, body_text, bullet_items in sheet_blocks:
        sheet.layout.row(height=7).add_text_box(
            TextBox(
                text_box_id=box_id,
                content=_section_box_content(
                    title, body_text, bullet_items, accent_for_blocks,
                ),
            ),
            width=_FULL,
        )


# ---------------------------------------------------------------------------
# App entry points
# ---------------------------------------------------------------------------

def _analysis_name(cfg: Config) -> str:
    preset = get_preset(cfg.theme_preset)
    if preset.analysis_name_prefix:
        return f"{preset.analysis_name_prefix} — Payment Reconciliation"
    return "Payment Reconciliation"


def build_payment_recon_app(cfg: Config) -> App:
    """Construct the Payment Reconciliation App as a tree.

    L.4.1 lands only the Getting Started sheet; subsequent substeps add
    the pipeline sheets (Sales / Settlements / Payments / Exceptions /
    Payment Reconciliation) and app-level wiring.
    """
    app = App(name="payment-recon", cfg=cfg)
    analysis = app.set_analysis(Analysis(
        analysis_id_suffix="payment-recon-analysis",
        name=_analysis_name(cfg),
    ))

    gs = analysis.add_sheet(Sheet(
        sheet_id=SHEET_GETTING_STARTED,
        name="Getting Started",
        title="Getting Started",
        description=(
            "Landing page — summarises each tab in this dashboard so readers "
            "know where to look first. No filters or visuals."
        ),
    ))
    _populate_getting_started(cfg, gs)
    return app
