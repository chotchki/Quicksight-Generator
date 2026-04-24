"""Tree-based builder for the Executives App (L.6 — greenfield).

First app built directly against the Phase L tree primitives instead
of being ported from imperative builders. The L.6 acceptance is that
a first-time author can wire a 4-sheet app without touching
``constants.py`` (the tree carries internal IDs); URL-facing sheet
IDs are still explicit but live inline here, not in a sibling
``constants.py`` module.

Sheets land per L.6 sub-step:

- L.6.2 — Skeleton + Getting Started shell (this commit).
- L.6.3 — Dataset SQL (`datasets.py`).
- L.6.4 — Account Coverage sheet.
- L.6.5 — Transaction Volume Over Time sheet.
- L.6.6 — Money Moved sheet.
- L.6.7 — Cross-app drills into AR Transactions.
- L.6.8 — Theme: reuse `default` (non-demo) / `sasquatch-bank` (demo).
- L.6.9 — Unit tests (mirror the per-app shape).
- L.6.10 — CLI wiring (`generate executives`, `--all` includes it).
- L.6.11 — Confirm Executives reads existing PR + AR + Investigation
  seeds without needing its own demo SQL.
- L.6.12 — Iteration gate: surface any L.1 friction.
"""

from __future__ import annotations

# Importing datasets registers each Executives DatasetContract via its
# module-level register_contract() side effect — required so the L.1.17
# bare-string / unvalidated-Column emit-time validator can resolve
# every ds["col"] ref in the visuals below.
from quicksight_gen.apps.executives import datasets as _register_contracts  # noqa: F401
from quicksight_gen.common import rich_text as rt
from quicksight_gen.common.config import Config
from quicksight_gen.common.ids import SheetId
from quicksight_gen.common.models import Analysis as ModelAnalysis
from quicksight_gen.common.models import Dashboard as ModelDashboard
from quicksight_gen.common.theme import get_preset
from quicksight_gen.common.tree import (
    Analysis,
    App,
    Sheet,
    TextBox,
)


# Layout constants — same pattern as PR/AR/Inv app.py modules.
_FULL = 36


# URL-facing sheet IDs — these need to be stable across deploys and
# embed-link rebuilds, so they stay explicit (per the URL-facing
# vs internal-IDs convention from L.1.16). Internal visual / action /
# layout IDs auto-resolve at emit time.
SHEET_EXEC_GETTING_STARTED = SheetId("exec-sheet-getting-started")
SHEET_EXEC_ACCOUNT_COVERAGE = SheetId("exec-sheet-account-coverage")
SHEET_EXEC_TRANSACTION_VOLUME = SheetId("exec-sheet-transaction-volume")
SHEET_EXEC_MONEY_MOVED = SheetId("exec-sheet-money-moved")


# Sheet descriptions — single source of truth, also surfaced in the
# Getting Started bullet blocks so each sheet's description matches
# the summary on the landing page.
_ACCOUNT_COVERAGE_DESCRIPTION = (
    "How many accounts the bank has on its books and how many of them "
    "have actually moved money in the selected period. Counts split "
    "by account type so you can see the shape of the deposit base "
    "next to the GL control accounts that drive operations."
)

_TRANSACTION_VOLUME_DESCRIPTION = (
    "Transaction throughput over time, sliced by transfer_type so you "
    "can see which rails are growing or contracting. The line chart is "
    "the trend; the bar chart is the period total per type."
)

_MONEY_MOVED_DESCRIPTION = (
    "Dollar volume moving across the bank, by rail, over time. Net "
    "(signed sum — flows into the bank are positive) and gross (sum of "
    "absolute values — total handle, regardless of direction) live "
    "side by side; the per-rail bar shows where the volume is coming "
    "from."
)


_ACCOUNT_COVERAGE_BULLETS = [
    "KPIs: total open accounts + active accounts in the period",
    "Bar charts: open + active counts by account type",
    "Detail table: per-account last activity date and count",
]

_TRANSACTION_VOLUME_BULLETS = [
    "KPIs: total transactions + average daily volume",
    "Daily transaction count, coloured by transfer_type",
    "Period total per transfer_type",
]

_MONEY_MOVED_BULLETS = [
    "KPIs: net money moved (Σ signed) + gross money moved (Σ |signed|)",
    "Daily gross money moved, coloured by transfer_type",
    "Period total per transfer_type",
]


# ---------------------------------------------------------------------------
# Getting Started (L.6.2)
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

    sheet.layout.row(height=4).add_text_box(
        TextBox(
            text_box_id="exec-gs-welcome",
            content=rt.text_box(
                rt.inline(
                    "Executives Dashboard",
                    font_size="36px",
                    color=accent,
                ),
                rt.BR,
                rt.BR,
                rt.body(
                    "Board-cadence view of the bank's transaction "
                    "throughput, money movement, and account coverage. "
                    "Scan for trends; click any row or bar to drill into "
                    "the operational sheets for the underlying "
                    "transactions."
                ),
            ),
        ),
        width=_FULL,
    )

    sheet.layout.row(height=6).add_text_box(
        TextBox(
            text_box_id="exec-gs-clickability-legend",
            content=rt.text_box(
                rt.heading("Clickable cells", color=accent),
                rt.BR,
                rt.BR,
                rt.body(
                    "Cells rendered in the theme accent color are "
                    "interactive:"
                ),
                rt.bullets_raw([
                    "Plain accent-coloured text — left-click drills to "
                    "an operational sheet (Account Reconciliation's "
                    "Transactions tab) filtered to the row's "
                    "account / transfer type",
                    rt.inline(
                        "Heads-up: drill-down filters stick after you "
                        "switch tabs. Refresh the dashboard to clear "
                        "them.",
                        color=accent,
                    ),
                ]),
            ),
        ),
        width=_FULL,
    )

    sheet_blocks = [
        (
            "exec-gs-account-coverage", "Account Coverage",
            _ACCOUNT_COVERAGE_DESCRIPTION, _ACCOUNT_COVERAGE_BULLETS,
        ),
        (
            "exec-gs-transaction-volume", "Transaction Volume Over Time",
            _TRANSACTION_VOLUME_DESCRIPTION, _TRANSACTION_VOLUME_BULLETS,
        ),
        (
            "exec-gs-money-moved", "Money Moved",
            _MONEY_MOVED_DESCRIPTION, _MONEY_MOVED_BULLETS,
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
# App entry points
# ---------------------------------------------------------------------------

def _analysis_name(cfg: Config) -> str:
    preset = get_preset(cfg.theme_preset)
    if preset.analysis_name_prefix:
        return f"{preset.analysis_name_prefix} — Executives"
    return "Executives"


# Sheet display order. Pre-register-all-shells pattern (mirrors
# AR/PR L.x.2) so cross-sheet drills can target by ref before all
# populators have run. The L.6.2 commit only populates Getting
# Started; the other 3 sheets ship as bare shells (id + metadata
# only) until L.6.4 / L.6.5 / L.6.6 land.
_EXEC_SHEET_SPECS: tuple[tuple[str, str, str, str], ...] = (
    (SHEET_EXEC_GETTING_STARTED, "Getting Started", "Getting Started",
     "Landing page — summarises each tab in this dashboard so readers "
     "know where to look first. No filters or visuals."),
    (SHEET_EXEC_ACCOUNT_COVERAGE, "Account Coverage", "Account Coverage",
     _ACCOUNT_COVERAGE_DESCRIPTION),
    (SHEET_EXEC_TRANSACTION_VOLUME, "Transaction Volume Over Time",
     "Transaction Volume Over Time", _TRANSACTION_VOLUME_DESCRIPTION),
    (SHEET_EXEC_MONEY_MOVED, "Money Moved", "Money Moved",
     _MONEY_MOVED_DESCRIPTION),
)


def build_executives_app(cfg: Config) -> App:
    """Construct the Executives App as a tree."""
    app = App(name="executives", cfg=cfg)
    analysis = app.set_analysis(Analysis(
        analysis_id_suffix="executives-analysis",
        name=_analysis_name(cfg),
    ))

    sheets: dict[str, Sheet] = {}
    for sheet_id, name, title, description in _EXEC_SHEET_SPECS:
        sheets[sheet_id] = analysis.add_sheet(Sheet(
            sheet_id=sheet_id,  # type: ignore[arg-type]
            name=name,
            title=title,
            description=description,
        ))

    _populate_getting_started(cfg, sheets[SHEET_EXEC_GETTING_STARTED])

    app.create_dashboard(
        dashboard_id_suffix="executives-dashboard",
        name=_analysis_name(cfg),
    )
    return app


# ---------------------------------------------------------------------------
# CLI / external-caller shims. Same shape as the other apps' shims.
# Wired into the CLI in L.6.10.
# ---------------------------------------------------------------------------

def build_analysis(cfg: Config) -> ModelAnalysis:
    """Build the complete Executives Analysis resource via the tree."""
    return build_executives_app(cfg).emit_analysis()


def build_executives_dashboard(cfg: Config) -> ModelDashboard:
    """Build the Executives Dashboard resource via the tree."""
    return build_executives_app(cfg).emit_dashboard()
