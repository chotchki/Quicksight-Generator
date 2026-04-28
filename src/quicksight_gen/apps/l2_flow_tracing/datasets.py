"""QuickSight DataSet builders for the L2 Flow Tracing app.

The Rails / Chains / L2 Exceptions tabs join L2-declared values
(static, from the L2 instance) to runtime activity (from the prefixed
``<prefix>_current_transactions`` matview). The L2 declarations are
inlined into the SQL as a CTE of literal rows — no per-rail dataset
proliferation, no per-instance database table.

Substep landmarks:

- M.3.4 — skeleton (no datasets)
- M.3.5 — Rails dataset (this commit)
- M.3.6 — Chains dataset
- M.3.7 — L2 Exceptions datasets (six small KPI-backers)
- M.3.8 — Auto metadata-driven filter dropdown sources
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
from quicksight_gen.common.models import DataSet
from quicksight_gen.common.tree import Dataset


# Visual identifiers — keys for the Dataset registry on App.
DS_RAILS = "l2ft-rails-ds"
DS_CHAINS = "l2ft-chains-ds"
# M.3.7 — six L2 exception sections, each backed by its own narrow dataset.
DS_EXC_CHAIN_ORPHANS = "l2ft-exc-chain-orphans-ds"
DS_EXC_UNMATCHED_TRANSFER_TYPE = "l2ft-exc-unmatched-transfer-type-ds"
DS_EXC_DEAD_RAILS = "l2ft-exc-dead-rails-ds"
DS_EXC_DEAD_BUNDLES_ACTIVITY = "l2ft-exc-dead-bundles-activity-ds"
DS_EXC_DEAD_METADATA = "l2ft-exc-dead-metadata-ds"
DS_EXC_DEAD_LIMIT_SCHEDULES = "l2ft-exc-dead-limit-schedules-ds"


# Per-Rail row table — declared L2 columns + runtime activity counts.
RAILS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("rail_name", "STRING"),
    ColumnSpec("transfer_type", "STRING"),
    ColumnSpec("leg_shape", "STRING"),
    ColumnSpec("source_role", "STRING"),
    ColumnSpec("destination_role", "STRING"),
    ColumnSpec("leg_role", "STRING"),
    ColumnSpec("max_pending_age", "STRING"),
    ColumnSpec("max_unbundled_age", "STRING"),
    ColumnSpec("posted_requirements", "STRING"),
    ColumnSpec("total_postings", "INTEGER"),
    ColumnSpec("pending_count", "INTEGER"),
    ColumnSpec("unbundled_count", "INTEGER"),
])


# Per-ChainEntry edge — declared parent→child relationship + runtime
# parent firing counts + matched-child counts + orphan rate. A row IS
# one Sankey edge in the Chains visual.
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


# -- Builders ----------------------------------------------------------------


def build_all_l2_flow_tracing_datasets(
    cfg: Config, l2_instance: L2Instance,
) -> list[Dataset]:
    """Return every Dataset the L2 Flow Tracing app needs.

    Mirrors `build_all_l1_dashboard_datasets`: derives an L2-aware
    ``cfg`` (so dataset IDs carry the L2 instance prefix as their
    middle segment per M.2d.3) when the caller hasn't pre-stamped it.
    Idempotent — re-deriving an already-L2-aware cfg is a no-op.

    M.3.5 ships Rails; M.3.6 adds Chains; M.3.7 adds the 6 L2
    Exceptions sections.
    """
    if cfg.l2_instance_prefix is None:
        cfg = replace(cfg, l2_instance_prefix=str(l2_instance.instance))
    return [
        build_rails_dataset(cfg, l2_instance),
        build_chains_dataset(cfg, l2_instance),
        build_exc_chain_orphans_dataset(cfg, l2_instance),
        build_exc_unmatched_transfer_type_dataset(cfg, l2_instance),
        build_exc_dead_rails_dataset(cfg, l2_instance),
        build_exc_dead_bundles_activity_dataset(cfg, l2_instance),
        build_exc_dead_metadata_dataset(cfg, l2_instance),
        build_exc_dead_limit_schedules_dataset(cfg, l2_instance),
    ]


def build_rails_dataset(cfg: Config, l2_instance: L2Instance) -> DataSet:
    """One row per declared Rail in the L2 instance.

    Static columns come from the L2 declaration (inlined as a VALUES CTE
    so the L2 stays out of the database). Runtime columns come from the
    ``<prefix>_current_transactions`` matview, aggregated per
    ``rail_name``. LEFT JOIN preserves Rails with zero activity in the
    window — those surface as L2.3 'Dead rails' on the Exceptions tab.

    Note: if multiple Rails share a ``transfer_type``, runtime counts
    on each row reflect the activity the matview attributes to THAT
    Rail's name (the schema's per-leg ``rail_name`` column makes the
    attribution unambiguous regardless of transfer_type sharing).
    """
    prefix = l2_instance.instance
    declared = _declared_rails_cte(l2_instance)
    sql = (
        f"WITH declared AS (\n{declared}\n),\n"
        f"runtime AS (\n"
        f"  SELECT\n"
        f"    rail_name,\n"
        f"    COUNT(*) AS total_postings,\n"
        f"    SUM(CASE WHEN status = 'Pending' THEN 1 ELSE 0 END) AS pending_count,\n"
        f"    SUM(CASE WHEN bundle_id IS NULL THEN 1 ELSE 0 END) AS unbundled_count\n"
        f"  FROM {prefix}_current_transactions\n"
        f"  GROUP BY rail_name\n"
        f")\n"
        f"SELECT\n"
        f"  d.rail_name,\n"
        f"  d.transfer_type,\n"
        f"  d.leg_shape,\n"
        f"  d.source_role,\n"
        f"  d.destination_role,\n"
        f"  d.leg_role,\n"
        f"  d.max_pending_age,\n"
        f"  d.max_unbundled_age,\n"
        f"  d.posted_requirements,\n"
        f"  COALESCE(r.total_postings, 0) AS total_postings,\n"
        f"  COALESCE(r.pending_count, 0) AS pending_count,\n"
        f"  COALESCE(r.unbundled_count, 0) AS unbundled_count\n"
        f"FROM declared d\n"
        f"LEFT JOIN runtime r ON r.rail_name = d.rail_name\n"
        f"ORDER BY d.rail_name"
    )
    return build_dataset(
        cfg, cfg.prefixed("l2ft-rails-dataset"),
        "L2FT Rails", "l2ft-rails",
        sql, RAILS_CONTRACT,
        visual_identifier=DS_RAILS,
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
