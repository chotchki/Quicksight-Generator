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
    DS_DRIFT,
    DS_LEDGER_DRIFT,
    DS_LIMIT_BREACH,
    DS_OVERDRAFT,
    DS_TODAYS_EXCEPTIONS,
    build_all_l1_dashboard_datasets,
)
from quicksight_gen.common import rich_text as rt
from quicksight_gen.common.config import Config
from quicksight_gen.common.ids import SheetId
from quicksight_gen.common.l2 import L2Instance
from quicksight_gen.common.theme import get_preset
from quicksight_gen.common.tree import (
    Analysis,
    App,
    Dataset,
    Sheet,
    TextBox,
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
SHEET_OVERDRAFT = SheetId("l1-sheet-overdraft")
SHEET_LIMIT_BREACH = SheetId("l1-sheet-limit-breach")
SHEET_TODAYS_EXCEPTIONS = SheetId("l1-sheet-todays-exceptions")


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

    # Row 2: leaf-drift table.
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
            ds_drift["account_id"].dim(),
            ds_drift["account_name"].dim(),
            ds_drift["account_role"].dim(),
            ds_drift["account_parent_role"].dim(),
            ds_drift["business_day_end"].date(),
            ds_drift["stored_balance"].numerical(),
            ds_drift["computed_balance"].numerical(),
            ds_drift["drift"].numerical(),
        ],
    )

    # Row 3: ledger (parent-account) drift table — same shape minus
    # account_parent_role (parents ARE the parents).
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
            ds_ledger_drift["account_id"].dim(),
            ds_ledger_drift["account_name"].dim(),
            ds_ledger_drift["account_role"].dim(),
            ds_ledger_drift["business_day_end"].date(),
            ds_ledger_drift["stored_balance"].numerical(),
            ds_ledger_drift["computed_balance"].numerical(),
            ds_ledger_drift["drift"].numerical(),
        ],
    )


def _populate_overdraft_sheet(
    cfg: Config,  # noqa: ARG001  (M.2a.7 wires theme accent on conditional formats)
    sheet: Sheet,
    *,
    datasets: dict[str, Dataset],
) -> None:
    """Overdraft sheet — KPI (count of violations) + violations table.

    Single dataset (`<prefix>_overdraft`) — only internal accounts, only
    days where stored balance < 0. No drill actions yet (M.2a.7).
    """
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

    sheet.layout.row(height=_TABLE_ROW_SPAN).add_table(
        width=_FULL,
        title="Overdraft Violations",
        subtitle=(
            "Each internal account-day where stored balance < 0. "
            "Negative magnitude indicates how far below zero the account "
            "ended the day."
        ),
        columns=[
            ds_overdraft["account_id"].dim(),
            ds_overdraft["account_name"].dim(),
            ds_overdraft["account_role"].dim(),
            ds_overdraft["account_parent_role"].dim(),
            ds_overdraft["business_day_end"].date(),
            ds_overdraft["stored_balance"].numerical(),
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
            ds["account_id"].dim(),
            ds["account_name"].dim(),
            ds["account_role"].dim(),
            ds["account_parent_role"].dim(),
            ds["business_day"].date(),
            ds["transfer_type"].dim(),
            magnitude_col,
        ],
        sort_by=(magnitude_col, "DESC"),
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
    description-driven, not hardcoded.
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

    sheet.layout.row(height=_TABLE_ROW_SPAN).add_table(
        width=_FULL,
        title="Limit Breach Detail",
        subtitle=(
            "Each (account, day, transfer_type) cell where outbound "
            "debit > cap. `outbound_total` and `cap` shown side-by-side "
            "so the magnitude of the breach is readable in-line."
        ),
        columns=[
            ds_lb["account_id"].dim(),
            ds_lb["account_name"].dim(),
            ds_lb["account_role"].dim(),
            ds_lb["account_parent_role"].dim(),
            ds_lb["business_day"].date(),
            ds_lb["transfer_type"].dim(),
            ds_lb["outbound_total"].numerical(),
            ds_lb["cap"].numerical(),
        ],
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

    app.create_dashboard(
        dashboard_id_suffix="l1-dashboard",
        name=_analysis_name(cfg, l2_instance),
    )
    return app
