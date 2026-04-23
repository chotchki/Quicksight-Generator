"""Tree-based builder for the Account Reconciliation App (L.3 port).

Replaces the constant-heavy + manually-cross-referenced builders in
``apps/account_recon/{analysis,filters,visuals}.py`` with the typed
tree primitives from ``common/tree/``. Sheets land one per L.3 sub-step:

- L.3.1 — Getting Started (text boxes only)
- L.3.2 — Balances (KPIs + ledger / sub-ledger drift tables + drills)
- L.3.3 — Transfers
- L.3.4 — Transactions
- L.3.5 — Today's Exceptions
- L.3.6 — Exceptions Trends
- L.3.7 — Daily Statement
- L.3.8 — App-level wiring (parameters, filter groups, filter controls,
  cross-sheet drill plumbing)

**Pre-registered sheet shells.** AR's drill actions cross-reference
sheets (Balances → Transactions, Balances → Daily Statement, etc.).
Rather than ordering substeps by dependency, ``build_account_recon_app``
pre-registers all 7 ``Sheet`` shells (in display order) up-front so any
populator can construct a ``Drill(target_sheet=other_sheet, ...)``
referencing any other shell. Unported sheets emit as bare shells (id +
metadata only); the per-sheet byte-identity tests target their sheet
by id, so unported shells don't pollute the tested surface.
"""

from __future__ import annotations

from dataclasses import dataclass

from quicksight_gen.apps.account_recon.constants import (
    DS_AR_LEDGER_ACCOUNTS,
    DS_AR_LEDGER_BALANCE_DRIFT,
    DS_AR_NON_ZERO_TRANSFERS,
    DS_AR_SUBLEDGER_ACCOUNTS,
    DS_AR_SUBLEDGER_BALANCE_DRIFT,
    DS_AR_BALANCE_DRIFT_TIMELINES_ROLLUP,
    DS_AR_DAILY_STATEMENT_SUMMARY,
    DS_AR_DAILY_STATEMENT_TRANSACTIONS,
    DS_AR_EXPECTED_ZERO_EOD_ROLLUP,
    DS_AR_TRANSACTIONS,
    DS_AR_TRANSFER_SUMMARY,
    DS_AR_TWO_SIDED_POST_MISMATCH_ROLLUP,
    DS_AR_UNIFIED_EXCEPTIONS,
    FG_AR_BALANCES_LEDGER_DRIFT,
    FG_AR_BALANCES_OVERDRAFT,
    FG_AR_BALANCES_SUBLEDGER_DRIFT,
    FG_AR_DATE_RANGE,
    FG_AR_DRILL_ACCOUNT_ON_TXN,
    FG_AR_DRILL_ACTIVITY_DATE_ON_TXN,
    FG_AR_DRILL_LEDGER_ON_BALANCES_SUBLEDGER,
    FG_AR_DRILL_SUBLEDGER_ON_TXN,
    FG_AR_DRILL_TRANSFER_ON_TXN,
    FG_AR_DRILL_TRANSFER_TYPE_ON_TXN,
    FG_AR_DS_ACCOUNT,
    FG_AR_DS_BALANCE_DATE,
    FG_AR_LEDGER_ACCOUNT,
    FG_AR_ORIGIN,
    FG_AR_POSTING_LEVEL,
    FG_AR_SUBLEDGER_ACCOUNT,
    FG_AR_TODAYS_EXC_ACCOUNT,
    FG_AR_TODAYS_EXC_AGING,
    FG_AR_TODAYS_EXC_CHECK_TYPE,
    FG_AR_TODAYS_EXC_IS_LATE,
    FG_AR_TRANSACTION_STATUS,
    FG_AR_TRANSACTIONS_FAILED,
    FG_AR_TRANSFER_STATUS,
    FG_AR_TRANSFER_TYPE,
    P_AR_ACCOUNT,
    P_AR_ACTIVITY_DATE,
    P_AR_DS_ACCOUNT,
    P_AR_DS_BALANCE_DATE,
    P_AR_LEDGER,
    P_AR_SUBLEDGER,
    P_AR_TRANSFER,
    P_AR_TRANSFER_TYPE,
    SHEET_AR_BALANCES,
    SHEET_AR_DAILY_STATEMENT,
    SHEET_AR_EXCEPTIONS_TRENDS,
    SHEET_AR_GETTING_STARTED,
    SHEET_AR_TODAYS_EXCEPTIONS,
    SHEET_AR_TRANSACTIONS,
    SHEET_AR_TRANSFERS,
)

# Importing datasets registers each AR DatasetContract via its
# module-level register_contract() side effect — required so the L.1.17
# bare-string / unvalidated-Column emit-time validator can resolve every
# ds["col"] ref in the visuals below.
from quicksight_gen.apps.account_recon import datasets as _register_contracts  # noqa: F401
from quicksight_gen.common import rich_text as rt
from quicksight_gen.common.config import Config
from quicksight_gen.common.theme import get_preset
from quicksight_gen.common.ids import ParameterName
from quicksight_gen.common.models import DateTimeDefaultValues
from quicksight_gen.common.tree._helpers import _AutoSentinel
from quicksight_gen.common.tree import (
    Analysis,
    App,
    CalcField,
    CategoryFilter,
    CellAccentMenu,
    CellAccentText,
    DateTimeParam,
    Dataset,
    DefaultDateTimePickerControl,
    DefaultDropdownControl,
    Drill,
    DrillResetSentinel,
    DrillSourceField,
    FilterGroup,
    SameSheetFilter,
    Sheet,
    StringParam,
    TextBox,
    TimeEqualityFilter,
    TimeRangeFilter,
)


# ---------------------------------------------------------------------------
# Layout constants — mirror apps/account_recon/analysis.py.
# ---------------------------------------------------------------------------

_FULL = 36
_HALF = 18
_KPI_ROW_SPAN = 6
_CHART_ROW_SPAN = 12
_TABLE_ROW_SPAN = 18


# ---------------------------------------------------------------------------
# Dataset refs. Registered on the App in build_account_recon_app; the
# populators reference them by Python variable. The Dataset arn is
# computed from cfg.dataset_arn(identifier) so the tree-built JSON
# matches the imperative DataSetIdentifierDeclarations.
# ---------------------------------------------------------------------------

def _datasets(cfg: Config) -> dict[str, Dataset]:
    """Map each AR logical dataset identifier to a typed `Dataset` ref.

    Order matches `build_all_datasets`: the QuickSight DataSetId for
    each dataset (e.g. ``qs-gen-ar-ledger-accounts-dataset``) becomes
    the path component of the dataset's ARN. The Analysis JSON's
    `DataSetIdentifierDeclarations` maps the logical identifier (used
    in visuals + filter columns) → the ARN (the deployed DataSet's
    cross-account-stable handle).
    """
    from quicksight_gen.apps.account_recon.datasets import build_all_datasets

    # Order must mirror `_build_dataset_declarations` in analysis.py
    # so each logical name lines up with the matching DataSet's
    # DataSetId at the same index.
    names = [
        DS_AR_LEDGER_ACCOUNTS,
        DS_AR_SUBLEDGER_ACCOUNTS,
        DS_AR_TRANSACTIONS,
        DS_AR_LEDGER_BALANCE_DRIFT,
        DS_AR_SUBLEDGER_BALANCE_DRIFT,
        DS_AR_TRANSFER_SUMMARY,
        DS_AR_NON_ZERO_TRANSFERS,
        DS_AR_EXPECTED_ZERO_EOD_ROLLUP,
        DS_AR_TWO_SIDED_POST_MISMATCH_ROLLUP,
        DS_AR_BALANCE_DRIFT_TIMELINES_ROLLUP,
        DS_AR_DAILY_STATEMENT_SUMMARY,
        DS_AR_DAILY_STATEMENT_TRANSACTIONS,
        DS_AR_UNIFIED_EXCEPTIONS,
    ]
    built = build_all_datasets(cfg)
    return {
        name: Dataset(identifier=name, arn=cfg.dataset_arn(ds.DataSetId))
        for name, ds in zip(names, built)
    }


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
# Drill-helper: AR cross-sheet drill into Transactions with stale-param
# auto-reset (mirror of apps/account_recon/visuals._ar_drill_to_transactions).
# Caller writes only the params that should narrow Transactions; every
# other PASS-filtered param the caller doesn't write is auto-reset to
# DrillResetSentinel so a prior drill's value can't leak through.
# ---------------------------------------------------------------------------

_AR_TXN_PASS_FILTERED_PARAMS = (
    P_AR_SUBLEDGER,
    P_AR_TRANSFER,
    P_AR_ACTIVITY_DATE,
    P_AR_TRANSFER_TYPE,
    P_AR_ACCOUNT,
)


def _ar_drill_to_transactions(
    *,
    target_sheet: Sheet,
    name: str,
    writes: list[tuple],
    trigger: str = "DATA_POINT_CLICK",
    action_id: str | None = None,
) -> Drill:
    """Cross-sheet drill into Transactions with full stale-param coverage."""
    written = {param.name for param, _ in writes}
    full_writes = list(writes)
    for param in _AR_TXN_PASS_FILTERED_PARAMS:
        if param.name not in written:
            full_writes.append((param, DrillResetSentinel()))
    return Drill(
        target_sheet=target_sheet,
        writes=full_writes,
        name=name,
        trigger=trigger,  # type: ignore[arg-type]
        action_id=action_id if action_id is not None else "auto",
    )


# ---------------------------------------------------------------------------
# Getting Started (L.3.1)
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
        ("ar-gs-balances", "Balances",
         _BALANCES_DESCRIPTION, _BALANCES_BULLETS),
        ("ar-gs-transfers", "Transfers",
         _TRANSFERS_DESCRIPTION, _TRANSFERS_BULLETS),
        ("ar-gs-transactions", "Transactions",
         _TRANSACTIONS_DESCRIPTION, _TRANSACTIONS_BULLETS),
        ("ar-gs-todays-exceptions", "Today's Exceptions",
         _TODAYS_EXCEPTIONS_DESCRIPTION, _TODAYS_EXCEPTIONS_BULLETS),
        ("ar-gs-exceptions-trends", "Exceptions Trends",
         _EXCEPTIONS_TRENDS_DESCRIPTION, _EXCEPTIONS_TRENDS_BULLETS),
        ("ar-gs-daily-statement", "Daily Statement",
         _DAILY_STATEMENT_DESCRIPTION, _DAILY_STATEMENT_BULLETS),
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
# Balances (L.3.2) — KPIs + ledger / sub-ledger drift tables with drills
# ---------------------------------------------------------------------------

def _populate_balances(
    cfg: Config,
    sheet: Sheet,
    *,
    transactions_sheet: Sheet,
    daily_statement_sheet: Sheet,
    datasets: dict[str, Dataset],
) -> None:
    """Balances tab — 2 KPIs, ledger drift table, sub-ledger drift table.

    Drill plumbing:
    - Ledger table → same-sheet right-click writes P_AR_LEDGER (filters
      sub-ledger table below via the L.3.8 filter group).
    - Sub-ledger table → left-click drills to Transactions writing
      P_AR_SUBLEDGER (with stale-param reset); right-click drills to
      Daily Statement writing P_AR_DS_ACCOUNT + P_AR_DS_BALANCE_DATE.
    """
    preset = get_preset(cfg.theme_preset)
    link_color = preset.accent
    link_tint = preset.link_tint

    ds_ledger = datasets[DS_AR_LEDGER_ACCOUNTS]
    ds_subledger = datasets[DS_AR_SUBLEDGER_ACCOUNTS]
    ds_ledger_drift = datasets[DS_AR_LEDGER_BALANCE_DRIFT]
    ds_subledger_drift = datasets[DS_AR_SUBLEDGER_BALANCE_DRIFT]

    # Row 1: two KPIs side-by-side.
    half = _FULL // 2
    kpi_row = sheet.layout.row(height=_KPI_ROW_SPAN)
    kpi_row.add_kpi(
        width=half,
        visual_id="ar-balances-kpi-ledgers",  # type: ignore[arg-type]
        title="Ledger Accounts",
        subtitle="Count of ledger accounts (internal + external)",
        values=[ds_ledger["ledger_account_id"].count(
            field_id="ar-balances-ledger-count",
        )],
    )
    kpi_row.add_kpi(
        width=half,
        visual_id="ar-balances-kpi-subledgers",  # type: ignore[arg-type]
        title="Sub-Ledger Accounts",
        subtitle="Count of individual sub-ledger accounts under all ledgers",
        values=[ds_subledger["subledger_account_id"].count(
            field_id="ar-balances-subledger-count",
        )],
    )

    # Row 2: ledger drift table (full width, unaggregated). Hoist the
    # ledger-id Dim to a local var so the right-click CF + drill action
    # both reference the same field_id.
    ledger_id_col = ds_ledger_drift["ledger_account_id"].dim(field_id="ar-bal-ledger-id")
    sheet.layout.row(height=_TABLE_ROW_SPAN).add_table(
        width=_FULL,
        visual_id="ar-balances-ledger-table",  # type: ignore[arg-type]
        title="Ledger Account Balances",
        subtitle=(
            "Each ledger account's stored vs computed daily balance. "
            "Computed = Σ of its sub-ledgers' stored balances. "
            "Right-click a ledger_account_id to filter the sub-ledger "
            "table below to that ledger's sub-ledgers."
        ),
        columns=[
            ledger_id_col,
            ds_ledger_drift["ledger_name"].dim(field_id="ar-bal-ledger-name"),
            ds_ledger_drift["scope"].dim(field_id="ar-bal-scope"),
            ds_ledger_drift["balance_date"].date(field_id="ar-bal-date"),
            ds_ledger_drift["stored_balance"].numerical(field_id="ar-bal-stored"),
            ds_ledger_drift["computed_balance"].numerical(field_id="ar-bal-computed"),
            ds_ledger_drift["drift"].numerical(field_id="ar-bal-drift"),
        ],
        sort_by=("ar-bal-date", "DESC"),
        actions=[
            # Same-sheet right-click drill — writes P_AR_LEDGER, then a
            # FilterGroup (declared in L.3.8) scoped to the sub-ledger
            # table only filters that visual.
            Drill(
                target_sheet=sheet,
                writes=[(
                    P_AR_LEDGER,
                    DrillSourceField(
                        field_id="ar-bal-ledger-id",
                        shape=P_AR_LEDGER.shape,
                    ),
                )],
                name="Filter Sub-Ledger Accounts Below",
                trigger="DATA_POINT_MENU",
                action_id="action-ar-balances-filter-subledgers",
            ),
        ],
        conditional_formatting=[
            CellAccentMenu(
                on=ledger_id_col,
                text_color=link_color, background_color=link_tint,
            ),
        ],
    )

    # Row 3: sub-ledger drift table (full width, unaggregated, two drills).
    subledger_id_col = ds_subledger_drift["subledger_account_id"].dim(field_id="ar-bal-subledger-id")
    sheet.layout.row(height=_TABLE_ROW_SPAN).add_table(
        width=_FULL,
        visual_id="ar-balances-subledger-table",  # type: ignore[arg-type]
        title="Sub-Ledger Account Balances",
        subtitle=(
            "Each sub-ledger account's stored vs computed daily balance. "
            "Computed = running Σ of posted transactions. Left-click a "
            "subledger_account_id to drill left into Transactions for "
            "that sub-ledger; right-click to drill right into the Daily "
            "Statement for that account-day."
        ),
        columns=[
            subledger_id_col,
            ds_subledger_drift["subledger_name"].dim(field_id="ar-bal-subledger-name"),
            ds_subledger_drift["ledger_name"].dim(field_id="ar-bal-subledger-ledger"),
            ds_subledger_drift["scope"].dim(field_id="ar-bal-subledger-scope"),
            ds_subledger_drift["balance_date"].date(field_id="ar-bal-subledger-date"),
            ds_subledger_drift["stored_balance"].numerical(field_id="ar-bal-subledger-stored"),
            ds_subledger_drift["computed_balance"].numerical(field_id="ar-bal-subledger-computed"),
            ds_subledger_drift["drift"].numerical(field_id="ar-bal-subledger-drift"),
        ],
        sort_by=("ar-bal-subledger-date", "DESC"),
        actions=[
            _ar_drill_to_transactions(
                target_sheet=transactions_sheet,
                name="View Transactions",
                writes=[(
                    P_AR_SUBLEDGER,
                    DrillSourceField(
                        field_id="ar-bal-subledger-id",
                        shape=P_AR_SUBLEDGER.shape,
                    ),
                )],
                action_id="action-ar-balances-subledger-to-txn",
            ),
            Drill(
                target_sheet=daily_statement_sheet,
                writes=[
                    (P_AR_DS_ACCOUNT, DrillSourceField(
                        field_id="ar-bal-subledger-id",
                        shape=P_AR_DS_ACCOUNT.shape,
                    )),
                    (P_AR_DS_BALANCE_DATE, DrillSourceField(
                        field_id="ar-bal-subledger-date",
                        shape=P_AR_DS_BALANCE_DATE.shape,
                    )),
                ],
                name="View Daily Statement",
                trigger="DATA_POINT_MENU",
                action_id="action-ar-balances-subledger-to-daily-statement",
            ),
        ],
        conditional_formatting=[
            CellAccentMenu(
                on=subledger_id_col,
                text_color=link_color, background_color=link_tint,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Transfers (L.3.3) — KPIs + status bar (with same-sheet click filter) +
# transfer summary table (with cross-sheet drill to Transactions).
# ---------------------------------------------------------------------------

def _populate_transfers(
    cfg: Config,
    sheet: Sheet,
    *,
    transactions_sheet: Sheet,
    datasets: dict[str, Dataset],
) -> None:
    preset = get_preset(cfg.theme_preset)
    link_color = preset.accent

    ds_xfr = datasets[DS_AR_TRANSFER_SUMMARY]
    ds_nzt = datasets[DS_AR_NON_ZERO_TRANSFERS]

    # Row 1: two KPIs side-by-side.
    half = _FULL // 2
    kpi_row = sheet.layout.row(height=_KPI_ROW_SPAN)
    kpi_row.add_kpi(
        width=half,
        visual_id="ar-transfers-kpi-count",  # type: ignore[arg-type]
        title="Total Transfers",
        subtitle="Count of transfers across all statuses",
        values=[ds_xfr["transfer_id"].count(field_id="ar-transfers-count")],
    )
    kpi_row.add_kpi(
        width=half,
        visual_id="ar-transfers-kpi-unhealthy",  # type: ignore[arg-type]
        title="Non-Zero Transfers",
        subtitle=(
            "Transfers whose non-failed legs don't sum to zero — the "
            "ledger is out of balance for these"
        ),
        values=[ds_nzt["transfer_id"].count(field_id="ar-transfers-unhealthy")],
    )

    # Row 2: status bar chart (full width). Click-to-filter targets the
    # summary table in row 3. We need bar BEFORE table in Visuals[]
    # ordering (matches imperative declaration order) but the
    # SameSheetFilter has to ref the table object. Solution: construct
    # the filter action with an empty target_visuals list, attach it
    # to the bar, then append the table to the action's list once it
    # exists. The action only resolves target_visuals' visual_ids at
    # emit time — by then the list is populated.
    filter_action = SameSheetFilter(
        target_visuals=[],
        name="Filter Transfer Summary",
        action_id="action-ar-transfers-bar-filter",
    )
    sheet.layout.row(height=_CHART_ROW_SPAN).add_bar_chart(
        width=_FULL,
        visual_id="ar-transfers-bar-status",  # type: ignore[arg-type]
        title="Transfer Status",
        subtitle=(
            "Count of transfers by net-zero status. Click a bar to "
            "filter the summary table below."
        ),
        category=[ds_xfr["net_zero_status"].dim(field_id="ar-xfr-status-dim")],
        values=[ds_xfr["transfer_id"].count(field_id="ar-xfr-status-count")],
        orientation="HORIZONTAL",
        bars_arrangement="CLUSTERED",
        category_label="Status",
        value_label="Transfers",
        actions=[filter_action],
    )

    # Row 3: transfer summary table (full width).
    transfer_id_col = ds_xfr["transfer_id"].dim(field_id="ar-xfr-id")
    table_transfers = sheet.layout.row(height=_TABLE_ROW_SPAN).add_table(
        width=_FULL,
        visual_id="ar-transfers-summary-table",  # type: ignore[arg-type]
        title="Transfer Summary",
        subtitle=(
            "Every transfer with its net amount, debit/credit totals, "
            "leg count, and net-zero status. Left-click a transfer_id "
            "to drill into Transactions for that transfer."
        ),
        columns=[
            transfer_id_col,
            ds_xfr["first_posted_at"].date(field_id="ar-xfr-posted"),
            ds_xfr["total_debit"].numerical(field_id="ar-xfr-debit"),
            ds_xfr["total_credit"].numerical(field_id="ar-xfr-credit"),
            ds_xfr["net_amount"].numerical(field_id="ar-xfr-net"),
            ds_xfr["net_zero_status"].dim(field_id="ar-xfr-status"),
            ds_xfr["scope_type"].dim(field_id="ar-xfr-scope"),
            ds_xfr["failed_leg_count"].numerical(field_id="ar-xfr-failed-legs"),
            ds_xfr["memo"].dim(field_id="ar-xfr-memo"),
        ],
        sort_by=("ar-xfr-posted", "DESC"),
        actions=[
            _ar_drill_to_transactions(
                target_sheet=transactions_sheet,
                name="View Transactions",
                writes=[(
                    P_AR_TRANSFER,
                    DrillSourceField(
                        field_id="ar-xfr-id",
                        shape=P_AR_TRANSFER.shape,
                    ),
                )],
                action_id="action-ar-transfers-to-txn",
            ),
        ],
        conditional_formatting=[
            CellAccentText(on=transfer_id_col, color=link_color),
        ],
    )
    # Back-patch the bar's filter action now that the table exists.
    filter_action.target_visuals.append(table_transfers)


# ---------------------------------------------------------------------------
# Transactions (L.3.4) — KPIs + 2 bar charts (with same-sheet click
# filter on each) + detail unaggregated table. No drill actions on the
# table — Transactions is the destination of every other sheet's drill.
# ---------------------------------------------------------------------------

def _populate_transactions(
    cfg: Config,
    sheet: Sheet,
    *,
    datasets: dict[str, Dataset],
) -> None:
    del cfg
    ds_txn = datasets[DS_AR_TRANSACTIONS]

    # Row 1: two KPIs.
    half = _FULL // 2
    kpi_row = sheet.layout.row(height=_KPI_ROW_SPAN)
    kpi_row.add_kpi(
        width=half,
        visual_id="ar-txn-kpi-count",  # type: ignore[arg-type]
        title="Total Transactions",
        subtitle="Count of all transactions (all statuses)",
        values=[ds_txn["transaction_id"].count(field_id="ar-txn-count")],
    )
    kpi_row.add_kpi(
        width=half,
        visual_id="ar-txn-kpi-failed",  # type: ignore[arg-type]
        title="Failed Transactions",
        subtitle=(
            "Transactions that did not post — money never moved. "
            "Contributes to non-zero transfers upstream."
        ),
        values=[ds_txn["transaction_id"].count(field_id="ar-txn-failed-count")],
    )

    # Two bar charts in row 2 (status horizontal + day vertical), each
    # with a same-sheet filter targeting the detail table in row 3.
    # Same back-patch trick as Transfers — construct the filter actions
    # with empty target_visuals, attach to bars, append the table after.
    status_filter = SameSheetFilter(
        target_visuals=[],
        name="Filter Transaction Detail",
        action_id="action-ar-txn-bar-filter",
    )
    day_filter = SameSheetFilter(
        target_visuals=[],
        name="Filter Transaction Detail",
        action_id="action-ar-txn-day-filter",
    )

    chart_row = sheet.layout.row(height=_CHART_ROW_SPAN)
    chart_row.add_bar_chart(
        width=_HALF,
        visual_id="ar-txn-bar-by-status",  # type: ignore[arg-type]
        title="Transactions by Status",
        subtitle=(
            "Breakdown of posted / pending / failed transactions. "
            "Click a bar to filter the detail table below."
        ),
        category=[ds_txn["status"].dim(field_id="ar-txn-status-dim")],
        values=[ds_txn["transaction_id"].count(field_id="ar-txn-status-count")],
        orientation="HORIZONTAL",
        bars_arrangement="CLUSTERED",
        category_label="Status",
        value_label="Transactions",
        actions=[status_filter],
    )
    chart_row.add_bar_chart(
        width=_HALF,
        visual_id="ar-txn-bar-by-day",  # type: ignore[arg-type]
        title="Transactions by Day",
        subtitle=(
            "Daily transaction volume split by status. Click a bar to "
            "filter the detail table below."
        ),
        category=[ds_txn["posted_at"].date(field_id="ar-txn-day-dim")],
        values=[ds_txn["transaction_id"].count(field_id="ar-txn-day-count")],
        colors=[ds_txn["status"].dim(field_id="ar-txn-day-color")],
        orientation="VERTICAL",
        bars_arrangement="STACKED",
        category_label="Date",
        value_label="Transactions",
        color_label="Status",
        actions=[day_filter],
    )

    # Row 3: detail table — full width unaggregated, no actions.
    table_txn = sheet.layout.row(height=_TABLE_ROW_SPAN).add_table(
        width=_FULL,
        visual_id="ar-txn-detail-table",  # type: ignore[arg-type]
        title="Transaction Detail",
        subtitle=(
            "Every leg of every transfer — newest first. Failed rows "
            "indicate legs that did not post."
        ),
        columns=[
            ds_txn["transaction_id"].dim(field_id="ar-txn-id"),
            ds_txn["transfer_id"].dim(field_id="ar-txn-transfer"),
            ds_txn["ledger_name"].dim(field_id="ar-txn-ledger"),
            ds_txn["subledger_name"].dim(field_id="ar-txn-subledger"),
            ds_txn["scope"].dim(field_id="ar-txn-scope"),
            ds_txn["posting_level"].dim(field_id="ar-txn-posting-level"),
            ds_txn["origin"].dim(field_id="ar-txn-origin"),
            ds_txn["amount"].numerical(field_id="ar-txn-amount"),
            ds_txn["status"].dim(field_id="ar-txn-status"),
            ds_txn["posted_at"].date(field_id="ar-txn-posted"),
            ds_txn["memo"].dim(field_id="ar-txn-memo"),
        ],
        sort_by=("ar-txn-posted", "DESC"),
    )
    # Back-patch both filters to point at the detail table.
    status_filter.target_visuals.append(table_txn)
    day_filter.target_visuals.append(table_txn)


# ---------------------------------------------------------------------------
# Today's Exceptions (L.3.5) — KPI + breakdown bar (with same-sheet
# click filter) + unified exception table (with 2 cross-sheet drills
# + 2 CF entries).
# ---------------------------------------------------------------------------

def _populate_todays_exceptions(
    cfg: Config,
    sheet: Sheet,
    *,
    transactions_sheet: Sheet,
    datasets: dict[str, Dataset],
) -> None:
    preset = get_preset(cfg.theme_preset)
    link_color = preset.accent
    link_tint = preset.link_tint

    ds_exc = datasets[DS_AR_UNIFIED_EXCEPTIONS]

    # Row 1: KPI (full width).
    sheet.layout.row(height=_KPI_ROW_SPAN).add_kpi(
        width=_FULL,
        visual_id="ar-todays-exc-kpi-total",  # type: ignore[arg-type]
        title="Total Exceptions",
        subtitle=(
            "Count of open exception rows across all 14 reconciliation "
            "checks. Use the breakdown below to triage by check type "
            "and severity."
        ),
        values=[ds_exc["check_type"].count(field_id="ar-todays-exc-total-count")],
    )

    # Row 2: breakdown bar (full width). Click-to-filter the table below.
    breakdown_filter = SameSheetFilter(
        target_visuals=[],
        name="Filter Exceptions Table",
        action_id="action-ar-todays-exc-bar-filter",
    )
    sheet.layout.row(height=_CHART_ROW_SPAN).add_bar_chart(
        width=_FULL,
        visual_id="ar-todays-exc-breakdown",  # type: ignore[arg-type]
        title="Exceptions by Check",
        subtitle=(
            "Count of open exceptions per check type, coloured by "
            "severity (red = drift / overdraft, orange = expected-zero, "
            "amber = limit-breach, yellow = other). Click a bar to "
            "filter the table below to that check type."
        ),
        category=[ds_exc["check_type"].dim(field_id="ar-todays-exc-check-dim")],
        values=[ds_exc["check_type"].count(field_id="ar-todays-exc-check-count")],
        colors=[ds_exc["severity"].dim(field_id="ar-todays-exc-severity-color")],
        orientation="HORIZONTAL",
        bars_arrangement="STACKED",
        category_label="Check",
        value_label="Exceptions",
        color_label="Severity",
        actions=[breakdown_filter],
    )

    # Row 3: unified table — full width unaggregated, two drills + 2 CF.
    # Hoist the two drill-source / CF-target columns to local vars so
    # the cell formats reference the same Dim objects as the columns
    # list (typed binding, no field_id string drift).
    transfer_id_col = ds_exc["transfer_id"].dim(field_id="ar-todays-exc-transfer-id")
    account_id_col = ds_exc["account_id"].dim(field_id="ar-todays-exc-account")
    table_exc = sheet.layout.row(height=_TABLE_ROW_SPAN).add_table(
        width=_FULL,
        visual_id="ar-todays-exc-table",  # type: ignore[arg-type]
        title="Open Exceptions",
        subtitle=(
            "Every open exception row across all 14 checks, sorted by "
            "severity then aging. Left-click a transfer_id to drill into "
            "Transactions for that transfer; right-click an account_id "
            "to drill into Transactions for that account-day. The two "
            "system-level drift rollups (concentration master sweep, GL "
            "vs Fed master) carry neither value — investigate them on "
            "the Trends sheet."
        ),
        columns=[
            ds_exc["check_type"].dim(field_id="ar-todays-exc-check"),
            ds_exc["severity"].dim(field_id="ar-todays-exc-severity"),
            # K.2: bind the FieldId to the YYYY-MM-DD string projection
            # (not the DATETIME exception_date) so the drill SourceField
            # writes pArActivityDate in a format the destination's
            # posted_date filter can match.
            ds_exc["exception_date_str"].dim(field_id="ar-todays-exc-date"),
            ds_exc["aging_bucket"].dim(field_id="ar-todays-exc-age"),
            ds_exc["days_outstanding"].numerical(field_id="ar-todays-exc-days"),
            # K.3.3: data-driven Late / On Time label.
            ds_exc["is_late"].dim(field_id="ar-todays-exc-is-late"),
            account_id_col,
            ds_exc["account_name"].dim(field_id="ar-todays-exc-account-name"),
            ds_exc["account_level"].dim(field_id="ar-todays-exc-account-level"),
            ds_exc["ledger_name"].dim(field_id="ar-todays-exc-ledger"),
            transfer_id_col,
            ds_exc["transfer_type"].dim(field_id="ar-todays-exc-transfer-type"),
            ds_exc["primary_amount"].numerical(field_id="ar-todays-exc-primary"),
            ds_exc["secondary_amount"].numerical(field_id="ar-todays-exc-secondary"),
        ],
        sort_by=[
            ("ar-todays-exc-severity", "ASC"),
            ("ar-todays-exc-days", "DESC"),
        ],
        actions=[
            _ar_drill_to_transactions(
                target_sheet=transactions_sheet,
                name="View Transactions",
                writes=[(
                    P_AR_TRANSFER,
                    DrillSourceField(
                        field_id="ar-todays-exc-transfer-id",
                        shape=P_AR_TRANSFER.shape,
                    ),
                )],
                action_id="action-ar-todays-exc-to-txn",
            ),
            _ar_drill_to_transactions(
                target_sheet=transactions_sheet,
                name="View Transactions for Account-Day",
                writes=[
                    (P_AR_ACCOUNT, DrillSourceField(
                        field_id="ar-todays-exc-account",
                        shape=P_AR_ACCOUNT.shape,
                    )),
                    (P_AR_ACTIVITY_DATE, DrillSourceField(
                        field_id="ar-todays-exc-date",
                        shape=P_AR_ACTIVITY_DATE.shape,
                    )),
                ],
                trigger="DATA_POINT_MENU",
                action_id="action-ar-todays-exc-to-txn-by-account",
            ),
        ],
        conditional_formatting=[
            CellAccentText(on=transfer_id_col, color=link_color),
            CellAccentMenu(
                on=account_id_col,
                text_color=link_color, background_color=link_tint,
            ),
        ],
    )
    breakdown_filter.target_visuals.append(table_exc)


# ---------------------------------------------------------------------------
# Exceptions Trends (L.3.6) — drift timelines rollup + 2 KPI/table
# rollups + aging matrix + per-check daily trend. No drills, no
# same-sheet filters — pure read-only trend view.
# ---------------------------------------------------------------------------

def _populate_exceptions_trends(
    cfg: Config,
    sheet: Sheet,
    *,
    datasets: dict[str, Dataset],
) -> None:
    del cfg
    ds_drift = datasets[DS_AR_BALANCE_DRIFT_TIMELINES_ROLLUP]
    ds_two_sided = datasets[DS_AR_TWO_SIDED_POST_MISMATCH_ROLLUP]
    ds_expected_zero = datasets[DS_AR_EXPECTED_ZERO_EOD_ROLLUP]
    ds_exc = datasets[DS_AR_UNIFIED_EXCEPTIONS]

    # Drift Timelines rollup — vertical clustered, colored by source check.
    sheet.layout.row(height=_CHART_ROW_SPAN).add_bar_chart(
        width=_FULL,
        visual_id="ar-exc-drift-timelines-rollup",  # type: ignore[arg-type]
        title="Balance Drift Timelines",
        subtitle=(
            "Per-day drift from Concentration Master sweep and GL vs "
            "Fed Master on one shared axis. Healthy days = 0; "
            "clustered bars = days a feed diverged."
        ),
        category=[ds_drift["drift_date"].date(field_id="ar-exc-drift-rollup-dim")],
        values=[ds_drift["drift"].sum(field_id="ar-exc-drift-rollup-val")],
        colors=[ds_drift["source_check"].dim(field_id="ar-exc-drift-rollup-color")],
        orientation="VERTICAL",
        bars_arrangement="CLUSTERED",
        category_label="Date",
        value_label="Drift ($)",
        color_label="Source",
    )

    # Two-Sided KPI + table.
    sheet.layout.row(height=_KPI_ROW_SPAN).add_kpi(
        width=_FULL,
        visual_id="ar-exc-kpi-two-sided-rollup",  # type: ignore[arg-type]
        title="Two-Sided Post Mismatch",
        subtitle=(
            "Total findings where one side of an expected SNB/Fed "
            "post pair landed but the other side never did"
        ),
        values=[ds_two_sided["transfer_id"].count(
            field_id="ar-exc-two-sided-rollup-count",
        )],
    )
    sheet.layout.row(height=_TABLE_ROW_SPAN).add_table(
        width=_FULL,
        visual_id="ar-exc-two-sided-rollup-table",  # type: ignore[arg-type]
        title="Two-Sided Post Mismatch",
        subtitle=(
            "Each row is a transfer where the side_present leg posted "
            "but side_missing never did. source_check identifies the "
            "detection rule; ordered oldest-first by aging."
        ),
        columns=[
            ds_two_sided["transfer_id"].dim(field_id="ar-exc-tsr-xfer-id"),
            ds_two_sided["observed_at"].date(field_id="ar-exc-tsr-observed-at"),
            ds_two_sided["amount"].numerical(field_id="ar-exc-tsr-amount"),
            ds_two_sided["side_present"].dim(field_id="ar-exc-tsr-side-present"),
            ds_two_sided["side_missing"].dim(field_id="ar-exc-tsr-side-missing"),
            ds_two_sided["aging_bucket"].dim(field_id="ar-exc-tsr-aging"),
            ds_two_sided["source_check"].dim(field_id="ar-exc-tsr-source"),
        ],
        sort_by=("ar-exc-tsr-aging", "DESC"),
    )

    # Expected-Zero KPI + table.
    sheet.layout.row(height=_KPI_ROW_SPAN).add_kpi(
        width=_FULL,
        visual_id="ar-exc-kpi-expected-zero-rollup",  # type: ignore[arg-type]
        title="Accounts Expected Zero at EOD",
        subtitle=(
            "Total non-zero EOD findings across Sweep targets, ACH "
            "Origination Settlement, and Internal Transfer Suspense — "
            "same SHAPE: a control account that should be zero, isn't"
        ),
        values=[ds_expected_zero["account_id"].count(
            field_id="ar-exc-expected-zero-rollup-count",
        )],
    )
    sheet.layout.row(height=_TABLE_ROW_SPAN).add_table(
        width=_FULL,
        visual_id="ar-exc-expected-zero-rollup-table",  # type: ignore[arg-type]
        title="Accounts Expected Zero at EOD",
        subtitle=(
            "Every (account, date) where a control account ended day "
            "non-zero. source_check identifies which detection rule "
            "fired; ordered oldest-first by aging."
        ),
        columns=[
            ds_expected_zero["account_id"].dim(field_id="ar-exc-ezr-acct-id"),
            ds_expected_zero["account_name"].dim(field_id="ar-exc-ezr-acct-name"),
            ds_expected_zero["account_level"].dim(field_id="ar-exc-ezr-level"),
            ds_expected_zero["balance_date"].date(field_id="ar-exc-ezr-date"),
            ds_expected_zero["stored_balance"].numerical(field_id="ar-exc-ezr-balance"),
            ds_expected_zero["aging_bucket"].dim(field_id="ar-exc-ezr-aging"),
            ds_expected_zero["source_check"].dim(field_id="ar-exc-ezr-source"),
        ],
        sort_by=("ar-exc-ezr-aging", "DESC"),
    )

    # Aging matrix — horizontal stacked, colored by check.
    sheet.layout.row(height=_CHART_ROW_SPAN).add_bar_chart(
        width=_FULL,
        visual_id="ar-exc-trends-aging-matrix",  # type: ignore[arg-type]
        title="Aging by Check",
        subtitle=(
            "Count of open exceptions per aging bucket, stacked by "
            "check type — concentration of stale (8-30, >30) bars "
            "marks checks that are falling behind."
        ),
        category=[ds_exc["aging_bucket"].dim(field_id="ar-exc-trends-aging-dim")],
        values=[ds_exc["check_type"].count(
            field_id="ar-exc-trends-aging-count",
        )],
        colors=[ds_exc["check_type"].dim(field_id="ar-exc-trends-aging-color")],
        orientation="HORIZONTAL",
        bars_arrangement="STACKED",
        category_label="Aging Bucket",
        value_label="Exceptions",
        color_label="Check",
    )

    # Per-check daily trend — vertical stacked, colored by check.
    sheet.layout.row(height=_CHART_ROW_SPAN).add_bar_chart(
        width=_FULL,
        visual_id="ar-exc-trends-per-check",  # type: ignore[arg-type]
        title="Exceptions per Check, by Day",
        subtitle=(
            "Daily count of open exception rows, stacked by check "
            "type. Use the date-range filter to widen or narrow the "
            "window; spikes that line up across checks usually point "
            "to a single upstream feed event."
        ),
        category=[ds_exc["exception_date"].date(field_id="ar-exc-trends-perchk-dim")],
        values=[ds_exc["check_type"].count(
            field_id="ar-exc-trends-perchk-count",
        )],
        colors=[ds_exc["check_type"].dim(field_id="ar-exc-trends-perchk-color")],
        orientation="VERTICAL",
        bars_arrangement="STACKED",
        category_label="Date",
        value_label="Exceptions",
        color_label="Check",
    )


# ---------------------------------------------------------------------------
# Daily Statement (L.3.7) — per-(account, day) feed-validation sheet.
# Three KPIs across row A (1/3 width each), two KPIs across row B
# (1/2 width each), then a full-width transaction detail table.
# ---------------------------------------------------------------------------

def _populate_daily_statement(
    cfg: Config,
    sheet: Sheet,
    *,
    datasets: dict[str, Dataset],
) -> None:
    del cfg
    ds_ds = datasets[DS_AR_DAILY_STATEMENT_SUMMARY]
    ds_ds_txn = datasets[DS_AR_DAILY_STATEMENT_TRANSACTIONS]

    # Row 1: opening / debits / credits — three 1/3-width KPIs.
    third = _FULL // 3
    row_a = sheet.layout.row(height=_KPI_ROW_SPAN)
    row_a.add_kpi(
        width=third,
        visual_id="ar-ds-kpi-opening",  # type: ignore[arg-type]
        title="Opening Balance",
        subtitle=(
            "Stored end-of-day balance on the prior business day — "
            "the starting point the day's posting activity walks from"
        ),
        values=[ds_ds["opening_balance"].sum(field_id="ar-ds-opening-val")],
    )
    row_a.add_kpi(
        width=third,
        visual_id="ar-ds-kpi-debits",  # type: ignore[arg-type]
        title="Total Debits",
        subtitle=(
            "Sum of positive signed_amount legs posted on the day "
            "(non-failed). Matches the Dr column on a statement."
        ),
        values=[ds_ds["total_debits"].sum(field_id="ar-ds-debits-val")],
    )
    row_a.add_kpi(
        width=third,
        visual_id="ar-ds-kpi-credits",  # type: ignore[arg-type]
        title="Total Credits",
        subtitle=(
            "Sum of negative signed_amount legs posted on the day "
            "(absolute value, non-failed). Matches the Cr column."
        ),
        values=[ds_ds["total_credits"].sum(field_id="ar-ds-credits-val")],
    )

    # Row 2: closing / drift — two 1/2-width KPIs.
    row_b = sheet.layout.row(height=_KPI_ROW_SPAN)
    row_b.add_kpi(
        width=_HALF,
        visual_id="ar-ds-kpi-closing",  # type: ignore[arg-type]
        title="Closing Balance (Stored)",
        subtitle=(
            "Stored end-of-day balance from daily_balances — what "
            "the feed asserts the account ended the day at"
        ),
        values=[ds_ds["closing_balance_stored"].sum(field_id="ar-ds-closing-val")],
    )
    row_b.add_kpi(
        width=_HALF,
        visual_id="ar-ds-kpi-drift",  # type: ignore[arg-type]
        title="Drift",
        subtitle=(
            "Stored closing − (opening + Σ signed legs). Zero on a "
            "clean feed; any non-zero value means the feed's balance "
            "doesn't match its own posting activity."
        ),
        values=[ds_ds["drift"].sum(field_id="ar-ds-drift-val")],
    )

    # Row 3: transaction detail (full width unaggregated).
    sheet.layout.row(height=_TABLE_ROW_SPAN).add_table(
        width=_FULL,
        visual_id="ar-ds-transactions-table",  # type: ignore[arg-type]
        title="Transaction Detail",
        subtitle=(
            "Every leg posted to the selected account on the selected "
            "day. counter_account_name shows the other side(s) of each "
            "transfer — the offsetting legs keyed against this account."
        ),
        columns=[
            ds_ds_txn["posted_at"].date(field_id="ar-ds-txn-posted-at"),
            ds_ds_txn["transfer_type"].dim(field_id="ar-ds-txn-type"),
            ds_ds_txn["origin"].dim(field_id="ar-ds-txn-origin"),
            ds_ds_txn["direction"].dim(field_id="ar-ds-txn-direction"),
            ds_ds_txn["signed_amount"].numerical(
                field_id="ar-ds-txn-signed-amount",
            ),
            ds_ds_txn["counter_account_name"].dim(
                field_id="ar-ds-txn-counter",
            ),
            ds_ds_txn["transfer_id"].dim(field_id="ar-ds-txn-transfer-id"),
            ds_ds_txn["status"].dim(field_id="ar-ds-txn-status"),
            ds_ds_txn["memo"].dim(field_id="ar-ds-txn-memo"),
        ],
        sort_by=("ar-ds-txn-posted-at", "ASC"),
    )


# ---------------------------------------------------------------------------
# L.3.8 — App-level wiring: parameters + drill helper calc fields +
# drill-down PASS filter groups. The K.2 PASS pattern: each drill writes
# a parameter; the destination dataset has a calc field that returns
# 'PASS' when (a) the param equals the sentinel "__ALL__" (untouched
# state) or (b) the column matches the param. A FilterGroup with
# `CategoryFilter.with_literal(value="PASS")` scopes the calc field to
# the destination sheet (or specific visuals), so the visible row set
# narrows to the drilled value or stays full when reset.
# ---------------------------------------------------------------------------

# K.2 sentinel — parameter default + the value drill resets write back
# to clear the filter. Hard-coded here (mirror of analysis.py:697); the
# same string appears in the calc-field expressions and the parameter
# defaults below.
_DRILL_RESET_SENTINEL = "__ALL__"


def _wire_parameters(analysis: Analysis) -> None:
    """Declare the 8 AR parameters: 6 drill-pass strings (with the
    sentinel default) + 1 daily-statement account string + 1
    daily-statement balance-date (rolling-today default)."""
    for drill_param in (
        P_AR_SUBLEDGER, P_AR_LEDGER, P_AR_TRANSFER, P_AR_ACTIVITY_DATE,
        P_AR_TRANSFER_TYPE, P_AR_ACCOUNT,
    ):
        analysis.add_parameter(StringParam(
            name=ParameterName(drill_param.name),
            default=[_DRILL_RESET_SENTINEL],
        ))
    # Daily Statement parameters — picker-driven, no drill / no sentinel.
    analysis.add_parameter(StringParam(
        name=ParameterName(P_AR_DS_ACCOUNT.name),
    ))
    analysis.add_parameter(DateTimeParam(
        name=ParameterName(P_AR_DS_BALANCE_DATE.name),
        time_granularity="DAY",
        default=DateTimeDefaultValues(
            RollingDate={"Expression": "truncDate('DD', now())"},
        ),
    ))


def _wire_drill_filter_groups(
    analysis: Analysis,
    *,
    sheets: dict[str, Sheet],
    datasets: dict[str, Dataset],
) -> None:
    """6 drill-down PASS filter groups + their backing calc fields.

    Each spec encodes one cross-sheet drill:
    - parameter to test
    - destination dataset + the column the parameter compares against
    - destination sheet (and optionally specific visuals to scope to)

    The calc field expression is the K.2 sentinel-or-match pattern;
    the FilterGroup uses ``CategoryFilter.with_literal(value="PASS")``
    so the parameter test lives in the calc field (avoiding the
    parameter-bound CustomFilterConfiguration's empty-string narrowing
    bug).
    """
    @dataclass(frozen=True)
    class _Spec:
        fg_id: str
        filter_id: str
        param_name: str
        dataset_id: str
        column_name: str
        sheet_id: str
        visuals: tuple[str, ...] | None = None

    txn_id = SHEET_AR_TRANSACTIONS
    bal_id = SHEET_AR_BALANCES
    txn_ds = DS_AR_TRANSACTIONS
    sub_drift_ds = DS_AR_SUBLEDGER_BALANCE_DRIFT

    specs = [
        _Spec(FG_AR_DRILL_SUBLEDGER_ON_TXN, "filter-ar-drill-subledger-on-txn",
              P_AR_SUBLEDGER.name, txn_ds, "subledger_account_id", txn_id),
        _Spec(FG_AR_DRILL_TRANSFER_ON_TXN, "filter-ar-drill-transfer-on-txn",
              P_AR_TRANSFER.name, txn_ds, "transfer_id", txn_id),
        _Spec(FG_AR_DRILL_ACTIVITY_DATE_ON_TXN,
              "filter-ar-drill-activity-date-on-txn",
              P_AR_ACTIVITY_DATE.name, txn_ds, "posted_date", txn_id),
        _Spec(FG_AR_DRILL_TRANSFER_TYPE_ON_TXN,
              "filter-ar-drill-transfer-type-on-txn",
              P_AR_TRANSFER_TYPE.name, txn_ds, "transfer_type", txn_id),
        _Spec(FG_AR_DRILL_ACCOUNT_ON_TXN, "filter-ar-drill-account-on-txn",
              P_AR_ACCOUNT.name, txn_ds, "account_id", txn_id),
        _Spec(FG_AR_DRILL_LEDGER_ON_BALANCES_SUBLEDGER,
              "filter-ar-drill-ledger-on-balances-subledger",
              P_AR_LEDGER.name, sub_drift_ds, "ledger_account_id", bal_id,
              ("ar-balances-subledger-table",)),
    ]

    for spec in specs:
        # `_drill_pass_<param>_on_<suffix>` mirrors the imperative
        # _DrillFilterSpec.calc_field_name shape so JSON byte-identity
        # holds.
        on_suffix = spec.fg_id.split("on-", 1)[-1].replace("-", "_")
        calc_name = f"_drill_pass_{spec.param_name}_on_{on_suffix}"
        ds = datasets[spec.dataset_id]
        calc = analysis.add_calc_field(CalcField(
            name=calc_name,
            dataset=ds,
            expression=(
                f"ifelse("
                f"${{{spec.param_name}}} = '{_DRILL_RESET_SENTINEL}', "
                f"'PASS', "
                f"ifelse({{{spec.column_name}}} = ${{{spec.param_name}}}, "
                f"'PASS', 'FAIL')"
                f")"
            ),
        ))
        fg = analysis.add_filter_group(FilterGroup(
            filter_group_id=spec.fg_id,  # type: ignore[arg-type]
            filters=[CategoryFilter.with_literal(
                filter_id=spec.filter_id,
                dataset=ds,
                column=calc,
                value="PASS",
                null_option="NON_NULLS_ONLY",
            )],
        ))
        target_sheet = sheets[spec.sheet_id]
        if spec.visuals is None:
            fg.scope_sheet(target_sheet)
        else:
            visuals = [
                v for v in target_sheet.visuals
                if not isinstance(v.visual_id, _AutoSentinel)
                and v.visual_id in spec.visuals
            ]
            target_sheet.scope(fg, visuals)


# ---------------------------------------------------------------------------
# L.3.8b — Sheet-level filter groups (18 total). Two patterns:
# - Multi-sheet filter groups carry a `default_control` so cross-sheet
#   FilterControls on other sheets inherit the widget config (AWS rule
#   for filters bound to multiple sheets).
# - Single-sheet filter groups omit `default_control`; the sheet's own
#   FilterControl provides the widget directly.
# ---------------------------------------------------------------------------


def _wire_sheet_filter_groups(
    analysis: Analysis,
    *,
    sheets: dict[str, Sheet],
    datasets: dict[str, Dataset],
) -> None:
    bal = sheets[SHEET_AR_BALANCES]
    xfr = sheets[SHEET_AR_TRANSFERS]
    txn = sheets[SHEET_AR_TRANSACTIONS]
    todays = sheets[SHEET_AR_TODAYS_EXCEPTIONS]
    trends = sheets[SHEET_AR_EXCEPTIONS_TRENDS]
    daily = sheets[SHEET_AR_DAILY_STATEMENT]

    ds_txn = datasets[DS_AR_TRANSACTIONS]
    ds_ledger = datasets[DS_AR_LEDGER_ACCOUNTS]
    ds_subledger = datasets[DS_AR_SUBLEDGER_ACCOUNTS]
    ds_xfr_summary = datasets[DS_AR_TRANSFER_SUMMARY]
    ds_ledger_drift = datasets[DS_AR_LEDGER_BALANCE_DRIFT]
    ds_sub_drift = datasets[DS_AR_SUBLEDGER_BALANCE_DRIFT]
    ds_exc = datasets[DS_AR_UNIFIED_EXCEPTIONS]
    ds_ds_summary = datasets[DS_AR_DAILY_STATEMENT_SUMMARY]

    visible = [bal, xfr, txn, todays, trends]
    account_scoped = [bal, txn]
    transfer_type_scoped = [xfr, txn, todays, trends]
    unified_exc_sheets = [todays, trends]

    def _multi_select(
        *, fg_id: str, filter_id: str, title: str,
        ds: Dataset, col: str, sheet_list: list[Sheet],
        cross_dataset_override: str | None = None,
    ) -> None:
        is_multi_sheet = len(sheet_list) > 1
        if cross_dataset_override is not None:
            cross = cross_dataset_override
        else:
            cross = "ALL_DATASETS" if is_multi_sheet else "SINGLE_DATASET"
        default = (
            DefaultDropdownControl(title=title, type="MULTI_SELECT")
            if is_multi_sheet else None
        )
        fg = analysis.add_filter_group(FilterGroup(
            filter_group_id=fg_id,  # type: ignore[arg-type]
            cross_dataset=cross,  # type: ignore[arg-type]
            filters=[CategoryFilter.with_values(
                filter_id=filter_id,
                dataset=ds, column=ds[col],
                values=[],
                select_all_options="FILTER_ALL_VALUES",
                default_control=default,
            )],
        ))
        for s in sheet_list:
            fg.scope_sheet(s)

    # Order matches imperative `build_filter_groups()`:
    # date_range / ledger / subledger / transfer_status / transaction_status /
    # transfer_type / posting_level / origin / 4 toggles / 2 daily-statement /
    # 4 today's-exceptions.

    # 1. Date range — TimeRangeFilter on transactions.posted_at, all
    # five visible sheets. Multi-sheet → carries default_control.
    date_fg = analysis.add_filter_group(FilterGroup(
        filter_group_id=FG_AR_DATE_RANGE,
        cross_dataset="ALL_DATASETS",
        filters=[TimeRangeFilter(
            filter_id="filter-ar-date-range",
            dataset=ds_txn,
            column=ds_txn["posted_at"],
            null_option="NON_NULLS_ONLY",
            time_granularity="DAY",
            default_control=DefaultDateTimePickerControl(
                title="Date Range", type="DATE_RANGE",
            ),
        )],
    ))
    for s in visible:
        date_fg.scope_sheet(s)

    _multi_select(
        fg_id=FG_AR_LEDGER_ACCOUNT, filter_id="filter-ar-ledger-account",
        title="Ledger Account",
        ds=ds_ledger, col="ledger_account_id", sheet_list=account_scoped,
    )
    _multi_select(
        fg_id=FG_AR_SUBLEDGER_ACCOUNT,
        filter_id="filter-ar-subledger-account",
        title="Sub-Ledger Account",
        ds=ds_subledger, col="subledger_account_id",
        sheet_list=account_scoped,
    )
    _multi_select(
        fg_id=FG_AR_TRANSFER_STATUS, filter_id="filter-ar-transfer-status",
        title="Transfer Status",
        ds=ds_xfr_summary, col="net_zero_status", sheet_list=[xfr],
    )
    _multi_select(
        fg_id=FG_AR_TRANSACTION_STATUS,
        filter_id="filter-ar-transaction-status",
        title="Transaction Status",
        ds=ds_txn, col="status", sheet_list=[txn],
    )
    _multi_select(
        fg_id=FG_AR_TRANSFER_TYPE, filter_id="filter-ar-transfer-type",
        title="Transfer Type",
        ds=ds_txn, col="transfer_type", sheet_list=transfer_type_scoped,
    )
    _multi_select(
        fg_id=FG_AR_POSTING_LEVEL, filter_id="filter-ar-posting-level",
        title="Posting Level",
        ds=ds_txn, col="posting_level", sheet_list=[txn],
    )
    # Origin: single-sheet but ALL_DATASETS (matches imperative — the
    # column appears in multiple datasets and the imperative didn't
    # override the cross_dataset default).
    _multi_select(
        fg_id=FG_AR_ORIGIN, filter_id="filter-ar-origin",
        title="Origin",
        ds=ds_txn, col="origin", sheet_list=[txn],
        cross_dataset_override="ALL_DATASETS",
    )

    # 4 state toggle filters (Show-Only-X).
    for fg_id, filter_id, sheet, ds, col in (
        (FG_AR_BALANCES_LEDGER_DRIFT, "filter-ar-balances-ledger-drift",
         bal, ds_ledger_drift, "drift_status"),
        (FG_AR_BALANCES_SUBLEDGER_DRIFT, "filter-ar-balances-subledger-drift",
         bal, ds_sub_drift, "drift_status"),
        (FG_AR_BALANCES_OVERDRAFT, "filter-ar-balances-overdraft",
         bal, ds_sub_drift, "overdraft_status"),
        (FG_AR_TRANSACTIONS_FAILED, "filter-ar-transactions-failed",
         txn, ds_txn, "is_failed"),
    ):
        fg = analysis.add_filter_group(FilterGroup(
            filter_group_id=fg_id,
            cross_dataset="SINGLE_DATASET",
            filters=[CategoryFilter.with_values(
                filter_id=filter_id,
                dataset=ds, column=ds[col],
                values=[],
                select_all_options="FILTER_ALL_VALUES",
            )],
        ))
        fg.scope_sheet(sheet)

    # Daily Statement account picker — parameter-bound CategoryFilter
    # (the picker is a ParameterControl, NOT a FilterControl, since
    # parameter-bound filter controls are disabled in the UI).
    fg_ds_acct = analysis.add_filter_group(FilterGroup(
        filter_group_id=FG_AR_DS_ACCOUNT,
        cross_dataset="ALL_DATASETS",
        filters=[CategoryFilter.with_parameter(
            filter_id="filter-ar-ds-account",
            dataset=ds_ds_summary,
            column=ds_ds_summary["account_id"],
            parameter=analysis.find_parameter(name=P_AR_DS_ACCOUNT.name),
            match_operator="EQUALS",
            null_option="NON_NULLS_ONLY",
        )],
    ))
    fg_ds_acct.scope_sheet(daily)

    # Daily Statement single-day picker — TimeEqualityFilter (NOT
    # TimeRangeFilter) bound to the date parameter.
    fg_ds_date = analysis.add_filter_group(FilterGroup(
        filter_group_id=FG_AR_DS_BALANCE_DATE,
        cross_dataset="ALL_DATASETS",
        filters=[TimeEqualityFilter(
            filter_id="filter-ar-ds-balance-date",
            dataset=ds_ds_summary,
            column=ds_ds_summary["balance_date"],
            parameter=analysis.find_parameter(name=P_AR_DS_BALANCE_DATE.name),
            time_granularity="DAY",
        )],
    ))
    fg_ds_date.scope_sheet(daily)

    # 4 Today's Exceptions sheet pickers — multi-sheet (Today's + Trends)
    # but SINGLE_DATASET (only the unified-exceptions dataset has the
    # columns); follow same shape as multi-select but with cross_dataset
    # override.
    _multi_select(
        fg_id=FG_AR_TODAYS_EXC_CHECK_TYPE,
        filter_id="filter-ar-todays-exc-check-type",
        title="Check Type",
        ds=ds_exc, col="check_type", sheet_list=unified_exc_sheets,
        cross_dataset_override="SINGLE_DATASET",
    )
    _multi_select(
        fg_id=FG_AR_TODAYS_EXC_ACCOUNT,
        filter_id="filter-ar-todays-exc-account",
        title="Account",
        ds=ds_exc, col="account_id", sheet_list=unified_exc_sheets,
        cross_dataset_override="SINGLE_DATASET",
    )
    _multi_select(
        fg_id=FG_AR_TODAYS_EXC_AGING,
        filter_id="filter-ar-todays-exc-aging",
        title="Aging Bucket",
        ds=ds_exc, col="aging_bucket", sheet_list=unified_exc_sheets,
        cross_dataset_override="SINGLE_DATASET",
    )
    _multi_select(
        fg_id=FG_AR_TODAYS_EXC_IS_LATE,
        filter_id="filter-ar-todays-exc-is-late",
        title="Lateness",
        ds=ds_exc, col="is_late", sheet_list=unified_exc_sheets,
        cross_dataset_override="SINGLE_DATASET",
    )


# ---------------------------------------------------------------------------
# L.3.8c — Per-sheet FilterControls. Multi-sheet filter groups bind
# CrossSheet controls (which inherit the default_control widget set on
# the FilterGroup); single-sheet filter groups bind direct dropdowns or
# state-toggle dropdowns. Daily Statement uses ParameterControls (a
# parameter-bound filter's widget MUST be a ParameterControl, not a
# FilterControl, per the QS UI rule).
# ---------------------------------------------------------------------------

def _filter_of(analysis: Analysis, fg_id: str) -> object:
    """Return the (single) inner filter for a registered filter group."""
    return analysis.find_filter_group(filter_group_id=fg_id).filters[0]  # type: ignore[arg-type]


def _wire_sheet_filter_controls(
    analysis: Analysis,
    *,
    sheets: dict[str, Sheet],
) -> None:
    bal = sheets[SHEET_AR_BALANCES]
    xfr = sheets[SHEET_AR_TRANSFERS]
    txn = sheets[SHEET_AR_TRANSACTIONS]
    todays = sheets[SHEET_AR_TODAYS_EXCEPTIONS]
    trends = sheets[SHEET_AR_EXCEPTIONS_TRENDS]
    daily = sheets[SHEET_AR_DAILY_STATEMENT]

    # Pre-fetch the multi-sheet filters by id (one fetch each).
    f_date = _filter_of(analysis, FG_AR_DATE_RANGE)
    f_ledger = _filter_of(analysis, FG_AR_LEDGER_ACCOUNT)
    f_subledger = _filter_of(analysis, FG_AR_SUBLEDGER_ACCOUNT)
    f_xfr_type = _filter_of(analysis, FG_AR_TRANSFER_TYPE)
    f_xfr_status = _filter_of(analysis, FG_AR_TRANSFER_STATUS)
    f_txn_status = _filter_of(analysis, FG_AR_TRANSACTION_STATUS)
    f_posting = _filter_of(analysis, FG_AR_POSTING_LEVEL)
    f_origin = _filter_of(analysis, FG_AR_ORIGIN)
    f_bal_ledger_drift = _filter_of(analysis, FG_AR_BALANCES_LEDGER_DRIFT)
    f_bal_subledger_drift = _filter_of(analysis, FG_AR_BALANCES_SUBLEDGER_DRIFT)
    f_bal_overdraft = _filter_of(analysis, FG_AR_BALANCES_OVERDRAFT)
    f_txn_failed = _filter_of(analysis, FG_AR_TRANSACTIONS_FAILED)
    f_exc_check_type = _filter_of(analysis, FG_AR_TODAYS_EXC_CHECK_TYPE)
    f_exc_account = _filter_of(analysis, FG_AR_TODAYS_EXC_ACCOUNT)
    f_exc_aging = _filter_of(analysis, FG_AR_TODAYS_EXC_AGING)
    f_exc_is_late = _filter_of(analysis, FG_AR_TODAYS_EXC_IS_LATE)

    p_ds_account = analysis.find_parameter(name=P_AR_DS_ACCOUNT.name)
    p_ds_date = analysis.find_parameter(name=P_AR_DS_BALANCE_DATE.name)
    # Pull the daily-statement summary Dataset via the
    # CategoryFilter we already registered (the filter's `dataset`
    # field is a typed Dataset ref). Saves passing `datasets=` in.
    ds_ds = _filter_of(analysis, FG_AR_DS_ACCOUNT).dataset  # type: ignore[attr-defined]

    # Balances — 6 controls.
    bal.add_filter_cross_sheet(
        filter=f_date, control_id="ctrl-ar-balances-date-range",  # type: ignore[arg-type]
    )
    bal.add_filter_cross_sheet(
        filter=f_ledger, control_id="ctrl-ar-balances-ledger-account",  # type: ignore[arg-type]
    )
    bal.add_filter_cross_sheet(
        filter=f_subledger, control_id="ctrl-ar-balances-subledger-account",  # type: ignore[arg-type]
    )
    bal.add_filter_dropdown(
        filter=f_bal_ledger_drift,
        title="Show Only Ledger Drift",
        type="SINGLE_SELECT",
        control_id="ctrl-ar-balances-ledger-drift",  # type: ignore[arg-type]
    )
    bal.add_filter_dropdown(
        filter=f_bal_subledger_drift,
        title="Show Only Sub-Ledger Drift",
        type="SINGLE_SELECT",
        control_id="ctrl-ar-balances-subledger-drift",  # type: ignore[arg-type]
    )
    bal.add_filter_dropdown(
        filter=f_bal_overdraft,
        title="Show Only Overdraft",
        type="SINGLE_SELECT",
        control_id="ctrl-ar-balances-overdraft",  # type: ignore[arg-type]
    )

    # Transfers — 3 controls.
    xfr.add_filter_cross_sheet(
        filter=f_date, control_id="ctrl-ar-transfers-date-range",  # type: ignore[arg-type]
    )
    xfr.add_filter_cross_sheet(
        filter=f_xfr_type, control_id="ctrl-ar-transfers-transfer-type",  # type: ignore[arg-type]
    )
    xfr.add_filter_dropdown(
        filter=f_xfr_status, title="Transfer Status",
        control_id="ctrl-ar-transfers-status",  # type: ignore[arg-type]
    )

    # Transactions — 8 controls.
    txn.add_filter_cross_sheet(
        filter=f_date, control_id="ctrl-ar-transactions-date-range",  # type: ignore[arg-type]
    )
    txn.add_filter_cross_sheet(
        filter=f_ledger, control_id="ctrl-ar-transactions-ledger-account",  # type: ignore[arg-type]
    )
    txn.add_filter_cross_sheet(
        filter=f_subledger, control_id="ctrl-ar-transactions-subledger-account",  # type: ignore[arg-type]
    )
    txn.add_filter_cross_sheet(
        filter=f_xfr_type, control_id="ctrl-ar-transactions-transfer-type",  # type: ignore[arg-type]
    )
    txn.add_filter_dropdown(
        filter=f_origin, title="Origin",
        control_id="ctrl-ar-transactions-origin",  # type: ignore[arg-type]
    )
    txn.add_filter_dropdown(
        filter=f_posting, title="Posting Level",
        control_id="ctrl-ar-transactions-posting-level",  # type: ignore[arg-type]
    )
    txn.add_filter_dropdown(
        filter=f_txn_status, title="Transaction Status",
        control_id="ctrl-ar-transactions-status",  # type: ignore[arg-type]
    )
    txn.add_filter_dropdown(
        filter=f_txn_failed, title="Show Only Failed",
        type="SINGLE_SELECT",
        control_id="ctrl-ar-transactions-failed",  # type: ignore[arg-type]
    )

    # Today's Exceptions — 6 cross-sheet controls.
    todays.add_filter_cross_sheet(
        filter=f_date, control_id="ctrl-ar-todays-exc-date-range",  # type: ignore[arg-type]
    )
    todays.add_filter_cross_sheet(
        filter=f_xfr_type, control_id="ctrl-ar-todays-exc-transfer-type",  # type: ignore[arg-type]
    )
    todays.add_filter_cross_sheet(
        filter=f_exc_check_type, control_id="ctrl-ar-todays-exc-check-type",  # type: ignore[arg-type]
    )
    todays.add_filter_cross_sheet(
        filter=f_exc_account, control_id="ctrl-ar-todays-exc-account",  # type: ignore[arg-type]
    )
    todays.add_filter_cross_sheet(
        filter=f_exc_aging, control_id="ctrl-ar-todays-exc-aging",  # type: ignore[arg-type]
    )
    todays.add_filter_cross_sheet(
        filter=f_exc_is_late, control_id="ctrl-ar-todays-exc-is-late",  # type: ignore[arg-type]
    )

    # Exceptions Trends — 6 cross-sheet controls (mirror Today's).
    trends.add_filter_cross_sheet(
        filter=f_date, control_id="ctrl-ar-exc-trends-date-range",  # type: ignore[arg-type]
    )
    trends.add_filter_cross_sheet(
        filter=f_xfr_type, control_id="ctrl-ar-exc-trends-transfer-type",  # type: ignore[arg-type]
    )
    trends.add_filter_cross_sheet(
        filter=f_exc_check_type, control_id="ctrl-ar-exc-trends-check-type",  # type: ignore[arg-type]
    )
    trends.add_filter_cross_sheet(
        filter=f_exc_account, control_id="ctrl-ar-exc-trends-account",  # type: ignore[arg-type]
    )
    trends.add_filter_cross_sheet(
        filter=f_exc_aging, control_id="ctrl-ar-exc-trends-aging",  # type: ignore[arg-type]
    )
    trends.add_filter_cross_sheet(
        filter=f_exc_is_late, control_id="ctrl-ar-exc-trends-is-late",  # type: ignore[arg-type]
    )

    # Daily Statement — 2 ParameterControls (NOT FilterControls — the
    # filters are parameter-bound).
    from quicksight_gen.common.tree import LinkedValues
    daily.add_parameter_dropdown(
        parameter=p_ds_account,
        title="Account",
        type="SINGLE_SELECT",
        selectable_values=LinkedValues(
            dataset=ds_ds, column_name="account_id",
        ),
        control_id="ctrl-ar-ds-account",  # type: ignore[arg-type]
    )
    daily.add_parameter_datetime_picker(
        parameter=p_ds_date,
        title="Balance Date",
        control_id="ctrl-ar-ds-balance-date",  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# App-level wiring
# ---------------------------------------------------------------------------

def _analysis_name(cfg: Config) -> str:
    preset = get_preset(cfg.theme_preset)
    if preset.analysis_name_prefix:
        return f"{preset.analysis_name_prefix} — Account Reconciliation"
    return "Account Reconciliation"


# Order matters — sheets register on the analysis in this list's order,
# which becomes the dashboard's tab order.
_AR_SHEET_SPECS: tuple[tuple[str, str, str, str], ...] = (
    (SHEET_AR_GETTING_STARTED, "Getting Started", "Getting Started",
     "Landing page — summarises each tab in this dashboard so readers "
     "know where to look first. No filters or visuals."),
    (SHEET_AR_BALANCES, "Balances", "Balances", _BALANCES_DESCRIPTION),
    (SHEET_AR_TRANSFERS, "Transfers", "Transfers", _TRANSFERS_DESCRIPTION),
    (SHEET_AR_TRANSACTIONS, "Transactions", "Transactions", _TRANSACTIONS_DESCRIPTION),
    (SHEET_AR_TODAYS_EXCEPTIONS, "Today's Exceptions", "Today's Exceptions",
     _TODAYS_EXCEPTIONS_DESCRIPTION),
    (SHEET_AR_EXCEPTIONS_TRENDS, "Exceptions Trends", "Exceptions Trends",
     _EXCEPTIONS_TRENDS_DESCRIPTION),
    (SHEET_AR_DAILY_STATEMENT, "Daily Statement", "Daily Statement",
     _DAILY_STATEMENT_DESCRIPTION),
)


def build_account_recon_app(cfg: Config) -> App:
    """Construct the Account Reconciliation App as a tree.

    Sheets are pre-registered in display order so cross-sheet drills can
    target any sheet by ref. Populators run in any order; unported
    sheets emit as bare shells (id + metadata) until their L.3.N
    sub-step lands.
    """
    app = App(name="account-recon", cfg=cfg)
    analysis = app.set_analysis(Analysis(
        analysis_id_suffix="account-recon-analysis",
        name=_analysis_name(cfg),
    ))

    # Datasets — register every AR dataset the populated sheets reference.
    # (L.3.2 only uses the four under Balances; subsequent substeps add
    # to this list.)
    datasets = _datasets(cfg)
    for ds in datasets.values():
        app.add_dataset(ds)

    # Pre-register all 7 sheet shells in display order.
    sheets: dict[str, Sheet] = {}
    for sheet_id, name, title, description in _AR_SHEET_SPECS:
        sheets[sheet_id] = analysis.add_sheet(Sheet(
            sheet_id=sheet_id,  # type: ignore[arg-type]
            name=name,
            title=title,
            description=description,
        ))

    # Populate sheets ported so far.
    _populate_getting_started(cfg, sheets[SHEET_AR_GETTING_STARTED])
    _populate_balances(
        cfg,
        sheets[SHEET_AR_BALANCES],
        transactions_sheet=sheets[SHEET_AR_TRANSACTIONS],
        daily_statement_sheet=sheets[SHEET_AR_DAILY_STATEMENT],
        datasets=datasets,
    )
    _populate_transfers(
        cfg,
        sheets[SHEET_AR_TRANSFERS],
        transactions_sheet=sheets[SHEET_AR_TRANSACTIONS],
        datasets=datasets,
    )
    _populate_transactions(cfg, sheets[SHEET_AR_TRANSACTIONS], datasets=datasets)
    _populate_todays_exceptions(
        cfg,
        sheets[SHEET_AR_TODAYS_EXCEPTIONS],
        transactions_sheet=sheets[SHEET_AR_TRANSACTIONS],
        datasets=datasets,
    )
    _populate_exceptions_trends(
        cfg, sheets[SHEET_AR_EXCEPTIONS_TRENDS], datasets=datasets,
    )
    _populate_daily_statement(
        cfg, sheets[SHEET_AR_DAILY_STATEMENT], datasets=datasets,
    )

    # L.3.8 — App-level wiring. Parameters first (validator depends on
    # them), then sheet-level filter groups (which reference the
    # parameters), then per-sheet FilterControls (which reference the
    # filter groups), then drill PASS calc fields + filter groups
    # (independent of controls; scoped to the populated sheets above).
    _wire_parameters(analysis)
    _wire_sheet_filter_groups(analysis, sheets=sheets, datasets=datasets)
    _wire_sheet_filter_controls(analysis, sheets=sheets)
    _wire_drill_filter_groups(analysis, sheets=sheets, datasets=datasets)

    app.create_dashboard(
        dashboard_id_suffix="account-recon-dashboard",
        name=_analysis_name(cfg),
    )
    return app


# ---------------------------------------------------------------------------
# CLI / external-caller shims. These mirror the imperative
# ``apps/account_recon/analysis`` shape so the CLI can swap to the
# tree-built app without changing its import surface.
# ---------------------------------------------------------------------------

def build_analysis(cfg: Config) -> ModelAnalysis:
    """Build the complete Account Recon Analysis resource via the tree."""
    return build_account_recon_app(cfg).emit_analysis()


def build_account_recon_dashboard(cfg: Config) -> ModelDashboard:
    """Build the Account Recon Dashboard resource via the tree."""
    return build_account_recon_app(cfg).emit_dashboard()
