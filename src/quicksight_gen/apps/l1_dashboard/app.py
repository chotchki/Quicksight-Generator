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
    M.2a.1 — package skeleton + Analysis + Dashboard registered (this commit)
    M.2a.2 — Getting Started sheet with description-driven prose
    M.2a.3 — Drift sheet
    M.2a.4 — Overdraft sheet
    M.2a.5 — Limit Breach sheet
    M.2a.6 — Today's Exceptions sheet (UNION across L1 views)
    M.2a.7 — Description-driven prose across every sheet
    M.2a.8 — Hash-lock the seed at the M.2a structure
    M.2a.9 — Deploy + verify against Aurora
    M.2a.10 — Iteration gate; decide on apps/account_recon/ deprecation
"""

from __future__ import annotations

from quicksight_gen.apps.account_recon._l2 import default_l2_instance
from quicksight_gen.common import rich_text as rt
from quicksight_gen.common.config import Config
from quicksight_gen.common.ids import SheetId
from quicksight_gen.common.l2 import L2Instance
from quicksight_gen.common.theme import get_preset
from quicksight_gen.common.tree import Analysis, App, Sheet, TextBox


# Sheet IDs — inlined in app.py per the greenfield-app convention
# (L.7 Executives) since the L1 dashboard isn't dragging legacy URL
# stability constraints from a previous deploy.
SHEET_GETTING_STARTED = SheetId("l1-sheet-getting-started")


_GETTING_STARTED_NAME = "Getting Started"
_GETTING_STARTED_TITLE = "L1 Reconciliation Dashboard"
_GETTING_STARTED_DESCRIPTION = (
    "Where to start. The dashboard groups every L1 SHOULD-constraint "
    "into one tab per exception kind — drift, overdraft, limit breach, "
    "expected EOD balance variance — plus a Today's Exceptions roll-up. "
    "Each tab queries one L1 invariant view directly; rows ARE the "
    "constraint violations."
)


def _analysis_name(cfg: Config, l2_instance: L2Instance) -> str:
    """Title shown on the deployed QuickSight Analysis."""
    # Persona-flavored title would come from L2 description fields under
    # M.7's render pipeline; for now use a stable "L1 Dashboard" label
    # plus the L2 instance prefix so multi-instance deployments are
    # distinguishable.
    return f"L1 Reconciliation Dashboard ({l2_instance.instance})"


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


def build_l1_dashboard_app(
    cfg: Config,
    *,
    l2_instance: L2Instance | None = None,
) -> App:
    """Construct the L1 Reconciliation Dashboard App as a tree.

    M.2a.2: registers Analysis + Dashboard + Getting Started sheet.
    Substeps M.2a.3-M.2a.6 add the per-invariant sheets (Drift,
    Overdraft, Limit Breach, Today's Exceptions). Each sheet IS one
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

    getting_started = analysis.add_sheet(Sheet(
        sheet_id=SHEET_GETTING_STARTED,
        name=_GETTING_STARTED_NAME,
        title=_GETTING_STARTED_TITLE,
        description=_GETTING_STARTED_DESCRIPTION,
    ))
    _populate_getting_started(cfg, getting_started, l2_instance)

    # Per-invariant sheets land in M.2a.3-M.2a.6.

    app.create_dashboard(
        dashboard_id_suffix="l1-dashboard",
        name=_analysis_name(cfg, l2_instance),
    )
    return app
