"""QuickSight DataSet builders for the L2 Flow Tracing app.

The Chains / L2 Exceptions tabs join L2-declared values (static, from
the L2 instance) to runtime activity (from the prefixed
``<prefix>_current_transactions`` matview). The L2 declarations are
inlined into the SQL as a CTE of literal rows — no per-rail dataset
proliferation, no per-instance database table.

The Rails tab is a transactions explorer (M.3.10c rewrite — the
M.3.5 declared-rails table moves to a future Docs tab). It uses two
new datasets that participate in the metadata cascade:

- ``l2ft-postings-ds``: one row per leg, parameterized on ``pKey`` +
  ``pValues`` so the metadata cascade filters it via QS ``<<$param>>``
  substitution into a JSONPath.
- ``l2ft-meta-values-ds``: distinct metadata values for the chosen
  key, parameterized on ``pKey`` so the Value dropdown narrows when
  the Key dropdown changes.

Substep landmarks:

- M.3.4 — skeleton (no datasets)
- M.3.5 — Rails dataset (later DROPPED in M.3.10c — moves to Docs tab)
- M.3.6 — Chains dataset
- M.3.7 — L2 Exceptions datasets (six small KPI-backers)
- M.3.8 — Auto metadata-driven filter dropdown sources
  (later DROPPED in M.3.10c — replaced by the cascade)
- M.3.10c — Rails tab redesign on dataset parameters
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from quicksight_gen.common.config import Config
from quicksight_gen.common.dataset_contract import (
    ColumnSpec,
    DatasetContract,
    build_dataset,
)
from quicksight_gen.common.l2 import (
    L2Instance,
    SingleLegRail,
    TwoLegRail,
    posted_requirements_for,
)
from quicksight_gen.common.models import (
    DataSet,
    DatasetParameter,
    StringDatasetParameter,
    StringDatasetParameterDefaultValues,
)
from quicksight_gen.common.tree import Dataset


# Visual identifiers — keys for the Dataset registry on App.
DS_POSTINGS = "l2ft-postings-ds"
DS_META_VALUES = "l2ft-meta-values-ds"
DS_CHAINS = "l2ft-chains-ds"
DS_CHAIN_INSTANCES = "l2ft-chain-instances-ds"
DS_TT_INSTANCES = "l2ft-tt-instances-ds"
DS_TT_LEGS = "l2ft-tt-legs-ds"
# M.3.7 — six L2 exception sections, each backed by its own narrow dataset.
DS_EXC_CHAIN_ORPHANS = "l2ft-exc-chain-orphans-ds"
DS_EXC_UNMATCHED_TRANSFER_TYPE = "l2ft-exc-unmatched-transfer-type-ds"
DS_EXC_DEAD_RAILS = "l2ft-exc-dead-rails-ds"
DS_EXC_DEAD_BUNDLES_ACTIVITY = "l2ft-exc-dead-bundles-activity-ds"
DS_EXC_DEAD_METADATA = "l2ft-exc-dead-metadata-ds"
DS_EXC_DEAD_LIMIT_SCHEDULES = "l2ft-exc-dead-limit-schedules-ds"


# Sentinel value for the metadata Key parameter's default. The
# transactions dataset's WHERE clause short-circuits to "no metadata
# filter" when the picked key equals this sentinel, so a freshly-
# loaded dashboard renders all rows even before the analyst engages
# the cascade. Placed at module scope so app.py + tests can reference
# it from a single source of truth.
META_KEY_ALL_SENTINEL = "__ALL__"

# Sentinel default for the multi-valued Value parameter. When the
# Key has been picked but no Value has yet been chosen, this default
# matches no real metadata value → the table goes empty as a hint
# the analyst still needs to pick a Value. Lives in CamelCase-safe
# form (no underscores other than at the boundaries — QS parameter
# *names* require alphanumerics, but parameter *values* can be
# anything the SQL accepts).
META_VALUE_PLACEHOLDER_SENTINEL = "__placeholder__"

# Dataset-parameter IDs are stable UUIDs so re-deploying produces
# byte-identical DatasetParameters JSON. QS-issued IDs would re-rotate
# on every regenerate.
_DSP_ID_PKEY = "11111111-1111-4111-8111-111111111111"
_DSP_ID_PVALUES = "22222222-2222-4222-8222-222222222222"


# Per-ChainEntry edge — declared parent→child relationship + runtime
# parent firing counts + matched-child counts + orphan rate. A row IS
# one Sankey edge in the Chains visual.
#
# M.3.10d: no longer wired into the Chains sheet (the Sankey + edge
# details moved out in favor of a per-instance explorer); kept in the
# module for the M.7 Docs render of declared topology.
CHAINS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("parent_name", "STRING"),
    ColumnSpec("child_name", "STRING"),
    ColumnSpec("required", "STRING"),     # 'Required' / 'Optional' for display
    ColumnSpec("xor_group", "STRING"),    # NULL when no XOR membership
    ColumnSpec("source_node", "STRING"),  # display label for the parent node
    ColumnSpec("target_node", "STRING"),  # display label for the child node
    ColumnSpec("parent_firing_count", "INTEGER"),
    ColumnSpec("child_firing_count", "INTEGER"),
    ColumnSpec("orphan_count", "INTEGER"),
    ColumnSpec("orphan_rate", "DECIMAL"),
])


# Per-parent-firing chain-instance row backing the Chains sheet's
# explorer (M.3.10d). One row per distinct parent transfer firing of
# any L2-declared chain-parent name; ``completion_status`` is computed
# inline from required-child firings against the parent's transfer_id.
# Parameterized on pKey + pValues for the metadata cascade.
CHAIN_INSTANCES_CONTRACT = DatasetContract(columns=[
    ColumnSpec("parent_chain_name", "STRING"),
    ColumnSpec("parent_transfer_id", "STRING"),
    ColumnSpec("parent_posting", "DATETIME"),
    ColumnSpec("parent_status", "STRING"),
    ColumnSpec("parent_amount_money", "DECIMAL"),
    ColumnSpec("required_total", "INTEGER"),
    ColumnSpec("required_fired", "INTEGER"),
    ColumnSpec("completion_status", "STRING"),
])


# Per-shared-Transfer row backing the Transfer Templates sheet's
# Table (M.3.10f). One row per (template_name, transfer_id) — the
# distinct shared Transfers that match a declared TransferTemplate.
# ``net_status`` reads 'Balanced' iff |actual_net - expected_net| <
# 0.01 else 'Imbalanced' — direct check of the SPEC's ExpectedNet
# invariant for the bundle. Parameterized on pKey + pValues.
TT_INSTANCES_CONTRACT = DatasetContract(columns=[
    ColumnSpec("template_name", "STRING"),
    ColumnSpec("transfer_id", "STRING"),
    ColumnSpec("posting", "DATETIME"),
    ColumnSpec("expected_net", "DECIMAL"),
    ColumnSpec("actual_net", "DECIMAL"),
    ColumnSpec("net_diff", "DECIMAL"),
    ColumnSpec("leg_count", "INTEGER"),
    ColumnSpec("net_status", "STRING"),
])


# Per-leg row backing the Transfer Templates sheet's Sankey (M.3.10f).
# One row per leg of any current_transactions row carrying a
# template_name (i.e., legs that joined a TransferTemplate's shared
# Transfer). ``flow_source`` / ``flow_target`` derive from
# ``amount_direction`` so the Sankey reads as:
#
#   debit account → template_name → credit account
#
# Width = ABS(amount_money). Each leg contributes one segment to one
# side of the template middle-node. The shared template middle-node
# means a 4-leg shared Transfer renders as 2 source nodes + the
# template + 2 target nodes — natural multi-leg flow visualization.
#
# Shares ``template_name`` + ``posting`` columns with tt-instances so
# cross_dataset='ALL_DATASETS' filter groups apply both the date +
# template dropdowns to BOTH datasets in lockstep.
#
# Parameterized on pKey + pValues for the metadata cascade.
TT_LEGS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("template_name", "STRING"),
    ColumnSpec("transfer_id", "STRING"),
    ColumnSpec("posting", "DATETIME"),
    ColumnSpec("account_name", "STRING"),
    ColumnSpec("account_role", "STRING"),
    ColumnSpec("amount_money", "DECIMAL"),
    ColumnSpec("amount_direction", "STRING"),
    ColumnSpec("amount_abs", "DECIMAL"),
    ColumnSpec("flow_source", "STRING"),
    ColumnSpec("flow_target", "STRING"),
])




# -- L2 Exception contracts (M.3.7) ------------------------------------------

# L2.1 — required Chain entries where parent fired but child didn't.
# Subset of CHAINS_CONTRACT pre-filtered to (required + orphan_count > 0).
EXC_CHAIN_ORPHANS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("parent_name", "STRING"),
    ColumnSpec("child_name", "STRING"),
    ColumnSpec("parent_firing_count", "INTEGER"),
    ColumnSpec("child_firing_count", "INTEGER"),
    ColumnSpec("orphan_count", "INTEGER"),
])


# L2.2 — Posted Transactions whose transfer_type doesn't match any
# declared Rail.transfer_type.
EXC_UNMATCHED_TRANSFER_TYPE_CONTRACT = DatasetContract(columns=[
    ColumnSpec("transfer_type", "STRING"),
    ColumnSpec("posting_count", "INTEGER"),
])


# L2.3 — Rails declared in L2 with zero postings in the window.
EXC_DEAD_RAILS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("rail_name", "STRING"),
    ColumnSpec("transfer_type", "STRING"),
    ColumnSpec("leg_shape", "STRING"),
])


# L2.4 — Aggregating-rail bundles_activity targets with zero matching
# activity in the window. Bundles_activity refs are Identifiers that
# the SPEC says match either rail_name OR transfer_type — the SQL
# checks both attributions.
EXC_DEAD_BUNDLES_ACTIVITY_CONTRACT = DatasetContract(columns=[
    ColumnSpec("aggregating_rail", "STRING"),
    ColumnSpec("bundle_target", "STRING"),
])


# L2.5 — Rail.metadata_keys declared in L2 that no posting carries a
# non-null value for in the window. Each row is one (rail_name,
# metadata_key) pair the L2 declared but the runtime never populated.
EXC_DEAD_METADATA_CONTRACT = DatasetContract(columns=[
    ColumnSpec("rail_name", "STRING"),
    ColumnSpec("metadata_key", "STRING"),
])


# L2.6 — LimitSchedule (parent_role, transfer_type) cells with zero
# outbound debit flow in the window. Means the cap is effectively dead
# — either nobody routes that role/type combination, or the L2 declared
# a cap nobody enforces against.
EXC_DEAD_LIMIT_SCHEDULES_CONTRACT = DatasetContract(columns=[
    ColumnSpec("parent_role", "STRING"),
    ColumnSpec("transfer_type", "STRING"),
    ColumnSpec("cap", "DECIMAL"),
])


# -- Rails tab (M.3.10c) — postings explorer + cascade source ---------------

# Per-leg view from <prefix>_current_transactions, parameterized on
# pKey + pValues so the metadata cascade filter applies via QS
# CustomSql substitution. The Rails sheet's transactions Table reads
# directly from this dataset.
POSTINGS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("id", "STRING"),
    ColumnSpec("transfer_id", "STRING"),
    ColumnSpec("transfer_parent_id", "STRING"),
    ColumnSpec("rail_name", "STRING"),
    ColumnSpec("transfer_type", "STRING"),
    ColumnSpec("account_id", "STRING"),
    ColumnSpec("account_name", "STRING"),
    ColumnSpec("account_role", "STRING"),
    ColumnSpec("account_scope", "STRING"),
    ColumnSpec("posting", "DATETIME"),
    ColumnSpec("amount_money", "DECIMAL"),
    ColumnSpec("amount_direction", "STRING"),
    ColumnSpec("status", "STRING"),
    ColumnSpec("bundle_id", "STRING"),
    ColumnSpec("bundle_status", "STRING"),  # 'Bundled' / 'Unbundled' calc
    ColumnSpec("origin", "STRING"),
])


# Long-form (metadata_key, metadata_value) for the cascade. QS's
# CascadingControlConfiguration uses the metadata_key column to
# filter rows by the Key dropdown's selection — picking 'customer_id'
# in Key narrows the dataset to rows WHERE metadata_key='customer_id',
# then DISTINCT metadata_value populates the Value dropdown.
# (Earlier single-column shape with dataset-parameter substitution
# DIDN'T work — QS's cascade is a column-match filter, not a
# parameter-driven re-query.)
META_VALUES_CONTRACT = DatasetContract(columns=[
    ColumnSpec("metadata_key", "STRING"),
    ColumnSpec("metadata_value", "STRING"),
])


# -- Builders ----------------------------------------------------------------


def build_all_l2_flow_tracing_datasets(
    cfg: Config, l2_instance: L2Instance,
) -> list[Dataset]:
    """Return every Dataset the L2 Flow Tracing app needs.

    Mirrors `build_all_l1_dashboard_datasets`: derives an L2-aware
    ``cfg`` (so dataset IDs carry the L2 instance prefix as their
    middle segment per M.2d.3) when the caller hasn't pre-stamped it.
    Idempotent — re-deriving an already-L2-aware cfg is a no-op.

    M.3.6 ships Chains; M.3.7 adds the 6 L2 Exceptions sections;
    M.3.10c adds the postings explorer + meta-values cascade source
    for the Rails tab (replacing M.3.5's declared-rails table — moves
    to a future Docs tab — and M.3.8's 28 per-key metadata dropdowns
    — replaced by the cascade); M.3.10d swaps the chains aggregate
    dataset for a per-parent-firing explorer (chain-instances);
    M.3.10f adds the Transfer Templates sheet with tt-instances (per
    shared Transfer) + tt-legs (per leg, backing the multi-leg flow
    Sankey).
    """
    if cfg.l2_instance_prefix is None:
        cfg = replace(cfg, l2_instance_prefix=str(l2_instance.instance))
    return [
        build_postings_dataset(cfg, l2_instance),
        build_meta_values_dataset(cfg, l2_instance),
        build_chain_instances_dataset(cfg, l2_instance),
        build_tt_instances_dataset(cfg, l2_instance),
        build_tt_legs_dataset(cfg, l2_instance),
        build_exc_chain_orphans_dataset(cfg, l2_instance),
        build_exc_unmatched_transfer_type_dataset(cfg, l2_instance),
        build_exc_dead_rails_dataset(cfg, l2_instance),
        build_exc_dead_bundles_activity_dataset(cfg, l2_instance),
        build_exc_dead_metadata_dataset(cfg, l2_instance),
        build_exc_dead_limit_schedules_dataset(cfg, l2_instance),
    ]


def declared_metadata_keys(l2_instance: L2Instance) -> list[str]:
    """Sorted list of distinct metadata keys declared across every
    rail in the L2 instance. Drives both the dropdown-source dataset
    list and the analysis-level parameter list — single source of
    truth for "what metadata keys does this L2 expose?".
    """
    keys: set[str] = set()
    for r in l2_instance.rails:
        for k in r.metadata_keys:
            keys.add(str(k))
    return sorted(keys)


def declared_chain_parents(l2_instance: L2Instance) -> list[str]:
    """Sorted list of distinct ChainEntry parent names. Drives the
    Chain dropdown's selectable values on the Chains sheet (M.3.10d).
    """
    return sorted({str(c.parent) for c in l2_instance.chains})


def declared_template_names(l2_instance: L2Instance) -> list[str]:
    """Sorted list of declared TransferTemplate names. Drives the
    Template dropdown's selectable values on the Transfer Templates
    sheet (M.3.10f).
    """
    return sorted(str(t.name) for t in l2_instance.transfer_templates)


def build_postings_dataset(
    cfg: Config, l2_instance: L2Instance,
) -> DataSet:
    """One row per leg from ``<prefix>_current_transactions``,
    parameterized on ``pKey`` + ``pValues`` so the metadata cascade
    filters server-side via QS ``<<$param>>`` substitution.

    Defaults: ``pKey = '__ALL__'`` short-circuits the metadata WHERE
    clause to "no metadata filter" → freshly-loaded dashboard renders
    every leg. ``pValues = '__placeholder__'`` matches no real value,
    so picking a Key without a Value goes empty (UX hint to pick both).

    Other filters (date range, rail, status, bundle status) apply via
    standard QS TimeRangeFilter + CategoryFilter on the analysis side
    — no parameterization needed for those.
    """
    prefix = l2_instance.instance
    sql = (
        f"SELECT\n"
        f"  id, transfer_id, transfer_parent_id, rail_name, transfer_type,\n"
        f"  account_id, account_name, account_role, account_scope,\n"
        f"  posting, amount_money, amount_direction, status, bundle_id,\n"
        f"  CASE WHEN bundle_id IS NULL THEN 'Unbundled' ELSE 'Bundled' END "
        f"AS bundle_status,\n"
        f"  origin\n"
        f"FROM {prefix}_current_transactions\n"
        # The metadata cascade short-circuit: when pKey is the sentinel,
        # the WHERE always evaluates true (no filtering); otherwise
        # JSON_VALUE compares the leg's metadata against the picked
        # values. Multi-valued IN takes the comma-list QS substitutes
        # for <<$pValues>>.
        f"WHERE\n"
        f"  <<$pKey>> = {_sql_str(META_KEY_ALL_SENTINEL)}\n"
        f"  OR JSON_VALUE(metadata, '$.' || <<$pKey>>) IN (<<$pValues>>)"
    )
    return build_dataset(
        cfg, cfg.prefixed("l2ft-postings-dataset"),
        "L2FT Postings", "l2ft-postings",
        sql, POSTINGS_CONTRACT,
        visual_identifier=DS_POSTINGS,
        dataset_parameters=[
            DatasetParameter(StringDatasetParameter=StringDatasetParameter(
                Id=_DSP_ID_PKEY,
                Name="pKey",
                ValueType="SINGLE_VALUED",
                DefaultValues=StringDatasetParameterDefaultValues(
                    StaticValues=[META_KEY_ALL_SENTINEL],
                ),
            )),
            DatasetParameter(StringDatasetParameter=StringDatasetParameter(
                Id=_DSP_ID_PVALUES,
                Name="pValues",
                ValueType="MULTI_VALUED",
                DefaultValues=StringDatasetParameterDefaultValues(
                    StaticValues=[META_VALUE_PLACEHOLDER_SENTINEL],
                ),
            )),
        ],
    )


def build_meta_values_dataset(
    cfg: Config, l2_instance: L2Instance,
) -> DataSet:
    """Long-form ``(metadata_key, metadata_value)`` for the cascade.

    Built as a UNION ALL across declared metadata keys, projecting one
    row per (transaction, key) combination where that key has a
    non-null value. The Value dropdown's ``LinkedValues`` sources
    from the ``metadata_value`` column; QS's
    ``CascadingControlConfiguration`` filters rows by the Key
    dropdown's selection matched against the ``metadata_key`` column
    — picking 'customer_id' narrows the dataset to that key's rows,
    then DISTINCT metadata_value populates the dropdown.

    No dataset parameters needed — the cascade is purely column-match
    on the analysis side. The earlier single-column +
    parameter-substituted shape didn't work because QS's cascade is
    a column-match filter, not a parameter-driven dataset re-query
    (M.3.10c finding).

    For an L2 instance with no declared metadata keys, the SELECT
    is replaced with `WHERE FALSE` so the dataset emits valid SQL
    that returns no rows.
    """
    prefix = l2_instance.instance
    keys = declared_metadata_keys(l2_instance)
    if not keys:
        sql = (
            "SELECT NULL::TEXT AS metadata_key, "
            "NULL::TEXT AS metadata_value\n"
            "WHERE FALSE"
        )
    else:
        # One SELECT per declared key. Each projects (key, value)
        # for transactions where that key has a non-null metadata
        # value. UNION ALL stitches them; DISTINCT happens at the
        # visual level via the dropdown's distinct-values semantics.
        branches = []
        for k in keys:
            json_path = f"$.{k}"
            branches.append(
                f"  SELECT {_sql_str(k)} AS metadata_key, "
                f"JSON_VALUE(metadata, {_sql_str(json_path)}) AS metadata_value\n"
                f"  FROM {prefix}_current_transactions\n"
                f"  WHERE metadata IS NOT NULL\n"
                f"    AND JSON_VALUE(metadata, {_sql_str(json_path)}) IS NOT NULL"
            )
        sql = "\n  UNION ALL\n".join(branches)
    return build_dataset(
        cfg, cfg.prefixed("l2ft-meta-values-dataset"),
        "L2FT Metadata Values", "l2ft-meta-values",
        sql, META_VALUES_CONTRACT,
        visual_identifier=DS_META_VALUES,
        # No dataset parameters — the cascade is column-match, not
        # parameter-driven SQL substitution.
    )


def build_chains_dataset(cfg: Config, l2_instance: L2Instance) -> DataSet:
    """One row per declared ChainEntry — the L2's parent→child topology
    joined to runtime parent firing counts + matched-child counts.

    A row IS one Sankey edge in the Chains visual. Counts come from
    ``<prefix>_current_transactions`` matched on the parent's name
    (which can be a Rail's ``rail_name`` OR a TransferTemplate's
    ``template_name`` — every leg row carries both, with template_name
    taking precedence when a rail is part of a template). Child
    matches require ``transfer_parent_id`` to point at one of the
    parent's transfer_ids — that's the runtime "did this child fire
    in response to this parent" relation.

    Orphan rate = (parent_firings without a matched child) /
    parent_firings. A required Chain entry with non-zero orphan rate
    is the seed for M.3.7's L2.1 'Chain orphans' exception.

    Note on portability: uses correlated subqueries instead of
    ARRAY_AGG (PG-only) to keep the SQL portable. The chains table is
    small (typically tens of entries), so the cost is bounded.
    """
    prefix = l2_instance.instance
    declared = _declared_chains_cte(l2_instance)
    sql = (
        f"WITH declared AS (\n{declared}\n),\n"
        f"edge_runtime AS (\n"
        f"  SELECT\n"
        f"    d.parent_name,\n"
        f"    d.child_name,\n"
        f"    d.required,\n"
        f"    d.xor_group,\n"
        f"    d.source_node,\n"
        f"    d.target_node,\n"
        f"    COALESCE((\n"
        f"      SELECT COUNT(DISTINCT t.transfer_id)\n"
        f"      FROM {prefix}_current_transactions t\n"
        f"      WHERE COALESCE(t.template_name, t.rail_name) = d.parent_name\n"
        f"    ), 0) AS parent_firing_count,\n"
        f"    COALESCE((\n"
        f"      SELECT COUNT(DISTINCT c.transfer_id)\n"
        f"      FROM {prefix}_current_transactions c\n"
        f"      WHERE COALESCE(c.template_name, c.rail_name) = d.child_name\n"
        f"        AND c.transfer_parent_id IN (\n"
        f"          SELECT t2.transfer_id\n"
        f"          FROM {prefix}_current_transactions t2\n"
        f"          WHERE COALESCE(t2.template_name, t2.rail_name) "
        f"= d.parent_name\n"
        f"        )\n"
        f"    ), 0) AS child_firing_count\n"
        f"  FROM declared d\n"
        f")\n"
        f"SELECT\n"
        f"  e.parent_name,\n"
        f"  e.child_name,\n"
        f"  e.required,\n"
        f"  e.xor_group,\n"
        f"  e.source_node,\n"
        f"  e.target_node,\n"
        f"  e.parent_firing_count,\n"
        f"  e.child_firing_count,\n"
        # GREATEST clamps at 0 — child can fire more than parent in some
        # patterns (e.g., one parent triggers many children); negative
        # orphans don't read intuitively in the visual.
        f"  GREATEST(e.parent_firing_count - e.child_firing_count, 0) "
        f"AS orphan_count,\n"
        f"  CASE\n"
        f"    WHEN e.parent_firing_count > 0\n"
        f"      THEN CAST(\n"
        f"        GREATEST(e.parent_firing_count - e.child_firing_count, 0) "
        f"AS DECIMAL(20,4)\n"
        f"      ) / e.parent_firing_count\n"
        f"    ELSE 0\n"
        f"  END AS orphan_rate\n"
        f"FROM edge_runtime e\n"
        f"ORDER BY e.parent_name, e.child_name"
    )
    return build_dataset(
        cfg, cfg.prefixed("l2ft-chains-dataset"),
        "L2FT Chains", "l2ft-chains",
        sql, CHAINS_CONTRACT,
        visual_identifier=DS_CHAINS,
    )


def build_chain_instances_dataset(
    cfg: Config, l2_instance: L2Instance,
) -> DataSet:
    """One row per parent transfer firing of a declared chain parent
    (M.3.10d). Backs the Chains sheet's per-instance explorer:

    - ``parent_chain_name`` — the L2-declared parent rail / template
      name. Drives the Chain dropdown's selectable values.
    - ``parent_transfer_id`` — DISTINCT transfer_id of the parent
      firing. Multiple legs of one transfer collapse to one row via
      GROUP BY.
    - ``completion_status`` — computed inline: 'Completed' iff every
      Required child declared for the parent has a matching child
      transfer (``transfer_parent_id = parent_transfer_id``);
      'Incomplete' if any required child is missing; 'No Required
      Children' when the parent's ChainEntries are all optional.
    - ``parent_metadata`` is read in the WHERE only — kept off the
      contract so users don't see raw JSON. ``pKey`` / ``pValues``
      substitute into a JSONPath ``IN (...)`` predicate same as the
      postings dataset; the ``__ALL__`` sentinel short-circuits to
      "no metadata filter".

    SQL portability: correlated subqueries (no ``ARRAY_AGG``); no
    JSONB; ``MAX`` aggregates over varchar status / metadata which
    isn't perfect but the parent transfer's legs share these values
    in practice. The chains table is bounded by L2 declarations
    (typically tens of entries) so the cost stays predictable.
    """
    prefix = l2_instance.instance
    declared = _declared_chains_cte(l2_instance)
    sql = (
        f"WITH declared AS (\n{declared}\n),\n"
        f"parent_chains AS (\n"
        f"  SELECT\n"
        f"    parent_name,\n"
        f"    SUM(CASE WHEN required = 'Required' THEN 1 ELSE 0 END) "
        f"AS required_total\n"
        f"  FROM declared\n"
        f"  GROUP BY parent_name\n"
        f"),\n"
        f"parent_firings AS (\n"
        f"  SELECT\n"
        f"    pc.parent_name AS parent_chain_name,\n"
        f"    pc.required_total,\n"
        f"    t.transfer_id AS parent_transfer_id,\n"
        f"    MIN(t.posting) AS parent_posting,\n"
        f"    MAX(t.status) AS parent_status,\n"
        f"    MAX(t.amount_money) AS parent_amount_money,\n"
        f"    MAX(t.metadata) AS parent_metadata\n"
        f"  FROM parent_chains pc\n"
        f"  JOIN {prefix}_current_transactions t\n"
        f"    ON COALESCE(t.template_name, t.rail_name) = pc.parent_name\n"
        f"  GROUP BY pc.parent_name, pc.required_total, t.transfer_id\n"
        f"),\n"
        f"firing_completion AS (\n"
        f"  SELECT\n"
        f"    pf.parent_chain_name,\n"
        f"    pf.parent_transfer_id,\n"
        f"    pf.parent_posting,\n"
        f"    pf.parent_status,\n"
        f"    pf.parent_amount_money,\n"
        f"    pf.required_total,\n"
        f"    pf.parent_metadata,\n"
        f"    (\n"
        f"      SELECT COUNT(DISTINCT d.child_name)\n"
        f"      FROM declared d\n"
        f"      WHERE d.parent_name = pf.parent_chain_name\n"
        f"        AND d.required = 'Required'\n"
        f"        AND EXISTS (\n"
        f"          SELECT 1 FROM {prefix}_current_transactions c\n"
        f"          WHERE COALESCE(c.template_name, c.rail_name) "
        f"= d.child_name\n"
        f"            AND c.transfer_parent_id = pf.parent_transfer_id\n"
        f"        )\n"
        f"    ) AS required_fired\n"
        f"  FROM parent_firings pf\n"
        f")\n"
        f"SELECT\n"
        f"  parent_chain_name,\n"
        f"  parent_transfer_id,\n"
        f"  parent_posting,\n"
        f"  parent_status,\n"
        f"  parent_amount_money,\n"
        f"  required_total,\n"
        f"  required_fired,\n"
        f"  CASE\n"
        f"    WHEN required_total = 0 THEN 'No Required Children'\n"
        f"    WHEN required_fired >= required_total THEN 'Completed'\n"
        f"    ELSE 'Incomplete'\n"
        f"  END AS completion_status\n"
        f"FROM firing_completion\n"
        f"WHERE\n"
        f"  <<$pKey>> = {_sql_str(META_KEY_ALL_SENTINEL)}\n"
        f"  OR JSON_VALUE(parent_metadata, '$.' || <<$pKey>>) "
        f"IN (<<$pValues>>)\n"
        f"ORDER BY parent_posting DESC"
    )
    return build_dataset(
        cfg, cfg.prefixed("l2ft-chain-instances-dataset"),
        "L2FT Chain Instances", "l2ft-chain-instances",
        sql, CHAIN_INSTANCES_CONTRACT,
        visual_identifier=DS_CHAIN_INSTANCES,
        dataset_parameters=[
            DatasetParameter(StringDatasetParameter=StringDatasetParameter(
                Id=_DSP_ID_PKEY,
                Name="pKey",
                ValueType="SINGLE_VALUED",
                DefaultValues=StringDatasetParameterDefaultValues(
                    StaticValues=[META_KEY_ALL_SENTINEL],
                ),
            )),
            DatasetParameter(StringDatasetParameter=StringDatasetParameter(
                Id=_DSP_ID_PVALUES,
                Name="pValues",
                ValueType="MULTI_VALUED",
                DefaultValues=StringDatasetParameterDefaultValues(
                    StaticValues=[META_VALUE_PLACEHOLDER_SENTINEL],
                ),
            )),
        ],
    )


# -- L2 Exception builders (M.3.7) -------------------------------------------


def build_exc_chain_orphans_dataset(
    cfg: Config, l2_instance: L2Instance,
) -> DataSet:
    """L2.1 — Required Chain entries where parent fired but no
    matched child fired in the window.

    Reuses the chains dataset's CTE shape (declared edges + edge
    runtime) and filters to ``required = 'Required' AND orphan_count
    > 0``. XOR-group multi/none violations are deferred to a follow-on
    substep — a precise XOR check needs per-Transfer-id grouping that
    the simpler aggregate doesn't capture.
    """
    prefix = l2_instance.instance
    declared = _declared_chains_cte(l2_instance)
    sql = (
        f"WITH declared AS (\n{declared}\n),\n"
        f"edge_runtime AS (\n"
        f"  SELECT\n"
        f"    d.parent_name,\n"
        f"    d.child_name,\n"
        f"    d.required,\n"
        f"    COALESCE((\n"
        f"      SELECT COUNT(DISTINCT t.transfer_id)\n"
        f"      FROM {prefix}_current_transactions t\n"
        f"      WHERE COALESCE(t.template_name, t.rail_name) = d.parent_name\n"
        f"    ), 0) AS parent_firing_count,\n"
        f"    COALESCE((\n"
        f"      SELECT COUNT(DISTINCT c.transfer_id)\n"
        f"      FROM {prefix}_current_transactions c\n"
        f"      WHERE COALESCE(c.template_name, c.rail_name) = d.child_name\n"
        f"        AND c.transfer_parent_id IN (\n"
        f"          SELECT t2.transfer_id\n"
        f"          FROM {prefix}_current_transactions t2\n"
        f"          WHERE COALESCE(t2.template_name, t2.rail_name) "
        f"= d.parent_name\n"
        f"        )\n"
        f"    ), 0) AS child_firing_count\n"
        f"  FROM declared d\n"
        f")\n"
        f"SELECT\n"
        f"  e.parent_name,\n"
        f"  e.child_name,\n"
        f"  e.parent_firing_count,\n"
        f"  e.child_firing_count,\n"
        f"  GREATEST(e.parent_firing_count - e.child_firing_count, 0) "
        f"AS orphan_count\n"
        f"FROM edge_runtime e\n"
        f"WHERE e.required = 'Required'\n"
        f"  AND e.parent_firing_count > e.child_firing_count\n"
        f"ORDER BY orphan_count DESC, e.parent_name, e.child_name"
    )
    return build_dataset(
        cfg, cfg.prefixed("l2ft-exc-chain-orphans-dataset"),
        "L2 Exc — Chain Orphans", "l2ft-exc-chain-orphans",
        sql, EXC_CHAIN_ORPHANS_CONTRACT,
        visual_identifier=DS_EXC_CHAIN_ORPHANS,
    )


def build_exc_unmatched_transfer_type_dataset(
    cfg: Config, l2_instance: L2Instance,
) -> DataSet:
    """L2.2 — Posted Transactions whose ``transfer_type`` doesn't
    match any declared ``Rail.transfer_type``.

    The runtime version of M.2d.1's deferred validator check
    ('every Transfer MUST match a Rail'). LEFT JOIN to a CTE of
    declared types + filter to NULL surfaces the unmatched rows.
    Output is per-transfer-type with a count of postings carrying
    that type — the table reveals what's leaking past the L2's rails.
    """
    prefix = l2_instance.instance
    declared = _declared_transfer_types_cte(l2_instance)
    sql = (
        f"WITH declared_types AS (\n{declared}\n)\n"
        f"SELECT\n"
        f"  t.transfer_type,\n"
        f"  COUNT(*) AS posting_count\n"
        f"FROM {prefix}_current_transactions t\n"
        f"LEFT JOIN declared_types d ON d.transfer_type = t.transfer_type\n"
        f"WHERE d.transfer_type IS NULL\n"
        f"GROUP BY t.transfer_type\n"
        f"ORDER BY posting_count DESC, t.transfer_type"
    )
    return build_dataset(
        cfg, cfg.prefixed("l2ft-exc-unmatched-transfer-type-dataset"),
        "L2 Exc — Unmatched Transfer Type",
        "l2ft-exc-unmatched-transfer-type",
        sql, EXC_UNMATCHED_TRANSFER_TYPE_CONTRACT,
        visual_identifier=DS_EXC_UNMATCHED_TRANSFER_TYPE,
    )


def build_exc_dead_rails_dataset(
    cfg: Config, l2_instance: L2Instance,
) -> DataSet:
    """L2.3 — Rails declared in L2 with zero postings in the window.

    Same shape as the Rails dataset but pre-filtered to
    ``COALESCE(r.total_postings, 0) = 0``. The KPI shows the count;
    the detail table lists the dead rails so the integrator can
    decide whether to retire the declaration or fix the ETL.
    """
    prefix = l2_instance.instance
    declared = _declared_rails_cte(l2_instance)
    sql = (
        f"WITH declared AS (\n{declared}\n),\n"
        f"runtime AS (\n"
        f"  SELECT rail_name, COUNT(*) AS total_postings\n"
        f"  FROM {prefix}_current_transactions\n"
        f"  GROUP BY rail_name\n"
        f")\n"
        f"SELECT\n"
        f"  d.rail_name,\n"
        f"  d.transfer_type,\n"
        f"  d.leg_shape\n"
        f"FROM declared d\n"
        f"LEFT JOIN runtime r ON r.rail_name = d.rail_name\n"
        f"WHERE COALESCE(r.total_postings, 0) = 0\n"
        f"ORDER BY d.rail_name"
    )
    return build_dataset(
        cfg, cfg.prefixed("l2ft-exc-dead-rails-dataset"),
        "L2 Exc — Dead Rails", "l2ft-exc-dead-rails",
        sql, EXC_DEAD_RAILS_CONTRACT,
        visual_identifier=DS_EXC_DEAD_RAILS,
    )


def build_exc_dead_bundles_activity_dataset(
    cfg: Config, l2_instance: L2Instance,
) -> DataSet:
    """L2.4 — Aggregating-rail bundles_activity targets that no
    posting matched (by either ``rail_name`` OR ``transfer_type``)
    in the window.

    Per SPEC: a bundles_activity ref MAY name either a rail or a
    transfer_type; the SQL checks both attributions to avoid
    false positives. Each row is one (aggregating_rail, target)
    pair the L2 declared but the runtime never realized.
    """
    prefix = l2_instance.instance
    declared = _declared_bundles_activity_cte(l2_instance)
    sql = (
        f"WITH declared_bundles AS (\n{declared}\n)\n"
        f"SELECT\n"
        f"  db.aggregating_rail,\n"
        f"  db.bundle_target\n"
        f"FROM declared_bundles db\n"
        f"WHERE NOT EXISTS (\n"
        f"  SELECT 1\n"
        f"  FROM {prefix}_current_transactions t\n"
        f"  WHERE t.rail_name = db.bundle_target\n"
        f"     OR t.transfer_type = db.bundle_target\n"
        f")\n"
        f"ORDER BY db.aggregating_rail, db.bundle_target"
    )
    return build_dataset(
        cfg, cfg.prefixed("l2ft-exc-dead-bundles-activity-dataset"),
        "L2 Exc — Dead Bundles Activity",
        "l2ft-exc-dead-bundles-activity",
        sql, EXC_DEAD_BUNDLES_ACTIVITY_CONTRACT,
        visual_identifier=DS_EXC_DEAD_BUNDLES_ACTIVITY,
    )


def build_exc_dead_metadata_dataset(
    cfg: Config, l2_instance: L2Instance,
) -> DataSet:
    """L2.5 — Rail.metadata_keys declared in L2 that no posting
    carries a non-null value for in the window.

    Each (rail, metadata_key) pair gets its own SQL fragment in the
    UNION ALL. Static JSON paths sidestep PostgreSQL's reluctance to
    accept dynamic JSONPath arguments to ``JSON_VALUE`` — keeps the
    SQL portable per the project's no-JSONB constraint.
    """
    prefix = l2_instance.instance
    fragments = _dead_metadata_check_fragments(l2_instance, prefix)
    if not fragments:
        # No rails declare metadata_keys — empty result, valid SQL.
        sql = (
            "SELECT NULL::TEXT AS rail_name, NULL::TEXT AS metadata_key "
            "WHERE FALSE"
        )
    else:
        sql = "\n  UNION ALL\n".join(fragments) + "\n"
        sql = sql + "ORDER BY rail_name, metadata_key"
    return build_dataset(
        cfg, cfg.prefixed("l2ft-exc-dead-metadata-dataset"),
        "L2 Exc — Dead Metadata Declarations",
        "l2ft-exc-dead-metadata",
        sql, EXC_DEAD_METADATA_CONTRACT,
        visual_identifier=DS_EXC_DEAD_METADATA,
    )


def build_exc_dead_limit_schedules_dataset(
    cfg: Config, l2_instance: L2Instance,
) -> DataSet:
    """L2.6 — LimitSchedule (parent_role, transfer_type) cells with
    zero outbound debit flow in the window.

    Means the cap is effectively dead — either nobody routes that
    role/type combination, or the L2 declared a cap nobody enforces
    against. NOT EXISTS over the prefixed transactions matview keeps
    the query bounded by the (small) limit-schedule count.
    """
    prefix = l2_instance.instance
    declared = _declared_limit_schedules_cte(l2_instance)
    sql = (
        f"WITH declared_limits AS (\n{declared}\n)\n"
        f"SELECT\n"
        f"  dl.parent_role,\n"
        f"  dl.transfer_type,\n"
        f"  dl.cap\n"
        f"FROM declared_limits dl\n"
        f"WHERE NOT EXISTS (\n"
        f"  SELECT 1\n"
        f"  FROM {prefix}_current_transactions t\n"
        f"  WHERE t.account_parent_role = dl.parent_role\n"
        f"    AND t.transfer_type = dl.transfer_type\n"
        f"    AND t.amount_direction = 'Debit'\n"
        f")\n"
        f"ORDER BY dl.parent_role, dl.transfer_type"
    )
    return build_dataset(
        cfg, cfg.prefixed("l2ft-exc-dead-limit-schedules-dataset"),
        "L2 Exc — Dead Limit Schedules",
        "l2ft-exc-dead-limit-schedules",
        sql, EXC_DEAD_LIMIT_SCHEDULES_CONTRACT,
        visual_identifier=DS_EXC_DEAD_LIMIT_SCHEDULES,
    )


# -- Internals ---------------------------------------------------------------


def _declared_rails_cte(l2_instance: L2Instance) -> str:
    """Render the L2-declared rails as a UNION ALL of SELECT-literal rows.

    UNION ALL of single-row SELECTs is used instead of ``VALUES (...)``
    so each column gets a CAST (or naked literal) that's resolved per
    row, avoiding the "type of column N is text but row M is null"
    inference problem PostgreSQL's planner sometimes hits with VALUES
    when most rows have NULL for a column.
    """
    if not l2_instance.rails:
        # Should not happen for a valid L2 (there must be some rails);
        # the validator would catch it. Return a safe empty CTE that
        # produces zero rows so the LEFT JOIN works.
        return (
            "  SELECT\n"
            "    NULL::TEXT AS rail_name,\n"
            "    NULL::TEXT AS transfer_type,\n"
            "    NULL::TEXT AS leg_shape,\n"
            "    NULL::TEXT AS source_role,\n"
            "    NULL::TEXT AS destination_role,\n"
            "    NULL::TEXT AS leg_role,\n"
            "    NULL::TEXT AS max_pending_age,\n"
            "    NULL::TEXT AS max_unbundled_age,\n"
            "    NULL::TEXT AS posted_requirements\n"
            "  WHERE FALSE"
        )
    rows: list[str] = []
    for r in l2_instance.rails:
        leg_shape = _leg_shape(r)
        if isinstance(r, TwoLegRail):
            source_role = _role_str(r.source_role)
            destination_role = _role_str(r.destination_role)
            leg_role = None
        else:
            source_role = None
            destination_role = None
            leg_role = _role_str(r.leg_role)
        max_pending = _duration_label(r.max_pending_age)
        max_unbundled = _duration_label(r.max_unbundled_age)
        posted_reqs = ",".join(
            sorted(str(k) for k in posted_requirements_for(l2_instance, r.name))
        )
        rows.append(
            "  SELECT "
            f"{_sql_str(str(r.name))} AS rail_name, "
            f"{_sql_str(str(r.transfer_type))} AS transfer_type, "
            f"{_sql_str(leg_shape)} AS leg_shape, "
            f"{_sql_nullable_str(source_role)} AS source_role, "
            f"{_sql_nullable_str(destination_role)} AS destination_role, "
            f"{_sql_nullable_str(leg_role)} AS leg_role, "
            f"{_sql_nullable_str(max_pending)} AS max_pending_age, "
            f"{_sql_nullable_str(max_unbundled)} AS max_unbundled_age, "
            f"{_sql_str(posted_reqs)} AS posted_requirements"
        )
    return "\n  UNION ALL\n".join(rows)


def _declared_chains_cte(l2_instance: L2Instance) -> str:
    """Render the L2-declared ChainEntry list as a UNION ALL of
    SELECT-literal rows.

    ``source_node`` / ``target_node`` are the display strings the
    Sankey reads — currently identical to the parent / child name,
    but kept as separate columns so M.3.6+ can attach a "(Required)"
    or "(XOR: <group>)" suffix without breaking the join semantics.
    """
    if not l2_instance.chains:
        return (
            "  SELECT\n"
            "    NULL::TEXT AS parent_name,\n"
            "    NULL::TEXT AS child_name,\n"
            "    NULL::TEXT AS required,\n"
            "    NULL::TEXT AS xor_group,\n"
            "    NULL::TEXT AS source_node,\n"
            "    NULL::TEXT AS target_node\n"
            "  WHERE FALSE"
        )
    rows: list[str] = []
    for c in l2_instance.chains:
        required_label = "Required" if c.required else "Optional"
        xor_group = str(c.xor_group) if c.xor_group is not None else None
        # Source / target node display strings — same as the names today;
        # M.3.6+ may suffix with required / xor info if visual readability
        # demands. Keeping the seam so the SQL stays stable.
        source_node = str(c.parent)
        target_node = str(c.child)
        rows.append(
            "  SELECT "
            f"{_sql_str(str(c.parent))} AS parent_name, "
            f"{_sql_str(str(c.child))} AS child_name, "
            f"{_sql_str(required_label)} AS required, "
            f"{_sql_nullable_str(xor_group)} AS xor_group, "
            f"{_sql_str(source_node)} AS source_node, "
            f"{_sql_str(target_node)} AS target_node"
        )
    return "\n  UNION ALL\n".join(rows)


def _leg_shape(rail: TwoLegRail | SingleLegRail) -> str:
    """Compact label combining leg arity + aggregating flag.

    Examples: "1-leg" / "2-leg" / "1-leg-aggregating" / "2-leg-aggregating".
    """
    arity = "2-leg" if isinstance(rail, TwoLegRail) else "1-leg"
    return f"{arity}-aggregating" if rail.aggregating else arity


def _role_str(role: tuple) -> str:
    """Render a RoleExpression (tuple of Identifiers) as a display string.

    Single-role: the name. UNION (multi-role): joined with " | " (the
    SPEC's union-set notation)."""
    parts = [str(r) for r in role]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return " | ".join(parts)


def _duration_label(td: timedelta | None) -> str | None:
    """Render a timedelta as a compact label ("24h", "1d", "30m").

    None → None (the SQL emits NULL). Non-evenly-divisible durations
    fall back to seconds.
    """
    if td is None:
        return None
    s = int(td.total_seconds())
    if s == 0:
        return "0s"
    if s % 86400 == 0:
        return f"{s // 86400}d"
    if s % 3600 == 0:
        return f"{s // 3600}h"
    if s % 60 == 0:
        return f"{s // 60}m"
    return f"{s}s"


def _sql_str(value: str) -> str:
    """Escape a Python string for embedding as a SQL string literal.

    Doubles single quotes per SQL standard (works on PostgreSQL +
    portable to other RDBMS per the project's portability constraint)."""
    return "'" + value.replace("'", "''") + "'"


def _sql_nullable_str(value: str | None) -> str:
    """SQL literal for an optional string — emits NULL when None."""
    if value is None:
        return "NULL"
    return _sql_str(value)


# -- M.3.7 CTE helpers -------------------------------------------------------


def _declared_transfer_types_cte(l2_instance: L2Instance) -> str:
    """Distinct ``Rail.transfer_type`` values, one per SELECT row.

    Distinct because multiple Rails MAY share a transfer_type (the
    M.2d.1-deferred validator rule); the L2.2 'Unmatched transfer_type'
    check just wants the SET of declared types so it can find what's
    NOT in it.
    """
    types = sorted({str(r.transfer_type) for r in l2_instance.rails})
    if not types:
        return (
            "  SELECT NULL::TEXT AS transfer_type WHERE FALSE"
        )
    rows = [
        f"  SELECT {_sql_str(t)} AS transfer_type"
        for t in types
    ]
    return "\n  UNION ALL\n".join(rows)


def _declared_bundles_activity_cte(l2_instance: L2Instance) -> str:
    """All (aggregating_rail, bundle_target) pairs the L2 declares.

    bundle_target is whatever Identifier the rail's
    ``bundles_activity`` lists — per SPEC, that resolves to either a
    rail_name or a transfer_type at runtime.
    """
    pairs: list[tuple[str, str]] = []
    for r in l2_instance.rails:
        if not r.aggregating:
            continue
        for target in r.bundles_activity:
            pairs.append((str(r.name), str(target)))
    if not pairs:
        return (
            "  SELECT NULL::TEXT AS aggregating_rail, "
            "NULL::TEXT AS bundle_target WHERE FALSE"
        )
    rows = [
        f"  SELECT {_sql_str(agg)} AS aggregating_rail, "
        f"{_sql_str(target)} AS bundle_target"
        for agg, target in pairs
    ]
    return "\n  UNION ALL\n".join(rows)


def _dead_metadata_check_fragments(
    l2_instance: L2Instance, prefix: str,
) -> list[str]:
    """One SELECT per declared (rail, metadata_key) pair guarded by
    NOT EXISTS against the prefixed transactions matview.

    Static JSON paths (``$.<literal>``) keep the SQL portable —
    PostgreSQL doesn't accept dynamic JSONPath arguments to
    ``JSON_VALUE`` without the v17+ JSON_TABLE syntax, and the
    project's no-JSONB constraint rules out the ``->>`` shortcut.
    """
    fragments: list[str] = []
    for r in l2_instance.rails:
        for key in r.metadata_keys:
            rail_name = str(r.name)
            key_name = str(key)
            json_path = f"$.{key_name}"
            fragments.append(
                f"  SELECT {_sql_str(rail_name)} AS rail_name, "
                f"{_sql_str(key_name)} AS metadata_key\n"
                f"  WHERE NOT EXISTS (\n"
                f"    SELECT 1\n"
                f"    FROM {prefix}_current_transactions t\n"
                f"    WHERE t.rail_name = {_sql_str(rail_name)}\n"
                f"      AND t.metadata IS NOT NULL\n"
                f"      AND JSON_VALUE(t.metadata, "
                f"{_sql_str(json_path)}) IS NOT NULL\n"
                f"  )"
            )
    return fragments


def _declared_limit_schedules_cte(l2_instance: L2Instance) -> str:
    """One SELECT row per LimitSchedule entry. The cap stays as a
    numeric literal; the parent_role + transfer_type are quoted
    string literals (they're Identifiers in the L2 model)."""
    if not l2_instance.limit_schedules:
        return (
            "  SELECT NULL::TEXT AS parent_role, "
            "NULL::TEXT AS transfer_type, "
            "NULL::DECIMAL AS cap WHERE FALSE"
        )
    rows: list[str] = []
    for ls in l2_instance.limit_schedules:
        rows.append(
            f"  SELECT {_sql_str(str(ls.parent_role))} AS parent_role, "
            f"{_sql_str(str(ls.transfer_type))} AS transfer_type, "
            # Cap is a Decimal; render as a SQL numeric literal.
            f"CAST({ls.cap} AS DECIMAL(20,2)) AS cap"
        )
    return "\n  UNION ALL\n".join(rows)


# -- Transfer Templates sheet (M.3.10f) ------------------------------------


def _declared_templates_cte(l2_instance: L2Instance) -> str:
    """Render L2-declared TransferTemplate names + expected_net as a
    UNION ALL of SELECT-literal rows. The tt-instances builder joins
    against this CTE so only declared templates appear in the dataset
    (any rogue ``template_name`` value in current_transactions that
    doesn't correspond to a declared TransferTemplate is excluded —
    surfaced separately by the L2.2 unmatched-transfer-type check).
    """
    if not l2_instance.transfer_templates:
        return (
            "  SELECT NULL::TEXT AS template_name, "
            "NULL::DECIMAL AS expected_net WHERE FALSE"
        )
    rows: list[str] = []
    for t in l2_instance.transfer_templates:
        rows.append(
            f"  SELECT {_sql_str(str(t.name))} AS template_name, "
            f"CAST({t.expected_net} AS DECIMAL(20,2)) AS expected_net"
        )
    return "\n  UNION ALL\n".join(rows)


def build_tt_instances_dataset(
    cfg: Config, l2_instance: L2Instance,
) -> DataSet:
    """One row per shared Transfer that matches a declared
    TransferTemplate (M.3.10f). Backs the Transfer Templates sheet's
    detail Table.

    A "shared Transfer" is one ``transfer_id`` from
    ``<prefix>_current_transactions`` whose legs all carry the same
    ``template_name`` matching a declared template. Per SPEC: every
    firing of a ``leg_rails`` rail with the same ``transfer_key``
    Metadata values posts to the same shared Transfer, so the
    transfer_id distinct-count = number of TransferTemplate
    instances.

    ``net_status`` reads 'Balanced' iff
    ``ABS(actual_net - expected_net) < 0.01`` else 'Imbalanced' —
    direct check of the L1 Conservation invariant against the L2's
    ExpectedNet declaration.

    Parameterized on pKey + pValues for the metadata cascade.
    """
    prefix = l2_instance.instance
    declared = _declared_templates_cte(l2_instance)
    sql = (
        f"WITH templates AS (\n{declared}\n),\n"
        f"firings AS (\n"
        f"  SELECT\n"
        f"    t.template_name,\n"
        f"    t.expected_net,\n"
        f"    ct.transfer_id,\n"
        f"    MIN(ct.posting) AS posting,\n"
        f"    SUM(ct.amount_money) AS actual_net,\n"
        f"    COUNT(*) AS leg_count,\n"
        f"    MAX(ct.metadata) AS parent_metadata\n"
        f"  FROM templates t\n"
        f"  JOIN {prefix}_current_transactions ct\n"
        f"    ON ct.template_name = t.template_name\n"
        f"  GROUP BY t.template_name, t.expected_net, ct.transfer_id\n"
        f")\n"
        f"SELECT\n"
        f"  template_name,\n"
        f"  transfer_id,\n"
        f"  posting,\n"
        f"  expected_net,\n"
        f"  actual_net,\n"
        f"  (actual_net - expected_net) AS net_diff,\n"
        f"  leg_count,\n"
        f"  CASE\n"
        f"    WHEN ABS(actual_net - expected_net) < 0.01 THEN 'Balanced'\n"
        f"    ELSE 'Imbalanced'\n"
        f"  END AS net_status\n"
        f"FROM firings\n"
        f"WHERE\n"
        f"  <<$pKey>> = {_sql_str(META_KEY_ALL_SENTINEL)}\n"
        f"  OR JSON_VALUE(parent_metadata, '$.' || <<$pKey>>) "
        f"IN (<<$pValues>>)\n"
        f"ORDER BY posting DESC, template_name, transfer_id"
    )
    return build_dataset(
        cfg, cfg.prefixed("l2ft-tt-instances-dataset"),
        "L2FT TT Instances", "l2ft-tt-instances",
        sql, TT_INSTANCES_CONTRACT,
        visual_identifier=DS_TT_INSTANCES,
        dataset_parameters=[
            DatasetParameter(StringDatasetParameter=StringDatasetParameter(
                Id=_DSP_ID_PKEY,
                Name="pKey",
                ValueType="SINGLE_VALUED",
                DefaultValues=StringDatasetParameterDefaultValues(
                    StaticValues=[META_KEY_ALL_SENTINEL],
                ),
            )),
            DatasetParameter(StringDatasetParameter=StringDatasetParameter(
                Id=_DSP_ID_PVALUES,
                Name="pValues",
                ValueType="MULTI_VALUED",
                DefaultValues=StringDatasetParameterDefaultValues(
                    StaticValues=[META_VALUE_PLACEHOLDER_SENTINEL],
                ),
            )),
        ],
    )


def build_tt_legs_dataset(
    cfg: Config, l2_instance: L2Instance,
) -> DataSet:
    """One row per leg of any shared Transfer that matches a declared
    TransferTemplate (M.3.10f). Backs the Transfer Templates sheet's
    Sankey:

    - ``flow_source`` → Sankey source node.
    - ``flow_target`` → Sankey target node.
    - ``amount_abs.sum()`` → ribbon thickness.

    ``flow_source`` / ``flow_target`` derive from
    ``amount_direction``:

    - Debit leg (``amount_money <= 0``, money OUT of the account):
      source = ``account_name``, target = ``template_name``.
    - Credit leg (``amount_money >= 0``, money IN to the account):
      source = ``template_name``, target = ``account_name``.

    The template_name acts as the middle node — a 4-leg shared
    Transfer renders as 2 source-account ribbons + the template +
    2 target-account ribbons. Filtering Template = 'X' on the sheet
    collapses the Sankey to that one template's flow pattern.

    Joining against the declared-templates CTE filters out any
    rogue ``template_name`` value in current_transactions that isn't
    in the L2 declaration (mirrors tt-instances).

    Parameterized on pKey + pValues for the metadata cascade.
    """
    prefix = l2_instance.instance
    declared = _declared_templates_cte(l2_instance)
    sql = (
        f"WITH templates AS (\n{declared}\n)\n"
        f"SELECT\n"
        f"  ct.template_name,\n"
        f"  ct.transfer_id,\n"
        f"  ct.posting,\n"
        f"  ct.account_name,\n"
        f"  ct.account_role,\n"
        f"  ct.amount_money,\n"
        f"  ct.amount_direction,\n"
        f"  ABS(ct.amount_money) AS amount_abs,\n"
        f"  CASE\n"
        f"    WHEN ct.amount_direction = 'Debit' THEN ct.account_name\n"
        f"    ELSE ct.template_name\n"
        f"  END AS flow_source,\n"
        f"  CASE\n"
        f"    WHEN ct.amount_direction = 'Debit' THEN ct.template_name\n"
        f"    ELSE ct.account_name\n"
        f"  END AS flow_target\n"
        f"FROM {prefix}_current_transactions ct\n"
        f"JOIN templates t ON t.template_name = ct.template_name\n"
        f"WHERE\n"
        f"  <<$pKey>> = {_sql_str(META_KEY_ALL_SENTINEL)}\n"
        f"  OR JSON_VALUE(ct.metadata, '$.' || <<$pKey>>) "
        f"IN (<<$pValues>>)\n"
        f"ORDER BY ct.posting DESC, ct.template_name, ct.transfer_id"
    )
    return build_dataset(
        cfg, cfg.prefixed("l2ft-tt-legs-dataset"),
        "L2FT TT Legs", "l2ft-tt-legs",
        sql, TT_LEGS_CONTRACT,
        visual_identifier=DS_TT_LEGS,
        dataset_parameters=[
            DatasetParameter(StringDatasetParameter=StringDatasetParameter(
                Id=_DSP_ID_PKEY,
                Name="pKey",
                ValueType="SINGLE_VALUED",
                DefaultValues=StringDatasetParameterDefaultValues(
                    StaticValues=[META_KEY_ALL_SENTINEL],
                ),
            )),
            DatasetParameter(StringDatasetParameter=StringDatasetParameter(
                Id=_DSP_ID_PVALUES,
                Name="pValues",
                ValueType="MULTI_VALUED",
                DefaultValues=StringDatasetParameterDefaultValues(
                    StaticValues=[META_VALUE_PLACEHOLDER_SENTINEL],
                ),
            )),
        ],
    )
