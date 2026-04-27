"""L1 Dashboard — generic L2-fed reconciliation dashboard.

Tree-built from scratch around the M.1a.7 L1 invariant views. Replaces
the v5 idiom translation layer (apps/account_recon/_l2_datasets.py) with
direct view consumption — each sheet IS one L1 SHOULD-constraint
visualized.

Architecture (M.2a.1 decision): parallel-stack with the legacy
apps/account_recon/ — the v5 AR app keeps working against its v5
schema deployment until M.2a.10 deprecates it. The L1 dashboard builds
fresh tree-built sheets against the v6 prefixed schema + L1 invariant
views per L2 instance, with no v5-idiom column shims.

Build pipeline:
    build_l1_dashboard_app(cfg, *, l2_instance=None) -> App

Default L2 instance is the canonical Sasquatch AR fixture (same as the
AR legacy stack); callers MAY override (tests, alternative-persona
deployments) via the kwarg.

Substep landmarks:
    M.2a.1 — package skeleton + Analysis + Dashboard registered
    M.2a.2 — Getting Started sheet with description-driven prose
    M.2a.3 — Drift sheet — KPIs + leaf + ledger drift tables
    M.2a.4 — Overdraft sheet — KPI + violations table
    M.2a.5 — Limit Breach sheet — KPI + breach table
    M.2a.6 — Today's Exceptions sheet — UNION across L1 views
    M.2a.7 — Description-driven prose across every sheet (this commit)
    M.2a.8 — Hash-lock the seed at the M.2a structure
    M.2a.9 — Deploy + verify against Aurora
    M.2a.10 — Iteration gate; decide on apps/account_recon/ deprecation
"""

from __future__ import annotations

from quicksight_gen.apps.account_recon._l2 import default_l2_instance
from quicksight_gen.apps.l1_dashboard.datasets import (
    DS_DAILY_STATEMENT_SUMMARY,
    DS_DAILY_STATEMENT_TRANSACTIONS,
    DS_DRIFT,
    DS_DRIFT_TIMELINE,
    DS_LEDGER_DRIFT,
    DS_LEDGER_DRIFT_TIMELINE,
    DS_LIMIT_BREACH,
    DS_OVERDRAFT,
    DS_TODAYS_EXCEPTIONS,
    DS_TRANSACTIONS,
    build_all_l1_dashboard_datasets,
)
from quicksight_gen.common import rich_text as rt
from quicksight_gen.common.config import Config
from quicksight_gen.common.ids import ParameterName, SheetId
from quicksight_gen.common.l2 import L2Instance
from quicksight_gen.common.models import DateTimeDefaultValues
from quicksight_gen.common.theme import get_preset
from quicksight_gen.common.tree import (
    Analysis,
    App,
    CategoryFilter,
    CellAccentText,
    Dataset,
    DateTimeParam,
    FilterGroup,
    LineChart,
    Sheet,
    StringParam,
    TextBox,
    TimeEqualityFilter,
    TimeRangeFilter,
)


# Layout constants — mirror apps/account_recon/app.py so visual heights
# read consistently across the two AR stacks.
_FULL = 36
_HALF = 18
_KPI_ROW_SPAN = 6
_CHART_ROW_SPAN = 12
_TABLE_ROW_SPAN = 18


# Sheet IDs — inlined in app.py per the greenfield-app convention
# (L.7 Executives) since the L1 dashboard isn't dragging legacy URL
# stability constraints from a previous deploy.
SHEET_GETTING_STARTED = SheetId("l1-sheet-getting-started")
SHEET_DRIFT = SheetId("l1-sheet-drift")
SHEET_DRIFT_TIMELINES = SheetId("l1-sheet-drift-timelines")
SHEET_OVERDRAFT = SheetId("l1-sheet-overdraft")
SHEET_LIMIT_BREACH = SheetId("l1-sheet-limit-breach")
SHEET_TODAYS_EXCEPTIONS = SheetId("l1-sheet-todays-exceptions")
SHEET_DAILY_STATEMENT = SheetId("l1-sheet-daily-statement")
SHEET_TRANSACTIONS = SheetId("l1-sheet-transactions")


# Parameter names — analysis-level parameters that drive the universal
# date-range filter (M.2b.1). Each data-bearing sheet has paired
# date-time picker controls bound to these params, so all 4 sheets'
# pickers stay in sync via shared parameter values.
P_L1_DATE_START = ParameterName("pL1DateStart")
P_L1_DATE_END = ParameterName("pL1DateEnd")

# M.2b.4 — Daily Statement parameters. Single-value account_id +
# single-value business_day_start drive the per-account-day filter on
# both the summary KPIs and the transactions detail table.
P_L1_DS_ACCOUNT = ParameterName("pL1DsAccount")
P_L1_DS_BALANCE_DATE = ParameterName("pL1DsBalanceDate")


_GETTING_STARTED_NAME = "Getting Started"
_GETTING_STARTED_TITLE = "L1 Reconciliation Dashboard"
_GETTING_STARTED_DESCRIPTION = (
    "Where to start. The dashboard groups every L1 SHOULD-constraint "
    "into one tab per exception kind — drift, overdraft, limit breach, "
    "expected EOD balance variance — plus a Today's Exceptions roll-up. "
    "Each tab queries one L1 invariant view directly; rows ARE the "
    "constraint violations."
)


_DRIFT_NAME = "Drift"
_DRIFT_TITLE = "Account Balance Drift"
_DRIFT_DESCRIPTION = (
    "Stored vs computed balance disagreements at end-of-day. Leaf table "
    "covers individual posting accounts (computed = cumulative net of "
    "every Money record through that BusinessDay's end). Ledger table "
    "covers parent accounts (computed = sum of child accounts' stored "
    "balances). Both tables only show rows where stored ≠ computed — "
    "every row is one SHOULD-constraint violation."
)


_DRIFT_TIMELINES_NAME = "Drift Timelines"
_DRIFT_TIMELINES_TITLE = "Drift Magnitude Over Time"
_DRIFT_TIMELINES_DESCRIPTION = (
    "Σ ABS(drift) per BusinessDay end, one line per account_role. "
    "Healthy days sit on the zero baseline; spikes mark when the feed "
    "or the parent-roll-up diverged. Use this to spot recurring "
    "violations vs one-off events — a role that spikes every Monday is "
    "a different problem than a role that spiked once after a deploy. "
    "KPIs surface the largest single-day magnitude in the past 7 days."
)


_OVERDRAFT_NAME = "Overdraft"
_OVERDRAFT_TITLE = "Internal Account Overdrafts"
_OVERDRAFT_DESCRIPTION = (
    "Internal accounts holding negative money at end-of-day. The L1 "
    "invariant is 'no internal account holds negative balance' — every "
    "row in the table below is one violation. External accounts are "
    "excluded by the underlying view (banks may legitimately overdraft "
    "us; we MUST NOT overdraft them)."
)


_LIMIT_BREACH_NAME = "Limit Breach"
_LIMIT_BREACH_TITLE = "Outbound Transfer Limit Breaches"
_LIMIT_BREACH_DESCRIPTION = (
    "Per-account, per-day, per-transfer-type cells where cumulative "
    "outbound debit exceeded the L2-configured cap. Caps are pulled "
    "from the L2 instance's LimitSchedules at schema-emit time and "
    "embedded inline in the underlying view — no JSON path lookups in "
    "the dataset SQL. Every row is one violation."
)


_TODAYS_EXCEPTIONS_NAME = "Today's Exceptions"
_TODAYS_EXCEPTIONS_TITLE = "Today's Exceptions"
_TODAYS_EXCEPTIONS_DESCRIPTION = (
    "The 9am scan — every L1 SHOULD-constraint violation across all 5 "
    "invariant views (drift, ledger drift, overdraft, limit breach, "
    "expected EOD balance), scoped to the most recent business day in "
    "the data. Replaces v5's ar_unified_exceptions matview with a live "
    "UNION; no REFRESH contract. KPI tracks total open count; bar chart "
    "breaks down by check_type; detail table sorts by magnitude so the "
    "biggest variances surface first."
)


_DAILY_STATEMENT_NAME = "Daily Statement"
_DAILY_STATEMENT_TITLE = "Per-Account Daily Statement"
_DAILY_STATEMENT_DESCRIPTION = (
    "Per-account, per-day walk: opening balance + day's debits + "
    "credits + closing balance + drift. Pick one account and one "
    "business day via the controls; KPIs surface the 5-number summary "
    "and the detail table lists every Money record posted that day. "
    "Drift = stored closing − (opening + signed-net flow); on a healthy "
    "feed it's exactly zero, so non-zero drift here is the single "
    "visual cue the underlying ledger doesn't reconcile for that "
    "account-day. Mirrors AR's Daily Statement pattern."
)


_TRANSACTIONS_NAME = "Transactions"
_TRANSACTIONS_TITLE = "Posting Ledger"
_TRANSACTIONS_DESCRIPTION = (
    "The raw posting ledger — one row per Money record (leg). "
    "Supersession-aware: the underlying view filters out replaced "
    "entries so what you see IS the current truth. Filter by account, "
    "transfer, status (Pending / Posted / Failed), origin "
    "(InternalInitiated / ExternalForcePosted / ExternalAggregated), "
    "or transfer type. Drill out to Daily Statement for the account-day "
    "context any leg sits in (drill wiring lands at M.2b.7)."
)


def _analysis_name(cfg: Config, l2_instance: L2Instance) -> str:
    """Title shown on the deployed QuickSight Analysis."""
    return f"L1 Reconciliation Dashboard ({l2_instance.instance})"


# -- L2-prose helpers --------------------------------------------------------
#
# M.2a.7's "description-driven prose" core: pull facts about the configured
# L2 instance into per-sheet text boxes so each sheet IS the handbook page
# for that L1 invariant under this institution. Switching L2 instance
# switches the prose across every sheet — tested at the substep that
# introduces each helper's call site.


def _l2_inventory_lines(l2_instance: L2Instance) -> list[str]:
    """Compact inventory bullets for the Getting Started coverage block."""
    accounts = l2_instance.accounts
    internal = sum(1 for a in accounts if a.scope == "internal")
    external = sum(1 for a in accounts if a.scope == "external")
    return [
        f"{internal} internal accounts, {external} external accounts",
        f"{len(l2_instance.account_templates)} account templates "
        f"(role classes that bind to specific accounts at posting time)",
        f"{len(l2_instance.rails)} rails "
        f"(reconciliation patterns the integrator declares)",
        f"{len(l2_instance.transfer_templates)} transfer templates "
        f"(multi-leg shared transfers)",
        f"{len(l2_instance.chains)} chains "
        f"(transfer-of-transfers ordered flows)",
        f"{len(l2_instance.limit_schedules)} limit schedules "
        f"(daily outbound caps by parent role × transfer type)",
    ]


def _l2_limit_schedule_lines(l2_instance: L2Instance) -> list[str]:
    """Per-LimitSchedule bullets — name, cap, and L2-supplied prose."""
    if not l2_instance.limit_schedules:
        return [
            "No limit schedules configured on this L2 instance — "
            "the limit-breach view returns zero rows by construction.",
        ]
    lines: list[str] = []
    for ls in l2_instance.limit_schedules:
        # Money is a Decimal; format with thousands separators + 2dp.
        cap_str = f"${ls.cap:,.2f}/day"
        head = f"{ls.parent_role} × {ls.transfer_type}: {cap_str}"
        if ls.description:
            lines.append(f"{head} — {ls.description}")
        else:
            lines.append(head)
    return lines


def _l2_internal_account_role_lines(l2_instance: L2Instance) -> list[str]:
    """One bullet per internal account or template with prose."""
    lines: list[str] = []
    for a in l2_instance.accounts:
        if a.scope != "internal":
            continue
        head = f"{a.role or a.id} ({a.id})"
        if a.description:
            lines.append(f"{head} — {a.description}")
        else:
            lines.append(head)
    for t in l2_instance.account_templates:
        if t.scope != "internal":
            continue
        head = f"{t.role} (template)"
        if t.description:
            lines.append(f"{head} — {t.description}")
        else:
            lines.append(head)
    return lines


def _l1_datasets(
    cfg: Config, l2_instance: L2Instance,
) -> dict[str, Dataset]:
    """Build every L1 dataset and return tree-ref Datasets keyed by id.

    Each AWS DataSet's ``DataSetId`` becomes the tree Dataset's ARN
    path component; the visual identifier (the registry key passed to
    `build_dataset()`) becomes the tree Dataset's ``identifier`` field.
    The contract is registered as a side-effect of `build_dataset()`,
    so subsequent ``ds["col"]`` accesses validate.
    """
    aws_datasets = build_all_l1_dashboard_datasets(cfg, l2_instance)
    # `build_all_l1_dashboard_datasets` returns AWS DataSets in the same
    # order as the visual identifiers below; map each to a tree Dataset.
    visual_ids = [
        DS_DRIFT, DS_LEDGER_DRIFT, DS_OVERDRAFT,
        DS_LIMIT_BREACH, DS_TODAYS_EXCEPTIONS,
        DS_DAILY_STATEMENT_SUMMARY, DS_DAILY_STATEMENT_TRANSACTIONS,
        DS_TRANSACTIONS,
        DS_DRIFT_TIMELINE, DS_LEDGER_DRIFT_TIMELINE,
    ]
    return {
        vid: Dataset(identifier=vid, arn=cfg.dataset_arn(aws.DataSetId))
        for vid, aws in zip(visual_ids, aws_datasets)
    }


def _populate_getting_started(
    cfg: Config,
    sheet: Sheet,
    l2_instance: L2Instance,
) -> None:
    """Render the Getting Started sheet using the L2 instance's prose.

    M.2a's "description-driven prose" core: the welcome text uses
    `l2_instance.description` as the body, and the coverage block lists
    the L2 inventory (account counts, rail counts, etc.) — both
    derived from the L2 instance, NOT hardcoded persona strings.
    Switching L2 instance switches the prose.
    """
    accent = get_preset(cfg.theme_preset).accent

    welcome_body = (
        l2_instance.description
        if l2_instance.description
        else "(L2 instance description missing — fill the top-level "
             "`description` field in the L2 YAML.)"
    )

    sheet.layout.row(height=8).add_text_box(
        TextBox(
            text_box_id="l1-gs-welcome",
            content=rt.text_box(
                rt.inline(
                    _GETTING_STARTED_TITLE,
                    font_size="36px",
                    color=accent,
                ),
                rt.BR, rt.BR,
                rt.body(welcome_body),
            ),
        ),
        width=_FULL,
    )

    sheet.layout.row(height=8).add_text_box(
        TextBox(
            text_box_id="l1-gs-coverage",
            content=rt.text_box(
                rt.subheading("L2 Coverage", color=accent),
                rt.BR,
                rt.body(
                    "What this dashboard reconciles, derived from the "
                    "configured L2 instance:"
                ),
                rt.bullets(_l2_inventory_lines(l2_instance)),
            ),
        ),
        width=_FULL,
    )


def _populate_drift_sheet(
    cfg: Config,
    sheet: Sheet,
    *,
    datasets: dict[str, Dataset],
    l2_instance: L2Instance,
) -> None:
    """Drift sheet — 2 KPIs + leaf-drift table + ledger-drift table.

    Both tables are unaggregated row passthroughs: the L1 views
    pre-filter to violations only (``stored_balance != computed_balance``)
    so each row is one SHOULD-constraint failure.

    M.2a.7: top-of-sheet TextBox enumerates the L2's internal accounts
    + their roles + L2-supplied prose so analysts see the universe of
    accounts drift can surface against.
    """
    accent = get_preset(cfg.theme_preset).accent
    ds_drift = datasets[DS_DRIFT]
    ds_ledger_drift = datasets[DS_LEDGER_DRIFT]

    sheet.layout.row(height=8).add_text_box(
        TextBox(
            text_box_id="l1-drift-accounts",
            content=rt.text_box(
                rt.subheading("Internal Accounts in Scope", color=accent),
                rt.BR,
                rt.body(
                    "Accounts where drift is checked — drift surfaces "
                    "where stored balance disagrees with the cumulative "
                    "net of posted Money records (leaf) or the sum of "
                    "child stored balances (parent):"
                ),
                rt.bullets(_l2_internal_account_role_lines(l2_instance)),
            ),
        ),
        width=_FULL,
    )

    # Row 2: two KPIs side-by-side — one count per drift-violation kind.
    half = _FULL // 2
    kpi_row = sheet.layout.row(height=_KPI_ROW_SPAN)
    kpi_row.add_kpi(
        width=half,
        title="Leaf Accounts in Drift",
        subtitle=(
            "Count of leaf-account day-rows where stored balance "
            "disagrees with the cumulative net of posted Money records."
        ),
        values=[ds_drift["account_id"].count()],
    )
    kpi_row.add_kpi(
        width=half,
        title="Parent Accounts in Drift",
        subtitle=(
            "Count of parent-account day-rows where stored balance "
            "disagrees with the sum of child accounts' stored balances."
        ),
        values=[ds_ledger_drift["account_id"].count()],
    )

    # Row 2: leaf-drift table. Pull account_id Dim local so the link
    # tint can reference the same field_id as the column.
    leaf_account_col = ds_drift["account_id"].dim()
    sheet.layout.row(height=_TABLE_ROW_SPAN).add_table(
        width=_FULL,
        title="Leaf Account Drift",
        subtitle=(
            "Each leaf account's stored vs computed balance per "
            "BusinessDay. Computed = cumulative Σ signed Money through "
            "that day's end. Drift = stored − computed; non-zero ⇒ feed "
            "diverged from the underlying ledger."
        ),
        columns=[
            leaf_account_col,
            ds_drift["account_name"].dim(),
            ds_drift["account_role"].dim(),
            ds_drift["account_parent_role"].dim(),
            ds_drift["business_day_end"].date(),
            ds_drift["stored_balance"].numerical(),
            ds_drift["computed_balance"].numerical(),
            ds_drift["drift"].numerical(),
        ],
        conditional_formatting=[
            CellAccentText(on=leaf_account_col, color=accent),
        ],
    )

    # Row 3: ledger (parent-account) drift table — same shape minus
    # account_parent_role (parents ARE the parents).
    parent_account_col = ds_ledger_drift["account_id"].dim()
    sheet.layout.row(height=_TABLE_ROW_SPAN).add_table(
        width=_FULL,
        title="Parent Account Drift",
        subtitle=(
            "Each parent account's stored vs computed balance per "
            "BusinessDay. Computed = Σ stored balances of its child "
            "accounts on that day. Drift = stored − computed; non-zero "
            "⇒ a child posting didn't roll up correctly."
        ),
        columns=[
            parent_account_col,
            ds_ledger_drift["account_name"].dim(),
            ds_ledger_drift["account_role"].dim(),
            ds_ledger_drift["business_day_end"].date(),
            ds_ledger_drift["stored_balance"].numerical(),
            ds_ledger_drift["computed_balance"].numerical(),
            ds_ledger_drift["drift"].numerical(),
        ],
        conditional_formatting=[
            CellAccentText(on=parent_account_col, color=accent),
        ],
    )


def _populate_drift_timelines_sheet(
    cfg: Config,
    sheet: Sheet,
    *,
    datasets: dict[str, Dataset],
) -> None:
    """Drift Timelines sheet — 2 KPIs + 2 line charts.

    KPIs surface the largest single-day Σ ABS(drift) over the past 7
    days for leaf and parent accounts respectively. Line charts plot
    Σ ABS(drift) per BusinessDay end with one line per account_role,
    so a recurring-drift role visually separates from a one-off spike.

    Datasets pre-aggregate via `GROUP BY business_day_end, account_role`
    on the (already small) drift / ledger_drift matviews. The line-chart
    Y-axis is the SUM of the pre-aggregated `abs_drift` measure since
    the dataset rows are already at (day, role) grain — the SUM is a
    no-op per cell but lets QS render the line chart.
    """
    ds_drift_timeline = datasets[DS_DRIFT_TIMELINE]
    ds_ledger_drift_timeline = datasets[DS_LEDGER_DRIFT_TIMELINE]

    # Row 1: 2 KPIs side-by-side — max single-day Σ ABS(drift) per kind.
    half = _FULL // 2
    kpi_row = sheet.layout.row(height=_KPI_ROW_SPAN)
    kpi_row.add_kpi(
        width=half,
        title="Largest Leaf Drift Day",
        subtitle=(
            "Max Σ ABS(drift) on any single BusinessDay across leaf "
            "accounts in the visible date range. Healthy = $0."
        ),
        values=[ds_drift_timeline["abs_drift"].max()],
    )
    kpi_row.add_kpi(
        width=half,
        title="Largest Parent Drift Day",
        subtitle=(
            "Max Σ ABS(drift) on any single BusinessDay across parent "
            "accounts in the visible date range. Healthy = $0."
        ),
        values=[ds_ledger_drift_timeline["abs_drift"].max()],
    )

    # Row 2: leaf drift line chart — one line per account_role.
    leaf_day_col = ds_drift_timeline["business_day_end"].date()
    sheet.layout.row(height=_CHART_ROW_SPAN).add_line_chart(
        width=_FULL,
        title="Leaf Account Drift Over Time",
        subtitle=(
            "Σ ABS(drift) per BusinessDay end for leaf accounts, one "
            "line per role. A role hugging zero is healthy; persistent "
            "non-zero ⇒ ongoing feed divergence; one-off spike ⇒ "
            "isolated event worth drilling into."
        ),
        category=[leaf_day_col],
        values=[ds_drift_timeline["abs_drift"].sum()],
        colors=[ds_drift_timeline["account_role"].dim()],
        category_label="BusinessDay end",
        value_label="Σ |drift|",
        sort_by=(leaf_day_col, "ASC"),
    )

    # Row 3: ledger (parent) drift line chart — same shape.
    parent_day_col = ds_ledger_drift_timeline["business_day_end"].date()
    sheet.layout.row(height=_CHART_ROW_SPAN).add_line_chart(
        width=_FULL,
        title="Parent Account Drift Over Time",
        subtitle=(
            "Σ ABS(drift) per BusinessDay end for parent accounts, one "
            "line per role. Non-zero ⇒ child postings didn't roll up "
            "correctly that day."
        ),
        category=[parent_day_col],
        values=[ds_ledger_drift_timeline["abs_drift"].sum()],
        colors=[ds_ledger_drift_timeline["account_role"].dim()],
        category_label="BusinessDay end",
        value_label="Σ |drift|",
        sort_by=(parent_day_col, "ASC"),
    )


def _populate_overdraft_sheet(
    cfg: Config,
    sheet: Sheet,
    *,
    datasets: dict[str, Dataset],
) -> None:
    """Overdraft sheet — KPI (count of violations) + violations table.

    Single dataset (`<prefix>_overdraft`) — only internal accounts, only
    days where stored balance < 0. M.2b.2 link tint on account_id; full
    drill wiring lands at M.2b.7.
    """
    accent = get_preset(cfg.theme_preset).accent
    ds_overdraft = datasets[DS_OVERDRAFT]

    sheet.layout.row(height=_KPI_ROW_SPAN).add_kpi(
        width=_FULL,
        title="Internal Accounts in Overdraft",
        subtitle=(
            "Count of internal-account day-rows holding negative stored "
            "balance — every row in the table below is one violation."
        ),
        values=[ds_overdraft["account_id"].count()],
    )

    account_col = ds_overdraft["account_id"].dim()
    sheet.layout.row(height=_TABLE_ROW_SPAN).add_table(
        width=_FULL,
        title="Overdraft Violations",
        subtitle=(
            "Each internal account-day where stored balance < 0. "
            "Negative magnitude indicates how far below zero the account "
            "ended the day."
        ),
        columns=[
            account_col,
            ds_overdraft["account_name"].dim(),
            ds_overdraft["account_role"].dim(),
            ds_overdraft["account_parent_role"].dim(),
            ds_overdraft["business_day_end"].date(),
            ds_overdraft["stored_balance"].numerical(),
        ],
        conditional_formatting=[
            CellAccentText(on=account_col, color=accent),
        ],
    )


def _populate_todays_exceptions_sheet(
    cfg: Config,
    sheet: Sheet,
    *,
    datasets: dict[str, Dataset],
    l2_instance: L2Instance,
) -> None:
    """Today's Exceptions sheet — KPI + check-type breakdown bar +
    sorted detail table.

    Backed by the live UNION ALL dataset across all 5 L1 invariant views
    (drift, ledger_drift, overdraft, limit_breach, expected_eod_balance_breach),
    pre-filtered to the most recent business day at the SQL layer. This
    is the v5 ar_unified_exceptions matview's replacement — no REFRESH
    contract; queries are live.

    M.2a.7: footer TextBox carries the L2 instance's top-level
    description, mirroring the Getting Started welcome — the unified
    view's job is to be the morning landing page, so it gets the
    institution's "what we are" prose at the bottom for context.
    """
    accent = get_preset(cfg.theme_preset).accent
    ds = datasets[DS_TODAYS_EXCEPTIONS]

    # Row 1: total count KPI (full width — single headline number).
    sheet.layout.row(height=_KPI_ROW_SPAN).add_kpi(
        width=_FULL,
        title="Open Exceptions",
        subtitle=(
            "Total count of L1 SHOULD-constraint violations on today's "
            "business day across all 5 invariant checks."
        ),
        values=[ds["account_id"].count()],
    )

    # Row 2: bar chart broken out by check_type (count per check kind).
    sheet.layout.row(height=_CHART_ROW_SPAN).add_bar_chart(
        width=_FULL,
        title="Exceptions by Check Type",
        subtitle=(
            "How today's open exceptions distribute across the 5 L1 "
            "invariants. Spikes in one check kind point at a recurring "
            "error class to investigate first."
        ),
        category=[ds["check_type"].dim()],
        values=[ds["account_id"].count()],
        orientation="HORIZONTAL",
    )

    # Row 3: detail table — every row is one violation, sorted by
    # magnitude DESC so the biggest variances surface first.
    magnitude_col = ds["magnitude"].numerical()
    account_col = ds["account_id"].dim()
    sheet.layout.row(height=_TABLE_ROW_SPAN).add_table(
        width=_FULL,
        title="Exception Detail",
        subtitle=(
            "Every violation on today's business day. Sorted by "
            "magnitude (largest first) so the biggest variances are "
            "the top rows. `transfer_type` and `account_parent_role` "
            "are NULL for checks that don't carry them."
        ),
        columns=[
            ds["check_type"].dim(),
            account_col,
            ds["account_name"].dim(),
            ds["account_role"].dim(),
            ds["account_parent_role"].dim(),
            ds["business_day"].date(),
            ds["transfer_type"].dim(),
            magnitude_col,
        ],
        sort_by=(magnitude_col, "DESC"),
        conditional_formatting=[
            CellAccentText(on=account_col, color=accent),
        ],
    )

    # Row 4: L2-description footer — the institution's "what we are"
    # prose. Mirrors the Getting Started welcome at the bottom of the
    # unified-view landing page.
    footer_body = (
        l2_instance.description
        if l2_instance.description
        else "(L2 instance description missing — fill the top-level "
             "`description` field in the L2 YAML.)"
    )
    sheet.layout.row(height=6).add_text_box(
        TextBox(
            text_box_id="l1-te-l2-footer",
            content=rt.text_box(
                rt.subheading("Institution Context", color=accent),
                rt.BR,
                rt.body(footer_body),
            ),
        ),
        width=_FULL,
    )


def _populate_limit_breach_sheet(
    cfg: Config,
    sheet: Sheet,
    *,
    datasets: dict[str, Dataset],
    l2_instance: L2Instance,
) -> None:
    """Limit Breach sheet — KPI + per-(account, day, type) breach table.

    Single dataset (`<prefix>_limit_breach`). Each row is one cell where
    cumulative outbound debit on that (account, day, transfer_type)
    exceeded the L2-configured cap. The cap column lives next to the
    outbound_total so analysts can read both numbers at once.

    M.2a.7: top-of-sheet TextBox enumerates the L2 LimitSchedules
    (parent_role × transfer_type → cap, plus L2-supplied prose) so
    analysts see "what's configured" before "what got breached" —
    description-driven, not hardcoded. M.2b.2: link tint on
    `account_id` for the M.2b.7 drill plumbing.
    """
    accent = get_preset(cfg.theme_preset).accent
    ds_lb = datasets[DS_LIMIT_BREACH]

    sheet.layout.row(height=8).add_text_box(
        TextBox(
            text_box_id="l1-lb-config",
            content=rt.text_box(
                rt.subheading("Configured Caps", color=accent),
                rt.BR,
                rt.body(
                    "Outbound debit caps from the L2 instance's "
                    "LimitSchedules — these are the thresholds the "
                    "view below compares against:"
                ),
                rt.bullets(_l2_limit_schedule_lines(l2_instance)),
            ),
        ),
        width=_FULL,
    )

    sheet.layout.row(height=_KPI_ROW_SPAN).add_kpi(
        width=_FULL,
        title="Limit Breach Cells",
        subtitle=(
            "Count of (account, day, transfer_type) cells where the "
            "outbound total exceeded the L2-configured cap."
        ),
        values=[ds_lb["account_id"].count()],
    )

    account_col = ds_lb["account_id"].dim()
    sheet.layout.row(height=_TABLE_ROW_SPAN).add_table(
        width=_FULL,
        title="Limit Breach Detail",
        subtitle=(
            "Each (account, day, transfer_type) cell where outbound "
            "debit > cap. `outbound_total` and `cap` shown side-by-side "
            "so the magnitude of the breach is readable in-line."
        ),
        columns=[
            account_col,
            ds_lb["account_name"].dim(),
            ds_lb["account_role"].dim(),
            ds_lb["account_parent_role"].dim(),
            ds_lb["business_day"].date(),
            ds_lb["transfer_type"].dim(),
            ds_lb["outbound_total"].numerical(),
            ds_lb["cap"].numerical(),
        ],
        conditional_formatting=[
            CellAccentText(on=account_col, color=accent),
        ],
    )


def _populate_transactions_sheet(
    cfg: Config,
    sheet: Sheet,
    *,
    datasets: dict[str, Dataset],
) -> None:
    """Transactions sheet — single detail table over the per-leg ledger.

    No KPIs above the table — the value of this sheet is "show me every
    leg + filter to the slice I care about." Filter dropdowns (wired in
    `_wire_per_sheet_dropdowns`) cover account / transfer / status /
    origin / transfer_type. M.2b.2 link tint on `account_id` +
    `transfer_id` cues the M.2b.7 drill plumbing.
    """
    accent = get_preset(cfg.theme_preset).accent
    ds_tx = datasets[DS_TRANSACTIONS]

    account_col = ds_tx["account_id"].dim()
    transfer_col = ds_tx["transfer_id"].dim()
    posting_col = ds_tx["posting"].date()
    sheet.layout.row(height=_TABLE_ROW_SPAN).add_table(
        width=_FULL,
        title="Posting Ledger",
        subtitle=(
            "Every Money record (leg) in the L2 instance's current "
            "view — supersession-aware, so replaced entries don't "
            "show. Sorted by posting time DESC so the most recent "
            "activity is at the top."
        ),
        columns=[
            account_col,
            ds_tx["account_name"].dim(),
            ds_tx["account_role"].dim(),
            transfer_col,
            ds_tx["transfer_type"].dim(),
            ds_tx["rail_name"].dim(),
            ds_tx["amount_money"].numerical(),
            ds_tx["amount_direction"].dim(),
            ds_tx["status"].dim(),
            ds_tx["origin"].dim(),
            posting_col,
        ],
        sort_by=(posting_col, "DESC"),
        conditional_formatting=[
            CellAccentText(on=account_col, color=accent),
            CellAccentText(on=transfer_col, color=accent),
        ],
    )


def _populate_daily_statement_sheet(
    cfg: Config,  # noqa: ARG001  (M.2b.13 wires drift-sign tints)
    sheet: Sheet,
    *,
    datasets: dict[str, Dataset],
) -> None:
    """Daily Statement — 5 KPIs across the day's walk + detail table.

    KPIs read the summary dataset (one row per account-day after sheet
    filters narrow). Detail table reads the per-leg transactions
    dataset. Both filtered by the M.2b.4 sheet-local
    (P_L1_DS_ACCOUNT, P_L1_DS_BALANCE_DATE) parameters via the filter
    groups wired in `_wire_daily_statement_filters`.
    """
    ds_summary = datasets[DS_DAILY_STATEMENT_SUMMARY]
    ds_txn = datasets[DS_DAILY_STATEMENT_TRANSACTIONS]

    # Row 1: 5 KPIs at width 7 each (sums to 35 of 36 grid cols; 1
    # column slack on the right).
    kpi_width = 7
    kpi_row = sheet.layout.row(height=_KPI_ROW_SPAN)
    kpi_row.add_kpi(
        width=kpi_width,
        title="Opening Balance",
        subtitle="End-of-prior-day stored balance for the picked account.",
        values=[ds_summary["opening_balance"].max()],
    )
    kpi_row.add_kpi(
        width=kpi_width,
        title="Debits",
        subtitle="Sum of Debit-direction Money records posted today.",
        values=[ds_summary["total_debits"].max()],
    )
    kpi_row.add_kpi(
        width=kpi_width,
        title="Credits",
        subtitle="Sum of Credit-direction Money records posted today.",
        values=[ds_summary["total_credits"].max()],
    )
    kpi_row.add_kpi(
        width=kpi_width,
        title="Closing Stored",
        subtitle="The day's stored closing balance from the feed.",
        values=[ds_summary["closing_balance_stored"].max()],
    )
    kpi_row.add_kpi(
        width=kpi_width,
        title="Drift",
        subtitle=(
            "Stored − recomputed. Non-zero ⇒ feed doesn't reconcile."
        ),
        values=[ds_summary["drift"].max()],
    )

    # Row 2: detail table — every Money record posted that day for the
    # picked account, after sheet filters narrow.
    sheet.layout.row(height=_TABLE_ROW_SPAN).add_table(
        width=_FULL,
        title="Posted Money Records",
        subtitle=(
            "Every leg posted on the picked account-day. Direction "
            "shows Debit / Credit; status filters out Failed legs in "
            "the summary KPIs but not here."
        ),
        columns=[
            ds_txn["transaction_id"].dim(),
            ds_txn["transfer_id"].dim(),
            ds_txn["transfer_type"].dim(),
            ds_txn["amount_money"].numerical(),
            ds_txn["amount_direction"].dim(),
            ds_txn["status"].dim(),
            ds_txn["origin"].dim(),
            ds_txn["posting"].date(),
            ds_txn["memo"].dim(),
        ],
    )


# -- M.2b.1: Universal date-range filter -------------------------------------
#
# Two analysis-level DateTimeParams drive a per-dataset FilterGroup family:
# every data-bearing sheet has paired date-time picker controls bound to the
# same params, so changing the date range on one sheet propagates to all.
# Per-dataset FilterGroups (rather than a single ALL_DATASETS group) because
# the L1 invariant views don't share a single date column name — daily-balance
# views expose `business_day_start`, while limit_breach + todays_exceptions
# expose `business_day` (DATE_TRUNC of posting). Per-dataset binding sidesteps
# the column-name mismatch without a schema migration.


# Default = last 7 days. QuickSight rolling-date expressions handle the
# "today" anchor; addDateTime yields the start-of-window 7 days back.
_DATE_END_DEFAULT_EXPR = "truncDate('DD', now())"
_DATE_START_DEFAULT_EXPR = "addDateTime(-7, 'DD', truncDate('DD', now()))"


def _wire_date_range_filter(
    analysis: Analysis,
    *,
    datasets: dict[str, Dataset],
    drift_sheet: Sheet,
    drift_timelines_sheet: Sheet,
    overdraft_sheet: Sheet,
    limit_breach_sheet: Sheet,
    todays_exceptions_sheet: Sheet,
) -> None:
    """Wire the universal date-range filter (params + groups + controls).

    Adds 2 DateTimeParams (P_L1_DATE_START + P_L1_DATE_END) with rolling
    7-day defaults; 5 SINGLE_DATASET FilterGroups (one per data-bearing
    dataset, each scoped to its sheet); paired ParameterDateTimePicker
    controls on every data-bearing sheet so the analyst sets the window
    once and it propagates.
    """
    date_start = analysis.add_parameter(DateTimeParam(
        name=P_L1_DATE_START,
        time_granularity="DAY",
        default=DateTimeDefaultValues(
            RollingDate={"Expression": _DATE_START_DEFAULT_EXPR},
        ),
    ))
    date_end = analysis.add_parameter(DateTimeParam(
        name=P_L1_DATE_END,
        time_granularity="DAY",
        default=DateTimeDefaultValues(
            RollingDate={"Expression": _DATE_END_DEFAULT_EXPR},
        ),
    ))

    # Param-bound dict literals — TimeRangeFilter.minimum/maximum are
    # passthrough dicts; {"Parameter": "<name>"} is the AWS shape for
    # parameter-driven bounds (mirrors how DateTimeDefaultValues
    # passthrough works).
    min_bound: dict[str, str] = {"Parameter": P_L1_DATE_START}
    max_bound: dict[str, str] = {"Parameter": P_L1_DATE_END}

    def _scope_one(
        dataset_key: str, date_col: str, sheet: Sheet, fg_id: str,
    ) -> None:
        ds = datasets[dataset_key]
        fg = analysis.add_filter_group(FilterGroup(
            filter_group_id=fg_id,  # type: ignore[arg-type]
            cross_dataset="SINGLE_DATASET",
            filters=[TimeRangeFilter(
                filter_id=f"filter-{fg_id}",
                dataset=ds,
                column=ds[date_col],
                null_option="NON_NULLS_ONLY",
                time_granularity="DAY",
                minimum=min_bound,
                maximum=max_bound,
            )],
        ))
        fg.scope_sheet(sheet)

    # Drift sheet — both leaf-drift + parent-drift datasets share
    # business_day_start.
    _scope_one(DS_DRIFT, "business_day_start", drift_sheet,
               "fg-l1-date-drift")
    _scope_one(DS_LEDGER_DRIFT, "business_day_start", drift_sheet,
               "fg-l1-date-ledger-drift")
    # Drift Timelines uses pre-aggregated datasets keyed on
    # business_day_end (one row per (day, role)).
    _scope_one(DS_DRIFT_TIMELINE, "business_day_end",
               drift_timelines_sheet, "fg-l1-date-drift-timeline")
    _scope_one(DS_LEDGER_DRIFT_TIMELINE, "business_day_end",
               drift_timelines_sheet, "fg-l1-date-ledger-drift-timeline")
    _scope_one(DS_OVERDRAFT, "business_day_start", overdraft_sheet,
               "fg-l1-date-overdraft")
    # Limit breach + today's exceptions expose `business_day` (truncated
    # posting), not `business_day_start`.
    _scope_one(DS_LIMIT_BREACH, "business_day", limit_breach_sheet,
               "fg-l1-date-limit-breach")
    _scope_one(DS_TODAYS_EXCEPTIONS, "business_day",
               todays_exceptions_sheet, "fg-l1-date-todays-exceptions")

    # Per-sheet date pickers — bound to the shared params so all five
    # sheets' pickers sync.
    for sheet in (
        drift_sheet, drift_timelines_sheet, overdraft_sheet,
        limit_breach_sheet, todays_exceptions_sheet,
    ):
        sheet.add_parameter_datetime_picker(
            parameter=date_start, title="Date From",
        )
        sheet.add_parameter_datetime_picker(
            parameter=date_end, title="Date To",
        )


def _wire_per_sheet_dropdowns(
    analysis: Analysis,
    *,
    datasets: dict[str, Dataset],
    drift_sheet: Sheet,
    drift_timelines_sheet: Sheet,
    overdraft_sheet: Sheet,
    limit_breach_sheet: Sheet,
    todays_exceptions_sheet: Sheet,
    transactions_sheet: Sheet,
) -> None:
    """M.2b.3 — per-sheet category filter dropdowns.

    Each dropdown is a multi-select with empty-default-means-all
    (`select_all_options="FILTER_ALL_VALUES"`), keyed off a
    `CategoryFilter.with_values(values=[])` per AR's pattern. Single-
    sheet scope (cross_dataset SINGLE_DATASET) for sheets backed by one
    dataset; cross_dataset ALL_DATASETS only on the Drift sheet, which
    has both leaf-drift + parent-drift datasets sharing the same
    column names.
    """

    def _dropdown(
        *,
        fg_id: str,
        ds: Dataset,
        col: str,
        title: str,
        sheet: Sheet,
        cross_dataset: str = "SINGLE_DATASET",
    ) -> None:
        cat_filter = CategoryFilter.with_values(
            filter_id=f"filter-{fg_id}",
            dataset=ds,
            column=ds[col],
            values=[],
            select_all_options="FILTER_ALL_VALUES",
        )
        fg = analysis.add_filter_group(FilterGroup(
            filter_group_id=fg_id,  # type: ignore[arg-type]
            cross_dataset=cross_dataset,  # type: ignore[arg-type]
            filters=[cat_filter],
        ))
        fg.scope_sheet(sheet)
        sheet.add_filter_dropdown(filter=cat_filter, title=title)

    ds_drift = datasets[DS_DRIFT]
    ds_overdraft = datasets[DS_OVERDRAFT]
    ds_lb = datasets[DS_LIMIT_BREACH]
    ds_te = datasets[DS_TODAYS_EXCEPTIONS]

    # Drift — both drift + ledger_drift datasets share column names, so
    # ALL_DATASETS lets one dropdown filter both tables on the sheet.
    _dropdown(
        fg_id="fg-l1-drift-account", ds=ds_drift, col="account_id",
        title="Account", sheet=drift_sheet, cross_dataset="ALL_DATASETS",
    )
    _dropdown(
        fg_id="fg-l1-drift-role", ds=ds_drift, col="account_role",
        title="Account Role", sheet=drift_sheet,
        cross_dataset="ALL_DATASETS",
    )

    # Drift Timelines — both timeline datasets share column names too.
    ds_drift_tl = datasets[DS_DRIFT_TIMELINE]
    _dropdown(
        fg_id="fg-l1-drift-tl-role", ds=ds_drift_tl, col="account_role",
        title="Account Role", sheet=drift_timelines_sheet,
        cross_dataset="ALL_DATASETS",
    )

    # Overdraft — single dataset.
    _dropdown(
        fg_id="fg-l1-overdraft-account", ds=ds_overdraft,
        col="account_id", title="Account", sheet=overdraft_sheet,
    )
    _dropdown(
        fg_id="fg-l1-overdraft-role", ds=ds_overdraft,
        col="account_role", title="Account Role",
        sheet=overdraft_sheet,
    )

    # Limit Breach — single dataset; account + transfer_type.
    _dropdown(
        fg_id="fg-l1-limit-breach-account", ds=ds_lb, col="account_id",
        title="Account", sheet=limit_breach_sheet,
    )
    _dropdown(
        fg_id="fg-l1-limit-breach-type", ds=ds_lb, col="transfer_type",
        title="Transfer Type", sheet=limit_breach_sheet,
    )

    # Today's Exceptions — check_type narrows the unified UNION; account
    # + transfer_type are the secondary narrow-downs.
    _dropdown(
        fg_id="fg-l1-todays-exc-check-type", ds=ds_te, col="check_type",
        title="Check Type", sheet=todays_exceptions_sheet,
    )
    _dropdown(
        fg_id="fg-l1-todays-exc-account", ds=ds_te, col="account_id",
        title="Account", sheet=todays_exceptions_sheet,
    )
    _dropdown(
        fg_id="fg-l1-todays-exc-type", ds=ds_te, col="transfer_type",
        title="Transfer Type", sheet=todays_exceptions_sheet,
    )

    # Transactions — 5 dropdowns covering the analyst's narrow vectors:
    # account / transfer / status / origin / transfer_type.
    ds_tx = datasets[DS_TRANSACTIONS]
    _dropdown(
        fg_id="fg-l1-tx-account", ds=ds_tx, col="account_id",
        title="Account", sheet=transactions_sheet,
    )
    _dropdown(
        fg_id="fg-l1-tx-transfer", ds=ds_tx, col="transfer_id",
        title="Transfer", sheet=transactions_sheet,
    )
    _dropdown(
        fg_id="fg-l1-tx-status", ds=ds_tx, col="status",
        title="Status", sheet=transactions_sheet,
    )
    _dropdown(
        fg_id="fg-l1-tx-origin", ds=ds_tx, col="origin",
        title="Origin", sheet=transactions_sheet,
    )
    _dropdown(
        fg_id="fg-l1-tx-type", ds=ds_tx, col="transfer_type",
        title="Transfer Type", sheet=transactions_sheet,
    )


def _wire_daily_statement_filters(
    analysis: Analysis,
    *,
    datasets: dict[str, Dataset],
    daily_statement_sheet: Sheet,
) -> None:
    """M.2b.4 — wire the Daily Statement sheet's per-account-day filter.

    Two analysis-level parameters (P_L1_DS_ACCOUNT, P_L1_DS_BALANCE_DATE)
    drive both the summary dataset and the transactions dataset via two
    SINGLE_DATASET FilterGroups each — same-shape (account_id +
    business_day_start) on the summary, (account_id + business_day) on
    the transactions. ParameterDropdown + ParameterDateTimePicker
    controls on the sheet bind to the params, so changing either
    propagates to KPIs + table at once.

    No defaults are pinned (no `RollingDate` / `default=...`) — at
    first load the controls render empty and the analyst picks. This
    avoids the no-hardcoded-data trap where a default account_id
    would have to know an L2-specific value.
    """
    ds_account = analysis.add_parameter(StringParam(
        name=P_L1_DS_ACCOUNT,
    ))
    ds_balance_date = analysis.add_parameter(DateTimeParam(
        name=P_L1_DS_BALANCE_DATE,
        time_granularity="DAY",
    ))

    summary_ds = datasets[DS_DAILY_STATEMENT_SUMMARY]
    txn_ds = datasets[DS_DAILY_STATEMENT_TRANSACTIONS]

    # Summary dataset: account_id + business_day_start.
    summary_account_fg = analysis.add_filter_group(FilterGroup(
        filter_group_id="fg-l1-ds-summary-account",  # type: ignore[arg-type]
        cross_dataset="SINGLE_DATASET",
        filters=[CategoryFilter.with_parameter(
            filter_id="filter-l1-ds-summary-account",
            dataset=summary_ds,
            column=summary_ds["account_id"],
            parameter=ds_account,
        )],
    ))
    summary_account_fg.scope_sheet(daily_statement_sheet)

    summary_date_fg = analysis.add_filter_group(FilterGroup(
        filter_group_id="fg-l1-ds-summary-date",  # type: ignore[arg-type]
        cross_dataset="SINGLE_DATASET",
        filters=[TimeEqualityFilter(
            filter_id="filter-l1-ds-summary-date",
            dataset=summary_ds,
            column=summary_ds["business_day_start"],
            parameter=ds_balance_date,
            time_granularity="DAY",
        )],
    ))
    summary_date_fg.scope_sheet(daily_statement_sheet)

    # Transactions dataset: account_id + business_day (DATE_TRUNC of
    # posting); same parameter-bound shape.
    txn_account_fg = analysis.add_filter_group(FilterGroup(
        filter_group_id="fg-l1-ds-txn-account",  # type: ignore[arg-type]
        cross_dataset="SINGLE_DATASET",
        filters=[CategoryFilter.with_parameter(
            filter_id="filter-l1-ds-txn-account",
            dataset=txn_ds,
            column=txn_ds["account_id"],
            parameter=ds_account,
        )],
    ))
    txn_account_fg.scope_sheet(daily_statement_sheet)

    txn_date_fg = analysis.add_filter_group(FilterGroup(
        filter_group_id="fg-l1-ds-txn-date",  # type: ignore[arg-type]
        cross_dataset="SINGLE_DATASET",
        filters=[TimeEqualityFilter(
            filter_id="filter-l1-ds-txn-date",
            dataset=txn_ds,
            column=txn_ds["business_day"],
            parameter=ds_balance_date,
            time_granularity="DAY",
        )],
    ))
    txn_date_fg.scope_sheet(daily_statement_sheet)

    # Sheet controls — single-select dropdown + datetime picker bound
    # to the params.
    daily_statement_sheet.add_parameter_dropdown(
        parameter=ds_account, title="Account",
        type="SINGLE_SELECT",
    )
    daily_statement_sheet.add_parameter_datetime_picker(
        parameter=ds_balance_date, title="Business Day",
    )


def build_l1_dashboard_app(
    cfg: Config,
    *,
    l2_instance: L2Instance | None = None,
) -> App:
    """Construct the L1 Reconciliation Dashboard App as a tree.

    M.2a.3: registers Analysis + Dashboard + Getting Started + Drift
    sheets, plus the 2 L1 invariant datasets (drift + ledger_drift).
    Substeps M.2a.4-M.2a.6 add the remaining per-invariant sheets
    (Overdraft, Limit Breach, Today's Exceptions). Each sheet IS one
    L1 SHOULD-constraint visualized via the M.1a.7 invariant views.

    Dashboard ID convention: ``<l2_prefix>-l1-dashboard``. Matches the
    M.2a reframe — "L1 dashboard configured by an L2 instance," not
    "AR app for SNB CMS."
    """
    if l2_instance is None:
        l2_instance = default_l2_instance()

    app = App(name="l1-dashboard", cfg=cfg)
    analysis = app.set_analysis(Analysis(
        analysis_id_suffix="l1-dashboard-analysis",
        name=_analysis_name(cfg, l2_instance),
    ))

    # Datasets first — registers contracts so visual ds["col"] refs validate.
    datasets = _l1_datasets(cfg, l2_instance)
    for ds in datasets.values():
        app.add_dataset(ds)

    getting_started = analysis.add_sheet(Sheet(
        sheet_id=SHEET_GETTING_STARTED,
        name=_GETTING_STARTED_NAME,
        title=_GETTING_STARTED_TITLE,
        description=_GETTING_STARTED_DESCRIPTION,
    ))
    _populate_getting_started(cfg, getting_started, l2_instance)

    drift_sheet = analysis.add_sheet(Sheet(
        sheet_id=SHEET_DRIFT,
        name=_DRIFT_NAME,
        title=_DRIFT_TITLE,
        description=_DRIFT_DESCRIPTION,
    ))
    _populate_drift_sheet(
        cfg, drift_sheet, datasets=datasets, l2_instance=l2_instance,
    )

    drift_timelines_sheet = analysis.add_sheet(Sheet(
        sheet_id=SHEET_DRIFT_TIMELINES,
        name=_DRIFT_TIMELINES_NAME,
        title=_DRIFT_TIMELINES_TITLE,
        description=_DRIFT_TIMELINES_DESCRIPTION,
    ))
    _populate_drift_timelines_sheet(
        cfg, drift_timelines_sheet, datasets=datasets,
    )

    overdraft_sheet = analysis.add_sheet(Sheet(
        sheet_id=SHEET_OVERDRAFT,
        name=_OVERDRAFT_NAME,
        title=_OVERDRAFT_TITLE,
        description=_OVERDRAFT_DESCRIPTION,
    ))
    _populate_overdraft_sheet(cfg, overdraft_sheet, datasets=datasets)

    limit_breach_sheet = analysis.add_sheet(Sheet(
        sheet_id=SHEET_LIMIT_BREACH,
        name=_LIMIT_BREACH_NAME,
        title=_LIMIT_BREACH_TITLE,
        description=_LIMIT_BREACH_DESCRIPTION,
    ))
    _populate_limit_breach_sheet(
        cfg, limit_breach_sheet,
        datasets=datasets, l2_instance=l2_instance,
    )

    todays_exceptions_sheet = analysis.add_sheet(Sheet(
        sheet_id=SHEET_TODAYS_EXCEPTIONS,
        name=_TODAYS_EXCEPTIONS_NAME,
        title=_TODAYS_EXCEPTIONS_TITLE,
        description=_TODAYS_EXCEPTIONS_DESCRIPTION,
    ))
    _populate_todays_exceptions_sheet(
        cfg, todays_exceptions_sheet,
        datasets=datasets, l2_instance=l2_instance,
    )

    daily_statement_sheet = analysis.add_sheet(Sheet(
        sheet_id=SHEET_DAILY_STATEMENT,
        name=_DAILY_STATEMENT_NAME,
        title=_DAILY_STATEMENT_TITLE,
        description=_DAILY_STATEMENT_DESCRIPTION,
    ))
    _populate_daily_statement_sheet(
        cfg, daily_statement_sheet, datasets=datasets,
    )

    transactions_sheet = analysis.add_sheet(Sheet(
        sheet_id=SHEET_TRANSACTIONS,
        name=_TRANSACTIONS_NAME,
        title=_TRANSACTIONS_TITLE,
        description=_TRANSACTIONS_DESCRIPTION,
    ))
    _populate_transactions_sheet(
        cfg, transactions_sheet, datasets=datasets,
    )

    # M.2b.1 — Universal date-range filter wires the sheets together.
    # Lands AFTER all sheets are populated since the FilterGroups scope
    # by sheet ref + the controls register on the sheets directly.
    _wire_date_range_filter(
        analysis,
        datasets=datasets,
        drift_sheet=drift_sheet,
        drift_timelines_sheet=drift_timelines_sheet,
        overdraft_sheet=overdraft_sheet,
        limit_breach_sheet=limit_breach_sheet,
        todays_exceptions_sheet=todays_exceptions_sheet,
    )

    # M.2b.3 + M.2b.5 — Per-sheet category filter dropdowns (account /
    # role / transfer_type / check_type / status / origin as
    # appropriate per sheet).
    _wire_per_sheet_dropdowns(
        analysis,
        datasets=datasets,
        drift_sheet=drift_sheet,
        drift_timelines_sheet=drift_timelines_sheet,
        overdraft_sheet=overdraft_sheet,
        limit_breach_sheet=limit_breach_sheet,
        todays_exceptions_sheet=todays_exceptions_sheet,
        transactions_sheet=transactions_sheet,
    )

    # M.2b.4 — Daily Statement per-account-day parameter filters.
    _wire_daily_statement_filters(
        analysis,
        datasets=datasets,
        daily_statement_sheet=daily_statement_sheet,
    )

    app.create_dashboard(
        dashboard_id_suffix="l1-dashboard",
        name=_analysis_name(cfg, l2_instance),
    )
    return app


# ---------------------------------------------------------------------------
# CLI / external-caller shims. The CLI imports these directly and writes
# the emit_analysis() / emit_dashboard() output to JSON files, mirroring
# the AR / PR / Investigation / Executives shape.
# ---------------------------------------------------------------------------


def build_analysis(
    cfg: Config,
    *,
    l2_instance: L2Instance | None = None,
):
    """Build the complete L1 Dashboard Analysis resource via the tree.

    Forwards ``l2_instance`` to ``build_l1_dashboard_app``; default
    behaviour (unset) auto-loads the canonical Sasquatch AR L2 fixture.
    Return type is the AWS-shape Analysis dataclass from common.models.
    """
    return build_l1_dashboard_app(cfg, l2_instance=l2_instance).emit_analysis()


def build_l1_dashboard_dashboard(
    cfg: Config,
    *,
    l2_instance: L2Instance | None = None,
):
    """Build the L1 Dashboard Dashboard resource via the tree."""
    return build_l1_dashboard_app(
        cfg, l2_instance=l2_instance,
    ).emit_dashboard()
