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
    M.2a.4 — Overdraft sheet (this commit) — KPI + violations table
    M.2a.5 — Limit Breach sheet
    M.2a.6 — Today's Exceptions sheet (UNION across L1 views)
    M.2a.7 — Description-driven prose across every sheet
    M.2a.8 — Hash-lock the seed at the M.2a structure
    M.2a.9 — Deploy + verify against Aurora
    M.2a.10 — Iteration gate; decide on apps/account_recon/ deprecation
"""

from __future__ import annotations

from quicksight_gen.apps.account_recon._l2 import default_l2_instance
from quicksight_gen.apps.l1_dashboard.datasets import (
    DS_DRIFT,
    DS_LEDGER_DRIFT,
    DS_OVERDRAFT,
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
_TABLE_ROW_SPAN = 18


# Sheet IDs — inlined in app.py per the greenfield-app convention
# (L.7 Executives) since the L1 dashboard isn't dragging legacy URL
# stability constraints from a previous deploy.
SHEET_GETTING_STARTED = SheetId("l1-sheet-getting-started")
SHEET_DRIFT = SheetId("l1-sheet-drift")
SHEET_OVERDRAFT = SheetId("l1-sheet-overdraft")


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


def _analysis_name(cfg: Config, l2_instance: L2Instance) -> str:
    """Title shown on the deployed QuickSight Analysis."""
    return f"L1 Reconciliation Dashboard ({l2_instance.instance})"


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
    visual_ids = [DS_DRIFT, DS_LEDGER_DRIFT, DS_OVERDRAFT]
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
    `l2_instance.description` as the body — NOT a hardcoded persona
    string. This is the seam M.2a.7 generalizes across every sheet
    (subtitle prose pulled from per-entity descriptions). For M.2a.2
    we just need the welcome + a single overview block.
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
        width=36,  # full QuickSight row width
    )


def _populate_drift_sheet(
    cfg: Config,  # noqa: ARG001  (M.2a.7 wires theme accent on conditional formats)
    sheet: Sheet,
    *,
    datasets: dict[str, Dataset],
) -> None:
    """Drift sheet — 2 KPIs + leaf-drift table + ledger-drift table.

    Both tables are unaggregated row passthroughs: the L1 views
    pre-filter to violations only (``stored_balance != computed_balance``)
    so each row is one SHOULD-constraint failure. No drill actions yet —
    M.2a.7 layers same-sheet + cross-sheet wiring on once every sheet
    exists.
    """
    ds_drift = datasets[DS_DRIFT]
    ds_ledger_drift = datasets[DS_LEDGER_DRIFT]

    # Row 1: two KPIs side-by-side — one count per drift-violation kind.
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
    _populate_drift_sheet(cfg, drift_sheet, datasets=datasets)

    overdraft_sheet = analysis.add_sheet(Sheet(
        sheet_id=SHEET_OVERDRAFT,
        name=_OVERDRAFT_NAME,
        title=_OVERDRAFT_TITLE,
        description=_OVERDRAFT_DESCRIPTION,
    ))
    _populate_overdraft_sheet(cfg, overdraft_sheet, datasets=datasets)

    # Per-invariant sheets land in M.2a.5-M.2a.6.

    app.create_dashboard(
        dashboard_id_suffix="l1-dashboard",
        name=_analysis_name(cfg, l2_instance),
    )
    return app
