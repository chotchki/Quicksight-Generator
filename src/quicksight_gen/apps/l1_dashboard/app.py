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
from quicksight_gen.common.config import Config
from quicksight_gen.common.l2 import L2Instance
from quicksight_gen.common.tree import Analysis, App


def _analysis_name(cfg: Config, l2_instance: L2Instance) -> str:
    """Title shown on the deployed QuickSight Analysis."""
    # Persona-flavored title would come from L2 description fields under
    # M.7's render pipeline; for now use a stable "L1 Dashboard" label
    # plus the L2 instance prefix so multi-instance deployments are
    # distinguishable.
    return f"L1 Reconciliation Dashboard ({l2_instance.instance})"


def build_l1_dashboard_app(
    cfg: Config,
    *,
    l2_instance: L2Instance | None = None,
) -> App:
    """Construct the L1 Reconciliation Dashboard App as a tree.

    M.2a.1: returns a minimal App with Analysis + Dashboard registered
    but NO sheets yet — substeps M.2a.2-M.2a.6 add sheets one at a
    time. Each sheet IS one L1 SHOULD-constraint visualized via the
    M.1a.7 invariant views.

    Dashboard ID convention: ``<l2_prefix>-l1-dashboard``. Matches the
    M.2a reframe — "L1 dashboard configured by an L2 instance," not
    "AR app for SNB CMS."
    """
    if l2_instance is None:
        l2_instance = default_l2_instance()

    app = App(name="l1-dashboard", cfg=cfg)
    app.set_analysis(Analysis(
        analysis_id_suffix="l1-dashboard-analysis",
        name=_analysis_name(cfg, l2_instance),
    ))
    # Sheets land in M.2a.2-M.2a.6.

    app.create_dashboard(
        dashboard_id_suffix="l1-dashboard",
        name=_analysis_name(cfg, l2_instance),
    )
    return app
