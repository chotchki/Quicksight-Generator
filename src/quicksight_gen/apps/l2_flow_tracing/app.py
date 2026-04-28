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
    DS_CHAIN_INSTANCES,
    DS_EXC_CHAIN_ORPHANS,
    DS_EXC_DEAD_BUNDLES_ACTIVITY,
    DS_EXC_DEAD_LIMIT_SCHEDULES,
    DS_EXC_DEAD_METADATA,
    DS_EXC_DEAD_RAILS,
    DS_EXC_UNMATCHED_TRANSFER_TYPE,
    DS_META_VALUES,
    DS_POSTINGS,
    DS_TT_INSTANCES,
    DS_TT_LEGS,
    META_KEY_ALL_SENTINEL,
    META_VALUE_PLACEHOLDER_SENTINEL,
    build_all_l2_flow_tracing_datasets,
    declared_chain_parents,
    declared_metadata_keys,
    declared_template_names,
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
SHEET_TRANSFER_TEMPLATES = SheetId("l2ft-sheet-transfer-templates")
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
_RAILS_TITLE = "Rails — Transactions Explorer"
_RAILS_DESCRIPTION = (
    "Filter the postings ledger by date range, rail, status, bundle "
    "status, and (cascading) metadata key + value. Pick a Metadata Key "
    "to populate the Value dropdown; pick one or more Values to narrow "
    "the table to legs carrying that metadata."
)


_CHAINS_NAME = "Chains"
_CHAINS_TITLE = "Chains — Per-Instance Explorer"
_CHAINS_DESCRIPTION = (
    "Filter declared chain firings by date range, chain (parent rail / "
    "template name), completion status, and (cascading) metadata key + "
    "value. One row per parent transfer firing; completion_status reads "
    "'Completed' when every Required child declared for the parent fired "
    "against this transfer_id, 'Incomplete' if any required child is "
    "missing, 'No Required Children' when only optional / XOR-group "
    "children are declared."
)


_TRANSFER_TEMPLATES_NAME = "Transfer Templates"
_TRANSFER_TEMPLATES_TITLE = "Transfer Templates — Multi-Leg Flow"
_TRANSFER_TEMPLATES_DESCRIPTION = (
    "Visualize the multi-leg flow of declared TransferTemplates: each "
    "shared Transfer's debit legs flow into the template (middle node), "
    "credit legs flow out to their destination accounts. Filter by date, "
    "template, net status (Balanced / Imbalanced — checks the "
    "ExpectedNet invariant), and (cascading) metadata key + value. The "
    "Sankey shows the flow shape; the Table below shows per-instance "
    "balance detail."
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
    transfer_templates_sheet = analysis.add_sheet(Sheet(
        sheet_id=SHEET_TRANSFER_TEMPLATES,
        name=_TRANSFER_TEMPLATES_NAME,
        title=_TRANSFER_TEMPLATES_TITLE,
        description=_TRANSFER_TEMPLATES_DESCRIPTION,
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
    _populate_chains_sheet(
        cfg, chains_sheet,
        analysis=analysis, datasets=datasets, l2_instance=l2_instance,
    )
    _populate_transfer_templates_sheet(
        cfg, transfer_templates_sheet,
        analysis=analysis, datasets=datasets, l2_instance=l2_instance,
    )
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
    # DS_POSTINGS + DS_META_VALUES driving the cascade. M.3.10d
    # swapped DS_CHAINS (aggregated edges) for DS_CHAIN_INSTANCES
    # (per parent firing) backing the chains explorer. M.3.10f adds
    # DS_TT_INSTANCES (per shared Transfer) + DS_TT_LEGS (per leg)
    # to back the new Transfer Templates sheet (Sankey + Table).
    visual_ids = [
        DS_POSTINGS,
        DS_META_VALUES,
        DS_CHAIN_INSTANCES,
        DS_TT_INSTANCES,
        DS_TT_LEGS,
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


# Date-filter defaults are intentionally "all time" so a freshly-loaded
# Rails tab renders all postings — the date pickers are for narrowing,
# not for a default scope. The L1 dashboard's rolling-7-day default
# DOESN'T fit here for two reasons: (1) the demo seed plants synthetic
# postings dated 2029-11 to 2030-01-01 (deliberately decoupled from
# wall-clock), so a "now-relative" default would exclude every demo row;
# (2) Rails is an explorer tab — the analyst comes in not knowing what
# range to look at, and an unconstrained default lets them see what's
# there before narrowing. Switch to RollingDate when the L2 instance
# carries production data with current timestamps.
_DATE_START_STATIC = "1900-01-01T00:00:00.000Z"
_DATE_END_STATIC = "2099-12-31T23:59:59.999Z"


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
       the postings dataset (so its ``<<$pKey>>`` substitution
       narrows the table).
    6. **Metadata Value** — multi-select ``ParameterDropdown`` with
       ``LinkedValues`` from the meta-values dataset. Bound to
       ``pL2ftMetaValue``, mapped to ``pValues`` on the postings
       dataset. ``CascadingControlConfiguration`` on this control
       points at the meta-values dataset's ``metadata_key`` column,
       so QS column-match-filters its rows by the Key dropdown's
       selection — which narrows the Value dropdown's options.

    Two distinct mechanisms working together:

    - Postings table filtering: dataset parameters
      (``<<$pKey>>`` / ``<<$pValues>>``) substituted into a JSONPath
      ``IN (...)`` predicate at query time.
    - Value dropdown options narrowing: column-match cascade against
      the long-form ``(metadata_key, metadata_value)`` meta-values
      dataset. (Earlier attempt to drive this via dataset parameters
      alone failed — QS's cascade is column-match, not parameter-
      driven re-query. See M.3.10c memory.)

    The declared-rails table that lived here pre-M.3.10c moved to
    a future Docs tab; the runtime postings explorer is the focus
    here.
    """
    ds_postings = datasets[DS_POSTINGS]
    ds_meta_values = datasets[DS_META_VALUES]

    # 1+2. Date range — params + TimeRangeFilter scoped to this sheet.
    date_start = analysis.add_parameter(DateTimeParam(
        name=ParameterName("pL2ftDateStart"),
        time_granularity="DAY",
        default=DateTimeDefaultValues(StaticValues=[_DATE_START_STATIC]),
    ))
    date_end = analysis.add_parameter(DateTimeParam(
        name=ParameterName("pL2ftDateEnd"),
        time_granularity="DAY",
        default=DateTimeDefaultValues(StaticValues=[_DATE_END_STATIC]),
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
        # Bridge to the postings dataset only — meta-values now uses
        # QS's native column-match cascade (driven by the Value
        # dropdown's CascadingControlConfiguration, not by SQL
        # substitution on the meta-values dataset).
        mapped_dataset_params=[
            (ds_postings, "pKey"),
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
    key_dropdown = sheet.add_parameter_dropdown(
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
        # Cascade: when Key changes, QS filters meta-values rows to
        # WHERE metadata_key = <Key's selected value>, then DISTINCT
        # metadata_value populates this dropdown. This is QS's
        # native column-match cascade — NOT the parameter-bridged
        # re-query approach (which we tried first; QS doesn't
        # actually refresh dropdown options on dataset-parameter
        # change at runtime — M.3.10c finding).
        cascade_source=key_dropdown,
        cascade_match_column=ds_meta_values["metadata_key"],
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
    analysis: Analysis,
    datasets: dict[str, Dataset],
    l2_instance: L2Instance,
) -> None:
    """Chains sheet — per-instance explorer (M.3.10d rewrite).

    Six controls in the sheet's filter bar drive a chain-instances
    Table:

    1. **Date From** + **Date To** — bind to ``pL2ftChainsDateStart``
       / ``pL2ftChainsDateEnd``; ``TimeRangeFilter`` on
       ``parent_posting``.
    2. **Chain** — multi-select ``CategoryFilter`` on
       ``parent_chain_name``.
    3. **Completion** — multi-select ``CategoryFilter`` on
       ``completion_status`` (Completed / Incomplete / No Required
       Children).
    4. **Metadata Key** — single-select ``ParameterDropdown`` with
       ``StaticValues`` (the L2's declared keys + ``__ALL__``
       sentinel). Mapped to ``pKey`` on the chain-instances dataset.
    5. **Metadata Value** — multi-select ``ParameterDropdown`` with
       ``LinkedValues`` from the meta-values dataset (shared with
       Rails). Mapped to ``pValues`` on the chain-instances dataset.
       ``CascadingControlConfiguration`` on this control points at
       the meta-values dataset's ``metadata_key`` column for the
       column-match cascade (same mechanism Rails uses).

    Visualization choice: Chains is a *runtime causality* concept
    (parent transfer fires → child transfer should fire later),
    not a multi-leg flow graph — Sankey does not read naturally.
    Per-firing Table is the right shape for now; revisit if a
    better visual primitive emerges. Multi-leg flow visualization
    belongs on TransferTemplates (which have explicit leg topology),
    if/when an L2 Templates explorer surface is added.
    """
    ds_chain_instances = datasets[DS_CHAIN_INSTANCES]
    ds_meta_values = datasets[DS_META_VALUES]

    # 1+2. Date range — params + TimeRangeFilter scoped to this sheet.
    # Separate from Rails' date params so the analyst's chains-window
    # selection doesn't perturb the rails view (and vice versa).
    date_start = analysis.add_parameter(DateTimeParam(
        name=ParameterName("pL2ftChainsDateStart"),
        time_granularity="DAY",
        default=DateTimeDefaultValues(StaticValues=[_DATE_START_STATIC]),
    ))
    date_end = analysis.add_parameter(DateTimeParam(
        name=ParameterName("pL2ftChainsDateEnd"),
        time_granularity="DAY",
        default=DateTimeDefaultValues(StaticValues=[_DATE_END_STATIC]),
    ))
    fg_date = analysis.add_filter_group(FilterGroup(
        filter_group_id="fg-l2ft-chains-date",  # type: ignore[arg-type]
        cross_dataset="SINGLE_DATASET",
        filters=[TimeRangeFilter(
            filter_id="filter-l2ft-chains-date",
            dataset=ds_chain_instances,
            column=ds_chain_instances["parent_posting"],
            null_option="NON_NULLS_ONLY",
            time_granularity="DAY",
            minimum={"Parameter": "pL2ftChainsDateStart"},
            maximum={"Parameter": "pL2ftChainsDateEnd"},
        )],
    ))
    fg_date.scope_sheet(sheet)
    sheet.add_parameter_datetime_picker(parameter=date_start, title="Date From")
    sheet.add_parameter_datetime_picker(parameter=date_end, title="Date To")

    # 3. Chain — multi-select on the L2-declared parent names. Empty
    # default + FILTER_ALL_VALUES means "no filter" until analyst picks.
    chain_filter = CategoryFilter.with_values(
        filter_id="filter-l2ft-chains-chain",
        dataset=ds_chain_instances,
        column=ds_chain_instances["parent_chain_name"],
        values=[],
        select_all_options="FILTER_ALL_VALUES",
    )
    fg_chain = analysis.add_filter_group(FilterGroup(
        filter_group_id="fg-l2ft-chains-chain",  # type: ignore[arg-type]
        cross_dataset="SINGLE_DATASET",
        filters=[chain_filter],
    ))
    fg_chain.scope_sheet(sheet)
    sheet.add_filter_dropdown(filter=chain_filter, title="Chain")

    # 4. Completion status — multi-select on the computed
    # completion_status column.
    completion_filter = CategoryFilter.with_values(
        filter_id="filter-l2ft-chains-completion",
        dataset=ds_chain_instances,
        column=ds_chain_instances["completion_status"],
        values=[],
        select_all_options="FILTER_ALL_VALUES",
    )
    fg_completion = analysis.add_filter_group(FilterGroup(
        filter_group_id="fg-l2ft-chains-completion",  # type: ignore[arg-type]
        cross_dataset="SINGLE_DATASET",
        filters=[completion_filter],
    ))
    fg_completion.scope_sheet(sheet)
    sheet.add_filter_dropdown(filter=completion_filter, title="Completion")

    # 5+6. Metadata cascade — same mechanism as Rails (M.3.10c memory):
    # SQL substitution on the chain-instances dataset for the table's
    # WHERE clause + column-match CascadingControlConfiguration on the
    # Value dropdown for option-narrowing. Separate analysis params
    # from Rails so per-sheet selection doesn't bleed across tabs.
    p_meta_key = analysis.add_parameter(StringParam(
        name=ParameterName("pL2ftChainsMetaKey"),
        default=[META_KEY_ALL_SENTINEL],
        multi_valued=False,
        mapped_dataset_params=[
            (ds_chain_instances, "pKey"),
        ],
    ))
    p_meta_value = analysis.add_parameter(StringParam(
        name=ParameterName("pL2ftChainsMetaValue"),
        default=[META_VALUE_PLACEHOLDER_SENTINEL],
        multi_valued=True,
        mapped_dataset_params=[
            (ds_chain_instances, "pValues"),
        ],
    ))
    declared_keys = declared_metadata_keys(l2_instance)
    key_dropdown = sheet.add_parameter_dropdown(
        parameter=p_meta_key,
        title="Metadata Key",
        type="SINGLE_SELECT",
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
        cascade_source=key_dropdown,
        cascade_match_column=ds_meta_values["metadata_key"],
    )

    sheet.layout.row(height=21).add_table(
        width=36,
        title="Chain Instances",
        subtitle=(
            "One row per parent transfer firing. completion_status reads "
            "'Completed' iff every Required child declared for the parent "
            "fired against this transfer_id; 'Incomplete' if any required "
            "child is missing. With no Metadata Key picked, every firing "
            "in the date window appears."
        ),
        columns=[
            ds_chain_instances["parent_posting"].date(),
            ds_chain_instances["parent_chain_name"].dim(),
            ds_chain_instances["parent_transfer_id"].dim(),
            ds_chain_instances["completion_status"].dim(),
            ds_chain_instances["required_fired"].numerical(),
            ds_chain_instances["required_total"].numerical(),
            ds_chain_instances["parent_amount_money"].numerical(),
            ds_chain_instances["parent_status"].dim(),
        ],
    )


def _populate_transfer_templates_sheet(
    cfg: Config,
    sheet: Sheet,
    *,
    analysis: Analysis,
    datasets: dict[str, Dataset],
    l2_instance: L2Instance,
) -> None:
    """Transfer Templates sheet — multi-leg flow Sankey + per-instance
    detail Table (M.3.10f).

    Two visuals stacked: Sankey (multi-leg flow through declared
    templates) and Table (per-shared-Transfer balance detail).

    Filter bar (six controls):

    1. **Date From** + **Date To** — bind to ``pL2ftTtDateStart`` /
       ``pL2ftTtDateEnd``; ``TimeRangeFilter`` on ``posting``.
       ``cross_dataset='ALL_DATASETS'`` so the filter narrows BOTH
       tt-instances + tt-legs (which both carry the column).
    2. **Template** — multi-select ``CategoryFilter`` on
       ``template_name``. Same ``ALL_DATASETS`` shape.
    3. **Net Status** — multi-select ``CategoryFilter`` on
       ``net_status`` (Balanced / Imbalanced) — tt-instances only
       (per-firing balance check). Filtering to 'Imbalanced' narrows
       the table to bundles failing the L1 Conservation invariant.
    4. **Metadata Key** — single-select ``ParameterDropdown`` with
       ``StaticValues`` (the L2's declared keys + ``__ALL__``
       sentinel). Mapped to ``pKey`` on BOTH tt-instances + tt-legs
       (so the cascade narrows both visuals via SQL substitution).
    5. **Metadata Value** — multi-select ``ParameterDropdown`` with
       ``LinkedValues`` from the meta-values dataset (shared with
       Rails / Chains). Mapped to ``pValues`` on BOTH datasets.
       ``CascadingControlConfiguration`` on this control points at
       the meta-values dataset's ``metadata_key`` column for the
       column-match cascade.

    Sankey reads as: debit accounts → template → credit accounts.
    Each shared Transfer's debit legs flow into the template middle
    node, credit legs flow out. Picking a single Template collapses
    the Sankey to that one template's flow shape.
    """
    ds_tt_instances = datasets[DS_TT_INSTANCES]
    ds_tt_legs = datasets[DS_TT_LEGS]
    ds_meta_values = datasets[DS_META_VALUES]

    # 1+2. Date range. ALL_DATASETS so tt-legs narrows in lockstep.
    date_start = analysis.add_parameter(DateTimeParam(
        name=ParameterName("pL2ftTtDateStart"),
        time_granularity="DAY",
        default=DateTimeDefaultValues(StaticValues=[_DATE_START_STATIC]),
    ))
    date_end = analysis.add_parameter(DateTimeParam(
        name=ParameterName("pL2ftTtDateEnd"),
        time_granularity="DAY",
        default=DateTimeDefaultValues(StaticValues=[_DATE_END_STATIC]),
    ))
    fg_date = analysis.add_filter_group(FilterGroup(
        filter_group_id="fg-l2ft-tt-date",  # type: ignore[arg-type]
        cross_dataset="ALL_DATASETS",
        filters=[TimeRangeFilter(
            filter_id="filter-l2ft-tt-date",
            dataset=ds_tt_instances,
            column=ds_tt_instances["posting"],
            null_option="NON_NULLS_ONLY",
            time_granularity="DAY",
            minimum={"Parameter": "pL2ftTtDateStart"},
            maximum={"Parameter": "pL2ftTtDateEnd"},
        )],
    ))
    fg_date.scope_sheet(sheet)
    sheet.add_parameter_datetime_picker(parameter=date_start, title="Date From")
    sheet.add_parameter_datetime_picker(parameter=date_end, title="Date To")

    # 3. Template — multi-select on declared template names.
    # ALL_DATASETS so tt-legs narrows in lockstep.
    template_filter = CategoryFilter.with_values(
        filter_id="filter-l2ft-tt-template",
        dataset=ds_tt_instances,
        column=ds_tt_instances["template_name"],
        values=[],
        select_all_options="FILTER_ALL_VALUES",
    )
    fg_template = analysis.add_filter_group(FilterGroup(
        filter_group_id="fg-l2ft-tt-template",  # type: ignore[arg-type]
        cross_dataset="ALL_DATASETS",
        filters=[template_filter],
    ))
    fg_template.scope_sheet(sheet)
    sheet.add_filter_dropdown(filter=template_filter, title="Template")

    # 4. Net Status — multi-select on the computed net_status column.
    # Single-dataset (tt-instances only — per-firing balance concept;
    # the Sankey aggregates per-edge so net_status would be an
    # ambiguous attribution at the leg level).
    net_status_filter = CategoryFilter.with_values(
        filter_id="filter-l2ft-tt-net-status",
        dataset=ds_tt_instances,
        column=ds_tt_instances["net_status"],
        values=[],
        select_all_options="FILTER_ALL_VALUES",
    )
    fg_net_status = analysis.add_filter_group(FilterGroup(
        filter_group_id="fg-l2ft-tt-net-status",  # type: ignore[arg-type]
        cross_dataset="SINGLE_DATASET",
        filters=[net_status_filter],
    ))
    fg_net_status.scope_sheet(sheet)
    sheet.add_filter_dropdown(filter=net_status_filter, title="Net Status")

    # 5+6. Metadata cascade — same mechanism as Rails / Chains.
    # mapped_dataset_params lists BOTH tt-instances + tt-legs so the
    # cascade narrows the Sankey + Table together.
    p_meta_key = analysis.add_parameter(StringParam(
        name=ParameterName("pL2ftTtMetaKey"),
        default=[META_KEY_ALL_SENTINEL],
        multi_valued=False,
        mapped_dataset_params=[
            (ds_tt_instances, "pKey"),
            (ds_tt_legs, "pKey"),
        ],
    ))
    p_meta_value = analysis.add_parameter(StringParam(
        name=ParameterName("pL2ftTtMetaValue"),
        default=[META_VALUE_PLACEHOLDER_SENTINEL],
        multi_valued=True,
        mapped_dataset_params=[
            (ds_tt_instances, "pValues"),
            (ds_tt_legs, "pValues"),
        ],
    ))
    declared_keys = declared_metadata_keys(l2_instance)
    key_dropdown = sheet.add_parameter_dropdown(
        parameter=p_meta_key,
        title="Metadata Key",
        type="SINGLE_SELECT",
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
        cascade_source=key_dropdown,
        cascade_match_column=ds_meta_values["metadata_key"],
    )

    # Sankey — multi-leg flow. flow_source / flow_target derive from
    # amount_direction (debit account → template → credit account).
    # Width = SUM(amount_abs).
    sheet.layout.row(height=14).add_sankey(
        width=36,
        title="Multi-Leg Flow — Account → Template → Account",
        subtitle=(
            "Width = total absolute amount through the edge in the "
            "filtered window. Debit legs (money out) flow from the "
            "source account to the template middle node; credit legs "
            "(money in) flow from the template to the destination "
            "account. Pick a single Template to see just that "
            "template's flow shape."
        ),
        source=ds_tt_legs["flow_source"].dim(),
        target=ds_tt_legs["flow_target"].dim(),
        weight=ds_tt_legs["amount_abs"].sum(),
    )

    sheet.layout.row(height=14).add_table(
        width=36,
        title="Template Instances",
        subtitle=(
            "One row per shared Transfer. net_status reads 'Balanced' "
            "iff the sum of legs matches the L2's expected_net within "
            "$0.01; 'Imbalanced' surfaces L1 Conservation breaks. "
            "leg_count = how many leg postings landed on this transfer."
        ),
        columns=[
            ds_tt_instances["posting"].date(),
            ds_tt_instances["template_name"].dim(),
            ds_tt_instances["transfer_id"].dim(),
            ds_tt_instances["net_status"].dim(),
            ds_tt_instances["actual_net"].numerical(),
            ds_tt_instances["expected_net"].numerical(),
            ds_tt_instances["net_diff"].numerical(),
            ds_tt_instances["leg_count"].numerical(),
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
