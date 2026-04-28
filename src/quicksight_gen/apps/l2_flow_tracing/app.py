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
    DS_META_VALUES,
    DS_POSTINGS,
    META_KEY_ALL_SENTINEL,
    META_VALUE_PLACEHOLDER_SENTINEL,
    build_all_l2_flow_tracing_datasets,
    declared_metadata_keys,
)
from quicksight_gen.common import rich_text as rt
from quicksight_gen.common.config import Config
from quicksight_gen.common.ids import ParameterName, SheetId
from quicksight_gen.common.l2 import L2Instance, load_instance
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
    LinkedValues,
    Sheet,
    StaticValues,
    StringParam,
    TextBox,
    TimeRangeFilter,
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
    """Title shown in QuickSight — matches L1's `Name (prefix)` shape so
    the two apps' QS asset names are visually consistent in the
    dashboard list."""
    return f"L2 Flow Tracing ({l2_instance.instance})"


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
    _populate_rails_sheet(
        cfg, rails_sheet,
        analysis=analysis, datasets=datasets, l2_instance=l2_instance,
    )
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
    # Order matches `build_all_l2_flow_tracing_datasets`. M.3.10c
    # dropped DS_RAILS + the 28 per-key dropdowns; replaced with
    # DS_POSTINGS + DS_META_VALUES driving the cascade.
    visual_ids = [
        DS_POSTINGS,
        DS_META_VALUES,
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


_DATE_END_DEFAULT_EXPR = "truncDate('DD', now())"
_DATE_START_DEFAULT_EXPR = (
    "addDateTime(-7, 'DD', truncDate('DD', now()))"
)


def _populate_rails_sheet(
    cfg: Config,
    sheet: Sheet,
    *,
    analysis: Analysis,
    datasets: dict[str, Dataset],
    l2_instance: L2Instance,
) -> None:
    """Rails sheet — interactive transactions explorer (M.3.10c rewrite).

    Six controls in the sheet's filter bar drive a transactions Table:

    1. **Date From** + **Date To** — bind to ``pL2ftDateStart`` /
       ``pL2ftDateEnd``; ``TimeRangeFilter`` on ``posting``.
    2. **Rail** — multi-select ``CategoryFilter`` on ``rail_name``.
    3. **Status** — multi-select ``CategoryFilter`` on ``status``.
    4. **Bundle** — multi-select ``CategoryFilter`` on the calc'd
       ``bundle_status`` ('Bundled' / 'Unbundled').
    5. **Metadata Key** — single-select ``ParameterDropdown`` with
       ``StaticValues`` (the L2's declared keys + ``__ALL__``
       sentinel). Bound to ``pL2ftMetaKey``, mapped to ``pKey`` on
       BOTH the postings dataset (filters the table) AND the
       meta-values dataset (narrows the Value dropdown's options).
    6. **Metadata Value** — multi-select ``ParameterDropdown`` with
       ``LinkedValues`` from the meta-values dataset. Bound to
       ``pL2ftMetaValue``, mapped to ``pValues`` on the postings
       dataset.

    The cascade is fully native QS: when the analyst picks a Key,
    QS's MappedDataSetParameters push the value into the meta-values
    dataset's ``pKey`` parameter, which re-runs that dataset's SQL
    (substituting the new key into the JSONPath) — the Value
    dropdown's options narrow automatically. No client-side
    JavaScript, no synthetic chaining.

    The declared-rails table that lived here pre-M.3.10c moved to
    a future Docs tab; the runtime postings explorer is the focus
    here.
    """
    accent = get_preset(cfg.theme_preset).accent
    ds_postings = datasets[DS_POSTINGS]
    ds_meta_values = datasets[DS_META_VALUES]

    sheet.layout.row(height=4).add_text_box(
        TextBox(
            text_box_id="l2ft-rails-header",
            content=rt.text_box(
                rt.subheading("Rails — Transactions Explorer", color=accent),
                rt.BR,
                rt.body(
                    "Filter the postings ledger by date range, rail, "
                    "status, bundle status, and (cascading) metadata "
                    "key + value. Pick a Metadata Key to populate the "
                    "Value dropdown; pick one or more Values to narrow "
                    "the table to legs carrying that metadata."
                ),
            ),
        ),
        width=36,
    )

    # 1+2. Date range — params + TimeRangeFilter scoped to this sheet.
    date_start = analysis.add_parameter(DateTimeParam(
        name=ParameterName("pL2ftDateStart"),
        time_granularity="DAY",
        default=DateTimeDefaultValues(
            RollingDate={"Expression": _DATE_START_DEFAULT_EXPR},
        ),
    ))
    date_end = analysis.add_parameter(DateTimeParam(
        name=ParameterName("pL2ftDateEnd"),
        time_granularity="DAY",
        default=DateTimeDefaultValues(
            RollingDate={"Expression": _DATE_END_DEFAULT_EXPR},
        ),
    ))
    fg_date = analysis.add_filter_group(FilterGroup(
        filter_group_id="fg-l2ft-rails-date",  # type: ignore[arg-type]
        cross_dataset="SINGLE_DATASET",
        filters=[TimeRangeFilter(
            filter_id="filter-l2ft-rails-date",
            dataset=ds_postings,
            column=ds_postings["posting"],
            null_option="NON_NULLS_ONLY",
            time_granularity="DAY",
            minimum={"Parameter": "pL2ftDateStart"},
            maximum={"Parameter": "pL2ftDateEnd"},
        )],
    ))
    fg_date.scope_sheet(sheet)
    sheet.add_parameter_datetime_picker(parameter=date_start, title="Date From")
    sheet.add_parameter_datetime_picker(parameter=date_end, title="Date To")

    # 3-5. Three "default-all multi-select" CategoryFilter dropdowns
    # (rail / status / bundle status). Empty values + FILTER_ALL_VALUES
    # is the AR/L1 idiom for "no filter applied until analyst picks".
    def _cat_dropdown(*, fg_id: str, col: str, title: str) -> None:
        cat = CategoryFilter.with_values(
            filter_id=f"filter-{fg_id}",
            dataset=ds_postings,
            column=ds_postings[col],
            values=[],
            select_all_options="FILTER_ALL_VALUES",
        )
        fg = analysis.add_filter_group(FilterGroup(
            filter_group_id=fg_id,  # type: ignore[arg-type]
            cross_dataset="SINGLE_DATASET",
            filters=[cat],
        ))
        fg.scope_sheet(sheet)
        sheet.add_filter_dropdown(filter=cat, title=title)

    _cat_dropdown(fg_id="fg-l2ft-rails-rail", col="rail_name", title="Rail")
    _cat_dropdown(fg_id="fg-l2ft-rails-status", col="status", title="Status")
    _cat_dropdown(
        fg_id="fg-l2ft-rails-bundle", col="bundle_status", title="Bundle",
    )

    # 6. Metadata cascade — the M.3.10c novelty.
    #
    # Key: single-select StaticValues from the L2 walk + sentinel.
    # Bound to pL2ftMetaKey, which maps to `pKey` on BOTH the
    # postings dataset (controls the WHERE clause) and the
    # meta-values dataset (controls which key's values populate the
    # Value dropdown).
    p_meta_key = analysis.add_parameter(StringParam(
        name=ParameterName("pL2ftMetaKey"),
        default=[META_KEY_ALL_SENTINEL],
        multi_valued=False,
        mapped_dataset_params=[
            (ds_postings, "pKey"),
            (ds_meta_values, "pKey"),
        ],
    ))
    # Value: multi-select LinkedValues from the meta-values dataset.
    # Bound to pL2ftMetaValue, mapped to `pValues` on the postings
    # dataset.
    p_meta_value = analysis.add_parameter(StringParam(
        name=ParameterName("pL2ftMetaValue"),
        default=[META_VALUE_PLACEHOLDER_SENTINEL],
        multi_valued=True,
        mapped_dataset_params=[
            (ds_postings, "pValues"),
        ],
    ))
    declared_keys = declared_metadata_keys(l2_instance)
    sheet.add_parameter_dropdown(
        parameter=p_meta_key,
        title="Metadata Key",
        type="SINGLE_SELECT",
        # Sentinel first so it's the visible default; declared keys
        # follow in sorted order.
        selectable_values=StaticValues(
            values=[META_KEY_ALL_SENTINEL] + declared_keys,
        ),
    )
    sheet.add_parameter_dropdown(
        parameter=p_meta_value,
        title="Metadata Value",
        type="MULTI_SELECT",
        selectable_values=LinkedValues(
            dataset=ds_meta_values,
            column_name="metadata_value",
        ),
    )

    # Transactions table — the postings dataset's SQL handles the
    # metadata-cascade WHERE clause via dataset parameters; the four
    # category filters narrow further.
    sheet.layout.row(height=21).add_table(
        width=36,
        title="Transactions",
        subtitle=(
            "One row per leg matching all the filters above. With no "
            "Metadata Key picked, every leg in the date window appears; "
            "picking a Key + one or more Values narrows to legs whose "
            "metadata carries that key=value pair."
        ),
        columns=[
            ds_postings["posting"].date(),
            ds_postings["rail_name"].dim(),
            ds_postings["transfer_id"].dim(),
            ds_postings["account_name"].dim(),
            ds_postings["amount_money"].numerical(),
            ds_postings["amount_direction"].dim(),
            ds_postings["status"].dim(),
            ds_postings["bundle_status"].dim(),
            ds_postings["transfer_parent_id"].dim(),
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
