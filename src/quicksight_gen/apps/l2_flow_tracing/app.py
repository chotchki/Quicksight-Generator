"""L2 Flow Tracing — exercise every L2 primitive on a runtime dashboard.

M.3.4 ships the skeleton: 4 sheets (Getting Started + Rails + Chains +
L2 Exceptions), description-driven prose on Getting Started, placeholder
prose on the other three. M.3.5+ populates each tab with its real
visuals + datasets.

The app is L2-instance-fed via the same M.2d.3 prefix pattern the L1
dashboard uses: ``cfg.l2_instance_prefix`` is auto-derived from the L2
instance's ``instance`` field at build time, so dashboard ID, analysis
ID, dataset IDs, and tag-based cleanup all key off the per-instance
prefix without callers needing to pre-stamp the field.

Build pipeline::

    build_l2_flow_tracing_app(cfg, *, l2_instance=None) -> App

Default L2 instance is the persona-neutral ``spec_example.yaml``
(M.3.2 repointed away from sasquatch_ar so production library code
carries no implicit Sasquatch flavor); callers MAY override
(tests, alternative-persona deployments) via the kwarg.

Substep landmarks (each tab gets its own substep):

- M.3.4 — package skeleton + Analysis + Dashboard + 4 placeholder sheets (this commit)
- M.3.5 — Rails tab — per-Rail row table with declared + runtime columns
- M.3.6 — Chains tab — Sankey + parent-firing-count edges
- M.3.7 — L2 Exceptions tab — 6 KPI + drill sections
- M.3.8 — Auto metadata-driven filter dropdowns
"""

from __future__ import annotations

from dataclasses import replace

from quicksight_gen.apps.l2_flow_tracing.datasets import (
    build_all_l2_flow_tracing_datasets,
)
from quicksight_gen.common import rich_text as rt
from quicksight_gen.common.config import Config
from quicksight_gen.common.ids import SheetId
from quicksight_gen.common.l2 import L2Instance, load_instance
from quicksight_gen.common.theme import get_preset
from quicksight_gen.common.tree import (
    Analysis,
    App,
    Sheet,
    TextBox,
)


# Sheet IDs — inlined per the greenfield-app convention (no constants.py
# until / unless URL stability forces it).
SHEET_GETTING_STARTED = SheetId("l2ft-sheet-getting-started")
SHEET_RAILS = SheetId("l2ft-sheet-rails")
SHEET_CHAINS = SheetId("l2ft-sheet-chains")
SHEET_L2_EXCEPTIONS = SheetId("l2ft-sheet-l2-exceptions")


_GETTING_STARTED_NAME = "Getting Started"
_GETTING_STARTED_TITLE = "L2 Flow Tracing"
_GETTING_STARTED_DESCRIPTION = (
    "What this dashboard is. The L1 dashboard answers 'are my postings "
    "internally consistent?' One step up: the L2 Flow Tracing dashboard "
    "answers 'is my L2 declaration alive?' — every Rail, every Chain, "
    "every TransferTemplate, every LimitSchedule the L2 instance "
    "declares should produce activity in the runtime data. When it "
    "doesn't, that's an L2 hygiene problem, not an L1 ledger problem."
)


_RAILS_NAME = "Rails"
_RAILS_TITLE = "Declared Rails — Shape and Activity"
_RAILS_DESCRIPTION = (
    "One row per declared Rail. Static columns show the L2 declaration "
    "(transfer_type, leg shape, role(s), aging caps, posted_requirements). "
    "Runtime columns show what's actually happening in the date window: "
    "total postings, pending count, unbundled count. Dead rails (zero "
    "activity in the window) surface as a Stuck-Pending-Aging-style "
    "exception on the L2 Exceptions tab."
)


_CHAINS_NAME = "Chains"
_CHAINS_TITLE = "Declared Chains — Parent-Child Firing Topology"
_CHAINS_DESCRIPTION = (
    "Sankey of declared Chain entries. Nodes are the union of Rails and "
    "TransferTemplates the chains reference; edge widths show parent "
    "firing counts in the window. Edge color encodes Required vs "
    "Optional and XOR-group membership. Edges where the orphan rate "
    "(parent fired but Required child didn't) is non-zero get a tint "
    "so analysts can spot broken cycles at a glance."
)


_L2_EXCEPTIONS_NAME = "L2 Exceptions"
_L2_EXCEPTIONS_TITLE = "L2 Hygiene Exceptions"
_L2_EXCEPTIONS_DESCRIPTION = (
    "Six L2-shaped exception kinds the L1 dashboard doesn't surface — "
    "each one is a 'your L2 declaration says X but the runtime data "
    "disagrees' signal. Distinct visual styling from the L1 Exceptions "
    "tab (different accent shade, leading 'L2:' prefix on titles) so "
    "analysts don't confuse the two surfaces. Sections: Chain orphans, "
    "Unmatched transfer_type, Dead rails, Dead bundles_activity, "
    "Dead metadata declarations, Dead LimitSchedules."
)


def _analysis_name(cfg: Config, l2_instance: L2Instance) -> str:
    """Title shown in QuickSight — surfaces the L2 prefix so multi-instance
    deployments are distinguishable in the UI."""
    return f"{l2_instance.instance} — L2 Flow Tracing"


def build_l2_flow_tracing_app(
    cfg: Config,
    *,
    l2_instance: L2Instance | None = None,
) -> App:
    """Construct the L2 Flow Tracing App as a tree.

    M.3.4: registers Analysis + Dashboard + 4 placeholder sheets
    (Getting Started + Rails + Chains + L2 Exceptions). No datasets,
    no visuals beyond the description prose. M.3.5+ populates each
    placeholder one substep at a time.

    Dashboard ID convention: ``<resource_prefix>-<l2_prefix>-l2-flow-tracing``
    (M.2d.3) — same prefix pattern the L1 dashboard uses, so N apps
    can deploy against the same L2 instance AND the same app can deploy
    against N L2 instances without QS resource collisions. Auto-derives
    ``cfg.l2_instance_prefix`` from ``l2_instance.instance`` if the
    caller hasn't pre-stamped it.
    """
    if l2_instance is None:
        l2_instance = _default_l2_instance()

    if cfg.l2_instance_prefix is None:
        cfg = replace(cfg, l2_instance_prefix=str(l2_instance.instance))

    app = App(name="l2-flow-tracing", cfg=cfg)
    analysis = app.set_analysis(Analysis(
        analysis_id_suffix="l2-flow-tracing-analysis",
        name=_analysis_name(cfg, l2_instance),
    ))

    # No datasets at M.3.4 — the call exists so the CLI integration is
    # uniform; M.3.5+ populates the list.
    for ds in build_all_l2_flow_tracing_datasets(cfg, l2_instance):
        app.add_dataset(ds)

    getting_started = analysis.add_sheet(Sheet(
        sheet_id=SHEET_GETTING_STARTED,
        name=_GETTING_STARTED_NAME,
        title=_GETTING_STARTED_TITLE,
        description=_GETTING_STARTED_DESCRIPTION,
    ))
    rails_sheet = analysis.add_sheet(Sheet(
        sheet_id=SHEET_RAILS,
        name=_RAILS_NAME,
        title=_RAILS_TITLE,
        description=_RAILS_DESCRIPTION,
    ))
    chains_sheet = analysis.add_sheet(Sheet(
        sheet_id=SHEET_CHAINS,
        name=_CHAINS_NAME,
        title=_CHAINS_TITLE,
        description=_CHAINS_DESCRIPTION,
    ))
    l2_exceptions_sheet = analysis.add_sheet(Sheet(
        sheet_id=SHEET_L2_EXCEPTIONS,
        name=_L2_EXCEPTIONS_NAME,
        title=_L2_EXCEPTIONS_TITLE,
        description=_L2_EXCEPTIONS_DESCRIPTION,
    ))

    _populate_getting_started(cfg, getting_started, l2_instance)
    _populate_placeholder(
        cfg, rails_sheet,
        title=_RAILS_TITLE,
        body=_RAILS_DESCRIPTION,
        substep="M.3.5",
        text_box_id="l2ft-rails-placeholder",
    )
    _populate_placeholder(
        cfg, chains_sheet,
        title=_CHAINS_TITLE,
        body=_CHAINS_DESCRIPTION,
        substep="M.3.6",
        text_box_id="l2ft-chains-placeholder",
    )
    _populate_placeholder(
        cfg, l2_exceptions_sheet,
        title=_L2_EXCEPTIONS_TITLE,
        body=_L2_EXCEPTIONS_DESCRIPTION,
        substep="M.3.7",
        text_box_id="l2ft-l2-exceptions-placeholder",
    )

    app.create_dashboard(
        dashboard_id_suffix="l2-flow-tracing",
        name=_analysis_name(cfg, l2_instance),
    )
    return app


def _default_l2_instance() -> L2Instance:
    """Persona-neutral default (M.3.2 — same as L1 dashboard's default).

    Loaded lazily from ``tests/l2/spec_example.yaml`` so the import graph
    doesn't pull the YAML at module load. Production callers always pass
    their own ``l2_instance``.
    """
    from pathlib import Path
    spec_yaml = Path(__file__).resolve().parents[3].parent / "tests" / "l2" / "spec_example.yaml"
    return load_instance(spec_yaml)


def _populate_getting_started(
    cfg: Config,
    sheet: Sheet,
    l2_instance: L2Instance,
) -> None:
    """Render the Getting Started sheet using the L2 instance's prose.

    Description-driven: welcome body comes from ``l2_instance.description``
    (NOT a hardcoded persona string). Switching L2 instance switches
    the prose — same contract the L1 dashboard's Getting Started follows.
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
            text_box_id="l2ft-gs-welcome",
            content=rt.text_box(
                rt.inline(
                    _GETTING_STARTED_TITLE,
                    font_size="36px",
                    color=accent,
                ),
                rt.BR, rt.BR,
                rt.body(_GETTING_STARTED_DESCRIPTION),
                rt.BR, rt.BR,
                rt.subheading("L2 Instance", color=accent),
                rt.BR,
                rt.body(welcome_body),
            ),
        ),
        width=36,
    )


def _populate_placeholder(
    cfg: Config,
    sheet: Sheet,
    *,
    title: str,
    body: str,
    substep: str,
    text_box_id: str,
) -> None:
    """Stub a placeholder sheet with the tab description + a 'lands at <substep>'
    note. Removed when the substep populator replaces this call."""
    accent = get_preset(cfg.theme_preset).accent
    sheet.layout.row(height=8).add_text_box(
        TextBox(
            text_box_id=text_box_id,
            content=rt.text_box(
                rt.inline(title, font_size="24px", color=accent),
                rt.BR, rt.BR,
                rt.body(body),
                rt.BR, rt.BR,
                rt.body(
                    f"(Skeleton at M.3.4 — visuals + datasets land at {substep}.)"
                ),
            ),
        ),
        width=36,
    )


# ---------------------------------------------------------------------------
# CLI / external-caller shims. Mirror the L1 dashboard signature so the CLI
# can plumb through generically.
# ---------------------------------------------------------------------------


def build_analysis(
    cfg: Config,
    *,
    l2_instance: L2Instance | None = None,
):
    """Build the complete L2 Flow Tracing Analysis resource via the tree."""
    return build_l2_flow_tracing_app(cfg, l2_instance=l2_instance).emit_analysis()


def build_l2_flow_tracing_dashboard(
    cfg: Config,
    *,
    l2_instance: L2Instance | None = None,
):
    """Build the L2 Flow Tracing Dashboard resource via the tree."""
    return build_l2_flow_tracing_app(cfg, l2_instance=l2_instance).emit_dashboard()
