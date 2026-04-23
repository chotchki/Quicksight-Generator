"""Tree-based builder for the Account Reconciliation App (L.3 port).

Replaces the constant-heavy + manually-cross-referenced builders in
``apps/account_recon/{analysis,filters,visuals}.py`` with the typed
tree primitives from ``common/tree/``. Sheets land one per L.3 sub-step:

- L.3.1 — Getting Started (text boxes only, app-level skeleton)
- L.3.2 — Balances
- L.3.3 — Transfers
- L.3.4 — Transactions
- L.3.5 — Today's Exceptions (biggest single sheet — unified table +
  14 per-check filter groups + cross-sheet check-type control)
- L.3.6 — Exceptions Trends (3 cross-check rollups + per-check daily
  trend grid)
- L.3.7 — Daily Statement
- L.3.8 — App-level wiring (datasets, parameters, drills)
"""

from __future__ import annotations

from quicksight_gen.apps.account_recon.constants import (
    SHEET_AR_GETTING_STARTED,
)

# Importing datasets registers each AR DatasetContract via its
# module-level register_contract() side effect — required so the L.1.17
# bare-string / unvalidated-Column emit-time validator can resolve every
# ds["col"] ref in the visuals below.
from quicksight_gen.apps.account_recon import datasets as _register_contracts  # noqa: F401
from quicksight_gen.common import rich_text as rt
from quicksight_gen.common.config import Config
from quicksight_gen.common.theme import get_preset
from quicksight_gen.common.models import Analysis as ModelAnalysis
from quicksight_gen.common.models import Dashboard as ModelDashboard
from quicksight_gen.common.tree import (
    Analysis,
    App,
    Sheet,
    TextBox,
)


# Layout constants mirror apps/account_recon/analysis.py.
_FULL = 36


# ---------------------------------------------------------------------------
# Sheet descriptions — single source of truth, also surfaced in the
# Getting Started bullet blocks so the description on each sheet's
# scope matches the summary on the landing page.
# ---------------------------------------------------------------------------

_BALANCES_DESCRIPTION = (
    "Stored daily balances at both levels. Ledger table compares stored "
    "ledger balance to the sum of its sub-ledgers' stored balances; "
    "sub-ledger table compares each sub-ledger's stored balance to the "
    "running sum of posted transactions. Drift rows bubble up on the "
    "Exceptions tab."
)

_TRANSFERS_DESCRIPTION = (
    "Every transfer represented as a group of transactions sharing a "
    "transfer_id. Healthy transfers net to zero across non-failed legs; "
    "non-zero transfers indicate a keying error or a failed counter-leg."
)

_TRANSACTIONS_DESCRIPTION = (
    "Raw posting ledger — one row per leg. Includes both sub-ledger "
    "postings and direct ledger postings (funding batches, fees, sweeps). "
    "Filter by Posting Level to isolate ledger-level activity. Failed "
    "rows feed the non-zero transfer cases on Exceptions."
)

_TODAYS_EXCEPTIONS_DESCRIPTION = (
    "The 9am scan — every open exception across all 14 reconciliation "
    "checks in one unified table, sorted by severity then aging. Top KPI "
    "tracks total open count; the breakdown bar shows distribution by "
    "check type, coloured by severity. Filter by check, account, or age "
    "bucket; left-click a transfer_id to drill into Transactions."
)

_EXCEPTIONS_TRENDS_DESCRIPTION = (
    "The trend / rollup view paired with Today's Exceptions. Cross-check "
    "rollups at the top teach the SHAPE of recurring error classes — "
    "balance drift over time, two-sided posts where one side landed and "
    "the other didn't, control accounts that should be zero at EOD but "
    "aren't. Below: an aging-by-check matrix and a daily per-check trend "
    "so spikes line up across checks. Filters carry over from Today's "
    "Exceptions."
)

_DAILY_STATEMENT_DESCRIPTION = (
    "Per-account daily statement — pick one account and one day, and "
    "the sheet walks opening balance, debits, credits, stored closing, "
    "and drift, plus every posted leg. Drift = stored closing − "
    "(opening + Σ signed legs); on a clean feed it's zero, so a non-zero "
    "value is the single visual cue that the feed doesn't reconcile."
)


# Per-sheet highlights used to build bulleted summaries on the Getting
# Started tab.
_BALANCES_BULLETS = [
    "Ledger balances: stored ledger vs Σ sub-ledgers' stored balances",
    "Sub-ledger balances: stored sub-ledger vs Σ posted transactions",
    "Click an account to drill into its transactions",
]

_TRANSFERS_BULLETS = [
    "Transfer summary: one row per transfer_id",
    "Unhealthy transfers (non-zero net or failed legs) surface on Exceptions",
    "Click a transfer to drill into its underlying transactions",
]

_TRANSACTIONS_BULLETS = [
    "Raw ledger — one row per posting (sub-ledger and ledger-level)",
    "Filters: date range, transfer type, posting level, Show Only Failed",
    "Ledger-level postings: funding batches, fee assessments, clearing sweeps",
    "Failed rows feed the non-zero transfer cases on Exceptions",
]

_TODAYS_EXCEPTIONS_BULLETS = [
    "Total open count + breakdown by check (coloured by severity)",
    "Unified table — every open exception, sorted severity then aging",
    "Filter by check, account, or aging bucket",
    "Left-click a transfer_id to drill into Transactions",
]

_EXCEPTIONS_TRENDS_BULLETS = [
    "Drift Timelines rollup (CMS sweep + GL/Fed Master on one axis)",
    "Two-Sided Post Mismatch + Accounts Expected Zero rollups (KPI + table)",
    "Aging-by-Check matrix and per-check daily trend",
    "Filters propagate to/from Today's Exceptions",
]

_DAILY_STATEMENT_BULLETS = [
    "Pick one account + one day via the sheet's filter controls",
    "Five KPIs: Opening, Debits, Credits, Closing (stored), Drift",
    "Drift = stored closing − (opening + Σ signed legs); zero on a clean feed",
    "Detail table: every leg with direction, counter-account, memo, and transfer_id",
    "Intended as the feed-validation artifact the Data Integration Team can screenshot",
]


# ---------------------------------------------------------------------------
# Getting Started (L.3.1)
# ---------------------------------------------------------------------------

def _section_box_content(
    title: str, body: str, bullet_items: list[str], accent: str,
) -> str:
    """Per-sheet Getting Started block: heading + body paragraph + bullets."""
    return rt.text_box(
        rt.heading(title, color=accent),
        rt.BR,
        rt.BR,
        rt.body(body),
        rt.BR,
        rt.bullets(bullet_items),
    )


def _build_getting_started_sheet(cfg: Config, analysis: Analysis) -> Sheet:
    """Getting Started — landing page with welcome, nav tip, optional demo
    flavor, and one block per other sheet.

    Layout: vertical stack of full-width text boxes. No visuals, no
    controls, no filters. Mirror of the imperative
    ``_build_getting_started_sheet`` in ``analysis.py``.
    """
    accent = get_preset(cfg.theme_preset).accent
    is_demo = cfg.demo_database_url is not None

    sheet = analysis.add_sheet(Sheet(
        sheet_id=SHEET_AR_GETTING_STARTED,
        name="Getting Started",
        title="Getting Started",
        description=(
            "Landing page — summarises each tab in this dashboard so readers "
            "know where to look first. No filters or visuals."
        ),
    ))

    sheet.layout.row(height=5).add_text_box(
        TextBox(
            text_box_id="ar-gs-welcome",
            content=rt.text_box(
                rt.inline(
                    "Account Reconciliation Dashboard",
                    font_size="36px",
                    color=accent,
                ),
                rt.BR,
                rt.BR,
                rt.body(
                    "Reconcile stored daily balances at the ledger- and "
                    "sub-ledger account levels against their computed "
                    "counterparts, plus transfer-level transactions for a "
                    "bank's double-entry ledger. Walk from aggregate balances "
                    "down to individual transactions — the Exceptions tab "
                    "pulls the problems together in one place."
                ),
            ),
        ),
        width=_FULL,
    )
    sheet.layout.row(height=4).add_text_box(
        TextBox(
            text_box_id="ar-gs-nav-tip",
            content=rt.text_box(
                rt.heading("Navigation tip", color=accent),
                rt.BR,
                rt.BR,
                rt.bullets_raw([
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
        sheet.layout.row(height=14).add_text_box(
            TextBox(
                text_box_id="ar-gs-demo-flavor",
                content=rt.text_box(
                    rt.heading(
                        "Demo scenario — Sasquatch National Bank",
                        color=accent,
                    ),
                    rt.BR,
                    rt.BR,
                    rt.body(
                        "Sasquatch National Bank (SNB), a Pacific Northwest "
                        "community bank, recently absorbed Farmers Exchange "
                        "Bank's commercial book. SNB's general ledger has "
                        "eight internal control accounts (Cash & Due From "
                        "FRB, ACH Origination Settlement, Card Acquiring "
                        "Settlement, Wire Settlement Suspense, Internal "
                        "Transfer Suspense, Cash Concentration Master, "
                        "Internal Suspense / Reconciliation, and Customer "
                        "Deposits — DDA Control) plus per-customer DDAs for "
                        "three coffee retailers (Bigfoot Brews, Sasquatch "
                        "Sips, Yeti Espresso) and four commercial customers "
                        "(Cascade Timber Mill, Pinecrest Vineyards, Big "
                        "Meadow Dairy, Harvest Moon Bakery)."
                    ),
                    rt.BR,
                    rt.BR,
                    rt.body(
                        "SNB's Cash Management Suite drives four telling "
                        "transfer flows: ZBA / Cash Concentration sweeps "
                        "(operating sub-accounts sweep to the master at "
                        "EOD), daily ACH origination sweeps to the FRB "
                        "Master Account, external force-posted card "
                        "settlements that internal books must catch up to, "
                        "and on-us internal transfers routed through the "
                        "Internal Transfer Suspense account. Each flow is "
                        "planted with both success cycles and characteristic "
                        "failure modes — sweep target non-zero, missing Fed "
                        "confirmation, force-post without internal catch-up, "
                        "stuck-in-suspense, reversed-but-not-credited."
                    ),
                    rt.BR,
                    rt.BR,
                    rt.body(
                        "Ledger and sub-ledger stored balances also carry "
                        "disjoint planted drift, plus a handful of off-amount "
                        "transfers, failed legs, limit breaches, and "
                        "overdrafts — so every Exceptions check surfaces "
                        "distinct rows. The Exceptions tab leads with "
                        "cross-check rollups so you learn to spot the same "
                        "SHAPE of error across multiple accounts."
                    ),
                    rt.BR,
                    rt.BR,
                    rt.body(
                        "AR is the unified view of SNB's shared ledger — "
                        "Payment Reconciliation's merchant DDAs (the same "
                        "coffee retailers' acquiring side) and external-rail "
                        "settlement account surface here too, alongside the "
                        "CMS accounts above. Use the Ledger and Sub-Ledger "
                        "pickers to scope your view if you want CMS-only."
                    ),
                    rt.BR,
                    rt.BR,
                    rt.body(
                        "Data is deterministic — anchor date is the day the "
                        "seed was generated. Explore the date-range, "
                        "transfer-type, posting-level, origin, and "
                        "show-only toggles to see how each tab responds."
                    ),
                ),
            ),
            width=_FULL,
        )

    sheet_blocks = [
        (
            "ar-gs-balances", "Balances",
            _BALANCES_DESCRIPTION, _BALANCES_BULLETS,
        ),
        (
            "ar-gs-transfers", "Transfers",
            _TRANSFERS_DESCRIPTION, _TRANSFERS_BULLETS,
        ),
        (
            "ar-gs-transactions", "Transactions",
            _TRANSACTIONS_DESCRIPTION, _TRANSACTIONS_BULLETS,
        ),
        (
            "ar-gs-todays-exceptions", "Today's Exceptions",
            _TODAYS_EXCEPTIONS_DESCRIPTION, _TODAYS_EXCEPTIONS_BULLETS,
        ),
        (
            "ar-gs-exceptions-trends", "Exceptions Trends",
            _EXCEPTIONS_TRENDS_DESCRIPTION, _EXCEPTIONS_TRENDS_BULLETS,
        ),
        (
            "ar-gs-daily-statement", "Daily Statement",
            _DAILY_STATEMENT_DESCRIPTION, _DAILY_STATEMENT_BULLETS,
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

    return sheet


# ---------------------------------------------------------------------------
# App-level wiring (L.3.8 lands the rest; L.3.1 stub builds Getting
# Started only so we can land the byte-identity skeleton).
# ---------------------------------------------------------------------------

def _analysis_name(cfg: Config) -> str:
    preset = get_preset(cfg.theme_preset)
    if preset.analysis_name_prefix:
        return f"{preset.analysis_name_prefix} — Account Reconciliation"
    return "Account Reconciliation"


def build_account_recon_app(cfg: Config) -> App:
    """Construct the Account Reconciliation App as a tree.

    Returns the App ready for ``app.emit_analysis()`` /
    ``app.emit_dashboard()``. Mid-port: only Getting Started is wired
    in L.3.1; subsequent sub-steps add the other six sheets.
    """
    app = App(name="account-recon", cfg=cfg)
    analysis = app.set_analysis(Analysis(
        analysis_id_suffix="account-recon-analysis",
        name=_analysis_name(cfg),
    ))
    _build_getting_started_sheet(cfg, analysis)
    app.create_dashboard(
        dashboard_id_suffix="account-recon-dashboard",
        name=_analysis_name(cfg),
    )
    return app
