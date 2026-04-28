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
    DS_CHAINS,
    DS_EXC_CHAIN_ORPHANS,
    DS_EXC_DEAD_BUNDLES_ACTIVITY,
    DS_EXC_DEAD_LIMIT_SCHEDULES,
    DS_EXC_DEAD_METADATA,
    DS_EXC_DEAD_RAILS,
    DS_EXC_UNMATCHED_TRANSFER_TYPE,
    DS_RAILS,
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
    CellAccentText,
    Dataset,
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

    # Tree Dataset refs keyed by visual_identifier — populators pull
    # by stable name. The CLI writes the AWS-shape DataSets separately
    # (this is the L1 dashboard's split-of-concern pattern).
    datasets = _l2ft_datasets(cfg, l2_instance)
    for ds in datasets.values():
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
    _populate_rails_sheet(cfg, rails_sheet, datasets=datasets)
    _populate_chains_sheet(cfg, chains_sheet, datasets=datasets)
    _populate_l2_exceptions_sheet(cfg, l2_exceptions_sheet, datasets=datasets)

    app.create_dashboard(
        dashboard_id_suffix="l2-flow-tracing",
        name=_analysis_name(cfg, l2_instance),
    )
    return app


def _l2ft_datasets(
    cfg: Config, l2_instance: L2Instance,
) -> dict[str, Dataset]:
    """Build every L2 Flow Tracing dataset and return tree-ref Datasets
    keyed by visual_identifier.

    Each AWS DataSet's ``DataSetId`` becomes the tree Dataset's ARN
    path component; the visual identifier (the key passed to
    `build_dataset()`) becomes the tree Dataset's ``identifier`` field.
    The contract is registered as a side-effect of `build_dataset()`,
    so subsequent ``ds["col"]`` accesses validate.

    Mirrors `apps/l1_dashboard/app.py::_l1_datasets` pattern — the CLI
    writes the AWS shapes; this builds the typed tree refs for visual
    wiring on the App.
    """
    aws_datasets = build_all_l2_flow_tracing_datasets(cfg, l2_instance)
    visual_ids = [
        DS_RAILS,
        DS_CHAINS,
        DS_EXC_CHAIN_ORPHANS,
        DS_EXC_UNMATCHED_TRANSFER_TYPE,
        DS_EXC_DEAD_RAILS,
        DS_EXC_DEAD_BUNDLES_ACTIVITY,
        DS_EXC_DEAD_METADATA,
        DS_EXC_DEAD_LIMIT_SCHEDULES,
    ]
    return {
        vid: Dataset(identifier=vid, arn=cfg.dataset_arn(aws.DataSetId))
        for vid, aws in zip(visual_ids, aws_datasets)
    }


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


def _populate_rails_sheet(
    cfg: Config,
    sheet: Sheet,
    *,
    datasets: dict[str, Dataset],
) -> None:
    """Rails sheet — one-row-per-Rail table joining L2 declaration to
    runtime activity (M.3.5).

    Static columns come from the L2 instance (inlined in the dataset's
    SQL CTE); runtime columns come from the prefixed
    ``<prefix>_current_transactions`` matview LEFT JOINed by
    ``rail_name``. Rails with zero activity in the window show
    ``total_postings = 0`` — they're the seeds for the L2.3 'Dead
    rails' exception (M.3.7).

    Visual layout: short header text, then one wide unaggregated table.
    The accent text on ``rail_name`` signals the column will be a drill
    anchor at M.3.7 (no drill action wired yet — drill plumbing lands
    when the per-Rail postings detail destination exists).
    """
    accent = get_preset(cfg.theme_preset).accent
    ds_rails = datasets[DS_RAILS]

    sheet.layout.row(height=8).add_text_box(
        TextBox(
            text_box_id="l2ft-rails-header",
            content=rt.text_box(
                rt.subheading("Rails", color=accent),
                rt.BR,
                rt.body(
                    "One row per declared Rail. Static columns reflect "
                    "the L2 declaration; runtime columns count what "
                    "actually landed in the window. A row with zero "
                    "Total Postings means the rail was declared but "
                    "never fired — the L2.3 'Dead rails' exception "
                    "surfaces those (M.3.7)."
                ),
            ),
        ),
        width=36,
    )

    rail_name_col = ds_rails["rail_name"].dim()
    sheet.layout.row(height=18).add_table(
        width=36,
        title="Declared Rails — Shape and Activity",
        subtitle=(
            "Static columns from the L2 instance; runtime counts from "
            "the prefixed transactions matview joined by rail_name."
        ),
        columns=[
            rail_name_col,
            ds_rails["transfer_type"].dim(),
            ds_rails["leg_shape"].dim(),
            ds_rails["source_role"].dim(),
            ds_rails["destination_role"].dim(),
            ds_rails["leg_role"].dim(),
            ds_rails["max_pending_age"].dim(),
            ds_rails["max_unbundled_age"].dim(),
            ds_rails["posted_requirements"].dim(),
            ds_rails["total_postings"].numerical(),
            ds_rails["pending_count"].numerical(),
            ds_rails["unbundled_count"].numerical(),
        ],
        conditional_formatting=[
            CellAccentText(on=rail_name_col, color=accent),
        ],
    )


def _populate_chains_sheet(
    cfg: Config,
    sheet: Sheet,
    *,
    datasets: dict[str, Dataset],
) -> None:
    """Chains sheet — Sankey of declared parent→child topology + a
    detail Table with the gating data Sankey can't show natively
    (M.3.6).

    Sankey: source = parent_name, target = child_name, weight =
    parent_firing_count. Edge thickness reads as "how many times this
    parent fired in the window." Nodes appear iff they participate
    in at least one declared chain entry.

    Detail Table below: same edges, but with required / xor_group /
    orphan_count / orphan_rate spelled out so analysts can see which
    edges are required vs optional and which have orphan parents.
    QuickSight's Sankey doesn't carry per-edge color encoding via
    conditional formatting natively; the detail table is the
    workaround until M.3.6+ explores per-edge tinting if AWS adds
    that capability.
    """
    accent = get_preset(cfg.theme_preset).accent
    ds_chains = datasets[DS_CHAINS]

    sheet.layout.row(height=8).add_text_box(
        TextBox(
            text_box_id="l2ft-chains-header",
            content=rt.text_box(
                rt.subheading("Chains", color=accent),
                rt.BR,
                rt.body(
                    "Sankey of declared Chain entries. Edge width = "
                    "parent firing count over the window. The detail "
                    "table below carries the L2 gating data — required "
                    "vs optional, XOR-group membership, orphan rate "
                    "(= parent firings without a matched child). A "
                    "Required edge with a non-zero orphan rate is the "
                    "seed for L2.1 'Chain orphans' (M.3.7)."
                ),
            ),
        ),
        width=36,
    )

    sheet.layout.row(height=18).add_sankey(
        width=36,
        title="Chain Topology — Parent → Child Firing Counts",
        subtitle=(
            "Width encodes how many times the parent fired in the "
            "window. Empty nodes mean the rail / template was declared "
            "but never fired."
        ),
        source=ds_chains["source_node"].dim(),
        target=ds_chains["target_node"].dim(),
        weight=ds_chains["parent_firing_count"].sum(),
    )

    sheet.layout.row(height=18).add_table(
        width=36,
        title="Chain Edge Details",
        subtitle=(
            "One row per declared Chain entry. Required + XOR-group "
            "carry the L2 gating semantic; orphan_count + orphan_rate "
            "show how many parent firings didn't have a matched child "
            "in the window."
        ),
        columns=[
            ds_chains["parent_name"].dim(),
            ds_chains["child_name"].dim(),
            ds_chains["required"].dim(),
            ds_chains["xor_group"].dim(),
            ds_chains["parent_firing_count"].numerical(),
            ds_chains["child_firing_count"].numerical(),
            ds_chains["orphan_count"].numerical(),
            ds_chains["orphan_rate"].numerical(),
        ],
    )


def _populate_l2_exceptions_sheet(
    cfg: Config,
    sheet: Sheet,
    *,
    datasets: dict[str, Dataset],
) -> None:
    """L2 Exceptions sheet — six KPI + table sections, one per L2
    hygiene check (M.3.7).

    Each section follows the same pattern: a small text-box header
    with the section's invariant statement, a KPI counting the
    violation rows, and a detail table listing them. The 'L2:'
    prefix on every visual title flags the surface so analysts
    don't confuse it with the L1 dashboard's exceptions tab.
    """
    accent = get_preset(cfg.theme_preset).accent

    sheet.layout.row(height=8).add_text_box(
        TextBox(
            text_box_id="l2ft-exc-header",
            content=rt.text_box(
                rt.subheading("L2 Exceptions", color=accent),
                rt.BR,
                rt.body(
                    "Six L2 hygiene checks. Each surfaces a "
                    "'declaration vs runtime' mismatch the L1 "
                    "dashboard's exceptions tab doesn't catch — "
                    "every row here is one piece of the L2 instance "
                    "the runtime data disagrees with."
                ),
            ),
        ),
        width=36,
    )

    _add_l2_exception_section(
        sheet=sheet,
        accent=accent,
        section_id="l2-1-chain-orphans",
        section_label="L2.1",
        title="Chain Orphans",
        body=(
            "Required Chain entries where the parent fired but the "
            "child didn't in the window. A non-zero count means the "
            "L2 says these flows MUST chain together but the runtime "
            "data shows broken cycles. (XOR-group multi/none "
            "violations are deferred to a follow-on substep.)"
        ),
        ds=datasets[DS_EXC_CHAIN_ORPHANS],
        kpi_value_col="parent_name",
        table_columns=[
            "parent_name", "child_name",
            "parent_firing_count", "child_firing_count", "orphan_count",
        ],
    )
    _add_l2_exception_section(
        sheet=sheet,
        accent=accent,
        section_id="l2-2-unmatched-transfer-type",
        section_label="L2.2",
        title="Unmatched Transfer Type",
        body=(
            "Posted Transactions whose transfer_type isn't in the L2's "
            "declared Rail.transfer_type set. Means the runtime feed "
            "is producing types the L2 doesn't know about — usually "
            "an integrator-side ETL gap or a stale L2 declaration."
        ),
        ds=datasets[DS_EXC_UNMATCHED_TRANSFER_TYPE],
        kpi_value_col="transfer_type",
        table_columns=["transfer_type", "posting_count"],
    )
    _add_l2_exception_section(
        sheet=sheet,
        accent=accent,
        section_id="l2-3-dead-rails",
        section_label="L2.3",
        title="Dead Rails",
        body=(
            "Rails declared in L2 with zero postings in the window. "
            "Either the rail was retired and the declaration should "
            "follow, or the ETL isn't producing activity through it "
            "yet — the L2 says it should."
        ),
        ds=datasets[DS_EXC_DEAD_RAILS],
        kpi_value_col="rail_name",
        table_columns=["rail_name", "transfer_type", "leg_shape"],
    )
    _add_l2_exception_section(
        sheet=sheet,
        accent=accent,
        section_id="l2-4-dead-bundles-activity",
        section_label="L2.4",
        title="Dead Bundles Activity",
        body=(
            "Aggregating-rail bundles_activity targets that no posting "
            "matched (by rail_name OR transfer_type) in the window. "
            "Means the bundler will never fire — the activity selector "
            "doesn't resolve to anything the runtime is producing."
        ),
        ds=datasets[DS_EXC_DEAD_BUNDLES_ACTIVITY],
        kpi_value_col="aggregating_rail",
        table_columns=["aggregating_rail", "bundle_target"],
    )
    _add_l2_exception_section(
        sheet=sheet,
        accent=accent,
        section_id="l2-5-dead-metadata",
        section_label="L2.5",
        title="Dead Metadata Declarations",
        body=(
            "Rail.metadata_keys that no posting on that rail carries a "
            "value for. Either the L2 over-declares what the rail "
            "exposes, or the integrator's ETL isn't propagating those "
            "keys onto the leg's metadata."
        ),
        ds=datasets[DS_EXC_DEAD_METADATA],
        kpi_value_col="rail_name",
        table_columns=["rail_name", "metadata_key"],
    )
    _add_l2_exception_section(
        sheet=sheet,
        accent=accent,
        section_id="l2-6-dead-limit-schedules",
        section_label="L2.6",
        title="Dead Limit Schedules",
        body=(
            "LimitSchedule (parent_role, transfer_type) cells with "
            "zero outbound debit flow in the window. The cap is "
            "effectively dead — either nobody routes that combo, or "
            "the L2 is enforcing against a flow that doesn't exist."
        ),
        ds=datasets[DS_EXC_DEAD_LIMIT_SCHEDULES],
        kpi_value_col="parent_role",
        table_columns=["parent_role", "transfer_type", "cap"],
    )


def _add_l2_exception_section(
    *,
    sheet: Sheet,
    accent: str,
    section_id: str,
    section_label: str,
    title: str,
    body: str,
    ds: Dataset,
    kpi_value_col: str,
    table_columns: list[str],
) -> None:
    """One L2 exception section — header text + KPI + table row.

    Lays out three rows: a short text-box (8 high), a KPI (6 high)
    half-width, and a table (12 high) full-width. The KPI counts
    rows in the dataset (every row IS one violation per the
    M.3.7 spec); the table lists them with the columns the section
    cares about. ``L2.X`` label leads every title for visual
    differentiation from the L1 dashboard.
    """
    sheet.layout.row(height=6).add_text_box(
        TextBox(
            text_box_id=f"l2ft-exc-{section_id}-header",
            content=rt.text_box(
                rt.subheading(f"{section_label} — {title}", color=accent),
                rt.BR,
                rt.body(body),
            ),
        ),
        width=36,
    )

    half = 18
    kpi_row = sheet.layout.row(height=6)
    kpi_row.add_kpi(
        width=half,
        title=f"L2: {title} — Violation Count",
        subtitle="One row per detected violation in the window.",
        values=[ds[kpi_value_col].count()],
    )
    kpi_row.add_kpi(
        width=half,
        title=f"L2: {title} — Distinct Subjects",
        subtitle=(
            "Distinct subjects involved (e.g., distinct rails, "
            "transfer_types, edges). May equal the violation count "
            "if every row carries a different subject."
        ),
        values=[ds[kpi_value_col].distinct_count()],
    )

    sheet.layout.row(height=12).add_table(
        width=36,
        title=f"L2: {title} — Detail",
        subtitle=(
            "Every row in this dataset IS one violation — open the "
            "L2 declaration that emitted the row to investigate."
        ),
        columns=[ds[c].dim() if c not in {
            "parent_firing_count", "child_firing_count",
            "orphan_count", "posting_count", "cap",
        } else ds[c].numerical() for c in table_columns],
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
